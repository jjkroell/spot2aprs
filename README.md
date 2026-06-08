# spot2aprs

Automatically upload your SPOT tracker's GPS position to [APRS-IS](https://www.aprs-is.net/) (the Automatic Packet Reporting System internet network), so your position appears on tracking maps like [aprs.fi](https://aprs.fi) in real time.

The script polls your SPOT device's public feed on a schedule you choose, converts the GPS coordinates into an APRS packet, and uploads it to the global APRS network. It runs continuously in the background, keeps a local history log, and can be installed as a persistent service so it starts automatically after a reboot — no manual intervention needed.

---

## What you need before you start

### 1. A SPOT tracker
Any SPOT Gen3, Gen4, or Spot X device with an active subscription. The device needs to have **Shared Page** / public sharing enabled on your findmespot.com account so the script can read its location.

### 2. Your SPOT Feed ID
This is a unique ID that identifies your device's public data feed. To find it:

1. Log in to [findmespot.com](https://www.findmespot.com)
2. Click **My Account**
3. Click **Get Started** or **Manage SPOT**
4. Go to **Share Your SPOT Location** → **Enable Sharing**
5. Your **Feed ID** will appear — it looks something like `0onlL1MpojDLSzlNpNYRMHuqcMkIl1234`

### 3. An amateur radio callsign
You need a valid amateur radio (ham radio) licence and callsign to transmit on APRS-IS. You cannot use APRS-IS without one. If you are a licensed amateur operator, your callsign will look like `VE7XX`, `W1ABC`, `KD9XYZ`, etc.

### 4. Your APRS-IS passcode
The passcode is a number derived from your callsign that proves you are the owner of it. You only need to calculate it once. Visit **[apps.magicbug.co.uk/passcode](https://apps.magicbug.co.uk/passcode/)**, enter your callsign, and it will show your passcode (a 4–5 digit number). Write it down.

### 5. Python 3.7 or newer

**On Windows:** Download Python from [python.org/downloads](https://www.python.org/downloads/). During installation, check the box that says **"Add Python to PATH"**.

**On macOS:** Open the Terminal app (press `Command+Space`, type `Terminal`). Run:
```
python3 --version
```
If Python is already installed it will show a version number. If not, macOS will prompt you to install it.

**On Linux (Ubuntu/Debian):** Open a terminal and run:
```
sudo apt install python3
```

---

## Quick start

### Step 1 — Download the script

**Easiest method — right-click to save:**

Right-click this link and choose **Save link as...** (Chrome/Edge) or **Save target as...** (Firefox):

[Right-click here → Save link as... → spot2aprs_setup.py](https://raw.githubusercontent.com/jjkroell/spot2aprs/master/spot2aprs_setup.py)

Save it somewhere easy to find — your Desktop or Downloads folder is fine.

> **Windows users:** your browser may save it as `spot2aprs_setup.py.txt`. If that happens, rename the file and remove the `.txt` so the filename ends in `.py` only.

**Alternative — GitHub file viewer:**

1. Go to [https://github.com/jjkroell/spot2aprs/blob/master/spot2aprs_setup.py](https://github.com/jjkroell/spot2aprs/blob/master/spot2aprs_setup.py)
2. Click the **Download raw file** button (downward arrow icon, top right of the file viewer)
3. Save to your Desktop or Downloads folder

### Step 2 — Open a terminal

A terminal is a text-based window where you type commands. You need one to run the script.

**Windows:** Press `Windows key + R`, type `cmd`, press Enter. A black window will open — this is the Command Prompt.

**macOS:** Press `Command + Space`, type `Terminal`, press Enter.

**Linux:** Press `Ctrl + Alt + T`, or search for "Terminal" in your application menu.

### Step 3 — Navigate to where you saved the script

In your terminal, type `cd` followed by the folder where you saved the file. For example:

**Windows (saved to Desktop):**
```
cd %USERPROFILE%\Desktop
```

**macOS/Linux (saved to Desktop):**
```
cd ~/Desktop
```

**macOS/Linux (saved to Downloads):**
```
cd ~/Downloads
```

### Step 4 — Run it

**macOS or Linux:**
```
python3 spot2aprs_setup.py
```

**Windows:**
```
python spot2aprs_setup.py
```

The first time you run it, the **setup wizard** will launch automatically. You only need to do this once — your answers are saved for all future runs. For optional flags you can use after setup, see [Command-line flags](#command-line-flags).

---

## First-run setup wizard — full walkthrough

When you run the script for the first time, it will walk you through a series of questions. Here is every question you will see, what it means, and what to enter.

---

```
═══════════════════════════════════════════════════════
  spot2aprs — Setup
═══════════════════════════════════════════════════════

SPOT Feed ID: log in to findmespot.com →
  My Account → Get Started → Enable Sharing → Feed ID
```

This is the intro screen. It reminds you where to find your Feed ID.

```
SPOT Feed ID:
```

Enter your SPOT Feed ID from your findmespot.com account, it is a long alphanumeric string.

**Example entry:** `0onlL1MpojDLSzlNpNYRMHuqcMkIl1234`

---

```
APRS callsign with SSID (e.g. VE7XX-9):
```

Enter your amateur radio callsign followed by an **SSID** (Secondary Station Identifier). The SSID is a number from 1–15 appended with a dash that distinguishes this station from others you might run. For a mobile/tracking use, **`-9`** is the conventional choice and is what most APRS clients will display as a vehicle icon by default.

**Example entry:** `VE7XX-9`

> Always include the SSID (e.g. `-9`). If you only enter `VE7XX` without an SSID the script will accept it, but `-9` is the right convention for a tracker.

```
APRS-IS passcode:
```

Enter your APRS-IS passcode — the 4–5 digit number you calculated from your callsign at [apps.magicbug.co.uk/passcode](https://apps.magicbug.co.uk/passcode/). As you type, the characters will not be visible on screen (it is treated like a password for security).

**Example entry:** `12345`

If the passcode is wrong, the script will report `APRS-IS rejected login — check callsign and passcode` when it tries to upload.

---

```
Poll interval in minutes (min 3, SPOT allows max every 2.5 min) [10]:
```

How often (in minutes) the script should check your SPOT device for a new position and upload it to APRS-IS. Press **Enter** to accept the default of 10 minutes.

- The minimum is **3 minutes** — SPOT's terms of service prohibit polling more frequently than every 2.5 minutes, so the script enforces a 3-minute floor.
- Your SPOT device itself only sends a new position every 2.5–5 minutes on most subscription plans, so polling faster than that gains you nothing.
- A value of **5–10 minutes** is recommended for most uses.

**Example entry:** `5` (poll every 5 minutes) or press Enter for the default of `10`

---

```
Skip upload if position is older than X minutes [60]:
```

If the most recent position from your SPOT device is older than this many minutes, the script will skip uploading it rather than sending stale data to APRS. Press **Enter** to accept the default of 60 minutes.

This is useful if your SPOT device has been turned off or is indoors and not getting a GPS fix — rather than repeatedly uploading an old position as if it were current, the script will just skip that poll cycle.

**Example entry:** `120` (skip if older than 2 hours) or press Enter for the default of `60`

---

The script now asks you to pick a map icon for your station. APRS icons are defined by two characters entered at two separate prompts — decide which icon you want from the table below first, then you'll enter each character one at a time.

| Symbol | Icon | Table character | Code character |
|--------|------|:-:|:-:|
| `/j` | Jeep (default) | `/` | `j` |
| `/k` | Truck | `/` | `k` |
| `/c` | Canoe | `/` | `c` |
| `/s` | Boat / Ship | `/` | `s` |
| `/'` | Small Aircraft | `/` | `'` |
| `/^` | Large Aircraft | `/` | `^` |
| `/[` | Person / Walker | `/` | `[` |
| `/b` | Bicycle | `/` | `b` |
| `/-` | House / Fixed station | `/` | `-` |
| `/g` | Glider | `/` | `g` |
| `\Y` | Yacht / Sailboat | `\` | `Y` |

```
Symbol table character [/]:
```

Enter the **table character** from the left column of your chosen row above — either `/` or `\`. Almost all common symbols use `/`. Press **Enter** to accept the default `/`.

```
Symbol code character [j]:
```

Enter the **code character** from the right column of your chosen row. Press **Enter** to accept the default `j` (Jeep).

**Example — Truck:** enter `/` at the first prompt, then `k` at the second.

**Example — Sailboat:** enter `\` at the first prompt, then `Y` at the second.

---

```
Extra comment text (optional, press Enter to skip) []:
```

An optional free-text comment that will be appended to every APRS packet. This text is visible to anyone viewing your position on aprs.fi or any other APRS client.

The script automatically includes your device's name, model, message type, and battery state in the comment. Your text here is added after that.

**Example entry:** `Pacific Coast trip` or press Enter to leave it blank.

---

After the last question the script saves your settings and prints:

```
Settings saved to /home/yourname/.spot2aprs.json
```

It then automatically installs a background service so the script keeps running even after you close the terminal and restarts itself after every reboot. You will see something like this (exact output depends on your operating system):

**Linux:**
```
Service installed and started.
  Status:  systemctl --user status spot2aprs
  Logs:    journalctl --user -u spot2aprs -f
  Stop:    systemctl --user stop spot2aprs
```

**macOS:**
```
Service installed and started.
  Logs:    tail -f ~/Library/Logs/spot2aprs.log
  Stop:    launchctl unload ~/Library/LaunchAgents/io.github.spot2aprs.plist
```

**Windows:**
```
Service installed and started.
  Status:  schtasks /query /tn "spot2aprs"
  Logs:    type C:\Users\yourname\spot2aprs_service.log
  Stop:    schtasks /end /tn "spot2aprs"
```

You can now close the terminal. The script is running in the background and will continue uploading your position every X minutes. Your position is now live on [aprs.fi](https://aprs.fi) — search for your callsign.

---

## Your settings and log files

The script stores two files in your home directory:

| File | Purpose |
|------|---------|
| `~/.spot2aprs.json` | Your saved settings (Feed ID, callsign, passcode, etc.) |
| `~/.spot2aprs_log.json` | Local history of the last 24 poll results |

`~` means your home folder:
- **Linux/macOS:** `/home/yourname/` or `/Users/yourname/`
- **Windows:** `C:\Users\yourname\`

These files are created automatically on first run. The settings file has its permissions set to owner-read-only so your passcode is not visible to other users on a shared system.

---

## Command-line flags

These are optional switches you can add after the script name when running it from the terminal. None of them are required for normal operation.

---

### `--reset`

Re-run the setup wizard from scratch, overwriting your saved settings.

```
python3 spot2aprs_setup.py --reset
```

Use this if:
- You got a new SPOT device with a different Feed ID
- You changed your callsign or SSID
- You want to change the poll interval or map symbol
- You entered something wrong during the original setup

The wizard will show your current saved values in square brackets `[like this]` — press Enter to keep them or type a new value.

---

### `--once`

Poll the SPOT API exactly one time, upload to APRS-IS (or report why it was skipped), then exit. Does not loop.

```
python3 spot2aprs_setup.py --once
```

Use this for:
- Testing that your setup is working correctly
- A one-off manual upload without starting the continuous loop
- Confirming what position the SPOT API is currently reporting

Example output:
```
[2026-06-07 20:05:00 UTC] Polling SPOT…
  Position : 49.25431, -123.12345  alt 12m  (3 min ago)
  Comment  : MyName SPOT4 OK Batt:GOOD
  Uploaded to APRS-IS ✓
```

---

### `--verbose`

Show extra technical detail during each poll, including the full API URL being called, the APRS-IS server's login response, and the exact APRS packet string being sent.

```
python3 spot2aprs_setup.py --verbose
```

Example extra output:
```
  Fetching: https://api.findmespot.com/spot-main-web/...
  APRS-IS: # javAPRSSrvr 4.3.0b07
  APRS-IS: # logresp VE7XX-9 verified, server T2CAWEST
  Packet   : VE7XX-9>APRS,TCPIP*:!4915.26N/12307.41Wj000/000/A=000039 MyName SPOT4 OK Batt:GOOD
  Uploaded to APRS-IS ✓
```

Use this when troubleshooting a problem (passcode rejected, API errors, etc.) or if you are curious what is being sent.

Can be combined with `--once`:
```
python3 spot2aprs_setup.py --once --verbose
```

---

### `--log`

Print a formatted table of your last 24 poll results, then exit. Does not start the poll loop.

```
python3 spot2aprs_setup.py --log
```

Example output:
```
#    Polled (UTC)               Lat         Lon   Age  Status
───────────────────────────────────────────────────────────────────────────
1    2026-06-07 19:00:00    49.25431   -123.12345     4m  uploaded
2    2026-06-07 19:10:00    49.25431   -123.12345    14m  uploaded
3    2026-06-07 19:20:00    49.25431   -123.12345    24m  skipped (too old: 61 min)
4    2026-06-07 19:30:00    49.25431   -123.12345     2m  uploaded
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `uploaded` | Position was successfully sent to APRS-IS |
| `skipped (too old: X min)` | Position was older than your max-age setting — not uploaded |
| `fetch_error: ...` | Could not reach the SPOT API (network problem, bad Feed ID, etc.) |
| `aprs_error: ...` | Connected to APRS-IS but upload failed (bad passcode, network drop, etc.) |

The log keeps the last **24 entries** automatically. Once it reaches 24, the oldest entry is dropped when a new one is added. The log file is stored at `~/.spot2aprs_log.json`.

---

### `--install-service`

Install (or reinstall) the background service manually. Under normal use you do not need this flag — the service is installed automatically the first time you run setup. Use this flag only if you previously uninstalled the service and want to reinstall it without re-running the full setup wizard.

```
python3 spot2aprs_setup.py --install-service
```

**On Linux** the script creates a systemd user service:

```
Service installed and started.
  Status:  systemctl --user status spot2aprs
  Logs:    journalctl --user -u spot2aprs -f
  Stop:    systemctl --user stop spot2aprs
```

**On macOS** the script creates a launchd agent in `~/Library/LaunchAgents/`:

```
Service installed and started.
  Logs:    tail -f ~/Library/Logs/spot2aprs.log
  Stop:    launchctl unload ~/Library/LaunchAgents/io.github.spot2aprs.plist
```

**On Windows** the script writes a small launcher file (`~/spot2aprs_service.bat`) and registers it as a Task Scheduler task that runs at logon:

```
Service installed and started.
  Status:  schtasks /query /tn "spot2aprs"
  Logs:    type C:\Users\yourname\spot2aprs_service.log
  Stop:    schtasks /end /tn "spot2aprs"
```

On all platforms the service runs silently in the background. It will start again after every reboot without any action from you.

---

### `--uninstall-service`

Remove the background service installed by `--install-service`.

```
python3 spot2aprs_setup.py --uninstall-service
```

This stops the service, disables it from starting at boot, and deletes the service file. Your config and log files (`~/.spot2aprs.json` and `~/.spot2aprs_log.json`) are left untouched — only the service itself is removed.

---

## Checking that it is working

Once the script is running (or after using `--once`), search for your callsign on **[aprs.fi](https://aprs.fi)**. Your position should appear within a few seconds of a successful upload.

If you do not see your position:
1. Run `python3 spot2aprs_setup.py --once --verbose` and read the output carefully
2. Check that your SPOT device has **Shared Page** enabled at findmespot.com
3. Verify your Feed ID by visiting the SPOT API directly in your browser:
   ```
   https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed/YOUR_FEED_ID/message.json
   ```
   Replace `YOUR_FEED_ID` with your actual Feed ID. You should see JSON data including your coordinates.
4. Check your APRS-IS passcode at [apps.magicbug.co.uk/passcode](https://apps.magicbug.co.uk/passcode/)

---

## Checking service logs

**Linux (systemd):**
```
# See current status
systemctl --user status spot2aprs

# Follow live logs
journalctl --user -u spot2aprs -f

# See last 50 lines
journalctl --user -u spot2aprs -n 50
```

**macOS (launchd):**
```
tail -f ~/Library/Logs/spot2aprs.log
```

**Windows (Task Scheduler):**
```
# Check task status in Command Prompt
schtasks /query /tn "spot2aprs"

# View the log file in Notepad
notepad %USERPROFILE%\spot2aprs_service.log

# Or print it in Command Prompt
type %USERPROFILE%\spot2aprs_service.log
```

On any platform you can also run `python3 spot2aprs_setup.py --log` to see a formatted summary of the last 24 poll results regardless of how the service is running.

---

## Updating your settings

To change any setting (Feed ID, callsign, interval, symbol, etc.) run:

```
python3 spot2aprs_setup.py --reset
```

Running `--reset` also reinstalls the service automatically with the new settings, so you do not need to do anything extra. If you need to restart the service manually:

**Linux:**
```
systemctl --user restart spot2aprs
```

**macOS:**
```
launchctl unload ~/Library/LaunchAgents/io.github.spot2aprs.plist
launchctl load -w ~/Library/LaunchAgents/io.github.spot2aprs.plist
```

**Windows:**
```
schtasks /end /tn "spot2aprs"
schtasks /run /tn "spot2aprs"
```

---

## How it works

1. The script reads your saved config from `~/.spot2aprs.json`
2. It calls the SPOT API at `api.findmespot.com` to get the latest message from your device
3. It checks the age of the position — if it is older than your `maxage` setting it skips this cycle
4. It converts the GPS coordinates and altitude into an APRS position packet
5. It opens a TCP connection to `rotate.aprs2.net:14580` (the APRS-IS tier-2 network), logs in with your callsign and passcode, sends the packet, and closes the connection
6. The result is written to `~/.spot2aprs_log.json`
7. It sleeps until the next poll interval and repeats

No external libraries beyond `requests` are required. The `requests` library is auto-installed on first run if it is not already present.

---

## Troubleshooting

**`APRS-IS rejected login — check callsign and passcode`**
Your passcode does not match your callsign. Recalculate it at [apps.magicbug.co.uk/passcode](https://apps.magicbug.co.uk/passcode/) and re-enter it with `--reset`.

**`SPOT API returned HTTP 403` or `HTTP 401`**
Your Feed ID is wrong, or Shared Page is not enabled for your device on findmespot.com.

**`SPOT feed returned 0 messages — device may be off or feed is empty`**
The SPOT API returned an empty feed. This usually means your device has not sent any messages recently (it may be indoors, turned off, or on a plan that has lapsed). Check that the device LED is tracking and that you can see messages on your findmespot.com account.

**`Installing 'requests'…` appears every run**
The `requests` package is not installed in a persistent location. This is harmless — it installs silently — but if you want to fix it permanently run: `pip3 install requests`

**Script runs fine manually but the service does not start**
Make sure you ran setup and have a working `~/.spot2aprs.json` before installing the service. Check the service logs (see above) for the exact error.

**Position on aprs.fi is stale / not updating**
Check your `--log` output to see if recent polls are showing `skipped (too old)`. If so, lower your `maxage` setting with `--reset`, or check that your SPOT device is actually transmitting new positions.

---

## License

GPL v3 — see [LICENSE](LICENSE)
