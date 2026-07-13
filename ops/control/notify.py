"""Telegram alerts + Wake-on-LAN.

Alerts are best-effort: a failing notification must never break a job.
"""
import os
import socket
import urllib.parse
import urllib.request

TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT_ID", "")


def tg(text):
    """Send a Telegram message. No-op if the bot isn't configured."""
    if not TG_TOKEN or not TG_CHAT:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return r.status == 200
    except Exception:
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
