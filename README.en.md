# NetConneXion

NetConneXion is a Windows desktop application that combines network profile management, Wi‑Fi controls, and a collection of network diagnostic tools.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)

[Русская версия](README.md)

## Features

### Network profiles

- Create, copy, edit, and delete IPv4 profiles.
- Configure DHCP or static IP, subnet mask, gateway, and DNS settings.
- Apply a profile to a selected network adapter.
- Import and export profiles as JSON.

### Wi‑Fi

- Scan for visible wireless networks.
- Display SSID, BSSID, signal strength, channel, frequency, speed, and security type.
- Connect to a selected visible network.
- Save network details in the application's profiles.
- View Wi‑Fi profiles stored by Windows.

### Network tools

- Ping and Traceroute.
- DNS Lookup using the system resolver by default, with support for a manually selected DNS server.
- HTTP Check and SSL certificate inspection.
- Network adapters, Netstat, ARP, and route table views.
- Wi‑Fi signal monitor and nearby network list.
- TCP port scanner and Windows DNS cache viewer.
- IPv4 subnet calculator.
- Batch IP checks from CSV/XLSX files with filtering and result export.

### Interface

- Light and dark themes.
- Russian and English languages.
- Start-with-Windows and system tray behavior settings.

## System requirements

- Windows 10 or Windows 11.
- Python 3.10 or newer when running from source.
- Administrator privileges are required only for operations that change Windows network settings.

Main dependencies:

| Package | Version |
|---|---|
| PySide6 | `>=6.7,<7.0` |
| pywin32 | `>=306` |
| keyring | `>=25.1` |
| openpyxl | `>=3.1.2` |
| typing_extensions | `>=4.9` |

## Install from source

```powershell
git clone https://github.com/mishamv/NetConneXion.git
cd NetConneXion
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m quickip
```

If you need to change a network adapter's settings, run the terminal as Administrator when required.

## Data storage

- In standard mode, user data is stored in `%PROGRAMDATA%\NetConneXion`.
- For portable mode, create `portable.flag` next to the executable; data will then be stored in the adjacent `data` directory.
- Wi‑Fi secrets are protected with Windows DPAPI, with the operating system credential store used as a fallback.

## Project structure

```text
NetConneXion/
├── quickip/
│   ├── app/             # application startup and composition
│   ├── core/            # configuration, storage, and security
│   ├── domain/          # domain models
│   ├── events/          # application events
│   ├── features/        # profiles, Wi-Fi, and network tools
│   ├── infrastructure/  # Windows integration and process execution
│   ├── shared/          # shared helpers and paths
│   └── ui_qt/           # PySide6 UI, themes, and widgets
├── data/                # localizations and UI resources
├── tests/               # automated tests
├── requirements.txt
└── NetConneXion.spec
```

## Tests

```powershell
python -m pytest -q
```

## Build an EXE

Install PyInstaller and run the build:

```powershell
python -m pip install pyinstaller
python -m PyInstaller NetConneXion.spec --clean --noconfirm
```

The executable will be created in the `dist` directory.

## Security

- Wi‑Fi passwords are not stored as plaintext.
- Windows commands are executed without passing user input through a command shell.
- Imported profile data is validated before use.

## License

Define the project's license terms before public distribution.
