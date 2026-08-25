"""
Which models this key can actually reach, kept current without a server.

This is a one-off purchase. There is no subscription pushing updates, no
auto-updater, and no server of ours for the app to ask - so a hand-written list
of model ids is a list that goes wrong on its own, in the customer's hands,
months after the sale. It already has: the Gemini 2.5 line this app shipped
with now answers 404 for any key that had not already used it, and says so in
the error rather than in any release note we would have seen.

The fix is that all three providers will tell you, on the user's own key, what
that key can reach:

    Anthropic   client.models.list()      -> claude-*
    OpenAI      client.models.list()      -> everything, needs sieving
    Google      client.models.list()      -> everything, needs sieving

So the app asks them. Nothing is sent to us - these are calls to the provider
the user is already paying, on the key they already entered, and the answer is
cached next to the app so it is asked at most once a week.

What comes back is merged with the rate cards in pricing.py rather than
replacing them:

  * a listed model with a rate card is offered as it always was;
  * a rate card the provider no longer lists is dropped from the menu, which
    is what stops a retired id sitting there failing;
  * a listed model we have no rate for is offered too, under its own heading,
    priced against the nearest card of the same family and marked so nobody
    reads the meter as gospel.

Rates cannot be discovered - no provider publishes them through the API - so
they stay hand-maintained. That is the honest split: what exists is a fact the
provider will tell you, what it costs is not.
"""

import json
import re
import threading
import time
from pathlib import Path

import pricing

CACHE_FILE = Path(__file__).with_name("models.json")

# How stale the list may get before the app refreshes it in the background.
# A week is far more often than model line-ups actually change, and still only
# one extra request a week against a key the user is already using.
MAX_AGE = 7 * 24 * 3600

# Ids that answer a text request but are not what this app is for: pictures,
# speech, embeddings, robots, and the specialised variants nobody choosing a
# model from a menu wants to see. Matched as substrings of the id, lower-cased.
NOT_FOR_US = (
    "embed", "tts", "audio", "whisper", "moderation", "transcribe", "realtime",
    "image", "vision-preview", "dall-e", "lyria", "veo", "imagen", "robotics",
    "computer-use", "deep-research", "search", "codex", "instruct",
    "customtools", "omni",
)

# What a family is worth, when a model turns up that we have no rate for: the
# nearest card of the same provider in the same size class. Order matters only
# among words that can both appear; flash-lite is handled ahead of these.
FAMILIES = ("haiku", "mini", "nano", "lite", "flash", "sonnet", "opus", "pro")

# How many models we were not shipped with to offer per provider. Google lists
# sixteen on an ordinary key, most of them variants of each other, and a menu
# nobody can read is no better than a menu that is out of date.
MAX_EXTRA = 8

_lock = threading.Lock()
_cache = None


# --- the cache ---------------------------------------------------------------

def _load():
    """{provider: {"when": epoch, "ids": [[id, label], ...]}}, or empty."""
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(_cache, dict):
                _cache = {}
        except Exception:
            _cache = {}          # never been asked, or the file got mangled
    return _cache


def _save():
    try:
        CACHE_FILE.write_text(json.dumps(_cache, indent=2), encoding="utf-8")
    except Exception:
        pass                     # read-only folder; the list is still correct
                                 # for this run, which is the important half


def age(provider):
    """Seconds since this provider was last asked, or None if never."""
    entry = _load().get(provider)
    if not entry:
        return None
    return max(0.0, time.time() - float(entry.get("when", 0)))


def stale(provider):
    seen = age(provider)
    return seen is None or seen > MAX_AGE


def listed(provider):
    """[(id, label)] the provider last said this key can reach, or None if it
    has never been asked. None and [] mean different things: never asked means
    show the built-in list untouched."""
    entry = _load().get(provider)
    if not entry:
        return None
    return [tuple(pair) for pair in entry.get("ids", [])]


# --- asking the providers ----------------------------------------------------

def _wanted(model_id):
    lowered = model_id.lower()
    return not any(word in lowered for word in NOT_FOR_US)


def _anthropic():
    import anthropic
    client = anthropic.Anthropic()
    out = []
    for m in client.models.list(limit=100):
        if _wanted(m.id):
            out.append((m.id, getattr(m, "display_name", None) or m.id))
    return out


def _openai():
    import openai
    client = openai.OpenAI()
    out = []
    for m in client.models.list():
        # OpenAI lists every model on the account - speech, embeddings, the
        # lot. Only the chat families can answer a screenshot.
        if not re.match(r"^(gpt-|o\d)", m.id):
            continue
        if not _wanted(m.id):
            continue
        out.append((m.id, m.id))
    return out


def _gemini():
    from google import genai
    client = genai.Client()
    out = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        # The API returns "models/gemini-x"; the app names them without the
        # prefix, and the SDK accepts either.
        name = (m.name or "").split("/")[-1]
        if not name.startswith("gemini") or not _wanted(name):
            continue
        out.append((name, getattr(m, "display_name", None) or name))
    return out


ASK = {"anthropic": _anthropic, "openai": _openai, "gemini": _gemini}


