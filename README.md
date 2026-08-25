<p align="center">
  <img src="assets/icon_128.png" width="96" alt="EIVA">
</p>

<h1 align="center">EIVA — Free</h1>

<p align="center"><em>An extra voice in the room. Select any text on your screen, get a straight answer.</em></p>

---

A small always-on-top window that reads a region of your screen and answers what
it finds there. Because it works at the screen level rather than through a chat
API, it doesn't care which app the conversation is in — Teams, WhatsApp, Slack,
a PDF, a screenshot of a screenshot.

This is the **free, open-source edition (MIT)**. It does one thing, and does it
well:

> **Drag a box around some text → the answer streams into the window.**

No OCR. The cropped screenshot goes straight to Claude, which reads it — so it
handles charts, diagrams and messy screenshots as well as plain text.

## What's in the free edition

| | |
|---|---|
| **Ask** | Drag a box around a question or a claim. The answer streams in. |
| **Models** | Opus 5, Sonnet 5 or Haiku 4.5 — your pick, remembered between runs. |
| **Running cost** | A live token meter: this session on the left, all-time on the right. Roughly a penny a question. |
| **Appearance** | Four themes (Light, Dark, Sepia, Contrast), adjustable font size, remembered window position. |
| **Copy** | One click puts the latest answer on the clipboard. |

## What Pro adds

The free edition is text-in, text-out. **[EIVA Pro](https://eiva.worldwidechoices.com)** adds the hands-free half:

- **Watch** — pick a region once; it answers on its own when new text appears.
- **Listen** — transcribes your PC's audio locally (Whisper, on the GPU) and answers questions it hears. No microphone opened.
- **Spoken answers** — read aloud through Windows' own voices, panned to either ear.
- **Live voice** — a two-way spoken conversation via Gemini Live.
- **Reference material** — drop files in a folder and let the answers draw on them.

Pro is a **one-off £1.99** (introductory). → **[eiva.worldwidechoices.com](https://eiva.worldwidechoices.com)**

## Setup

You need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/) — tick *Add python.exe to PATH*).

1. Download or clone this folder.
2. Double-click **`eiva.cmd`**. On a fresh machine it runs `setup.ps1`, which
   builds a private virtual environment and installs the two dependencies
   (`anthropic`, `pillow`). Safe to re-run.
3. Click **Keys** and paste your Anthropic API key.

To start it with no console window at all, use **`eiva.vbs`** (pin it to the
taskbar). To watch the output while debugging:

```
eiva.cmd --console
```

### You bring your own key

The app **never ships with an API key** and never sends anything anywhere except
your own question, to Anthropic, over your own key. Get one at
[console.anthropic.com](https://console.anthropic.com) → API keys, and set a
spend cap while you're there.

Your key is stored in your Windows account environment (via `setx`) — **never**
written next to the script, so it can't be committed by accident. Clearing it in
the Keys dialog removes it.

> **Note:** a Claude Pro subscription covers claude.ai and Claude Code. It does
> **not** include API credit — that's billed separately, per token. A
> chat-region screenshot is only a few hundred tokens, so an evening's use lands
> around 20–30p.

## Privacy

- Screenshots you capture are sent **only** to Anthropic, to answer your
  question. Nothing is stored or sent anywhere else.
- No telemetry, no analytics, no account, no phone-home.
- Settings live in `settings.json` next to the script (machine-local, git-ignored).

See the full [Privacy Policy](https://eiva.worldwidechoices.com/privacy.html).

## Files

| | |
|---|---|
| `eiva.py` | the whole free application |
| `keys.py` | where the API key is kept, and how the window changes it |
| `pricing.py` | what the Claude API costs, per token |
| `setup.ps1` | one-time environment setup |
| `eiva.cmd` / `eiva.vbs` | launchers |

## Licence

MIT — see [LICENSE](LICENSE). Do what you like with it.
