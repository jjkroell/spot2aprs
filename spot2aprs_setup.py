#!/usr/bin/env python3
"""
spot2aprs_setup.py  —  Interactive setup and run script
Fetches the latest SPOT tracker position and uploads it to APRS-IS.

Download and run:
    python3 spot2aprs_setup.py

On first run it asks for your settings (SPOT feed ID, callsign, passcode,
interval, symbol, comment) and saves them to ~/.spot2aprs.json.
Then it runs continuously, polling the SPOT API and uploading to APRS-IS
on your chosen interval. Press Ctrl-C to stop.

Run with --reset to re-enter all settings.
"""

import sys
import os
import json
import socket
import time
import datetime
import argparse
import getpass
import subprocess

CONFIG_FILE = os.path.expanduser("~/.spot2aprs.json")

SPOT_API_URL = (
    "https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed"
    "/{feed_id}/message.json"
)

APRS_SERVER = "rotate.aprs2.net"
APRS_PORT   = 14580

# SPOT terms require at least 2.5 min between calls
MIN_INTERVAL = 3

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
    "/-": "House / Fixed station",
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
    hemi = "N" if lat >= 0 else "S"
    lat  = abs(lat)
    deg  = int(lat)
    mins = (lat - deg) * 60.0
    return f"{deg:02d}{mins:05.2f}{hemi}"


def dec2aprs_lon(lon: float) -> str:
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


