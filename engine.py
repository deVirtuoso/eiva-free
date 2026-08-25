"""
One question, three providers.

The window knows how to draw an answer; it does not know, and should not have
to know, that Anthropic wants its system prompt as a list of blocks, OpenAI
wants a data: URL for the image, and Google wants raw bytes and a separate
config object. All of that lives here, behind one call:

    usage = stream_answer(model, system_parts, parts, on_chunk)

`parts` is the question - plain dicts of {"text": ...} and {"image": <png in
base64>} - and `on_chunk` is handed the answer as it arrives. What comes back
is a usage dict in one shape, whoever produced it, which is what lets a single
meter price all three.

The SDKs are imported on the first call rather than at the top of the file, and
a missing one is a sentence on screen rather than a crash. Someone who only has
an Anthropic key should not have to install Google's client library to run the
app, and an install whose virtual environment predates this file should keep
working on the provider it already had.
"""

MAX_TOKENS = 1500

# Seconds before a request that has stopped making progress is given up on.
# Generous, because a long answer legitimately takes a while - but finite,
# because the alternative is a window that reads "thinking..." until it is
# killed. Stop cannot rescue it: cancellation is checked between chunks, and a
# stalled request has no next chunk.
TIMEOUT = 120

# Anthropic's effort dial. Low is faster and cheaper, high more thorough.
# Only some of their models accept it, and the ones that don't reject the whole
# request rather than ignoring the field, so the model's rate card carries the
# flag and this is only ever passed when that says so.
EFFORT = "medium"

# Import name -> what to install, for the message shown when it is missing.
SDKS = {
    "anthropic": ("anthropic", "anthropic"),
    "openai": ("openai", "openai"),
    "gemini": ("google.genai", "google-genai"),
}


class EngineError(Exception):
    """Something the user can act on, phrased for the status line."""


def sdk_missing(provider):
    """The install line for a provider whose client library is not here, or
    None when it is. Checked before a call so the answer is advice rather than
    a traceback in eiva.log."""
    module, package = SDKS[provider]
    try:
        __import__(module)
        return None
    except Exception:
        return f"{package} is not installed - run setup.ps1 again"


def _text_of(system_parts):
    """The system prompt as one string, for the two providers that take it
    that way. The parts arrive most-stable-first, which is the order they
    should be read in too."""
    return "\n\n".join(p["text"] for p in system_parts if p.get("text"))


def stream_answer(model, system_parts, parts, on_chunk, cancelled=None):
    """Stream one answer. `model` is a rate card from pricing.ANSWER_MODELS.

    on_chunk(text) is called for every piece of the answer as it arrives;
    returning True from it stops the stream early - that is how "Stop" and
    watch mode's "nothing to answer" get out without waiting for the rest.

    Returns {"in", "out", "cache_read", "cache_write"}, counting whatever was
    used before the stream ended, early or not. Leaving early does not make the
    tokens free.
    """
    provider = model["provider"]
    missing = sdk_missing(provider)
    if missing:
        raise EngineError(missing)
    runner = {"anthropic": _anthropic, "openai": _openai,
              "gemini": _gemini}[provider]
    try:
        return runner(model, system_parts, parts, on_chunk, cancelled)
    except EngineError:
        raise
    except Exception as e:
        raise EngineError(readable(provider, e))


def _stop(on_chunk, cancelled, chunk):
    """True when the stream should end here - either the window asked to stop,
    or whoever is collecting the text has seen enough."""
    if cancelled is not None and cancelled.is_set():
        return True
    return bool(on_chunk(chunk))


# --- Anthropic ---------------------------------------------------------------

def _anthropic(model, system_parts, parts, on_chunk, cancelled):
    import anthropic

    content = []
    for part in parts:
        if "image" in part:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": part["image"]}})
        else:
            content.append({"type": "text", "text": part["text"]})

    system = []
    for p in system_parts:
        block = {"type": "text", "text": p["text"]}
        # A cached block is identical on every request, so it is written to
        # cache once and read back at a tenth of the price after that.
        if p.get("cache"):
            block["cache_control"] = {"type": "ephemeral"}
        system.append(block)

    extra = {"output_config": {"effort": EFFORT}} if model.get("effort") else {}
    used = {}
    # The client is bound to a name for the whole call. Built inline, it is
    # unreferenced the moment the expression ends, and a collected client
    # closes the connection the stream is still reading from.
    client = anthropic.Anthropic(timeout=TIMEOUT)
    with client.messages.stream(
        model=model["id"], max_tokens=MAX_TOKENS, system=system,
        messages=[{"role": "user", "content": content}], **extra,
    ) as stream:
        for chunk in stream.text_stream:
            if _stop(on_chunk, cancelled, chunk):
                break
        try:
            usage = stream.current_message_snapshot.usage
            used = {"in": usage.input_tokens or 0,
                    "out": usage.output_tokens or 0,
                    "cache_read": getattr(
                        usage, "cache_read_input_tokens", 0) or 0,
                    "cache_write": getattr(
                        usage, "cache_creation_input_tokens", 0) or 0}
        except Exception:
            pass
    return used


