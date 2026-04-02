# NetConneXion

A modern Windows desktop application for managing network profiles and Wi-Fi connections, built with PySide6 / Qt6.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![UI](https://img.shields.io/badge/UI-PySide6%20%2F%20Qt6-green)

## Features

### Network Profiles
- Create, edit, and delete IP configuration profiles (IP address, subnet mask, gateway, DNS)
- Apply any profile with a single click via `netsh`
- Auto-switch profile by Wi-Fi SSID (connect to a network → profile activates automatically)
- Import / export profiles as JSON

### Wi-Fi Manager
- Scan and display nearby networks (SSID, signal, security, channel, band, speed)
- Connect to saved or new networks; save passwords encrypted with Windows DPAPI
- View and manage saved Wi-Fi profiles

### Network Tools
| Tool | Description |
|------|-------------|
| Ping | ICMP ping with statistics |
| DNS Lookup | Forward / reverse DNS resolution |
| Port Scanner | Scan single ports, comma-separated lists, or ranges (e.g. `22,80,443,8000-8100`) |
| Traceroute | Network path tracing |
| Netstat | Live connections table (Protocol / Local / Remote / State / PID) |
| ARP Table | ARP cache with IP → MAC mapping |
| HTTP Check | HTTP/HTTPS response time and status |
| SSL Certificate | TLS certificate details (subject, issuer, validity, SAN, cipher) |
| Route Table | Windows routing table via PowerShell `Get-NetRoute` |
| Wi-Fi Signal Monitor | Real-time dBm / quality graph, roaming event log |

### History
- Full log of profile applications with timestamps and before/after state
- One-click rollback to any previous configuration

### Settings
- Light / dark theme
- Language selection
- Auto-apply profile on Wi-Fi SSID change
- Startup with Windows (optional)

## Requirements

- Windows 10 / 11
- Python 3.10+
- Administrator privileges (required for `netsh` commands)

```
PySide6 >= 6.5
pywin32 >= 306   # Windows DPAPI password encryption (optional but recommended)
```

## Installation

```bash
git clone https://github.com/mishamv/NetConneXion.git
cd NetConneXion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Optional: enable DPAPI password encryption
python -m pip install pywin32
python .venv\Scripts\pywin32_postinstall.py -install
```

## Running

```bash
# Run as administrator for full netsh access
python -m quickip
```

Or right-click → "Run as administrator" in your file manager.

## Project Structure

```
quickip/
  app/              # Bootstrap, DI container, entry point
  domain/           # Domain models and services
  events/           # Event bus
  features/         # Feature modules (profiles, wifi, tools, history, settings)
  ui_qt/            # PySide6 UI layer
    pages/          # Page widgets (profiles, wifi, tools, settings)
    qss/            # Qt stylesheets (dark / light)
    assets/         # Icons and SVG assets
  core/             # Shared infrastructure (process runner, security vault, paths)
data/               # User data (gitignored): profiles, settings, history, logs
```

## Security

- Wi-Fi passwords are encrypted at rest using **Windows DPAPI** (machine + user binding) via `pywin32`
- Passwords are decrypted in-memory only at connection time and never written to disk in plaintext
- If `pywin32` is unavailable the app falls back to connecting via existing Windows WLAN profiles

## Building an Installer

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --onefile ^
  --name NetConneXion ^
  --add-data "quickip;quickip" ^
  --add-data "data/locales;data/locales" ^
  -m quickip
```

Then run Inno Setup on the generated spec for a proper Windows installer.

