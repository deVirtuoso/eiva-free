"""
EIVA - Free edition.

A small always-on-top window that reads a region of your screen and answers
what it finds there, in text.

  ASK   drag a box around a question -> the answer streams into the window.

That is the whole of the free edition, on purpose: select text, get a text
answer. Watch mode, listening, spoken answers, the live voice conversation and
reference material are the Pro edition - see the Unlock link at the bottom.

You bring your own API key: Anthropic, OpenAI or Google, whichever you
already have. Any of the three can read the screen and answer it - pick the
model from the Model menu. The app never ships with a key, never writes one
next to itself, and never sends anything anywhere except your own question, to
the provider whose model you picked, on your own key.

Font size, colour scheme, window position and the chosen model are remembered
between runs (settings.json, next to this file). No OCR - the screenshot goes
straight to the model, which reads it.
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

import catalog
import engine
import keys
import machine
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

BODY_FAMILY = "Corbel"
LABEL_FAMILY = "Consolas"

# "Unlock Pro" goes straight to the checkout. The page in between only ever
# lost people, and everything they need to read is on the Unlock window itself.
BUY_URL = "https://buy.stripe.com/3cI14p3UV8CGfwM1O6gw001"
DOWNLOAD_URL = "https://eiva.worldwidechoices.com/#download"

APP_DIR = Path(__file__).parent
ICON_ICO = APP_DIR / "assets" / "icon.ico"

SETTINGS_FILE = APP_DIR / "settings.json"
# No geometry until the window has been built and measured - see
# fit_window. An empty string here is what "never been run" looks like.
DEFAULTS = {"font_size": 11, "theme": "Light", "geometry": "",
            "answer_model": MODEL, "spend": 0.0}

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
    # Settings written before there was more than one provider named the two
    # fields after the only one there was. Carried over rather than reset, so
    # nobody loses their running total or their chosen model to an upgrade.
    if "answer_model" not in data and data.get("claude_model"):
        data["answer_model"] = data["claude_model"]
    if not data.get("spend") and data.get("spend_claude"):
        data["spend"] = data["spend_claude"]
    for gone in ("claude_model", "spend_claude"):
        data.pop(gone, None)
    # Not "is it one of ours": the menu now offers models discovered from the
    # provider, and one of those chosen last week must survive a restart.
    # Only an id nothing could route falls back.
    if not pricing.known_shape(data.get("answer_model")):
        data["answer_model"] = MODEL
    if data.get("theme") not in THEMES:
        data["theme"] = "Light"
    try:
        data["spend"] = float(data["spend"])
    except Exception:
        data["spend"] = 0.0
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
    """A small modal for entering an API key - one row per provider.

    Any of the three can answer the screen, so the dialog never insists on a
    particular one. It opens on whichever the window was about to use, says in
    a line why it is asking, and leaves the others there for anyone who would
    rather switch. Keys are stored in the Windows environment through
    keys.save, never next to the script."""

    def __init__(self, chair, focus=None, because=""):
        self.chair = chair
        self.rows = {}
        t = chair.theme

        self.win = tk.Toplevel(chair.root)
        self.win.title("API keys")
        self.win.configure(bg=t["bg"])
        self.win.transient(chair.root)
        self.win.resizable(False, False)
        # The main window is always-on-top; without this the dialog opens
        # behind it and looks like nothing happened.
        self.win.attributes("-topmost", True)
        try:
            self.win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        head = because or ("Any one of these can read the screen and answer "
                           "it. You only need the key you already have.")
        tk.Label(self.win, text=head, font=(BODY_FAMILY, 10), bg=t["bg"],
                 fg=t["text"], justify="left", anchor="w", wraplength=430
                 ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self.win, font=(LABEL_FAMILY, 8), bg=t["bg"], fg=t["dim"],
                 justify="left", anchor="w",
                 text=("You are billed by the provider directly. Keys are "
                       "stored in your Windows\naccount, not in this folder, "
                       "and take effect straight away.")
                 ).pack(fill="x", padx=16, pady=(0, 10))

        for provider in keys.PROVIDERS:
            self.add_row(provider, highlight=(provider["id"] == focus))

        self.note = tk.Label(self.win, text="", font=(LABEL_FAMILY, 8),
                             bg=t["bg"], fg=t["dim"], anchor="w",
                             justify="left", wraplength=430)
        self.note.pack(fill="x", padx=16, pady=(2, 6))

        self._btn(self.win, "Done", self.close).pack(anchor="e", padx=16,
                                                     pady=(0, 14))
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        first = focus or keys.PROVIDERS[0]["id"]
        self.rows[first]["entry"].focus_set()

    def add_row(self, provider, highlight=False):
        t = self.chair.theme
        frame = tk.Frame(self.win, bg=t["bg"])
        frame.pack(fill="x", padx=16, pady=(0, 10))

        title = f"{provider['label']} - {provider['note']}"
        tk.Label(frame, text=title, font=(BODY_FAMILY, 10,
                                          "bold" if highlight else "normal"),
                 bg=t["bg"], fg=t["text"], anchor="w", justify="left",
                 wraplength=430).pack(fill="x")

        state = tk.Label(frame, text=self.state_text(provider),
                         font=(LABEL_FAMILY, 8), bg=t["bg"], fg=t["dim"],
                         anchor="w")
        state.pack(fill="x")

        row = tk.Frame(frame, bg=t["bg"])
        row.pack(fill="x", pady=(4, 0))
        entry = tk.Entry(row, width=34, show="*", font=(LABEL_FAMILY, 10),
                         relief="flat", bg=t["panel"], fg=t["text"],
                         insertbackground=t["text"])
        entry.pack(side="left", fill="x", expand=True, ipady=3)
        entry.bind("<Return>", lambda e, p=provider: self.save(p))

        self._btn(row, "Show", lambda e=entry: e.configure(
            show="" if e.cget("show") else "*")).pack(side="left", padx=(6, 0))
        self._btn(row, "Save",
                  lambda p=provider: self.save(p)).pack(side="left", padx=(4, 0))
        self._btn(row, "Clear",
                  lambda p=provider: self.clear(p)).pack(side="left", padx=(4, 0))

        tk.Label(frame, text=f"get one at {provider['where']}",
                 font=(LABEL_FAMILY, 8), bg=t["bg"], fg=t["dim"], anchor="w"
                 ).pack(fill="x", pady=(2, 0))

        self.rows[provider["id"]] = {"entry": entry, "state": state}

    def _btn(self, parent, text, cmd):
        t = self.chair.theme
        return tk.Button(parent, text=text, command=cmd, relief="flat",
                         font=(LABEL_FAMILY, 9), bg=t["btn"],
                         fg=t["btntext"], activebackground=t["sel"],
                         activeforeground=t["text"], padx=10, pady=3,
                         cursor="hand2")

    @staticmethod
    def state_text(provider):
        return "currently: " + keys.masked(keys.current(provider["env"]))

    def save(self, provider):
        row = self.rows[provider["id"]]
        typed = row["entry"].get().strip()
        wrong = keys.looks_wrong(provider, typed)
        if wrong:
            self.note.configure(text=f"{provider['label']}: not saved, {wrong}")
            return
        ok, message = keys.save(provider["env"], typed)
        if ok and keys.unfamiliar(provider, typed):
            message += ("  (unusual prefix for this provider - worth a look "
                        "if it doesn't work)")
        row["entry"].delete(0, "end")
        row["entry"].configure(show="*")
        row["state"].configure(text=self.state_text(provider))
        self.note.configure(text=f"{provider['label']}: {message}")
        # A key is only worth anything once the window knows it is there: the
        # model menu marks what is reachable, and the status line stops
        # complaining.
        self.chair.on_keys_changed(provider["id"])

    def clear(self, provider):
        ok, message = keys.forget(provider["env"])
        self.rows[provider["id"]]["state"].configure(
            text=self.state_text(provider))
        self.note.configure(text=f"{provider['label']}: {message}")
        self.chair.on_keys_changed(None)

    def close(self):
        self.win.destroy()


# --- the unlock window -------------------------------------------------------

class UnlockDialog:
    """What "Unlock Pro" opens.

    A Pro licence is issued for one computer, so the buyer has to give their
    machine code at checkout. Making them go and find it is where this kind of
    purchase falls over, so the code is worked out here, shown in full, and put
    on the clipboard before the window is even on screen.

    The key that comes back can be pasted here rather than waiting for the Pro
    download: it is written to the same place Pro reads it from, so Pro starts
    activated and never shows its activation screen at all."""

    def __init__(self, chair):
        self.chair = chair
        t = chair.theme
        self.code = machine.machine_code_display()

        self.win = tk.Toplevel(chair.root)
        self.win.title("Unlock EIVA Pro")
        self.win.configure(bg=t["bg"])
        self.win.transient(chair.root)
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        try:
            self.win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        tk.Label(self.win, text="EIVA Pro - one-off \u00a31.99, one computer",
                 font=(BODY_FAMILY, 12, "bold"), bg=t["bg"], fg=t["text"],
                 anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self.win, anchor="w", justify="left", wraplength=430,
                 font=(BODY_FAMILY, 10), bg=t["bg"], fg=t["text"],
                 text="Watch, Listen, spoken answers, live voice and "
                      "reference files."
                 ).pack(fill="x", padx=16, pady=(0, 12))

        # --- the machine code, already copied --------------------------------
        box = tk.Frame(self.win, bg=t["panel"])
        box.pack(fill="x", padx=16)
        tk.Label(box, text="YOUR MACHINE CODE", font=(LABEL_FAMILY, 8, "bold"),
                 bg=t["panel"], fg=t["dim"], anchor="w"
                 ).pack(fill="x", padx=12, pady=(10, 0))
        # An Entry rather than a Label: it can be selected and re-copied by
        # hand, which is the first thing anyone tries when a paste goes astray.
        self.code_entry = tk.Entry(box, font=(LABEL_FAMILY, 14, "bold"),
                                   relief="flat", justify="left",
                                   bg=t["panel"], fg=t["accent"],
                                   readonlybackground=t["panel"],
                                   width=len(self.code) + 1)
        self.code_entry.insert(0, self.code)
        self.code_entry.configure(state="readonly")
        self.code_entry.pack(side="left", padx=12, pady=(2, 10))
        self._btn(box, "Copy again", self.copy_code).pack(side="right", padx=12)

        tk.Label(self.win, anchor="w", justify="left", wraplength=430,
                 font=(BODY_FAMILY, 10), bg=t["bg"], fg=t["text"],
                 text="Copied to your clipboard. Paste it into the "
                      "\u201cMachine code\u201d box on the\ncheckout page - "
                      "your licence is issued for this computer only."
                 ).pack(fill="x", padx=16, pady=(10, 10))

        self._btn(self.win, "Open the checkout again", self.buy).pack(
            fill="x", padx=16)

        # --- the key that comes back -----------------------------------------
        tk.Label(self.win, text="LICENCE KEY", font=(LABEL_FAMILY, 8, "bold"),
                 bg=t["bg"], fg=t["dim"], anchor="w"
                 ).pack(fill="x", padx=16, pady=(16, 2))
        tk.Label(self.win, anchor="w", justify="left", wraplength=430,
                 font=(LABEL_FAMILY, 8), bg=t["bg"], fg=t["dim"],
                 text="Already been sent one? Paste it here and Pro will "
                      "start activated."
                 ).pack(fill="x", padx=16)
        self.entry = tk.Text(self.win, height=3, width=1, wrap="char",
                             font=(LABEL_FAMILY, 9), relief="flat",
                             bg=t["panel"], fg=t["text"],
                             insertbackground=t["text"])
        self.entry.pack(fill="x", padx=16, pady=(4, 6))

        row = tk.Frame(self.win, bg=t["bg"])
        row.pack(fill="x", padx=16)
        self._btn(row, "Activate", self.activate).pack(side="left")
        self._btn(row, "Download Pro", self.download).pack(side="left",
                                                           padx=(6, 0))
        self._btn(row, "Close", self.close).pack(side="right")

        self.note = tk.Label(self.win, text="", font=(LABEL_FAMILY, 8),
                             bg=t["bg"], fg=t["dim"], anchor="w",
                             justify="left", wraplength=430)
        self.note.pack(fill="x", padx=16, pady=(8, 14))

        if machine.staged():
            self.note.configure(
                text="A licence for this computer is already saved. Pro will "
                     "start activated.", fg=t["accent"])

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        self.copy_code()
        self.entry.focus_set()

    def _btn(self, parent, text, cmd):
        t = self.chair.theme
        return tk.Button(parent, text=text, command=cmd, relief="flat",
                         font=(LABEL_FAMILY, 9), bg=t["btn"],
                         fg=t["btntext"], activebackground=t["sel"],
                         activeforeground=t["text"], padx=10, pady=4,
                         cursor="hand2")

    def copy_code(self):
        self.chair.root.clipboard_clear()
        self.chair.root.clipboard_append(self.code)
        self.chair.say(f"machine code {self.code} copied - paste it at checkout")

    def buy(self):
        webbrowser.open(BUY_URL)

    def download(self):
        webbrowser.open(DOWNLOAD_URL)

    def activate(self):
        ok, message = machine.stage(self.entry.get("1.0", "end"))
        self.note.configure(text=message,
                            fg=self.chair.theme["accent"] if ok else "#B00020")
        if ok:
            self.entry.delete("1.0", "end")

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



def work_area(root):
    """The desktop minus the taskbar, in real pixels.

    winfo_screenwidth counts the strip the taskbar sits on, and a window
    sized to that cannot show its own bottom row.
    """
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    box = RECT()
    try:
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(box), 0):
            return box.right - box.left, box.bottom - box.top
    except Exception:
        pass
    return root.winfo_screenwidth(), root.winfo_screenheight() - 48


def fit_window(root, saved, roomy=0):
    """Size the window so that every control fits, then honour what was saved.

    Tk can only say how much room the controls need once they exist, so this
    runs after the window is built. The answer panel asks for almost nothing
    and stretches instead, so what comes back is the size of the controls
    themselves - correct at any display scale, font size, or length of button
    label, with no hand-kept number to fall out of step with the layout.

    That size becomes the floor: the smallest the window can be dragged to,
    and, plus roomy pixels of answer panel, what a first run opens at. A size
    saved from a previous run is kept when it is larger, and where the window
    was put is kept either way.
    """
    root.update_idletasks()
    limit_w, limit_h = work_area(root)
    need_w = min(root.winfo_reqwidth(), limit_w)
    need_h = min(root.winfo_reqheight(), limit_h)
    root.minsize(need_w, need_h)

    # Nothing saved means a first run: open with room for a few answers
    # rather than at the bare minimum the controls happen to need.
    want_w, want_h, where = need_w, min(need_h + roomy, limit_h), ""
    was = re.match(r"(\d+)x(\d+)(.*)", str(saved or ""))
    if was:
        want_w = min(max(int(was[1]), need_w), limit_w)
        want_h = min(max(int(was[2]), need_h), limit_h)
        where = was[3]
    root.geometry(f"{want_w}x{want_h}{where}")
    # Goes to eiva.log when there is no console. It is the first thing to look
    # at when someone says the window came up the wrong size on their machine.
    print(f"window: controls need {need_w}x{need_h}, opening {want_w}x{want_h}")

# --- the window --------------------------------------------------------------

class Chair:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.theme = THEMES[self.settings["theme"]]
        self.meter = pricing.AnswerMeter(self.settings["spend"])
        self.busy = False
        self.cancelled = threading.Event()
        self.answers = []
        self.answer = ""

        root.title("EIVA - Free")
        root.attributes("-topmost", True)
        try:
            root.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        self._build()
        self.apply_theme()
        self.prefer_a_model_we_can_run()
        self.refresh_ready()
        self.render_all()
        # Quietly, and only when the cached list has gone stale, so the window
        # is never waiting on a round trip to draw itself.
        self.refresh_models(quiet=True)
        # Last, with every control in place and its final text set.
        body = tkfont.Font(family=BODY_FAMILY,
                           size=self.settings["font_size"])
        fit_window(root, self.settings["geometry"],
                   roomy=body.metrics("linespace") * 8)

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
        # Filled in by paint_models, which runs again whenever a key
        # changes: which models are reachable is not fixed at build time.
        self.model_menu = tk.Menu(self.model_btn, tearoff=0)
        self.model_btn.configure(menu=self.model_menu)
        self.keys_btn = self._btn(self.mrow, "Keys", self.edit_keys)
        self.keys_btn.pack(side="right")

        # output area. width/height are deliberately tiny: a Text widget asks
        # for 80x24 characters by default, which would set the whole window
        # size and squeeze the rows below it out. It stretches to fill instead.
        self.out = tk.Text(self.root, wrap="word", relief="flat",
                           padx=12, pady=10, font=(BODY_FAMILY, fs),
                           state="disabled", cursor="arrow",
                           width=1, height=5)
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
                               font=(LABEL_FAMILY, 8), width=1)
        self.status.pack(fill="x", padx=10, pady=(2, 0))

        self.upsell = tk.Label(
            self.root, cursor="hand2", anchor="w", font=(LABEL_FAMILY, 8),
            text="✦  Watch · Listen · Voice · Reference "
                 "files  →  Unlock Pro")
        self.upsell.pack(fill="x", padx=10, pady=(0, 8))
        self.upsell.bind("<Button-1>", lambda e: self.unlock_pro())

        self.paint_models()

    def _btn(self, parent, text, cmd, accent=False):
        """accent marks the primary action, with weight rather than colour.

        It used to fill the button with the theme's accent and write on it in
        white, which came out white-on-yellow in Contrast, and, whenever the
        button was disabled, in whatever grey tk chose - unreadable on the
        teal. A bold label says "this is the one" in every theme and in every
        state, and cannot collide with a foreground colour we don't set."""
        return tk.Button(parent, text=text, command=cmd, relief="flat",
                         font=(LABEL_FAMILY, 9,
                               "bold" if accent else "normal"),
                         padx=8, pady=3, cursor="hand2",
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

        # Every button, the primary one included, takes the same colours.
        # disabledforeground is set explicitly because tk's own default grey
        # is chosen without reference to the background we just gave it.
        for b in (self.ask_btn, self.copy_btn, self.clear_btn, self.stop_btn,
                  self.keys_btn, self.theme_btn):
            b.configure(bg=t["btn"], fg=t["btntext"],
                        activebackground=t["sel"], activeforeground=t["text"],
                        disabledforeground=t["dim"])
        for child in self.brow.winfo_children():
            if isinstance(child, tk.Button):
                child.configure(bg=t["btn"], fg=t["btntext"],
                                activebackground=t["sel"],
                                disabledforeground=t["dim"])

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
        """Redraw the model menu as well as its button.

        The menu is rebuilt rather than built once because whether a model can
        be reached is not a fixed property of the model: it turns on a key that
        can be added, or cleared, while the window is open. Models with no key
        are still listed and still clickable - picking one is a perfectly good
        way to say "I want to use that", and it opens the key dialog."""
        self.model_menu.delete(0, "end")
        for provider, label in pricing.PROVIDER_LABELS.items():
            models = catalog.menu_for(provider)
            if not models:
                continue
            if self.model_menu.index("end") is not None:
                self.model_menu.add_separator()
            ready = keys.have(provider)
            self.model_menu.add_command(
                label=label + ("" if ready else "   (no key yet)"),
                state="disabled")
            for m in models:
                # A tilde on a model we were not shipped with: it is offered
                # because the provider says this key can reach it, but the
                # rate is borrowed from its nearest relative, and a meter
                # reading is only as good as the rate behind it.
                mark = "  ~" if m.get("estimated") else ""
                self.model_menu.add_command(
                    label="   " + m["label"] + mark,
                    command=lambda mid=m["id"]: self.select_model(mid))

        self.model_menu.add_separator()
        self.model_menu.add_command(label="Refresh model list",
                                    command=self.refresh_models)
        self.model_btn.configure(
            text=f"Model: {self.label_of(self.settings['answer_model'])}")

    def label_of(self, model_id):
        """The short name for a model, discovered ones included."""
        return catalog.card_for(model_id).get("label", model_id)

    def refresh_models(self, quiet=False):
        """Ask each provider we hold a key for what that key can reach now.

        A one-off purchase has no update channel: no subscription pushes a new
        model list, and there is no server of ours to ask. So the app asks the
        provider directly, on the user's own key - nothing reaches us - and
        caches the answer for a week. It is the only thing that keeps a menu
        written today from being wrong in a year, and it is not hypothetical:
        the Gemini ids this app first shipped with were retired within months.
        """
        wanted = [p for p in pricing.PROVIDER_LABELS
                  if keys.have(p) and not engine.sdk_missing(p)]
        if not wanted:
            return
        if quiet:
            wanted = [p for p in wanted if catalog.stale(p)]
            if not wanted:
                return
        else:
            self.say("checking which models your keys can reach...")

        def done(notes):
            # Back to the main thread: the menu is a widget, and this is not.
            self.root.after(0, self.models_refreshed, notes, quiet)

        catalog.refresh_in_background(wanted, done)

    def models_refreshed(self, notes, quiet):
        self.paint_models()
        gone = [mid for p in pricing.PROVIDER_LABELS
                for mid in catalog.retired(p)]
        if self.settings["answer_model"] in gone:
            # The model in use has been retired under us. Move to something
            # that works rather than let the next question fail.
            provider = pricing.provider_of(self.settings["answer_model"])
            replacement = catalog.middle_of_the_range(provider)
            if replacement:
                self.settings["answer_model"] = replacement["id"]
                self.paint_models()
                self.say(f"that model was retired - now on "
                         f"{self.label_of(self.settings['answer_model'])}")
                return
        if not quiet:
            self.say("model list updated  ·  " + ", ".join(notes))

    def select_model(self, model_id):
        self.settings["answer_model"] = model_id
        self.paint_models()
        save_settings(self.settings)
        card = catalog.card_for(model_id)
        note = "  (rate estimated)" if card.get("estimated") else ""
        self.say(f"model: {self.label_of(model_id)}{note}")
        # Picking a model whose key is missing is the clearest possible signal
        # that the key is wanted, so ask for it there and then rather than
        # waiting for the next question to fail.
        self.check_ready(prompt=True)

    def prefer_a_model_we_can_run(self):
        """At start-up only, move off a provider with no key if another is
        ready to go. Someone who has an OpenAI key and no Anthropic one should
        not have to find the Model menu before their first question works. An
        explicit choice made later is never second-guessed - this runs once.

        "Ready" means a key *and* the client library: switching to a provider
        whose SDK is not installed would trade one dead end for another."""
        if keys.have(pricing.provider_of(self.settings["answer_model"])):
            return
        for provider in pricing.PROVIDER_LABELS:
            if not keys.have(provider) or engine.sdk_missing(provider):
                continue
            pick = catalog.middle_of_the_range(provider)
            if pick:
                self.settings["answer_model"] = pick["id"]
                return

    def check_ready(self, prompt=False):
        """Can the chosen model actually be called? When it cannot, say why -
        and, if we are here because the user asked for something, open the
        dialog that fixes it.

        This is the whole answer to a button that used to do nothing at all.
        Nothing is ever disabled for want of a key: the click is what tells us
        the key is wanted."""
        model = catalog.card_for(self.settings["answer_model"])
        provider = pricing.provider_of(model["id"])
        label = pricing.PROVIDER_LABELS[provider]

        missing_sdk = engine.sdk_missing(provider)
        if missing_sdk:
            self.say(f"{label}: {missing_sdk}")
            return False

        if keys.have(provider):
            self.say("ready")
            return True

        self.say(f"no {label} key yet - click Keys, or pick another model")
        if prompt:
            KeyDialog(self, focus=provider, because=(
                f"{model['label']} needs your {label} key before it can "
                f"answer anything. Paste it below - or close this and pick a "
                f"model from a provider you already have a key for."))
        return False

    def refresh_ready(self):
        self.paint_models()
        return self.check_ready()

    def on_keys_changed(self, provider_id):
        """Called by the key dialog after a save or a clear. A key that has
        just been entered is almost certainly the one the user wants to use,
        so the model follows it."""
        if provider_id and keys.have(provider_id):
            if pricing.provider_of(self.settings["answer_model"]) != provider_id:
                pick = catalog.middle_of_the_range(provider_id)
                if pick:
                    self.settings["answer_model"] = pick["id"]
                    save_settings(self.settings)
        self.refresh_ready()
        # A key that has only just arrived has never been asked what it can
        # reach.
        self.refresh_models(quiet=True)

    def edit_keys(self):
        KeyDialog(self)

    def update_cost(self):
        self.cost_lbl.configure(
            text=f"session {pricing.money(self.meter.session)}  ·  "
                 f"all time {pricing.money(self.meter.total)}")

    def show_cost_breakdown(self):
        self.say(f"{pricing.money(self.meter.session)} this session "
                 f"({self.meter.detail()})  ·  "
                 f"right-click the figures to reset the session")

    def reset_session_cost(self):
        self.meter.session = 0.0
        self.update_cost()
        self.say("session cost reset - the all-time figure is kept")

    def record_usage(self, usage, model_id):
        """Price a finished call against the model that served it, whichever
        provider that was."""
        self.meter.add(usage, model_id)
        self.settings["spend"] = self.meter.total
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
                "The answer streams in here. You bring your own API key - "
                "**Anthropic**, **OpenAI** or **Google**, whichever you "
                "already have. Click **Keys** to add one, and **Model** to "
                "pick what answers.")
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

    def unlock_pro(self):
        """The Unlock link. Opens the checkout, because that is what it says it
        does, and the window that carries the machine code the checkout is
        about to ask for - already on the clipboard."""
        webbrowser.open(BUY_URL)
        UnlockDialog(self)

    def ask(self):
        if self.busy:
            return
        if not self.check_ready(prompt=True):
            return
        self.pick_region(lambda bbox: self.send(self.capture(bbox)))

    def question_parts(self, img):
        """The question, in the provider-neutral shape engine.py takes."""
        return [
            {"image": to_png_b64(img)},
            {"text": "Here is the region of our conversation. Answer it."},
        ]

    def send(self, img):
        if self.busy:
            return
        self.cancelled.clear()
        self.busy = True
        self.say("thinking...")
        self.ask_btn.configure(state="disabled")
        parts = self.question_parts(img)
        threading.Thread(target=self.stream, args=(parts,),
                         daemon=True).start()

    def stream(self, parts):
        model = catalog.card_for(self.settings["answer_model"])
        collected = []
        started = False

        def on_chunk(piece):
            """Draw one piece of the answer. Returning True ends the stream,
            which is how Stop gets out without waiting for the rest."""
            nonlocal started
            if self.cancelled.is_set():
                return True
            collected.append(piece)
            if not started:
                self.root.after(0, self.show, "".join(collected))
                started = True
            else:
                self.root.after(0, self.append, piece)
            return False

        try:
            usage = engine.stream_answer(model, [{"text": SYSTEM}], parts,
                                         on_chunk, self.cancelled)
            # Leaving early does not make the tokens free, so this runs on
            # every path out of the call.
            self.record_usage(usage, model["id"])

            answer = "".join(collected)
            if self.cancelled.is_set():
                self.root.after(0, self.say, "stopped")
            elif answer.strip():
                self.root.after(0, self.add_answer, answer)
                self.root.after(0, self.say, "ready")
            else:
                self.root.after(0, self.say, "ready")
        except engine.EngineError as e:
            self.root.after(0, self.say, str(e))
            # "not available on this key" means our list is out of date. Go
            # and find out what is available, rather than leaving the user to
            # wonder why a model in the menu does not work.
            if "not available" in str(e):
                self.root.after(0, self.refresh_models)
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
            self.settings["spend"] = self.meter.total
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