def aprsis_send(callsign, passcode, packet, server=APRS_SERVER, port=APRS_PORT, verbose=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect((server, port))

    banner = sock.recv(512).decode("utf-8", errors="replace").strip()
    if verbose:
        print(f"  APRS-IS: {banner}")

    login = f"user {callsign} pass {passcode} vers spot2aprs 2.0\r\n"
    sock.sendall(login.encode())

    resp = sock.recv(512).decode("utf-8", errors="replace").strip()
    if verbose:
        print(f"  APRS-IS: {resp}")
    if "unverified" in resp.lower():
        raise RuntimeError("APRS-IS rejected login — check callsign and passcode.")

    sock.sendall((packet + "\r\n").encode())
    sock.close()


# ── SPOT API ──────────────────────────────────────────────────────────────────

def fetch_spot(requests_mod, feed_id, verbose=False):
    url = SPOT_API_URL.format(feed_id=feed_id)
    if verbose:
        print(f"  Fetching: {url}")

    r = requests_mod.get(url, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"SPOT API returned HTTP {r.status_code}")

    data = r.json()["response"]["feedMessageResponse"]
    count = data.get("count", 0)
    if count == 0:
        raise RuntimeError("SPOT feed returned 0 messages — device may be off or feed is empty.")

    messages = data.get("messages", {}).get("message", [])
    if isinstance(messages, dict):
        messages = [messages]
    return messages[0]


def message_age_minutes(msg):
    dt_str = msg.get("dateTime", "")
    try:
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
    print(f"Settings saved to {CONFIG_FILE}")


def ask(prompt, default=None, secret=False, cast=None):
    display = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    while True:
        val = (getpass.getpass(display) if secret else input(display)).strip()
        val = val if val else (str(default) if default is not None else "")
        if not val:
            print("  (required)")
            continue
        if cast:
            try:
                return cast(val)
            except ValueError:
                print(f"  Must be a number, try again.")
                continue
        return val


def setup_wizard(cfg):
    print()
    print("═" * 55)
    print("  spot2aprs — Setup")
    print("═" * 55)
    print()
    print("SPOT Feed ID: log in to findmespot.com →")
    print("  My Account → Get Started → Enable Sharing → Feed ID")
    print()

    cfg["spot_feed_id"]  = ask("SPOT Feed ID", cfg.get("spot_feed_id"))
    cfg["callsign"]      = ask("APRS callsign with SSID (e.g. VE7XX-9)",
                                cfg.get("callsign")).upper()
    cfg["aprs_passcode"] = ask("APRS-IS passcode  (aprs.do/passcode)",
                                cfg.get("aprs_passcode"), secret=True, cast=int)
    cfg["interval"]      = ask(
        f"Poll interval in minutes (min {MIN_INTERVAL}, SPOT allows max every 2.5 min)",
        cfg.get("interval", 10), cast=int)
    if cfg["interval"] < MIN_INTERVAL:
        print(f"  Interval too low — setting to {MIN_INTERVAL} min minimum.")
        cfg["interval"] = MIN_INTERVAL

    cfg["maxage"] = ask("Skip upload if position is older than X minutes",
                         cfg.get("maxage", 60), cast=int)

    print()
    print("APRS symbol — common choices:")
    for code, label in SYMBOL_HINTS.items():
        print(f"  {code}  →  {label}")
    print()
    cfg["sym_table"] = ask("Symbol table character", cfg.get("sym_table", "/"))[-1]
    cfg["sym_code"]  = ask("Symbol code character",  cfg.get("sym_code",  "j"))[-1]
    cfg["comment"]   = ask("Extra comment text (optional, press Enter to skip)",
                            cfg.get("comment", ""))

    print()
    save_config(cfg)
    return cfg


# ── Single poll cycle ─────────────────────────────────────────────────────────

def run_once(requests_mod, cfg, verbose=False):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now} UTC] Polling SPOT…")

    try:
        msg = fetch_spot(requests_mod, cfg["spot_feed_id"], verbose=verbose)
    except Exception as e:
        print(f"  ERROR fetching SPOT: {e}")
        return

    age = message_age_minutes(msg)
    lat = float(msg["latitude"])
    lon = float(msg["longitude"])
    alt = float(msg.get("altitude", 0) or 0)

    name     = msg.get("messengerName", "")
    model    = msg.get("modelId", "")
    msg_type = msg.get("messageType", "")
    battery  = msg.get("batteryState", "N/A")

    comment = (
        f"{name} {model} {msg_type} Batt:{battery}"
        + (f" {cfg['comment']}" if cfg.get("comment") else "")
    ).strip()

    print(f"  Position : {lat:.5f}, {lon:.5f}  alt {alt:.0f}m  ({age} min ago)")
    print(f"  Comment  : {comment}")

    if age > int(cfg.get("maxage", 60)):
        print(f"  Skipping — position is {age} min old (max {cfg['maxage']} min).")
        return

    packet = build_packet(
        callsign  = cfg["callsign"],
        lat       = lat,
        lon       = lon,
        alt_m     = alt,
        comment   = comment,
        sym_table = cfg.get("sym_table", "/"),
        sym_code  = cfg.get("sym_code",  "j"),
    )

    if verbose:
        print(f"  Packet   : {packet}")

    try:
        aprsis_send(cfg["callsign"], int(cfg["aprs_passcode"]), packet, verbose=verbose)
        print(f"  Uploaded to APRS-IS ✓")
    except Exception as e:
        print(f"  ERROR uploading to APRS-IS: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Poll SPOT API and upload positions to APRS-IS continuously."
    )
    parser.add_argument("--reset",   action="store_true", help="Re-enter all settings.")
    parser.add_argument("--once",    action="store_true", help="Run once and exit.")
    parser.add_argument("--verbose", action="store_true", help="Extra output.")
    args = parser.parse_args()

    requests_mod = ensure_requests()

    cfg = {} if args.reset else load_config()

    if not cfg.get("spot_feed_id") or not cfg.get("callsign"):
        cfg = setup_wizard(cfg)
    elif args.reset:
        cfg = setup_wizard(cfg)
    else:
        print(f"Loaded config from {CONFIG_FILE}  (--reset to change settings)")

    interval_sec = int(cfg.get("interval", 10)) * 60

    if args.once:
        run_once(requests_mod, cfg, verbose=args.verbose)
        return

    print()
    print(f"Running — polling every {cfg['interval']} minutes.  Press Ctrl-C to stop.")
    print(f"Callsign : {cfg['callsign']}")
    print(f"Feed ID  : {cfg['spot_feed_id']}")

    while True:
        run_once(requests_mod, cfg, verbose=args.verbose)
        next_run = datetime.datetime.utcnow() + datetime.timedelta(seconds=interval_sec)
        print(f"  Next poll at {next_run.strftime('%H:%M:%S')} UTC")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
