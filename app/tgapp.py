"""Telegram Mini App: who is sending, and what the public link may reach.

Identity: the bot hands each person a Mini App link with a signed pass
    t = <device_id>.<expires unix>.<hmac>
where device_id is the same hashed id the bot already sends (sha256(salt + telegram id)),
so the server never sees a raw Telegram id. The HMAC key is derived from TELEGRAM_BOT_TOKEN,
which both the bot and the server read from .env; the token itself never leaves .env.
A valid pass is what makes the Mini App's GPS location count as exact.

Public link: Telegram only opens Mini Apps over https, so for the phone the app is reached
through a tunnel (cloudflared). Every tunnelled request arrives from 127.0.0.1 with forwarding
headers; such requests are never "trusted" and may only reach the Mini App page, its assets
and its report upload. The inspector, contractor and demo controls stay local.
"""
import hashlib
import hmac
import time
from typing import Optional

from .config import env

PASS_HOURS = 12  # the button stays in the chat; a fresh pass comes with every bot reply
PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host", "forwarded", "x-real-ip")
PUBLIC_PATHS = {"/tg", "/health", "/reports/app"}
PUBLIC_PREFIXES = ("/assets/",)


def _key() -> Optional[bytes]:
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return None
    team = env("BOT_PASSWORD", "") or env("LANTERN_PASSWORD", "")  # new password -> all old passes die
    return hmac.new(b"lantern-miniapp-pass", (token + "|" + team).encode(), hashlib.sha256).digest()


def _sign(key: bytes, body: str) -> str:
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()[:32]


def make_pass(device_id: str, now: Optional[float] = None, hours: float = PASS_HOURS) -> Optional[str]:
    key = _key()
    if key is None:
        return None
    body = f"{device_id}.{int((now or time.time()) + hours * 3600)}"
    return f"{body}.{_sign(key, body)}"


def check_pass(token: Optional[str], now: Optional[float] = None) -> Optional[str]:
    """The device id if the pass is genuine and not expired, else None."""
    key = _key()
    if key is None or not token or token.count(".") != 2:
        return None
    device, expires, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(key, f"{device}.{expires}")):
        return None
    try:
        if int(expires) < (now or time.time()):
            return None
    except ValueError:
        return None
    return device[:64] or None


def proxied(headers) -> bool:
    """True when the request came through the tunnel (or any reverse proxy)."""
    return any(h in headers for h in PROXY_HEADERS)


def client_ip(headers, host: Optional[str]) -> Optional[str]:
    if not proxied(headers):
        return host
    ip = headers.get("cf-connecting-ip") or (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return ip or host


def public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)
