"""
EIVA - Free edition.

A small always-on-top window that reads a region of your screen and answers
what it finds there, in text.

  ASK   drag a box around a question -> the answer streams into the window.

That is the whole of the free edition, on purpose: select text, get a text
answer. Watch mode, listening, spoken answers, the live voice conversation and
reference material are the Pro edition - see the Unlock link at the bottom.

You bring your own Anthropic API key. The app never ships with a key, never
writes one next to itself, and never sends anything anywhere except your own
question, to Anthropic, over your own key.

Font size, colour scheme, window position and the chosen model are remembered
between runs (settings.json, next to this file). No OCR - the screenshot goes
straight to Claude, which reads it.
"""

import base64
import ctypes
import io
import json
import os
import re
import sys
import threading
import time
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

# --- somewhere to put output when there is no console ------------------------
LOG_FILE = Path(__file__).with_name("eiva.log")
LOG_LIMIT = 256 * 1024


def route_output_to_log():
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        start_over = LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_LIMIT
        stream = open(LOG_FILE, "w" if start_over else "a", buffering=1,
                      encoding="utf-8", errors="replace")
    except Exception:
        return
    sys.stdout = sys.stderr = stream
    stream.write(f"\n--- started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")


route_output_to_log()

from PIL import ImageGrab
import anthropic

import keys
import pricing

# --- Windows display scaling (before any window is created) ------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

MODEL = "claude-opus-5"     # the model a fresh install starts on
EFFORT = "medium"          # low = faster/cheaper, high = more thorough

BODY_FAMILY = "Corbel"
LABEL_FAMILY = "Consolas"

PRO_URL = "https://eiva.worldwidechoices.com/#pro"     # where "Unlock Pro" points

APP_DIR = Path(__file__).parent
ICON_ICO = APP_DIR / "assets" / "icon.ico"

SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULTS = {"font_size": 11, "theme": "Light", "geometry": "440x520",
            "claude_model": MODEL, "spend_claude": 0.0}

HISTORY = 25

THEMES = {
    "Light":    {"bg": "#F1F4F7", "panel": "#FFFFFF", "text": "#16202B",
                 "dim": "#7C8B99", "accent": "#0C7A7C", "btn": "#E4EAEF",
                 "btntext": "#16202B", "sel": "#CFE7E7"},
    "Dark":     {"bg": "#0F151B", "panel": "#171F27", "text": "#E3EAF1",
                 "dim": "#71818F", "accent": "#3EB5B2", "btn": "#2A3742",
                 "btntext": "#E3EAF1", "sel": "#1E4644"},
    "Sepia":    {"bg": "#EFE7DA", "panel": "#FBF6EC", "text": "#2E2519",
                 "dim": "#8B7C64", "accent": "#8A5A22", "btn": "#E2D7C4",
                 "btntext": "#2E2519", "sel": "#E4D2B4"},
    "Contrast": {"bg": "#000000", "panel": "#000000", "text": "#FFFFFF",
                 "dim": "#B0B0B0", "accent": "#FFD400", "btn": "#242424",
                 "btntext": "#FFFFFF", "sel": "#443A00"},
}

SYSTEM = """You are EIVA, an extra participant sitting in on a conversation
between several people. They will show you a screenshot of part of it.

Read it and respond to what is there. Most of it will not be phrased as a
question - people mid-argument rarely ask one - and it still needs an answer:

- A flat assertion is a claim to be checked. Say whether it holds, what it
  rests on, and what it leaves out.
- A number or statistic is a claim too. Confirm it, correct it, or say you
  cannot verify it. Never let a wrong figure stand unremarked.
- A half-finished argument needs its missing step named, not quietly filled in.
- Two people talking past each other need the actual point of disagreement
  identified, with any part that is only a dispute about words separated out.
- A term used loosely, or in two senses at once, needs defining before the rest
  of the answer means anything.

Say there is nothing to answer only when nothing is being claimed at all.

Content:
- Be brief. A couple of sentences per question unless it genuinely needs more.
- Say plainly when the evidence is thin, rather than sounding equally confident
  either way.
- If asked which argument is stronger, say which, and why. Don't fence-sit.
- Never invent a citation. Flag anything you're recalling rather than certain of.

Formatting - this matters, they read it in a small window:
- Answer the questions in the order they appear on screen.
- Give each question its own short paragraph, separated by a blank line.
- Lead with the direct answer, then the qualification. Not the other way round.
- Put **bold** on the answer itself - the name, the number, the verdict - and
  nowhere else. One bold phrase per paragraph at most.
- No headings, no preamble, no sign-off, no "great question"."""


