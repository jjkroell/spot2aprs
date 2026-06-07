#!/usr/bin/env python3
"""
spot2aprs_setup.py  —  Interactive setup and run script
Fetches the latest SPOT tracker position and uploads it to APRS-IS.

Download and run:
    python3 spot2aprs_setup.py

Settings are saved to ~/.spot2aprs.json so you only need to enter them once.
Run with --reset to re-enter all settings.
Run with --cron  to just print the cron line for scheduled use.
"""

import sys
import os
import json
import math
import socket
import datetime
import argparse
import getpass
import subprocess

CONFIG_FILE = os.path.expanduser("~/.spot2aprs.json")

SPOT_API_URL = (
    "https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed"
    "/{feed_id}/message.json"
)

APRS_SERVER  = "rotate.aprs2.net"
APRS_PORT    = 14580

SYMBOL_HINTS = {
    "/j": "Jeep",
    "/k": "Truck",
    "/c": "Canoe",
    "\\Y": "Yacht / Sailboat",
    "/s": "Boat / Ship",
    "/'": "Small Aircraft",
    "/^": "Large Aircraft",
    "/[": "Person (Walker)",
    "/b": "Bicycle",
    "/-": "House",
    "/f": "Fire truck",
    "/g": "Glider",
}


# ── Dependency bootstrap ──────────────────────────────────────────────────────

def ensure_requests():
    try:
        import requests
        return requests
    except ImportError:
        print("Installing 'requests'…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "requests"],
            stdout=subprocess.DEVNULL,
        )
        import requests
        return requests


# ── APRS helpers ──────────────────────────────────────────────────────────────

def dec2aprs_lat(lat: float) -> str:
    """Decimal degrees → APRS DDMM.HH[NS]"""
    hemi = "N" if lat >= 0 else "S"
    lat  = abs(lat)
    deg  = int(lat)
    mins = (lat - deg) * 60.0
    return f"{deg:02d}{mins:05.2f}{hemi}"


def dec2aprs_lon(lon: float) -> str:
    """Decimal degrees → APRS DDDMM.HH[EW]"""
    hemi = "E" if lon >= 0 else "W"
    lon  = abs(lon)
    deg  = int(lon)
    mins = (lon - deg) * 60.0
    return f"{deg:03d}{mins:05.2f}{hemi}"


def build_packet(callsign, lat, lon, alt_m, comment, sym_table="/", sym_code="j"):
    alt_ft = int((alt_m or 0) * 3.28084)
    body = (
        f"!{dec2aprs_lat(lat)}{sym_table}"
        f"{dec2aprs_lon(lon)}{sym_code}"
        f"000/000/A={alt_ft:06d} {comment}"
    )
    return f"{callsign}>APRS,TCPIP*:{body}"


def aprsis_send(callsign, passcode, packet, server=APRS_SERVER, port=APRS_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect((server, port))

    banner = sock.recv(512).decode("utf-8", errors="replace").strip()
    print(f"  APRS-IS: {banner}")

    login = f"user {callsign} pass {passcode} vers spot2aprs 2.0\r\n"
    sock.sendall(login.encode())

    resp = sock.recv(512).decode("utf-8", errors="replace").strip()
    print(f"  APRS-IS: {resp}")
    if "unverified" in resp.lower():
        raise RuntimeError("APRS-IS rejected login — check callsign and passcode.")

    sock.sendall((packet + "\r\n").encode())
    sock.close()


# ── SPOT API ──────────────────────────────────────────────────────────────────

def fetch_spot(requests, feed_id, verbose=False):
    url = SPOT_API_URL.format(feed_id=feed_id)
    if verbose:
        print(f"  Fetching: {url}")

    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"SPOT API returned HTTP {r.status_code}")

    data = r.json()["response"]["feedMessageResponse"]
    count = data.get("count", 0)
    if verbose:
        print(f"  SPOT messages in feed: {count}")
    if count == 0:
        raise RuntimeError("SPOT feed returned 0 messages.")

    messages = data.get("messages", {}).get("message", [])
    if isinstance(messages, dict):
        messages = [messages]  # single message comes back as a dict, not list
    return messages[0]


def message_age_minutes(msg):
    dt_str  = msg.get("dateTime", "")
    try:
        # SPOT timestamps are UTC with offset e.g. "2024-07-01T12:34:56+0000"
        if dt_str.endswith("+0000"):
            dt_str = dt_str[:-5] + "+00:00"
        msg_time = datetime.datetime.fromisoformat(dt_str)
        if msg_time.tzinfo is None:
            msg_time = msg_time.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return int((now - msg_time).total_seconds() / 60)
    except Exception:
        return 0


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)
    print(f"\nSettings saved to {CONFIG_FILE}")


