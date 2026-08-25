"""
Where the API keys live, and how the window changes them.

A key is never written next to the script. A plain-text key in the project
folder is a key that gets committed by accident, and no .gitignore rule is
worth relying on for that. It goes where the setup instructions already put
it - the user's own Windows environment, through setx, which survives a
reboot and is there for every terminal afterwards.

setx only reaches processes started after it, so the key is also set on this
process as it is saved. The change therefore takes effect on the very next
question and still holds tomorrow, with no restart in between.

The free edition answers the screen, and any of the three providers below can
do that - you bring whichever key you already have. One is enough; a second is
only worth adding if you want to switch between them. The app never ships with
a key and never phones one home.
"""

import os
import subprocess

# Everything the dialog needs to describe a key it has never seen. The
# prefixes are the ones each provider has issued so far - Google alone has
# used two - so a key that matches none of them is remarked on rather than
# refused. A prefix list goes out of date; a working key should not be blocked
# by ours being old.
PROVIDERS = [
    {"env": "ANTHROPIC_API_KEY",
     "id": "anthropic",
     "label": "Anthropic (Claude)",
     "note": "answers the screen",
     "starts": ("sk-ant-",),
     "where": "console.anthropic.com -> API keys"},
    {"env": "OPENAI_API_KEY",
     "id": "openai",
     "label": "OpenAI (GPT)",
     "note": "answers the screen",
     "starts": ("sk-",),
     "where": "platform.openai.com/api-keys"},
    {"env": "GEMINI_API_KEY",
     "id": "gemini",
     "label": "Google (Gemini)",
     "note": "answers the screen",
     "starts": ("AIza", "AQ."),
     "where": "aistudio.google.com/apikey"},
]

BY_ID = {p["id"]: p for p in PROVIDERS}

# setx truncates silently past this, which would leave a key that looks saved
# and fails on use. Better to refuse it.
MAX_LENGTH = 1024


def current(env):
    return os.environ.get(env, "").strip()


def have(provider_id):
    """True if the key for this provider is set. The window asks this before
    every call it is about to make, so that a missing key is a sentence on
    screen rather than a button that does nothing."""
    provider = BY_ID.get(provider_id)
    return bool(provider and current(provider["env"]))


def masked(key):
    key = (key or "").strip()
    if not key:
        return "not set"
    if len(key) <= 12:
        return "*" * len(key)
    return f"{key[:7]}...{key[-4:]}  ({len(key)} chars)"


def looks_wrong(provider, key):
    key = key.strip()
    if not key:
        return "empty"
    if len(key) > MAX_LENGTH:
        return f"too long to store ({len(key)} chars)"
    if any(c.isspace() for c in key):
        return "contains a space - check the paste"
    return None


def unfamiliar(provider, key):
    return not key.strip().startswith(tuple(provider["starts"]))


def _run(args):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, capture_output=True, text=True,
                          creationflags=flags)


def save(env, key):
    key = key.strip()
    os.environ[env] = key
    try:
        done = _run(["setx", env, key])
    except Exception as e:
        return False, f"active now, but not saved for next time ({e})"
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        return False, ("active now, but not saved for next time: "
                       + (detail[-1] if detail else "setx failed"))
    return True, "saved - active now and next time"


def forget(env):
    os.environ.pop(env, None)
    try:
        _run(["reg", "delete", "HKCU\\Environment", "/v", env, "/f"])
    except Exception as e:
        return False, f"cleared for this run only ({e})"
    return True, "cleared"
