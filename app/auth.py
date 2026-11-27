"""Login for the Lantern web app (username + password -> signed session cookie).

Why: every resident report is checked by the AI service, which runs on our paid API key.
Nobody can read that key (it stays in the model service's .env), but strangers could *use*
it by sending reports. So when LANTERN_PASSWORD is set:

- the pages (inspector, contractor, resident form, API docs) need a login;
- the API needs a login too, except for machine callers on this computer (the Telegram bot,
  the camera worker, the demo script: TRUSTED_HOSTS without proxy headers) or with the
  INTERNAL_API_KEY header;
- the Telegram Mini App keeps its own per-person pass from the bot (app/tgapp.py).

The session cookie is <user>.<expires>.<hmac>; the key is derived from the password, so changing
the password logs everybody out. Without LANTERN_PASSWORD login is off (tests, old setups).
"""
import hashlib
import hmac
import time
from collections import defaultdict, deque
from typing import Optional

from .config import env

COOKIE = "lantern_session"
SESSION_HOURS = 12
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60   # 5 wrong passwords in 15 min from one address -> wait
PAGES = {"/", "/inspector", "/contractor", "/report", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
OPEN = {"/login", "/logout"}

_fails: dict = defaultdict(deque)


def password() -> str:
    return env("LANTERN_PASSWORD", "")


def user() -> str:
    return env("LANTERN_USER", "lantern")


def enabled() -> bool:
    return bool(password())


def _key() -> bytes:
    return hashlib.sha256(("lantern-session:" + password()).encode()).digest()


def _sign(body: str) -> str:
    return hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]


def check_login(username: str, pwd: str) -> bool:
    if not enabled():
        return False
    ok_user = hmac.compare_digest((username or "").strip().lower().encode(), user().lower().encode())
    ok_pwd = hmac.compare_digest((pwd or "").encode(), password().encode())
    return ok_user and ok_pwd


def make_session(now: Optional[float] = None) -> str:
    body = f"{user()}.{int((now or time.time()) + SESSION_HOURS * 3600)}"
    return f"{body}.{_sign(body)}"


def valid_session(token: Optional[str], now: Optional[float] = None) -> bool:
    if not enabled() or not token or token.count(".") != 2:
        return False
    name, expires, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(f"{name}.{expires}")) or name != user():
        return False
    try:
        return int(expires) >= (now or time.time())
    except ValueError:
        return False


def too_many_fails(addr: str, now: Optional[float] = None) -> bool:
    now = now or time.time()
    q = _fails[addr]
    while q and q[0] < now - FAIL_WINDOW:
        q.popleft()
    return len(q) >= MAX_FAILS


def failed(addr: str, now: Optional[float] = None) -> None:
    _fails[addr].append(now or time.time())


def safe_next(target: Optional[str]) -> str:
    """Only local paths after login (no //evil.example redirects)."""
    t = target or "/inspector"
    return t if t.startswith("/") and not t.startswith("//") and "\\" not in t else "/inspector"


LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lantern login</title>
<style>
  :root { --bg: #f4f6f9; --card: #ffffff; --text: #14213d; --muted: #5b6475; --line: #d9dee7; --accent: #f2a93b;
          --bad: #c62828; }
  @media (prefers-color-scheme: dark) { :root { --bg: #0f1623; --card: #172235; --text: #eef2f8; --muted: #9aa6ba;
          --line: #2a3850; --bad: #ff8a80; } }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px;
         background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  form { width: 100%; max-width: 360px; background: var(--card); border: 1px solid var(--line); border-radius: 14px;
         padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; display: flex; gap: 8px; align-items: center; }
  p { color: var(--muted); margin: 0 0 18px; font-size: 14px; }
  label { display: block; font-weight: 600; margin: 12px 0 4px; font-size: 14px; }
  input { width: 100%; padding: 11px 12px; border-radius: 9px; border: 1px solid var(--line); background: transparent;
          color: var(--text); font: inherit; }
  button { width: 100%; margin-top: 18px; padding: 12px; border: 0; border-radius: 9px; background: var(--accent);
           color: #1b1300; font: inherit; font-weight: 700; cursor: pointer; }
  .err { color: var(--bad); font-weight: 600; margin-top: 12px; font-size: 14px; }
</style>
</head>
<body>
<form method="post" action="/login">
  <h1>🏮 Lantern</h1>
  <p>Ienāc, lai turpinātu / Log in to continue</p>
  <input type="hidden" name="next" value="__NEXT__">
  <label for="u">Lietotājs / Username</label>
  <input id="u" name="username" autocomplete="username" required autofocus>
  <label for="p">Parole / Password</label>
  <input id="p" name="password" type="password" autocomplete="current-password" required>
  __ERROR__
  <button type="submit">Ienākt / Log in</button>
</form>
</body>
</html>
"""


def login_page(next_path: str, error: str = "") -> str:
    from html import escape
    err = f'<div class="err" role="alert">{escape(error)}</div>' if error else ""
    return LOGIN_HTML.replace("__NEXT__", escape(safe_next(next_path))).replace("__ERROR__", err)
