"""
Where the API key lives, and how the window changes it.

A key is never written next to the script. A plain-text key in the project
folder is a key that gets committed by accident, and no .gitignore rule is
worth relying on for that. It goes where the setup instructions already put
it - the user's own Windows environment, through setx, which survives a
reboot and is there for every terminal afterwards.

setx only reaches processes started after it, so the key is also set on this
process as it is saved. The change therefore takes effect on the very next
question and still holds tomorrow, with no restart in between.

The free edition needs one key: Anthropic. You bring your own - the app never
ships with a key and never phones one home.
"""

import os
import subprocess

PROVIDERS = [
    {"env": "ANTHROPIC_API_KEY",
     "label": "Anthropic",
     "note": "answers the screen",
     "starts": ("sk-ant-",),
     "where": "console.anthropic.com -> API keys"},
]

# setx truncates silently past this, which would leave a key that looks saved
# and fails on use. Better to refuse it.
MAX_LENGTH = 1024


def current(env):
    return os.environ.get(env, "").strip()


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
