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

    --reset            Re-enter all settings
    --install-service  Install as a persistent background service
                       (systemd on Linux, launchd on macOS)
    --uninstall-service  Remove the service
    --once             Run once and exit
    --verbose          Extra output
"""

import sys
import os
import json
import socket
import platform
import time
import datetime
import argparse
import getpass
import subprocess

CONFIG_FILE  = os.path.expanduser("~/.spot2aprs.json")
LOG_FILE     = os.path.expanduser("~/.spot2aprs_log.json")
LOG_MAX      = 24

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


# ── Poll log ─────────────────────────────────────────────────────────────────

def log_append(entry: dict):
    """Append a poll result to the log, keeping only the last LOG_MAX entries."""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                entries = json.load(f)
        else:
            entries = []
    except Exception:
        entries = []

    entries.append(entry)
    entries = entries[-LOG_MAX:]  # trim to last 24

    with open(LOG_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def log_print():
    """Print the poll history in a readable table."""
    if not os.path.exists(LOG_FILE):
        print("No log entries yet.")
        return
    with open(LOG_FILE) as f:
        entries = json.load(f)
    if not entries:
        print("No log entries yet.")
        return

    print(f"\n{'#':<4} {'Polled (UTC)':<22} {'Lat':>10} {'Lon':>11} {'Age':>6} {'Status'}")
    print("─" * 75)
    for i, e in enumerate(entries, 1):
        lat    = f"{e.get('lat', 0):10.5f}" if e.get('lat') is not None else " " * 10
        lon    = f"{e.get('lon', 0):11.5f}" if e.get('lon') is not None else " " * 11
        age    = f"{e.get('age_min', '?'):>5}m"
        status = e.get("status", "?")
        polled = e.get("polled_at", "")[:19]
        print(f"{i:<4} {polled:<22} {lat} {lon} {age}  {status}")
    print()


# ── Single poll cycle ─────────────────────────────────────────────────────────

def run_once(requests_mod, cfg, verbose=False):
    polled_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{polled_at} UTC] Polling SPOT…")

    log_entry = {"polled_at": polled_at, "lat": None, "lon": None, "age_min": None, "status": "error"}

    try:
        msg = fetch_spot(requests_mod, cfg["spot_feed_id"], verbose=verbose)
    except Exception as e:
        print(f"  ERROR fetching SPOT: {e}")
        log_entry["status"] = f"fetch_error: {e}"
        log_append(log_entry)
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

    log_entry.update({"lat": lat, "lon": lon, "alt_m": alt, "age_min": age,
                      "comment": comment, "spot_time": msg.get("dateTime", "")})

    print(f"  Position : {lat:.5f}, {lon:.5f}  alt {alt:.0f}m  ({age} min ago)")
    print(f"  Comment  : {comment}")

    if age > int(cfg.get("maxage", 60)):
        print(f"  Skipping — position is {age} min old (max {cfg['maxage']} min).")
        log_entry["status"] = f"skipped (too old: {age} min)"
        log_append(log_entry)
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
        log_entry["status"] = "uploaded"
        log_entry["packet"] = packet
    except Exception as e:
        print(f"  ERROR uploading to APRS-IS: {e}")
        log_entry["status"] = f"aprs_error: {e}"

    log_append(log_entry)


# ── Service install / uninstall ───────────────────────────────────────────────

SYSTEMD_SERVICE = """\
[Unit]
Description=SPOT to APRS-IS uploader
After=network-online.target
Wants=network-online.target

[Service]
ExecStart={python} {script}
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""

LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.github.spot2aprs</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{logfile}</string>
    <key>StandardErrorPath</key>
    <string>{logfile}</string>
