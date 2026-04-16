# NetConneXion

A modern Windows desktop application for managing network profiles and Wi-Fi connections, built with PySide6 / Qt6.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![UI](https://img.shields.io/badge/UI-PySide6%20%2F%20Qt6-green)

[Русский](README.md)

---

## Features

### Network Profiles
- Create, edit, and delete IP configuration profiles (IP address, subnet mask, gateway, DNS)
- Apply any profile with a single click via `netsh`
- Auto-switch profile by Wi-Fi SSID (connect to a network → profile activates automatically)
- Import / export profiles as JSON

### Wi-Fi Manager
- Scan and display nearby networks (SSID, signal, security, channel, band, speed)
- Connect to saved or new networks; passwords encrypted with Windows DPAPI or system keyring
- View and manage saved Wi-Fi profiles

### Network Tools
| Tool | Description |
|------|-------------|
| Ping | ICMP ping with statistics |
| DNS Lookup | Forward / reverse DNS resolution |
| Port Scanner | Single ports, comma-separated lists, or ranges (e.g. `22,80,443,8000-8100`) |
| Traceroute | Network path tracing |
| Netstat | Live connections table (Protocol / Local / Remote / State) |
| ARP Table | ARP cache with IP → MAC → Interface mapping |
| Network Adapters | All network interface parameters (equivalent to `ipconfig /all`) |
| Route Table | Windows routing table (IPv4 / IPv6) |
| HTTP Check | HTTP/HTTPS response time and status code |
| SSL Certificate | TLS certificate details (subject, issuer, validity, SAN, cipher) |
| Wi-Fi Signal Monitor | Real-time dBm / quality graph, roaming event log |
| DNS Cache | View and flush the Windows DNS cache |
| IP Batch Check | Bulk IP reachability check from CSV or Excel: ping + reverse DNS, export results |

### History
- Full log of profile applications with timestamps and before/after state
- One-click rollback to any previous configuration

### Settings
- Light / dark theme
- Language selection (Russian / English)
- Minimize to tray, start minimized, start with Windows
- Auto-scan interval for Wi-Fi
- Auto-apply profile on Wi-Fi SSID change

---

## Requirements

- Windows 10 / 11
- Python 3.10+
- Administrator privileges (required for `netsh` commands)

```
PySide6 >= 6.5
pywin32 >= 306   # Windows DPAPI password encryption (recommended)
keyring >= 25.0  # Fallback password storage (if pywin32 is unavailable)
openpyxl >= 3.1  # Excel support for IP Batch Check
```

---

## Installation

```bash
git clone https://github.com/mishamv/NetConneXion.git
cd NetConneXion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Optional: enable DPAPI password encryption
pip install pywin32
python .venv\Scripts\pywin32_postinstall.py -install
```

---

## Running

```bash
# Run as administrator for full netsh access
python -m quickip
```

Or right-click → "Run as administrator" in your file manager.

---

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

---

## Security

- Wi-Fi passwords are encrypted at rest using **Windows DPAPI** (machine + user binding) via `pywin32`
- If `pywin32` is unavailable, the app falls back to the system **keyring** (Windows Credential Manager)
- Passwords are decrypted in-memory only at connection time and never written to disk in plaintext
- Legacy base64-encoded profiles are automatically migrated on first connect

---

## Building an Executable

```bash
# Install build dependencies (once)
pip install pyinstaller pillow

# Build
python -m PyInstaller NetConneXion.spec --clean --noconfirm
```

Or simply run `build.bat`. Output: `dist\NetConneXion\NetConneXion.exe`.