def ask(prompt, default=None, secret=False, cast=None):
    display = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    while True:
        val = (getpass.getpass(display) if secret else input(display)).strip()
        val = val if val else (str(default) if default is not None else "")
        if not val:
            print("  (required — please enter a value)")
            continue
        if cast:
            try:
                return cast(val)
            except ValueError:
                print(f"  Must be a {cast.__name__}, try again.")
                continue
        return val


def setup_wizard(cfg):
    print("\n" + "═" * 55)
    print("  spot2aprs — First-Time Setup")
    print("═" * 55)
    print("You can find your SPOT Feed ID in the SPOT website:")
    print("  My Account → Get Started → Enable Sharing → Feed ID")
    print()

    cfg["spot_feed_id"]   = ask("SPOT Feed ID",
                                 cfg.get("spot_feed_id"))
    cfg["callsign"]       = ask("Your APRS callsign (e.g. VE7XX-9)",
                                 cfg.get("callsign")).upper()
    cfg["aprs_passcode"]  = ask("APRS-IS passcode  (see aprs.do/passcode)",
                                 cfg.get("aprs_passcode"), cast=int)
    cfg["maxage"]         = ask("Max position age to upload (minutes)",
                                 cfg.get("maxage", 60), cast=int)

    print()
    print("APRS symbol — common choices:")
    for code, label in SYMBOL_HINTS.items():
        print(f"  {code}  →  {label}")
    cfg["sym_table"] = ask("Symbol table char",
                            cfg.get("sym_table", "/"))[-1]
    cfg["sym_code"]  = ask("Symbol code char",
                            cfg.get("sym_code",  "j"))[-1]
    cfg["comment"]   = ask("Extra comment appended to position (optional)",
                            cfg.get("comment", ""))

    save_config(cfg)
    return cfg


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch SPOT position and upload to APRS-IS."
    )
    parser.add_argument("--reset",   action="store_true",
                        help="Re-enter all settings.")
    parser.add_argument("--cron",    action="store_true",
                        help="Print a cron line and exit.")
    parser.add_argument("--verbose", action="store_true",
                        help="Extra output.")
    args = parser.parse_args()

    requests = ensure_requests()

    cfg = {} if args.reset else load_config()

    if not cfg.get("spot_feed_id") or not cfg.get("callsign"):
        cfg = setup_wizard(cfg)
    else:
        print(f"Using saved config from {CONFIG_FILE}  (run with --reset to change)")
        if args.verbose:
            print(f"  Callsign : {cfg['callsign']}")
            print(f"  Feed ID  : {cfg['spot_feed_id']}")
            print(f"  Max age  : {cfg['maxage']} min")

    if args.cron:
        script = os.path.abspath(__file__)
        print("\nAdd this to your crontab (runs every 10 minutes):")
        print(f"  */10 * * * *  {sys.executable} {script} >> /var/log/spot2aprs.log 2>&1\n")
        print("Edit with:  crontab -e")
        return

    # ── Fetch SPOT ────────────────────────────────────────────────────────────
    print("\nFetching latest SPOT position…")
    try:
        msg = fetch_spot(requests, cfg["spot_feed_id"], verbose=args.verbose)
    except Exception as e:
        print(f"ERROR fetching SPOT data: {e}")
        sys.exit(1)

    age = message_age_minutes(msg)
    lat = float(msg["latitude"])
    lon = float(msg["longitude"])
    alt = float(msg.get("altitude", 0) or 0)

    name      = msg.get("messengerName", "")
    model     = msg.get("modelId", "")
    msg_type  = msg.get("messageType", "")
    battery   = msg.get("batteryState", "N/A")
    timestamp = msg.get("dateTime", "")

    comment = (
        f"{name} {model} {msg_type} Batt:{battery}"
        + (f" {cfg['comment']}" if cfg.get("comment") else "")
    ).strip()

    print(f"  Position : {lat:.5f}, {lon:.5f}  alt {alt:.0f}m")
    print(f"  Timestamp: {timestamp}  ({age} min ago)")
    print(f"  Comment  : {comment}")

    if age > int(cfg.get("maxage", 60)):
        print(f"\nPosition is {age} min old (max {cfg['maxage']} min) — not uploading.")
        sys.exit(0)

    # ── Build and send APRS packet ────────────────────────────────────────────
    packet = build_packet(
        callsign  = cfg["callsign"],
        lat       = lat,
        lon       = lon,
        alt_m     = alt,
        comment   = comment,
        sym_table = cfg.get("sym_table", "/"),
        sym_code  = cfg.get("sym_code",  "j"),
    )

    print(f"\nAPRS packet: {packet}")
    print("\nConnecting to APRS-IS…")

    try:
        aprsis_send(cfg["callsign"], int(cfg["aprs_passcode"]), packet)
    except Exception as e:
        print(f"ERROR uploading to APRS-IS: {e}")
        sys.exit(1)

    print(f"\nUploaded successfully at {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")


if __name__ == "__main__":
    main()
