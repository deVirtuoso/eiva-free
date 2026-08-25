"""
This machine's code, and somewhere to leave a licence key for Pro to find.

The free edition never checks a licence - it has nothing to unlock. What it
does have is the two things that make buying Pro seamless:

  * the machine code, which the buyer has to give at checkout because a Pro
    licence is issued for one computer. Working it out here means they never
    have to go and find it;

  * a place to put the key that comes back. Pro reads its licence from
    %APPDATA%\\EIVA\\license.key, so a key pasted into the free window before
    Pro is even downloaded is already waiting when Pro first starts, and the
    activation screen never appears.

The machine code must be computed exactly as pro/licensing.py computes it -
same salt, same inputs, same truncation - or the licence the seller issues
will name a different computer to the one that asked for it. That is why the
constants below are spelled out rather than imported: the two editions ship
separately, and this file has to stand on its own.

Nothing here verifies a signature. Verifying needs the Ed25519 public key and
the cryptography library, and it is Pro - compiled, and the only thing with
something to lose - that does it properly. What this does is the cheap,
obvious checks: is this a licence key at all, and is it for this machine? Those
catch a bad paste or a key issued for the buyer's other PC straight away,
rather than after a download.
"""

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path

# Must match pro/licensing.py exactly.
PRODUCT = "eiva-pro"
APP_NAME = "EIVA"
LICENSE_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
LICENSE_FILE = LICENSE_DIR / "license.key"


def _machine_guid():
    """The Windows install's own GUID, from the registry. Stable across
    reboots and unique per installation."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            return str(val).strip()
    except Exception:
        return ""


def _volume_serial():
    """A secondary signal: the C: volume serial number. Folded in so that a
    cloned machine that somehow shares a GUID still differs."""
    try:
        vol = ctypes.c_uint()
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"), None, 0, ctypes.byref(vol),
            None, None, None, 0)
        return str(vol.value)
    except Exception:
        return ""


def machine_id():
    """A short, stable code for this machine. Hashed so it reveals nothing
    about the hardware, and salted with the product name so the same machine
    yields a different code for a different product."""
    raw = f"{PRODUCT}|{_machine_guid()}|{_volume_serial()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()[:16]


def machine_code_display(mid=None):
    """The machine code in readable groups, for showing the buyer."""
    mid = mid or machine_id()
    return "-".join(mid[i:i + 4] for i in range(0, len(mid), 4))


def _payload(key_text):
    """The claims inside a licence key, without checking who signed them."""
    body, _, sig = key_text.strip().replace("\n", "").partition(".")
    if not body or not sig:
        raise ValueError("not a licence key")
    pad = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + pad).decode("utf-8"))


def stage(key_text):
    """Put a licence key where Pro will look for it. Returns (ok, message).

    The message is shown as-is, so it says what happens next rather than only
    what happened."""
    key_text = (key_text or "").strip()
    if not key_text:
        return False, "Paste the licence key you were sent first."
    try:
        claims = _payload(key_text)
    except Exception:
        return False, ("That doesn't look like a licence key. Copy the whole "
                       "line you were sent, including the full stop in the "
                       "middle.")
    if claims.get("p") != PRODUCT:
        return False, "That key is for a different product."
    if claims.get("m") != machine_id():
        return False, ("That key was issued for a different computer. This "
                       f"one is {machine_code_display()} - send that code on "
                       "and it can be reissued at no charge.")
    try:
        LICENSE_DIR.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(key_text, encoding="utf-8")
    except Exception as e:
        return False, f"The key is for this computer, but couldn't be saved: {e}"
    return True, ("Saved. Download EIVA Pro and it will start already "
                  "activated - there is nothing else to enter.")


def staged():
    """True if a licence key is already sitting where Pro will find it."""
    try:
        return bool(LICENSE_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return False
