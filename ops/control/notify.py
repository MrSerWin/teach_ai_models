"""Telegram alerts + Wake-on-LAN.

Alerts are best-effort: a failing notification must never break a job.
"""
import json
import os
import socket
import urllib.parse
import urllib.request

# Preferred: route through the QO telegram-service (it owns the @QOResearchBot
# token and maps `account` -> channel, e.g. QirimOnline). Requires the service
# to be reachable from wherever this runs (the NAS) — it binds localhost on the
# Mac by default, so expose/deploy it reachably or use the direct fallback.
TG_SERVICE_URL = os.environ.get("TELEGRAM_SERVICE_URL", "").rstrip("/")
TG_ACCOUNT = os.environ.get("TELEGRAM_ACCOUNT", "default")

# Direct fallback: talk to the Bot API ourselves with @QOResearchBot's token
# (reuses the existing bot — no new BotFather bot) + the target chat/channel.
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT_ID", "")


def _via_service(text):
    payload = json.dumps({
        "account": TG_ACCOUNT, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(f"{TG_SERVICE_URL}/send", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status == 200


def _via_bot_api(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
        return r.status == 200


def tg(text):
    """Send a Telegram message (best-effort). Prefers the QO telegram-service;
    falls back to a direct Bot API call. No-op if neither is configured."""
    try:
        if TG_SERVICE_URL:
            return _via_service(text)
        if TG_TOKEN and TG_CHAT:
            return _via_bot_api(text)
    except Exception:
        return False
    return False


def wake_on_lan(mac, broadcast="255.255.255.255", port=9):
    """Send a WoL magic packet. Must run on the same L2 segment as the target —
    i.e. from the NAS, not from a laptop on the road."""
    mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError(f"bad MAC: {mac}")
    payload = b"\xff" * 6 + bytes.fromhex(mac_clean) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, (broadcast, port))
    return True