# --- small helpers -----------------------------------------------------------

def load_settings():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    if data.get("claude_model") not in pricing.CLAUDE_IDS:
        data["claude_model"] = MODEL
    if data.get("theme") not in THEMES:
        data["theme"] = "Light"
    return data


def save_settings(data):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def virtual_screen():
    g = ctypes.windll.user32.GetSystemMetrics
    return g(76), g(77), g(78), g(79)


def grab(bbox):
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def to_png_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def dpi_scale():
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
    except Exception:
        return 1.0


def strip_markup(text):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


# --- the key dialog ----------------------------------------------------------

class KeyDialog:
    """A tiny modal to paste the Anthropic key into. Stored in the Windows
    environment through keys.save, never next to the script."""

    def __init__(self, chair):
        self.chair = chair
        t = chair.theme
        self.win = tk.Toplevel(chair.root)
        self.win.title("API key")
        self.win.configure(bg=t["bg"])
        self.win.transient(chair.root)
        self.win.resizable(False, False)
        try:
            self.win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        prov = keys.PROVIDERS[0]
        pad = {"padx": 14, "pady": 6}
        tk.Label(self.win, text="Anthropic API key",
                 font=(LABEL_FAMILY, 11, "bold"),
                 bg=t["bg"], fg=t["text"]).grid(row=0, column=0, sticky="w",
                                                columnspan=2, **pad)
        tk.Label(self.win, text=f"{prov['note']}  ·  from {prov['where']}",
                 font=(BODY_FAMILY, 10), bg=t["bg"],
                 fg=t["dim"]).grid(row=1, column=0, sticky="w",
                                   columnspan=2, padx=14)

        self.state = tk.Label(self.win, text=self._state_text(),
                              font=(LABEL_FAMILY, 9), bg=t["bg"], fg=t["dim"])
        self.state.grid(row=2, column=0, sticky="w", columnspan=2, padx=14,
                        pady=(6, 2))

        self.entry = tk.Entry(self.win, width=48, show="*",
                              font=(LABEL_FAMILY, 10), bg=t["panel"],
                              fg=t["text"], insertbackground=t["text"])
        self.entry.grid(row=3, column=0, columnspan=2, padx=14, pady=6)
        self.entry.focus_set()

        row = tk.Frame(self.win, bg=t["bg"])
        row.grid(row=4, column=0, columnspan=2, sticky="e", padx=14, pady=10)
        self._btn(row, "Save", self.save).pack(side="left", padx=4)
        self._btn(row, "Clear", self.clear).pack(side="left", padx=4)
        self._btn(row, "Close", self.close).pack(side="left", padx=4)
        self.win.bind("<Return>", lambda e: self.save())
        self.win.bind("<Escape>", lambda e: self.close())

    def _btn(self, parent, text, cmd):
        t = self.chair.theme
        return tk.Button(parent, text=text, command=cmd, relief="flat",
                         font=(LABEL_FAMILY, 10), bg=t["btn"],
                         fg=t["btntext"], activebackground=t["sel"],
                         padx=10, pady=3, cursor="hand2")

    @staticmethod
    def _state_text():
        env = keys.PROVIDERS[0]["env"]
        return f"currently: {keys.masked(keys.current(env))}"

    def save(self):
        prov = keys.PROVIDERS[0]
        key = self.entry.get().strip()
        wrong = keys.looks_wrong(prov, key)
        if wrong:
            self.state.configure(text=f"not saved: {wrong}")
            return
        ok, msg = keys.save(prov["env"], key)
        note = "" if not keys.unfamiliar(prov, key) else \
            "  (unusual prefix - saved anyway)"
        self.state.configure(text=msg + note)
        self.entry.delete(0, "end")
        self.chair.connect_claude()

    def clear(self):
        ok, msg = keys.forget(keys.PROVIDERS[0]["env"])
        self.state.configure(text=msg)
        self.chair.connect_claude()

    def close(self):
        self.win.destroy()