def refresh(provider):
    """Ask one provider what this key can reach and remember the answer.

    Returns (ok, note). Never raises: a refresh that fails leaves whatever was
    known before in place, because a menu built from a week-old list beats a
    menu built from nothing."""
    try:
        found = ASK[provider]()
    except Exception as e:
        return False, f"could not list {provider} models ({type(e).__name__})"
    if not found:
        return False, f"{provider} listed no usable models"
    with _lock:
        _load()[provider] = {"when": time.time(), "ids": [list(p) for p in found]}
        _save()
    return True, f"{provider}: {len(found)} models"


def refresh_in_background(providers, when_done=None):
    """Refresh on a worker thread. The window must not wait on three HTTP
    round trips before it can draw a menu."""
    def work():
        notes = []
        for provider in providers:
            ok, note = refresh(provider)
            notes.append(note)
        if when_done:
            when_done(notes)

    threading.Thread(target=work, daemon=True).start()


# --- what the menu should show -----------------------------------------------

def _family_of(model_id):
    """Which size class an id belongs to, matched on whole words.

    Whole words, and not substrings, for one specific reason: every Google id
    contains "gemini", and "gemini" contains "mini" - so a substring match
    files the entire Gemini line under the cheapest OpenAI rate and quietly
    under-reports what an evening cost by a factor of six."""
    words = set(re.split(r"[^a-z0-9]+", model_id.lower()))
    if "flash" in words and "lite" in words:
        return "flash-lite"
    for family in FAMILIES:
        if family in words:
            return family
    return None


def _newness(model_id):
    """The version number in an id, for putting the newest first. A list
    nobody curated has to be ordered by something, and "3.7" above "2.5" is
    right far more often than alphabetical is."""
    # A floating alias is the one id that cannot go stale, which is worth a
    # great deal to a program nobody will ever update. Sorted above every
    # numbered version so the cap below never drops it.
    if model_id.endswith("-latest"):
        return 9999.0
    found = re.search(r"(\d+(?:\.\d+)?)", model_id)
    try:
        return float(found.group(1)) if found else 0.0
    except ValueError:
        return 0.0


def _prune(pairs):
    """Drop the preview of something that has since shipped. Providers leave
    both listed for months, and offering `x-preview` next to `x` is a choice
    with no right answer."""
    ids = {mid for mid, _ in pairs}
    out = []
    for mid, label in pairs:
        base = re.sub(r"-preview(-[\d-]+)?$", "", mid)
        if base != mid and base in ids:
            continue
        out.append((mid, label))
    return out


def _rate_for(provider, model_id):
    """A rate card for a model we were not shipped with, borrowed from the
    nearest one of the same family. Marked estimated, because it is."""
    family = _family_of(model_id)
    kin = [m for m in pricing.models_for(provider)
           if family and _family_of(m["id"]) == family]
    # Failing a family match, the middle of the range is a fairer guess than
    # whichever card happens to be listed first.
    if not kin:
        by_price = sorted(pricing.models_for(provider),
                          key=lambda m: m.get("in", 0))
        kin = by_price[len(by_price) // 2:] or []
    nearest = (kin or pricing.models_for(provider) or pricing.ANSWER_MODELS)[0]
    card = dict(nearest)
    card.update({"id": model_id, "provider": provider, "estimated": True})
    card.pop("until", None)              # an introductory rate is not inherited
    return card


def menu_for(provider):
    """The rate cards to offer for one provider: what we shipped, minus
    anything the provider has since retired, plus anything new it now lists.

    Before the provider has ever been asked, this is exactly the built-in list
    - the app has to work on the first run, offline, with no round trip."""
    known = pricing.models_for(provider)
    found = listed(provider)
    if found is None:
        return known

    live_ids = {mid for mid, _ in found}
    out = [m for m in known if m["id"] in live_ids]

    extra = []
    for mid, label in _prune(found):
        if any(m["id"] == mid for m in known):
            continue
        card = _rate_for(provider, mid)
        card["label"] = label
        extra.append(card)

    extra.sort(key=lambda c: (-_newness(c["id"]), c["id"]))
    return out + extra[:MAX_EXTRA]


def retired(provider):
    """Model ids we shipped that the provider no longer lists. Worth saying
    out loud once, because the answer to "where did my model go" is here."""
    found = listed(provider)
    if found is None:
        return []
    live_ids = {mid for mid, _ in found}
    return [m["id"] for m in pricing.models_for(provider)
            if m["id"] not in live_ids]


def middle_of_the_range(provider):
    """The model to pick when the app is choosing on the user's behalf.

    Not the best one. Auto-selection happens for somebody who has not chosen
    at all - most often on a brand-new key, which is most often on a free
    tier, where the flagship is the one model that answers 429 before it
    answers anything. The middle of the price list is fast, cheap enough not
    to be a surprise, and available on tiers the top of the range is not.

    Only models we shipped a real rate card for are considered: a discovered
    model's price is a guess, and guessing is no way to sort by price.
    """
    priced = [m for m in menu_for(provider) if not m.get("estimated")]
    if not priced:
        priced = menu_for(provider)
    if not priced:
        return None
    priced.sort(key=lambda m: m.get("in", 0))
    return priced[len(priced) // 2]


def card_for(model_id, provider=None):
    """The rate card for any id, shipped or discovered."""
    provider = provider or pricing.provider_of(model_id)
    for card in menu_for(provider):
        if card["id"] == model_id:
            return card
    return pricing.answer_model(model_id)
