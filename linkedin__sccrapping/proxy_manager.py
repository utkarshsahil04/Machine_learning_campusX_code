"""
proxy_manager.py — Tor-based IP Rotation
=========================================
Uses the Tor SOCKS5 proxy (port 9150) + stem library to request
a fresh Tor circuit (= new exit IP) between keywords.

Requirements:
  1. Tor Browser must be running (or Tor standalone service on port 9150/9051)
  2. pip install stem requests

 HOW IT WORKS:
  - All browser traffic goes through Tor → your real IP is hidden
  - After each keyword, rotate_ip() signals Tor to pick a new exit node
  - Each keyword appears to come from a different country/IP
"""

import time
import requests

# ── Tor control settings ────────────────────────────────────────────────────
TOR_SOCKS_PORT   = 9150   # SOCKS5 proxy port (Tor Browser default)
TOR_CONTROL_PORT = 9151   # Control port (Tor Browser default)
#                           If using standalone Tor daemon: 9050 / 9051
TOR_PASSWORD     = ""     # Leave empty if no control password is set
# ────────────────────────────────────────────────────────────────────────────

PROXY_CONFIG = {"server": f"socks5://127.0.0.1:{TOR_SOCKS_PORT}"}


def get_current_ip() -> str:
    """Return the current exit IP seen through Tor."""
    try:
        resp = requests.get(
            "https://api.ipify.org",
            proxies={"https": f"socks5h://127.0.0.1:{TOR_SOCKS_PORT}"},
            timeout=15,
        )
        return resp.text.strip()
    except Exception as e:
        return f"(unknown — {e})"


def rotate_ip(wait: int = 5) -> str:
    """
    Send NEWNYM signal to Tor to get a fresh circuit (new exit IP).
    Returns the new IP string, or a fallback message on failure.

    Args:
        wait: seconds to wait after signalling before checking new IP.
    """
    try:
        from stem import Signal
        from stem.control import Controller

        with Controller.from_port(port=TOR_CONTROL_PORT) as ctrl:
            if TOR_PASSWORD:
                ctrl.authenticate(password=TOR_PASSWORD)
            else:
                ctrl.authenticate()
            ctrl.signal(Signal.NEWNYM)

        print(f"  🔄 Tor circuit rotated — waiting {wait}s for new route...")
        time.sleep(wait)
        new_ip = get_current_ip()
        print(f"  🌍 New IP: {new_ip}")
        return new_ip

    except ImportError:
        print("  ⚠️  stem not installed. Run: pip install stem")
        return "(stem missing)"
    except Exception as e:
        print(f"  ⚠️  Could not rotate Tor IP: {e}")
        return "(rotation failed)"


def is_tor_running() -> bool:
    """Quick check — can we reach the internet through Tor?"""
    try:
        requests.get(
            "https://api.ipify.org",
            proxies={"https": f"socks5h://127.0.0.1:{TOR_SOCKS_PORT}"},
            timeout=10,
        )
        return True
    except Exception:
        return False