# --- the region picker -------------------------------------------------------

class RegionPicker:
    """Dim the screen, let the user drag a rectangle, return its bbox."""

    DIM = 0.45
    EDGE = "#FFD400"
    MIN = 8

    def __init__(self, root, accent, on_done):
        self.on_done = on_done
        vx, vy, vw, vh = virtual_screen()
        s = dpi_scale()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", self.DIM)
        self.win.configure(cursor="crosshair", bg="#05080B")

        self.canvas = tk.Canvas(self.win, bg="#05080B", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.origin = (vx, vy)
        self.min_drag = int(self.MIN * s)
        self.w_shadow = max(7, int(round(7 * s)))
        self.w_edge = max(3, int(round(3 * s)))
        self.start = None
        self.shadow = self.rect = self.readout = None

        centre = max(vw // 2, root.winfo_screenwidth() // 2) - vx
        self.canvas.create_text(
            centre, int(70 * s), anchor="n", fill="#FFFFFF",
            font=(BODY_FAMILY, 15, "bold"),
            text="Drag a box around the text        Esc to cancel")

        self.canvas.bind("<Button-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.win.bind("<Escape>", lambda e: self.cancel())
        self.win.focus_force()

    def press(self, e):
        self.start = (e.x, e.y)
        for item in (self.shadow, self.rect, self.readout):
            if item:
                self.canvas.delete(item)
        self.shadow = self.canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#000000", width=self.w_shadow)
        self.rect = self.canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline=self.EDGE, width=self.w_edge)
        self.readout = self.canvas.create_text(
            e.x, e.y, anchor="sw", fill=self.EDGE, text="",
            font=(BODY_FAMILY, 13, "bold"))

    def drag(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        self.canvas.coords(self.shadow, x0, y0, e.x, e.y)
        self.canvas.coords(self.rect, x0, y0, e.x, e.y)
        self.canvas.coords(self.readout, min(x0, e.x),
                           min(y0, e.y) - self.w_shadow)
        self.canvas.itemconfigure(
            self.readout, text=f"{abs(e.x - x0)} x {abs(e.y - y0)}")

    def release(self, e):
        if not self.start:
            return self.cancel()
        ox, oy = self.origin
        x1, x2 = sorted((self.start[0], e.x))
        y1, y2 = sorted((self.start[1], e.y))
        self.win.destroy()
        if x2 - x1 < self.min_drag or y2 - y1 < self.min_drag:
            self.on_done(None)
        else:
            self.on_done((x1 + ox, y1 + oy, x2 + ox, y2 + oy))

    def cancel(self):
        self.win.destroy()
        self.on_done(None)


# --- the window --------------------------------------------------------------

class Chair:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.theme = THEMES[self.settings["theme"]]
        self.claude_meter = pricing.ClaudeMeter(self.settings["spend_claude"])
        self.client = None
        self.busy = False
        self.cancelled = threading.Event()
        self.answers = []
        self.answer = ""

        root.title("EIVA - Free")
        root.geometry(self.settings["geometry"])
        root.minsize(360, 380)
        root.attributes("-topmost", True)
        try:
            root.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        self._build()
        self.apply_theme()
        self.connect_claude()
        self.render_all()

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-plus>", lambda e: self.resize(1))
        root.bind("<Control-minus>", lambda e: self.resize(-1))
        root.bind("<Control-c>", lambda e: self.copy())

    # --- layout --------------------------------------------------------------

    def _build(self):
        fs = self.settings["font_size"]

        self.top = tk.Frame(self.root)
        self.top.pack(fill="x", padx=8, pady=(8, 4))
        self.title_lbl = tk.Label(self.top, text="EIVA",
                                  font=(LABEL_FAMILY, 11, "bold"))
        self.title_lbl.pack(side="left")
        self.cost_lbl = tk.Label(self.top, text="", font=(LABEL_FAMILY, 8),
                                 cursor="hand2")
        self.cost_lbl.pack(side="right")
        self.cost_lbl.bind("<Button-1>", lambda e: self.show_cost_breakdown())
        self.cost_lbl.bind("<Button-3>", lambda e: self.reset_session_cost())

        # models row
        self.mrow = tk.Frame(self.root)
        self.mrow.pack(fill="x", padx=8, pady=2)
        self.model_btn = tk.Menubutton(self.mrow, relief="flat",
                                       font=(LABEL_FAMILY, 9), cursor="hand2")
        self.model_btn.pack(side="left")
        self.model_menu = tk.Menu(self.model_btn, tearoff=0)
        for m in pricing.CLAUDE_MODELS:
            self.model_menu.add_command(
                label=m["label"],
                command=lambda mid=m["id"]: self.select_model(mid))
        self.model_btn.configure(menu=self.model_menu)
        self.keys_btn = self._btn(self.mrow, "Keys", self.edit_keys)
        self.keys_btn.pack(side="right")

        # output area
        self.out = tk.Text(self.root, wrap="word", relief="flat",
                           padx=12, pady=10, font=(BODY_FAMILY, fs),
                           state="disabled", cursor="arrow")
        self.out.pack(fill="both", expand=True, padx=8, pady=4)

        # action row
        self.arow = tk.Frame(self.root)
        self.arow.pack(fill="x", padx=8, pady=2)
        self.ask_btn = self._btn(self.arow, "Ask about a region", self.ask,
                                 accent=True)
        self.ask_btn.pack(side="left")
        self.copy_btn = self._btn(self.arow, "Copy", self.copy)
        self.copy_btn.pack(side="left", padx=(6, 0))
        self.clear_btn = self._btn(self.arow, "Clear", self.clear_screen)
        self.clear_btn.pack(side="left", padx=(6, 0))
        self.stop_btn = self._btn(self.arow, "Stop", self.stop_everything)
        self.stop_btn.pack(side="left", padx=(6, 0))

        # appearance row
        self.brow = tk.Frame(self.root)
        self.brow.pack(fill="x", padx=8, pady=2)
        self._btn(self.brow, "A-", lambda: self.resize(-1)).pack(side="left")
        self._btn(self.brow, "A+", lambda: self.resize(1)).pack(side="left",
                                                                padx=(4, 0))
        self.theme_btn = self._btn(self.brow, "Theme", self.cycle_theme)
        self.theme_btn.pack(side="left", padx=(4, 0))

        # status + upsell footer
        self.status = tk.Label(self.root, text="", anchor="w",
                               font=(LABEL_FAMILY, 8))
        self.status.pack(fill="x", padx=10, pady=(2, 0))

        self.upsell = tk.Label(
            self.root, cursor="hand2", anchor="w", font=(LABEL_FAMILY, 8),
            text="✦  Watch · Listen · Voice · Reference "
                 "files  →  Unlock Pro")
        self.upsell.pack(fill="x", padx=10, pady=(0, 8))
        self.upsell.bind("<Button-1>", lambda e: webbrowser.open(PRO_URL))

        self.paint_models()

    def _btn(self, parent, text, cmd, accent=False):
        return tk.Button(parent, text=text, command=cmd, relief="flat",
                         font=(LABEL_FAMILY, 9), padx=8, pady=3,
                         cursor="hand2",
                         name=("accent" if accent else str(id(text))[-6:]))

    # --- theme ---------------------------------------------------------------

    def apply_theme(self):
        t = self.theme
        self.root.configure(bg=t["bg"])
        for f in (self.top, self.mrow, self.arow, self.brow):
            f.configure(bg=t["bg"])
        self.title_lbl.configure(bg=t["bg"], fg=t["text"])
        self.cost_lbl.configure(bg=t["bg"], fg=t["dim"])
        self.status.configure(bg=t["bg"], fg=t["dim"])
        self.upsell.configure(bg=t["bg"], fg=t["accent"])
        self.model_btn.configure(bg=t["btn"], fg=t["btntext"],
                                 activebackground=t["sel"])
        self.out.configure(bg=t["panel"], fg=t["text"],
                           insertbackground=t["text"])

        for b in (self.ask_btn, self.copy_btn, self.clear_btn, self.stop_btn,
                  self.keys_btn, self.theme_btn):
            b.configure(bg=t["btn"], fg=t["btntext"],
                        activebackground=t["sel"], activeforeground=t["text"])
        for child in self.brow.winfo_children():
            if isinstance(child, tk.Button):
                child.configure(bg=t["btn"], fg=t["btntext"],
                                activebackground=t["sel"])
        self.ask_btn.configure(bg=t["accent"], fg="#FFFFFF",
                               activebackground=t["accent"],
                               activeforeground="#FFFFFF")

        fs = self.settings["font_size"]
        self.out.configure(font=(BODY_FAMILY, fs))
        self.out.tag_configure("bold", font=(BODY_FAMILY, fs, "bold"))
        self.out.tag_configure("para", spacing3=int(fs * 0.7))
        self.out.tag_configure("head", font=(BODY_FAMILY, fs + 1, "bold"),
                               foreground=t["accent"], spacing1=fs, spacing3=4)
        self.out.tag_configure("item", lmargin1=6, lmargin2=20)
        self.out.tag_configure("stamp", font=(LABEL_FAMILY, max(7, fs - 3)),
                               foreground=t["dim"], spacing1=fs, spacing3=4)
        self.out.tag_configure("muted", foreground=t["dim"])

    def cycle_theme(self):
        names = list(THEMES)
        nxt = names[(names.index(self.settings["theme"]) + 1) % len(names)]
        self.settings["theme"] = nxt
        self.theme = THEMES[nxt]
        self.apply_theme()
        self.render_all()
        save_settings(self.settings)

    def resize(self, step):
        self.settings["font_size"] = max(8, min(22,
                                         self.settings["font_size"] + step))
        self.apply_theme()
        self.render_all()
        save_settings(self.settings)

    # --- models / keys / cost -----------------------------------------------

    def paint_models(self):
        self.model_btn.configure(
            text=f"Model: {pricing.label_for(self.settings['claude_model'])}")

    def select_model(self, model_id):
        self.settings["claude_model"] = model_id
        self.paint_models()
        save_settings(self.settings)
        self.say(f"model: {pricing.label_for(model_id)}")

    def connect_claude(self):
        try:
            if not keys.current("ANTHROPIC_API_KEY"):
                raise RuntimeError("no key")
            self.client = anthropic.Anthropic()
        except Exception:
            self.client = None
        ready = self.client is not None
        self.ask_btn.configure(state="normal" if ready else "disabled")
        self.say("ready" if ready
                 else "no Anthropic key - click Keys to add one")
        return ready

    def edit_keys(self):
        KeyDialog(self)

    def update_cost(self):
        self.cost_lbl.configure(
            text=f"session {pricing.money(self.claude_meter.session)}  ·  "
                 f"all time {pricing.money(self.claude_meter.total)}")

    def show_cost_breakdown(self):
        self.say(f"Claude {pricing.money(self.claude_meter.session)} "
                 f"({self.claude_meter.detail()})  ·  "
                 f"right-click the figures to reset the session")

    def reset_session_cost(self):
        self.claude_meter.session = 0.0
        self.update_cost()
        self.say("session cost reset - the all-time figure is kept")

    def record_claude_usage(self, stream):
        try:
            usage = stream.current_message_snapshot.usage
        except Exception:
            return
        self.claude_meter.add(usage, self.settings["claude_model"])
        self.settings["spend_claude"] = self.claude_meter.total
        self.root.after(0, self.update_cost)

    # --- rendering -----------------------------------------------------------

    def insert_rich(self, line, tag):
        for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", line)):
            if part:
                self.out.insert("end", part,
                                (tag, "bold") if i % 2 else (tag,))

    def insert_answer(self, text):
        for block in re.split(r"\n\s*\n", text.strip()):
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            for n, line in enumerate(lines):
                last = n == len(lines) - 1
                if line.startswith("#"):
                    self.insert_rich(line.lstrip("# ").strip(), "head")
                elif re.match(r"^([-*•]|\d+[.)])\s+", line):
                    body = re.sub(r"^([-*•]|\d+[.)])\s+", "", line)
                    self.out.insert("end", "•  ", ("item",))
                    self.insert_rich(body, "item")
                else:
                    self.insert_rich(line, "para" if last else "")
                self.out.insert("end", "\n")

    def render_all(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        for n, (stamp, text) in enumerate(self.answers):
            label = stamp if n else f"{stamp}   latest"
            self.out.insert("end", label + "\n", ("stamp",))
            self.insert_answer(text)
        if not self.answers:
            self.insert_answer(
                "Click **Ask about a region** and drag a box around a "
                "question on screen.\n\n"
                "The answer streams in here. You bring your own Anthropic "
                "key - click **Keys** to add it.")
        self.out.configure(state="disabled")
        self.out.see("1.0")
        self.copy_btn.configure(state="normal" if self.answers else "disabled")

    def add_answer(self, text):
        self.answer = text
        self.answers.insert(0, (time.strftime("%H:%M"), text.strip()))
        del self.answers[HISTORY:]
        self.render_all()

    def clear_screen(self):
        self.answers = []
        self.answer = ""
        self.render_all()
        self.say("cleared")

    def show(self, text):
        self.answer = text
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.see("end")
        self.out.configure(state="disabled")

    def append(self, chunk):
        self.answer += chunk
        self.out.configure(state="normal")
        self.out.insert("end", chunk)
        self.out.see("end")
        self.out.configure(state="disabled")

    # --- small helpers -------------------------------------------------------

    def say(self, text):
        self.status.configure(text=text)

    def copy(self):
        if not self.answer:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.answer)
        self.say("copied - paste it into the chat")

    def capture(self, bbox):
        self.root.withdraw()
        self.root.update()
        time.sleep(0.18)
        try:
            return grab(bbox)
        finally:
            self.root.deiconify()

    def pick_region(self, then):
        self.root.withdraw()
        self.root.update()
        time.sleep(0.12)

        def done(bbox):
            self.root.deiconify()
            if bbox is None:
                self.say("cancelled")
            else:
                then(bbox)

        RegionPicker(self.root, self.theme["accent"], done)

    def stop_everything(self):
        self.cancelled.set()
        self.say("stopped")

    # --- ask -----------------------------------------------------------------

    def ask(self):
        if self.busy:
            return
        self.pick_region(lambda bbox: self.send(self.capture(bbox)))

    def image_blocks(self, img):
        return [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": to_png_b64(img)}},
            {"type": "text", "text":
                "Here is the region of our conversation. Answer it."},
        ]

    def send(self, img):
        if self.busy or self.client is None:
            return
        self.cancelled.clear()
        self.busy = True
        self.say("thinking...")
        self.ask_btn.configure(state="disabled")
        blocks = self.image_blocks(img)
        threading.Thread(target=self.stream, args=(blocks,),
                         daemon=True).start()

    def stream(self, blocks):
        first = True
        buffer = ""
        model = pricing.claude_model(self.settings["claude_model"])
        extra = {"output_config": {"effort": EFFORT}} if model["effort"] else {}
        try:
            with self.client.messages.stream(
                model=model["id"],
                max_tokens=1500,
                system=SYSTEM,
                messages=[{"role": "user", "content": blocks}],
                **extra,
            ) as stream:
                for chunk in stream.text_stream:
                    if self.cancelled.is_set():
                        break
                    buffer += chunk
                    if first:
                        self.root.after(0, self.show, buffer)
                        first = False
                    else:
                        self.root.after(0, self.append, chunk)
                self.record_claude_usage(stream)

            if buffer.strip() and not self.cancelled.is_set():
                self.root.after(0, self.add_answer, buffer)
                self.root.after(0, self.say, "ready")
            elif self.cancelled.is_set():
                self.root.after(0, self.say, "stopped")
            else:
                self.root.after(0, self.say, "ready")
        except anthropic.RateLimitError:
            self.root.after(0, self.say, "rate limited - wait a moment")
        except anthropic.APIStatusError as e:
            self.root.after(0, self.say, f"API error {e.status_code}")
        except anthropic.APIConnectionError:
            self.root.after(0, self.say, "connection failed - check network")
        except Exception as e:
            self.root.after(0, self.say, f"error: {e}")
        finally:
            self.busy = False
            self.root.after(0, self.ask_btn.configure, {"state": "normal"})

    # --- shutdown ------------------------------------------------------------

    def close(self):
        self.cancelled.set()
        try:
            self.settings["geometry"] = self.root.winfo_geometry()
            self.settings["spend_claude"] = self.claude_meter.total
            save_settings(self.settings)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    Chair(root)
    root.mainloop()


if __name__ == "__main__":
    main()
