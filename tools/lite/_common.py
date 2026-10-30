"""Shared helpers for Workflow Lite tools. Standard library only (Windows Git Bash, macOS, Linux).

v1.6 Core fixes:
  - UTF-8 output everywhere (Windows consoles default to cp1252 and crashed on ⚠ →)        [fix 2]
  - State is split per chat (one small file per session) and every write is atomic + locked,
    so several tabs/hooks writing at once can't erase each other                          [fix 1]
  - lite.env is read even if saved with a BOM or as UTF-16 (Notepad / PowerShell)           [fix 8]
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ---- fix 2: never crash on non-ASCII output -------------------------------------------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HOME = Path.home()
LITE_DIR = HOME / ".uaply"              # private, per-founder, never committed
ENV_FILE = LITE_DIR / "lite.env"        # FOUNDER, TRELLO_KEY, TRELLO_TOKEN ...
STATE_DIR = LITE_DIR / "state"          # global.json + one sess-<id>.json per chat
DEFAULT_BOARD = "TUiuK5fz"              # "UAply Team Board" short link (the real team board)


# ---- fix 8: tolerant env file ----------------------------------------------------------------
def _read_text_any(p: Path) -> str:
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def load_env():
    """Read ~/.uaply/lite.env (KEY=VALUE lines) into os.environ without overriding real env vars."""
    try:
        if ENV_FILE.exists():
            for line in _read_text_any(ENV_FILE).splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.split(" #", 1)[0]
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass  # a broken env file must never break a hook; doctor.py reports it


def git(*args, cwd=None, check=True, timeout=20):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def founder():
    load_env()
    return os.environ.get("FOUNDER") or git("config", "user.name", check=False) or "unknown"


# ---- fix 1: atomic, locked JSON state --------------------------------------------------------
class _Lock:
    """Cross-platform lock file (O_EXCL). Waits up to ~2s, then breaks a stale lock (>10s old)."""
    def __init__(self, path: Path):
        self.path = path.with_suffix(path.suffix + ".lock")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(100):
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 10:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                time.sleep(0.02)
        return self  # give up waiting; still write atomically

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _update_json(p: Path, update: dict):
    with _Lock(p):
        data = _read_json(p)
        data.update(update)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, p)          # atomic on Windows and POSIX
        return data


def _sess_file(sid):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(sid or "nosession"))[:80] or "nosession"
    return STATE_DIR / f"sess-{safe}.json"


def read_state():
    return _read_json(STATE_DIR / "global.json")


def write_state(update):
    return _update_json(STATE_DIR / "global.json", update)


def read_sess(sid):
    return _read_json(_sess_file(sid))


def write_sess(sid, update):
    update = dict(update, touched=time.time())
    out = _update_json(_sess_file(sid), update)
    _prune()
    return out


def _prune():
    """Delete per-chat files untouched for 7 days (cheap; runs at most once an hour)."""
    marker = STATE_DIR / ".pruned"
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < 3600:
            return
        marker.touch()
        week = time.time() - 7 * 86400
        for f in STATE_DIR.glob("sess-*.json"):
            if f.stat().st_mtime < week:
                f.unlink()
    except Exception:
        pass


# ---- Trello ----------------------------------------------------------------------------------
def trello(method, path, params=None, timeout=15):
    """Call the Trello REST API. Needs TRELLO_KEY and TRELLO_TOKEN in env or ~/.uaply/lite.env."""
    load_env()
    key, token = os.environ.get("TRELLO_KEY"), os.environ.get("TRELLO_TOKEN")
    if not key or not token:
        raise RuntimeError("TRELLO_KEY / TRELLO_TOKEN not set (put them in ~/.uaply/lite.env)")
    q = dict(params or {}, key=key, token=token)
    url = f"https://api.trello.com/1{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(q)
    else:
        data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    return json.loads(body) if body else {}


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_stdin_json():
    """Hook payloads are UTF-8 JSON; read raw bytes so a cp1252 console can't garble them."""
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8-sig") or "{}")
    except Exception:
        return {}
