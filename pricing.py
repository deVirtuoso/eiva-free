"""
What an answer costs, worked out from the tokens the provider reports back.

Three providers can answer the screen - Anthropic, OpenAI and Google - and you
pay whichever one you brought a key for, directly, at their published rate.
Rates are dollars per million tokens, written down here rather than fetched, so
the window still works with no connection and a price change is a one-line
edit. Nothing else in the app reads a rate.

Re-check the figures against the three price lists below when RATES_CHECKED
starts to look old. A stale rate does not break anything - the meter is a guide
to what you are spending, not a bill - but a wrong one is worse than none.
"""

from datetime import date

# All three price lists last read on this date:
#   https://claude.com/pricing
#   https://platform.openai.com/docs/pricing
#   https://ai.google.dev/gemini-api/docs/pricing
RATES_CHECKED = "2026-08-25"

ANTHROPIC = "anthropic"
OPENAI = "openai"
GEMINI = "gemini"

# Anthropic bills cached input off the input rate: a tenth to read a cache
# entry, a quarter more than usual to write one. The other two providers
# discount cached input too, but report it inside the ordinary input count,
# so there is nothing separate for the meter to price.
CACHE_READ = 0.1
CACHE_WRITE = 1.25

# The Anthropic rates below were checked against the price list; the OpenAI
# and Google ones are the published figures for the generation each id belongs
# to and are worth confirming before quoting them at anybody. The meter is a
# guide to what an evening costs, not a bill, so a rate that has drifted
# misreports the total without breaking anything.
#
# Every model that can answer a screenshot, in the order the menu shows them.
# "effort" is Anthropic's, and is not accepted by every model of theirs -
# Haiku rejects it - so the flag rides with the rate rather than being guessed
# at the call site. Adding a model is a line here and nothing else: the menu,
# the meter and the provider routing all read this list.
ANSWER_MODELS = [
    {"id": "claude-opus-5", "label": "Opus 5", "provider": ANTHROPIC,
     "effort": True, "in": 5.00, "out": 25.00},
    {"id": "claude-sonnet-5", "label": "Sonnet 5", "provider": ANTHROPIC,
     "effort": True, "in": 3.00, "out": 15.00,
     # Introductory rate, on until the end of August 2026.
     "until": date(2026, 8, 31), "in_until": 2.00, "out_until": 10.00},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5", "provider": ANTHROPIC,
     "effort": False, "in": 1.00, "out": 5.00},

    {"id": "gpt-5.1", "label": "GPT-5.1", "provider": OPENAI,
     "in": 1.25, "out": 10.00},
    {"id": "gpt-5-mini", "label": "GPT-5 mini", "provider": OPENAI,
     "in": 0.25, "out": 2.00},
    {"id": "gpt-4.1", "label": "GPT-4.1", "provider": OPENAI,
     "in": 2.00, "out": 8.00},

    # Google retires an id rather than freezing it: the 2.5 line these
    # started on now answers 404 for any key that had not already used it,
    # with a message naming its replacement. When one of these stops working,
    # the error text says what to put here - and
    #   python -c "from google import genai; print([m.name for m in genai.Client().models.list()])"
    # lists what the key can actually reach.
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro",
     "provider": GEMINI, "thinking": "low", "in": 2.00, "out": 12.00},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash",
     "provider": GEMINI, "thinking": "low", "in": 0.30, "out": 2.50},
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash Lite",
     "provider": GEMINI, "thinking": "low", "in": 0.10, "out": 0.40},
]

ANSWER_IDS = [m["id"] for m in ANSWER_MODELS]

# Kept because the settings file and the older code speak in these terms.
CLAUDE_MODELS = [m for m in ANSWER_MODELS if m["provider"] == ANTHROPIC]
CLAUDE_IDS = [m["id"] for m in CLAUDE_MODELS]

PROVIDER_LABELS = {ANTHROPIC: "Anthropic", OPENAI: "OpenAI",
                   GEMINI: "Google Gemini"}


def answer_model(model_id):
    """The rate card for a model id, falling back to the first one listed."""
    for m in ANSWER_MODELS:
        if m["id"] == model_id:
            return m
    return ANSWER_MODELS[0]


# The old name, still used where the call site only ever meant "the model that
# answers".
claude_model = answer_model


# How each provider names its models. Needed because the app now offers models
# it was not shipped with - discovered from the provider on the user's own key
# - and an id with no rate card still has to be routed to the right SDK. Get
# this wrong and a Gemini id is sent to Anthropic, which is a 404 with a
# baffling message.
PREFIXES = (
    ("claude", ANTHROPIC),
    ("gpt", OPENAI),
    ("o1", OPENAI), ("o3", OPENAI), ("o4", OPENAI),
    ("gemini", GEMINI), ("gemma", GEMINI),
)


def provider_of(model_id):
    for m in ANSWER_MODELS:
        if m["id"] == model_id:
            return m["provider"]
    lowered = str(model_id or "").lower()
    for prefix, provider in PREFIXES:
        if lowered.startswith(prefix):
            return provider
    return ANSWER_MODELS[0]["provider"]


def known_shape(model_id):
    """True if this is an id we could route. A settings file naming something
    unroutable - a typo, or a model from a provider we have since dropped -
    falls back to the default rather than failing on every question."""
    lowered = str(model_id or "").lower()
    return any(lowered.startswith(p) for p, _ in PREFIXES)


def models_for(provider):
    return [m for m in ANSWER_MODELS if m["provider"] == provider]


def label_for(model_id):
    for m in ANSWER_MODELS:
        if m["id"] == model_id:
            return m["label"]
    return model_id


def rates_for(model):
    """(input, output) per million, honouring an introductory rate if it has
    not expired. Dated rather than deleted, so the day it lapses the figures
    go up on their own instead of quietly staying wrong."""
    if "until" in model and date.today() <= model["until"]:
        return model["in_until"], model["out_until"]
    return model["in"], model["out"]


claude_rates = rates_for


def money(usd):
    """Money at a readable precision. A question costs about a penny."""
    if usd >= 0.1:
        return f"${usd:,.2f}"
    if usd >= 0.01:
        return f"${usd:.3f}"
    if usd >= 0.0001 or usd <= 0:
        return f"${usd:.4f}"
    return "<$0.0001"


class AnswerMeter:
    """Tokens in, dollars out. Priced per call against the model that actually
    served it, so switching model - or provider - mid-session still totals
    correctly.

    It takes the plain dict engine.py normalises every provider's usage into,
    rather than one provider's own usage object, which is what lets one meter
    stand behind all three."""

    def __init__(self, spent=0.0):
        self.session = 0.0
        self.total = float(spent)
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def add(self, usage, model_id):
        if not usage:
            return 0.0
        model = answer_model(model_id)
        rate_in, rate_out = rates_for(model)

        fresh = usage.get("in", 0) or 0
        read = usage.get("cache_read", 0) or 0
        written = usage.get("cache_write", 0) or 0
        out = usage.get("out", 0) or 0

        cost = (fresh * rate_in
                + read * rate_in * CACHE_READ
                + written * rate_in * CACHE_WRITE
                + out * rate_out) / 1_000_000

        self.session += cost
        self.total += cost
        self.tokens_in += fresh + read + written
        self.tokens_out += out
        self.calls += 1
        return cost

    def detail(self):
        return (f"{self.calls} calls, {self.tokens_in:,} in / "
                f"{self.tokens_out:,} out")


# The meter had one provider behind it when it was written; the name outlived
# that.
ClaudeMeter = AnswerMeter