</dict>
</plist>
"""


def install_service():
    script = os.path.abspath(__file__)
    python = sys.executable
    system = platform.system()

    if system == "Linux":
        service_dir = os.path.expanduser("~/.config/systemd/user")
        service_file = os.path.join(service_dir, "spot2aprs.service")
        os.makedirs(service_dir, exist_ok=True)

        with open(service_file, "w") as f:
            f.write(SYSTEMD_SERVICE.format(python=python, script=script))
        print(f"Wrote service file: {service_file}")

        cmds = [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "spot2aprs"],
            ["systemctl", "--user", "start",  "spot2aprs"],
            ["loginctl", "enable-linger", os.environ.get("USER", "")],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            label = " ".join(cmd)
            if result.returncode == 0:
                print(f"  ✓ {label}")
            else:
                print(f"  ✗ {label}")
                if result.stderr:
                    print(f"    {result.stderr.strip()}")

        print()
        print("Service installed and started.")
        print("  Status:  systemctl --user status spot2aprs")
        print("  Logs:    journalctl --user -u spot2aprs -f")
        print("  Stop:    systemctl --user stop spot2aprs")

    elif system == "Darwin":
        plist_dir  = os.path.expanduser("~/Library/LaunchAgents")
        plist_file = os.path.join(plist_dir, "io.github.spot2aprs.plist")
        logfile    = os.path.expanduser("~/Library/Logs/spot2aprs.log")
        os.makedirs(plist_dir, exist_ok=True)

        with open(plist_file, "w") as f:
            f.write(LAUNCHD_PLIST.format(python=python, script=script, logfile=logfile))
        print(f"Wrote plist: {plist_file}")

        result = subprocess.run(
            ["launchctl", "load", "-w", plist_file],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✓ launchctl load")
        else:
            print(f"  ✗ launchctl load: {result.stderr.strip()}")

        print()
        print("Service installed and started.")
        print(f"  Logs:    tail -f {logfile}")
        print(f"  Stop:    launchctl unload {plist_file}")

    elif system == "Windows":
        bat_file = os.path.expanduser("~/spot2aprs_service.bat")
        logfile  = os.path.expanduser("~/spot2aprs_service.log")
        with open(bat_file, "w") as f:
            f.write(f'@echo off\n"{python}" "{script}" >> "{logfile}" 2>&1\n')
        print(f"Wrote launcher: {bat_file}")

        cmds = [
            ["schtasks", "/create", "/tn", "spot2aprs", "/tr", bat_file, "/sc", "ONLOGON", "/f"],
            ["schtasks", "/run",    "/tn", "spot2aprs"],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            label  = " ".join(cmd)
            if result.returncode == 0:
                print(f"  ✓ {label}")
            else:
                print(f"  ✗ {label}")
                if result.stderr:
                    print(f"    {result.stderr.strip()}")

        print()
        print("Service installed and started.")
        print(f'  Status:  schtasks /query /tn "spot2aprs"')
        print(f"  Logs:    type {logfile}")
        print(f'  Stop:    schtasks /end /tn "spot2aprs"')

    else:
        print(f"Unsupported OS: {system}")
        print("Please set up a service manually to run:")
        print(f"  {python} {script}")
        sys.exit(1)


def uninstall_service():
    system = platform.system()

    if system == "Linux":
        cmds = [
            ["systemctl", "--user", "stop",    "spot2aprs"],
            ["systemctl", "--user", "disable", "spot2aprs"],
        ]
        for cmd in cmds:
            subprocess.run(cmd, capture_output=True)
            print(f"  ✓ {' '.join(cmd)}")

        service_file = os.path.expanduser("~/.config/systemd/user/spot2aprs.service")
        if os.path.exists(service_file):
            os.remove(service_file)
            print(f"  ✓ Removed {service_file}")

        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        print("Service removed.")

    elif system == "Darwin":
        plist_file = os.path.expanduser("~/Library/LaunchAgents/io.github.spot2aprs.plist")
        if os.path.exists(plist_file):
            subprocess.run(["launchctl", "unload", "-w", plist_file], capture_output=True)
            os.remove(plist_file)
            print(f"  ✓ Removed {plist_file}")
        print("Service removed.")

    elif system == "Windows":
        cmds = [
            ["schtasks", "/end",    "/tn", "spot2aprs"],
            ["schtasks", "/delete", "/tn", "spot2aprs", "/f"],
        ]
        for cmd in cmds:
            subprocess.run(cmd, capture_output=True)
            print(f"  ✓ {' '.join(cmd)}")

        bat_file = os.path.expanduser("~/spot2aprs_service.bat")
        if os.path.exists(bat_file):
            os.remove(bat_file)
            print(f"  ✓ Removed {bat_file}")
        print("Service removed.")

    else:
        print(f"Unsupported OS: {system}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Poll SPOT API and upload positions to APRS-IS continuously."
    )
    parser.add_argument("--reset",             action="store_true", help="Re-enter all settings.")
    parser.add_argument("--once",              action="store_true", help="Run once and exit.")
    parser.add_argument("--verbose",           action="store_true", help="Extra output.")
    parser.add_argument("--log",               action="store_true", help="Print poll history and exit.")
    parser.add_argument("--install-service",   action="store_true", help="Install as a persistent background service.")
    parser.add_argument("--uninstall-service", action="store_true", help="Remove the background service.")
    args = parser.parse_args()

    if args.uninstall_service:
        uninstall_service()
        return

    if args.log:
        log_print()
        return

    requests_mod = ensure_requests()

    cfg = {} if args.reset else load_config()
    needs_setup = not cfg.get("spot_feed_id") or not cfg.get("callsign") or args.reset

    if needs_setup:
        cfg = setup_wizard(cfg)
        print()
        install_service()
        return
    else:
        print(f"Loaded config from {CONFIG_FILE}  (--reset to change settings)")

    if args.install_service:
        print()
        install_service()
        return

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
