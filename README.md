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

This is the **MIT source edition** — the Python, to read and run. There is
also a single ready-made download on the site that needs no Python at all; it
runs exactly these features until a Pro licence is added, and turns into Pro
without a second download. Either way this does one thing, and does it well:

> **Drag a box around some text → the answer streams into the window.**

No OCR. The cropped screenshot goes straight to the model, which reads it — so
it handles charts, diagrams and messy screenshots as well as plain text.

**Bring whichever key you already have.** Anthropic, OpenAI or Google can all
answer; pick one from the **Model** menu. You need a key for only one of them.

## What's in the free edition

| | |
|---|---|
| **Ask** | Drag a box around a question or a claim. The answer streams in. |
| **Models** | Anthropic (Opus 5, Sonnet 5, Haiku 4.5), OpenAI (GPT-5.1, GPT-5 mini, GPT-4.1) or Google (Gemini 3.1 Pro, 3.6 Flash, 3.5 Flash Lite) — your pick, remembered between runs. |
| **A list that stays current** | Models get retired. Once a week the app asks each provider, on your own key, what that key can actually reach — dropping what has gone and offering what is new. Nothing is sent to us; there is no server to send it to. |
| **Running cost** | A live token meter: this session on the left, all-time on the right. Roughly a penny a question, billed by your provider, direct to you. |
| **Appearance** | Four themes (Light, Dark, Sepia, Contrast), adjustable font size, remembered window position. |
| **Copy** | One click puts the latest answer on the clipboard. |

## What Pro adds

The free edition is text-in, text-out. **[EIVA Pro](https://eiva.worldwidechoices.com)** adds the hands-free half:

- **Watch** — pick a region once; it answers on its own when new text appears.
- **Listen** — transcribes your PC's audio locally (Whisper, on the GPU) and answers questions it hears. No microphone opened.
- **Spoken answers** — read aloud through Windows' own voices, panned to either ear.
- **Live voice** — a two-way spoken conversation, with optional webcam and
  screen share. This one runs on **Google Gemini's Live API** and needs a
  Google key specifically: no other provider offers it, so an Anthropic or
  OpenAI key cannot stand in. Everything else in Pro works on whichever key
  you already have.
- **Reference material** — drop files in a folder and let the answers draw on them.

Pro is a **one-off £1.99** (introductory), and **each licence activates one
computer** — it is tied to that machine's code and does not expire. Moving to a
new PC means a reissued key, which costs nothing; ask and it is sent.

**Unlocking it from here.** Click **✦ Unlock Pro** at the bottom of the window
and three things happen at once: the checkout opens, this computer's machine
code is worked out and copied to your clipboard, and a small window shows you
the code with what to do with it. Paste it into the *Machine code* box at
checkout — that is what your licence gets issued against.

When the key comes back, you can paste it into that same window **before** you
download Pro. It is written to where Pro looks for it, so Pro starts already
activated and never shows an activation screen at all.

## Setup

Nothing to install first — not even Python.

1. **Download the zip and extract it.** Right-click → *Extract All*, and put
   the folder somewhere that stays put — Documents is fine, Downloads is fine.
   Don't run it from inside the zip: Windows shows you the contents without
   unpacking them, and anything installed there is deleted when the window
   closes. (Setup checks for this and says so rather than half-installing.)
2. **Double-click `setup.cmd`.** That's the whole install. It finds a Python
   that will do, installs one for your account if the machine has none (via
   `winget`, or the signed installer from
   [python.org](https://www.python.org/downloads/) — no administrator rights
   either way), builds a private virtual environment beside the script, and
   installs the dependencies (`pillow` for screen capture, plus the
   `anthropic`, `openai` and `google-genai` clients — all three go in, so
   switching provider later is a menu choice, not another install). It is safe
   to run again at any time; it repairs rather than duplicates.

   Rather use a Python you already installed? `setup.cmd -NoPythonInstall`.

   You can skip this step entirely and just double-click **`eiva.cmd`** — it
   runs setup itself the first time, and after anything breaks the virtual
   environment.
3. **Double-click `eiva.cmd`** to start it. Then click **Keys** and paste an
   API key — Anthropic, OpenAI or Google. One is enough. If you already have
   one in your Windows environment, the app finds it and picks a matching
   model on its own.

To start it with no console window at all, use **`eiva.vbs`** (pin it to the
taskbar). To watch the output while debugging:

```
eiva.cmd --console
```

### If PowerShell refuses to run the script

Running `.\setup.ps1` yourself gets you one of these, and neither is a problem
with the download:

```
... cannot be loaded because running scripts is disabled on this system.
... cannot be loaded. The file ...\setup.ps1 is not digitally signed.
```

That is Windows' script policy, and the second one is what you get *after*
setting `RemoteSigned` — every file in a folder that came from the internet
carries a mark saying so, and `RemoteSigned` answers that mark by demanding a
signature. **Use `setup.cmd` instead.** A `.cmd` file is not subject to the
policy, and it starts PowerShell with the policy relaxed for that one process;
nothing about your machine is changed. Setup then clears the download mark on
its own files, so `.\setup.ps1` works normally from then on if you prefer it.

You never need to run `Set-ExecutionPolicy`.

### You bring your own key

The app **never ships with an API key** and never sends anything anywhere except
your own question, to the provider whose model you picked, over your own key.
Any one of these will do:

| Provider | Get a key at | Keys look like |
|---|---|---|
| Anthropic (Claude) | [console.anthropic.com](https://console.anthropic.com) → API keys | `sk-ant-…` |
| OpenAI (GPT) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | `sk-…` |
| Google (Gemini) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `AIza…` |

Set a spend cap while you are there. Your key is stored in your Windows account
environment (via `setx`) — **never** written next to the script, so it can't be
committed by accident. Clearing it in the Keys dialog removes it.

Nothing is ever disabled for want of a key: if you click **Ask about a region**
without one, the app says which key it needs and opens the box to paste it in.

> **Note:** a Claude Pro subscription covers claude.ai and Claude Code. It does
> **not** include API credit — that's billed separately, per token. A
> chat-region screenshot is only a few hundred tokens, so an evening's use lands
> around 20–30p.

## Privacy

- Screenshots you capture are sent **only** to the provider whose model you
  chose — Anthropic, OpenAI or Google — to answer your question. Nothing is
  stored or sent anywhere else.
- No telemetry, no analytics, no account, no phone-home.
- Settings live in `settings.json` next to the script (machine-local, git-ignored).

See the full [Privacy Policy](https://eiva.worldwidechoices.com/privacy.html).

## Files

| | |
|---|---|
| `eiva.py` | the whole free application |
| `engine.py` | one streaming call, three providers behind it |
| `keys.py` | where the API keys are kept, and how the window changes them |
| `catalog.py` | asks each provider what your key can reach, so the model list never goes stale |
| `machine.py` | this computer's code, for buying and activating Pro |
| `pricing.py` | what each provider costs, per token |
| `setup.cmd` | the installer — the one to double-click |
| `setup.ps1` | what it runs; the setup itself |
| `eiva.cmd` / `eiva.vbs` | launchers |

## Licence

MIT — see [LICENSE](LICENSE). Do what you like with it.