# --- OpenAI ------------------------------------------------------------------

def _openai(model, system_parts, parts, on_chunk, cancelled):
    import openai

    content = []
    for part in parts:
        if "image" in part:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + part["image"]}})
        else:
            content.append({"type": "text", "text": part["text"]})

    used = {}
    client = openai.OpenAI(timeout=TIMEOUT)   # see the note in _anthropic
    stream = client.chat.completions.create(
        model=model["id"],
        max_completion_tokens=MAX_TOKENS,
        messages=[{"role": "system", "content": _text_of(system_parts)},
                  {"role": "user", "content": content}],
        stream=True,
        # Without this the final usage frame is never sent and the meter has
        # nothing to price the call with.
        stream_options={"include_usage": True},
    )
    try:
        for event in stream:
            usage = getattr(event, "usage", None)
            if usage is not None:
                cached = 0
                details = getattr(usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = getattr(details, "cached_tokens", 0) or 0
                used = {"in": (usage.prompt_tokens or 0) - cached,
                        "cache_read": cached,
                        "out": usage.completion_tokens or 0}
            if not event.choices:
                continue
            piece = event.choices[0].delta.content
            if piece and _stop(on_chunk, cancelled, piece):
                break
    finally:
        # Leaving the loop early leaves the connection open otherwise.
        try:
            stream.close()
        except Exception:
            pass
    return used


# --- Google Gemini -----------------------------------------------------------

def _gemini(model, system_parts, parts, on_chunk, cancelled):
    import base64

    from google import genai
    from google.genai import types

    content = []
    for part in parts:
        if "image" in part:
            content.append(types.Part.from_bytes(
                data=base64.b64decode(part["image"]), mime_type="image/png"))
        else:
            content.append(types.Part.from_text(text=part["text"]))

    settings = {
        "system_instruction": _text_of(system_parts),
        "max_output_tokens": MAX_TOKENS,
    }
    # Gemini 3 reasons before it answers, and left to itself will spend most of
    # a 1500-token budget doing it - forty-odd seconds for a question about a
    # screenshot. The level rides with the rate card, the way Anthropic's
    # effort does, so a model that does not take the field never sees it.
    if model.get("thinking"):
        settings["thinking_config"] = types.ThinkingConfig(
            thinking_level=model["thinking"])

    used = {}
    # timeout is in milliseconds here, unlike the other two.
    client = genai.Client(                # see the note in _anthropic
        http_options=types.HttpOptions(timeout=TIMEOUT * 1000))
    stream = client.models.generate_content_stream(
        model=model["id"],
        contents=[types.Content(role="user", parts=content)],
        config=types.GenerateContentConfig(**settings),
    )
    for event in stream:
        usage = getattr(event, "usage_metadata", None)
        if usage is not None:
            # Gemini reports the running total for the request, so the last
            # frame seen is the whole count rather than something to add up.
            cached = getattr(usage, "cached_content_token_count", 0) or 0
            used = {"in": (usage.prompt_token_count or 0) - cached,
                    "cache_read": cached,
                    "out": getattr(usage, "candidates_token_count", 0) or 0}
        piece = getattr(event, "text", None)
        if piece and _stop(on_chunk, cancelled, piece):
            break
    return used


# --- turning a provider's exception into a sentence --------------------------

def readable(provider, error):
    """Every SDK raises its own classes, and the window has one status line.
    Match on what the exception says rather than importing three exception
    hierarchies in order to catch them by type."""
    name = type(error).__name__
    text = str(error)
    lowered = (name + " " + text).lower()

    if ("authenticationerror" in lowered or "401" in text
            or "api key" in lowered or "unauthenticated" in lowered):
        return f"{provider} rejected the key - click Keys and check it"
    if "permissiondenied" in lowered or "403" in text:
        return f"{provider} refused the request - check the key's permissions"
    if ("ratelimit" in lowered or "429" in text
            or "resource_exhausted" in lowered):
        return "rate limited - wait a moment"
    if "notfound" in lowered or "404" in text:
        return "that model is not available on this key"
    if "connection" in lowered or "timeout" in lowered:
        return "connection failed - check network"
    if "credit" in lowered or "quota" in lowered or "billing" in lowered:
        return f"{provider} reports no credit on this key"
    # Long provider payloads run off the end of the status line.
    return f"{provider} error: {text[:120]}"
