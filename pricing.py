"""
What the Claude API costs, worked out from the tokens it reports back.

Rates are dollars per million tokens, written down here rather than fetched, so
the window still works with no connection and a price change is a one-line edit.

This is the free edition: it talks to Claude only. (The Pro edition adds the
Gemini Live voice models and meters them by modality.)
"""

from datetime import date

# Price list last read on this date. Worth re-checking when it looks old:
#   https://claude.com/pricing
RATES_CHECKED = "2026-08-19"

# Claude bills cached input off the input rate: a tenth to read a cache entry,
# a quarter more than usual to write one.
CACHE_READ = 0.1
CACHE_WRITE = 1.25

# "effort" is not accepted by every model - Haiku rejects it - so the flag
# rides with the rate rather than being guessed at the call site.
CLAUDE_MODELS = [
    {"id": "claude-opus-5", "label": "Opus 5", "effort": True,
     "in": 5.00, "out": 25.00},
    {"id": "claude-sonnet-5", "label": "Sonnet 5", "effort": True,
     "in": 3.00, "out": 15.00,
     # Introductory rate, on until the end of August 2026.
     "until": date(2026, 8, 31), "in_until": 2.00, "out_until": 10.00},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5", "effort": False,
     "in": 1.00, "out": 5.00},
]

CLAUDE_IDS = [m["id"] for m in CLAUDE_MODELS]


def claude_model(model_id):
    """The rate card for a model id, falling back to the first one listed."""
    for m in CLAUDE_MODELS:
        if m["id"] == model_id:
            return m
    return CLAUDE_MODELS[0]


def label_for(model_id):
    for m in CLAUDE_MODELS:
        if m["id"] == model_id:
            return m["label"]
    return model_id


def claude_rates(model):
    """(input, output) per million, honouring an introductory rate if it has
    not expired."""
    if "until" in model and date.today() <= model["until"]:
        return model["in_until"], model["out_until"]
    return model["in"], model["out"]


def money(usd):
    """Money at a readable precision. A question costs about a penny."""
    if usd >= 0.1:
        return f"${usd:,.2f}"
    if usd >= 0.01:
        return f"${usd:.3f}"
    if usd >= 0.0001 or usd <= 0:
        return f"${usd:.4f}"
    return "<$0.0001"


class ClaudeMeter:
    """Tokens in, dollars out. Priced per call against the model that actually
    served it, so switching model mid-session still totals correctly."""

    def __init__(self, spent=0.0):
        self.session = 0.0
        self.total = float(spent)
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def add(self, usage, model_id):
        if usage is None:
            return 0.0
        model = claude_model(model_id)
        rate_in, rate_out = claude_rates(model)

        fresh = usage.input_tokens or 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        out = usage.output_tokens or 0

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
