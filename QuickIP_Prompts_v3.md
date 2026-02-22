# Quick IP Change — Master Prompts v3
# Architecture: Feature-based (Vertical Slices)
# Source: Quick-IP-change_v2 (reference for logic, not structure)

---

## GLOBAL QUALITY RULES
> Apply to ALL steps without exception.

- **Language**: all comments, docstrings, log messages — English only
- **File size**: 350–550 lines hard limit. If a file exceeds 550 lines — split it
- **Minimal changes**: touch only files explicitly listed in the step. Do not refactor unrelated code
- **DI convention**: `View(parent, presenter)`, `Presenter(container: ServiceContainer)`
- **Ambiguity**: if something is unclear — add `# Assumption: <explanation>` comment and proceed
- **No cross-feature imports**: features import only from `quickip/core/`. Features never import from each other
- **Inter-feature communication**: only via `core/events/bus.py` (publish/subscribe)
- **OS commands**: `core/system/process_runner.ProcessRunner` is the ONLY allowed subprocess wrapper. No direct `subprocess` calls anywhere else
- **Every step response must include**:
  - List of created/modified files with line counts
  - Section "Out-of-scope issues noticed" (do not fix — just list)

---

## TARGET STRUCTURE

```
quickip/
├── core/
│   ├── models.py
│   ├── interfaces.py
│   ├── events/
│   │   ├── bus.py
│   │   └── types.py
│   ├── system/
│   │   └── process_runner.py
│   ├── security/
│   │   └── vault.py
│   ├── storage/
│   │   └── base_repo.py
│   ├── ui/
│   │   ├── dialogs.py
│   │   └── theme.py
│   ├── tray/
│   │   └── tray_icon.py
│   ├── i18n.py
│   ├── logging.py
│   └── paths.py
│
├── features/
│   ├── profiles/
│   │   ├── view.py
│   │   ├── presenter.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── import_export.py
│   ├── wifi/
│   │   ├── view/
│   │   │   ├── wifi_view.py
│   │   │   ├── networks_panel.py
│   │   │   ├── profiles_panel.py
│   │   │   └── options_panel.py
│   │   ├── presenter.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── netsh_parser.py
│   │   └── xml_builder.py
│   ├── tools/
│   │   ├── view/
│   │   │   ├── tools_view.py
│   │   │   ├── connections_panel.py
│   │   │   ├── console_panel.py
│   │   │   ├── adapters_panel.py
│   │   │   └── scanner_panel.py
│   │   ├── presenter.py
│   │   ├── repository.py
│   │   └── services/
│   │       ├── connections.py
│   │       ├── adapters.py
│   │       ├── scanner.py
│   │       └── console.py
│   ├── history/
│   │   ├── view.py
│   │   ├── presenter.py
│   │   └── repository.py
│   └── settings/
│       ├── view.py
│       ├── presenter.py
│       └── repository.py
│
└── app/
    ├── bootstrap.py
    └── main_window.py
```

---

## STEP 1 — Core Foundation

**Goal**: move/adapt all shared infrastructure into `quickip/core/`. No new logic — only relocation and import path updates.

### Source files to migrate (from v2):

| Source (v2) | Target (v3) | Action |
|---|---|---|
| `quickip/domain/models.py` | `quickip/core/models.py` | copy, update imports |
| `quickip/domain/interfaces.py` | `quickip/core/interfaces.py` | copy, update imports |
| `quickip/events/bus.py` | `quickip/core/events/bus.py` | copy, update imports |
| `quickip/events/event_types.py` | `quickip/core/events/types.py` | copy, update imports, remove `AutoSwitchTriggered` event |
| `quickip/infrastructure/system/process_runner.py` | `quickip/core/system/process_runner.py` | copy, update imports |
| `quickip/infrastructure/tray/tray_icon.py` | `quickip/core/tray/tray_icon.py` | copy, update imports |
| `quickip/infrastructure/services/i18n_service.py` | `quickip/core/i18n.py` | copy, flatten to single file, update imports |
| `quickip/shared/logging.py` | `quickip/core/logging.py` | copy, update imports |
| `quickip/shared/paths.py` | `quickip/core/paths.py` | copy + add new paths (see below) |
| `quickip/ui/dialogs.py` | `quickip/core/ui/dialogs.py` | copy, update imports |
| `quickip/ui/theme.py` | `quickip/core/ui/theme.py` | copy, update imports |

### New files to create:

**`quickip/core/storage/base_repo.py`**
Base JSON repository. Extracted common pattern from v2 `json_profile_repo.py`:
```python
class BaseJsonRepository:
    def __init__(self, file_path: Path) -> None: ...
    def _load_raw(self) -> list[dict]: ...   # load JSON array, return [] on missing/corrupt
    def _save_raw(self, data: list[dict]) -> None: ...  # atomic write via temp file + rename
```
Atomic write pattern: write to `<file>.tmp`, then `os.replace(tmp, target)`.

**`quickip/core/security/vault.py`** — NEW (DPAPI wrapper)

```python
class VaultUnavailableError(Exception):
    """Raised when pywin32 is not installed."""

class VaultPortabilityError(Exception):
    """Raised when data was encrypted on a different machine/user."""

def protect_text(plaintext: str) -> str:
    """
    Encrypt plaintext string using Windows DPAPI.
    Returns base64-encoded ciphertext.
    Raises VaultUnavailableError if pywin32 is not installed.
    """

def unprotect_text(ciphertext: str) -> str:
    """
    Decrypt base64-encoded DPAPI ciphertext.
    Raises VaultUnavailableError if pywin32 is not installed.
    Raises VaultPortabilityError if data was encrypted by different user/machine.
    """
```

Implementation notes:
- Use `win32crypt.CryptProtectData` / `CryptUnprotectData`
- `protect_text`: `win32crypt.CryptProtectData(plaintext.encode('utf-8'), None, None, None, None, 0)` → base64
- `unprotect_text`: base64 decode → `CryptUnprotectData` → decode utf-8
- On `ImportError` of `win32crypt` → raise `VaultUnavailableError`
- On `pywintypes.error` during unprotect → raise `VaultPortabilityError`
- **No silent plaintext fallback** — fail loudly

**`quickip/core/paths.py`** — extend existing paths with:
```python
def get_wifi_profiles_file() -> Path:    # → data/wifi_profiles.json
def get_wifi_options_file() -> Path:     # → data/wifi_options.json
def get_tools_settings_file() -> Path:  # → data/tools_settings.json
```

### requirements.txt update:
Add `pywin32>=306` if not present.

### __init__.py files:
Create empty `__init__.py` in every new package:
`quickip/core/`, `quickip/core/events/`, `quickip/core/system/`, `quickip/core/security/`,
`quickip/core/storage/`, `quickip/core/ui/`, `quickip/core/tray/`,
`quickip/features/`

### Validation:
After completing Step 1, run:
```bash
python -c "from quickip.core.models import Profile; from quickip.core.events.bus import get_event_bus; from quickip.core.security.vault import protect_text; print('core OK')"
```
Fix any import errors before proceeding.

---

## STEP 2 — App Shell (bootstrap + main_window)

**Goal**: rewrite `app/bootstrap.py` and `app/main_window.py` to use new `core/` paths and new `features/` structure. At this step features are NOT yet implemented — use stub views as placeholders.

### `quickip/app/bootstrap.py`

Rewrite `ServiceContainer` to import from `quickip.core.*`:

```python
from quickip.core.events.bus import EventBus, get_event_bus
from quickip.core.logging import setup_logging
from quickip.core.paths import (
    get_log_dir, get_profiles_file, get_history_file,
    get_settings_file, get_mappings_file,
    get_wifi_profiles_file, get_wifi_options_file,
    get_tools_settings_file,
)
from quickip.core.system.process_runner import ProcessRunner
from quickip.core.security.vault import VaultUnavailableError
from quickip.core.i18n import I18nService
```

Keep same `ServiceContainer` structure. Add to container:
```python
self.vault_available: bool  # True if pywin32 is installed, check on init
```

Check vault availability:
```python
try:
    from quickip.core.security.vault import protect_text
    protect_text("test")
    self.vault_available = True
except VaultUnavailableError:
    self.vault_available = False
    logger.warning("DPAPI vault unavailable – pywin32 not installed")
```

Remove from container:
- `self.mapping_repo` (auto-switch removed)
- `self.profile_match` (auto-switch removed)
- `self.conflict_check` (move to features/profiles/service.py in Step 3)

Keep in container (will be used by features):
- `self.event_bus`
- `self.profile_repo` — temporary, will be replaced by `features/profiles/repository.py` in Step 3
- `self.history_repo` — temporary
- `self.settings_repo` — temporary
- `self.process_runner`
- `self.netsh` (NetshClient)
- `self.network_probe`
- `self.toast`
- `self.updater`
- `self.i18n`
- `self.profile_apply` — temporary
- `self.import_export` — temporary
- `self.diagnostics` — temporary

### `quickip/app/main_window.py`

Rewrite to use feature views. Navigation sections: `network`, `wifi`, `history`, `tools`, `settings`.
Remove `dashboard` and `auto_switch` sections entirely.

Nav buttons (sidebar, icon only):
```python
nav = [
    ("network", "🌐"),
    ("wifi",    "📶"),
    ("history", "📜"),
    ("tools",   "🛠"),
    ("settings","⚙️"),
]
```

i18n keys for section titles:
```python
_SECTION_I18N_KEYS = {
    "network":  "section_network",
    "wifi":     "section_wifi",
    "history":  "section_history",
    "tools":    "section_tools",
    "settings": "section_settings",
}
```

Import feature views (these will be stubs at this step):
```python
from quickip.features.profiles.view import ProfilesView
from quickip.features.history.view import HistoryView
from quickip.features.tools.view.tools_view import ToolsView
from quickip.features.wifi.view.wifi_view import WifiView
from quickip.features.settings.view import SettingsView
```

Import feature presenters:
```python
from quickip.features.profiles.presenter import ProfilesPresenter
from quickip.features.history.presenter import HistoryPresenter
from quickip.features.tools.presenter import ToolsPresenter
from quickip.features.wifi.presenter import WifiPresenter
from quickip.features.settings.presenter import SettingsPresenter
```

Create stub placeholders for each feature (simple CTkFrame with a label). These will be replaced in Steps 3–7.

Wiring pattern in `__init__`:
```python
# 1. Bootstrap
self.container = bootstrap(icon_path=icon_path)

# 2. Build shell (sidebar + topbar + content)
self._build_shell()

# 3. Create presenters first
self.profiles_presenter = ProfilesPresenter(self.container)
self.history_presenter  = HistoryPresenter(self.container)
self.tools_presenter    = ToolsPresenter(self.container)
self.wifi_presenter     = WifiPresenter(self.container)
self.settings_presenter = SettingsPresenter(self.container)

# 4. Create views, pass presenter
self.profiles_view = ProfilesView(self.section_frames["network"], self.profiles_presenter)
self.history_view  = HistoryView(self.section_frames["history"],  self.history_presenter)
self.tools_view    = ToolsView(self.section_frames["tools"],      self.tools_presenter)
self.wifi_view     = WifiView(self.section_frames["wifi"],        self.wifi_presenter)
self.settings_view = SettingsView(self.section_frames["settings"],self.settings_presenter)

# 5. Pack views
for view in (self.profiles_view, self.history_view, self.tools_view,
             self.wifi_view, self.settings_view):
    view.pack(fill="both", expand=True)
```

Keep from v2:
- `_ensure_admin()` function
- `TrayIcon` setup with `on_show` / `on_exit` / `on_close`
- `_set_theme()` + `_apply_theme_ui()`
- `_retheme_labels_recursive()`
- `notify_profile_applied()` (used by tray)

Remove from v2:
- All `auto_switch_presenter` references
- `_wire_cross_view()` method (cross-view wiring will be done via EventBus in each feature)
- `DashboardView` import and usage

### Validation:
```bash
python -m quickip
```
Application must launch, show sidebar with 5 nav buttons, stub content areas, no import errors.

---

## STEP 3 — Feature: Profiles

**Goal**: implement `quickip/features/profiles/` — full profiles management page.
Logic source: v2 `quickip/presenters/profiles_presenter.py`, `quickip/ui/profiles_view.py`, `quickip/domain/services/`.

### Files to create:

#### `quickip/features/profiles/repository.py`
Migrate from v2 `quickip/infrastructure/storage/json_profile_repo.py`.
- Inherit from `core.storage.base_repo.BaseJsonRepository`
- Import `Profile`, `IPMode`, `DNSMode` from `quickip.core.models`
- Keep serialization/deserialization logic identical to v2

#### `quickip/features/profiles/service.py`
Consolidate from v2:
- `domain/services/profile_apply_service.py` → `apply_profile()`
- `domain/services/diagnostics_service.py` → `ConflictCheckService`
- `domain/services/profile_match_service.py` → NOT needed (auto-switch removed)

```python
class ProfileService:
    def __init__(self, container: ServiceContainer) -> None: ...

    def apply(self, profile: Profile) -> ApplyResult: ...
    def check_conflicts(self, profiles: list[Profile]) -> list[str]: ...
    def get_adapters(self) -> list[str]: ...
```

#### `quickip/features/profiles/import_export.py`
Migrate from v2 `domain/services/import_export_service.py`.
Keep identical logic — import/export JSON, handle `ImportConflict`, `ImportReport`.

#### `quickip/features/profiles/presenter.py`
Migrate from v2 `quickip/presenters/profiles_presenter.py`.

Constructor:
```python
def __init__(self, container: ServiceContainer) -> None:
    self._container = container
    self._repo = ProfileRepository(get_profiles_file())
    self._service = ProfileService(container)
    self._import_export = ImportExportService(self._repo, container.event_bus)
    self._view: Optional[ProfilesViewProtocol] = None
```

Method `bind_view(view)` — called from `view.__init__`.

Keep all logic from v2 presenter:
- `load_initial()`, `refresh_list()`, `select_profile()`, `save_profile()`
- `delete_profile()`, `apply_profile()`, `import_profiles()`, `export_profiles()`
- Validation: IP/mask/gateway format check, duplicate name check
- Dirty state tracking (unsaved changes dialog)

Publish events from `core.events.types`:
- `ProfileApplied`, `ProfileApplyFailed`, `ProfileCreated`, `ProfileUpdated`, `ProfileDeleted`

#### `quickip/features/profiles/view.py`
Migrate from v2 `quickip/ui/profiles_view.py` (706 lines → split into logical sections within file or submodules if needed to stay under 550 lines).

If file exceeds 550 lines, split:
```
quickip/features/profiles/
    view.py              ← top frame, imports and delegates to panels
    _list_panel.py       ← left: profile list + CRUD buttons
    _form_panel.py       ← right: form fields (IP, mask, gateway, DNS)
    _actions_bar.py      ← top: Apply, Import, Export buttons
```

Constructor: `ProfilesView(parent, presenter: ProfilesPresenter)`
On init: call `presenter.bind_view(self)`, then `presenter.load_initial()`.

Keep from v2:
- Left panel: profile list with adapter filter dropdown + search
- Right panel: form with IP mode toggle, IP/mask/gateway fields, DNS mode toggle, DNS fields
- Adapter filter: "Все адаптеры" + list from `presenter.get_adapters()`
- Dirty state: unsaved changes dialog via `core.ui.dialogs.ask_save_changes()`
- Tags input field
- Apply button (top-right, large)
- Import / Export buttons

Subscribe via EventBus:
```python
container.event_bus.subscribe(ProfileApplied, self._on_profile_applied)
container.event_bus.subscribe(ProfileDeleted, self._on_profile_deleted)
```

Remove from v2:
- `update_wifi_profile_combo()` callback (auto-switch removed)
- `refresh_related_panels` callback to auto-switch

### Validation:
```bash
python -m quickip
```
Navigate to "Сеть" tab. Profile list loads, CRUD works, Apply executes netsh commands.

---

## STEP 4 — Feature: History

**Goal**: implement `quickip/features/history/` — history page.
Logic source: v2 `quickip/presenters/history_presenter.py`, `quickip/ui/history_view.py`.

### Files to create:

#### `quickip/features/history/repository.py`
Migrate from v2 `quickip/infrastructure/storage/json_history_repo.py`.
Inherit from `BaseJsonRepository`. Keep identical serialization.

#### `quickip/features/history/presenter.py`
Migrate from v2 `quickip/presenters/history_presenter.py`.

Constructor:
```python
def __init__(self, container: ServiceContainer) -> None:
    self._container = container
    self._repo = HistoryRepository(get_history_file())
    self._view: Optional[HistoryViewProtocol] = None
```

Method `bind_view(view)`.

Subscribe to `ProfileApplied` and `ProfileApplyFailed` events to auto-refresh list.

Keep: `refresh()`, `get_stats()`, `clear_history()`, `export_history()`, `filter_by_profile()`.

#### `quickip/features/history/view.py`
Migrate from v2 `quickip/ui/history_view.py`.
Constructor: `HistoryView(parent, presenter: HistoryPresenter)`
On init: `presenter.bind_view(self)`, then `presenter.refresh()`.

Keep from v2:
- Table: Date | Profile | Adapter | Status | Duration
- Filter by profile dropdown
- Stats panel (total/success/failed/avg duration)
- Clear history button with confirmation
- Export button (CSV)
- Row click → detail dialog

### Validation:
Apply a profile → switch to History tab → entry appears.

---

## STEP 5 — Feature: Settings

**Goal**: implement `quickip/features/settings/` — settings page (language + theme).

### Files to create:

#### `quickip/features/settings/repository.py`
Thin wrapper around `container.settings_repo` (the existing `JsonSettingsRepository`).
No new file storage needed — delegates to the shared settings file.

```python
class SettingsRepository:
    def __init__(self, container: ServiceContainer) -> None:
        self._repo = container.settings_repo

    def get_language(self) -> str:
        return self._repo.get("language", "ru")

    def set_language(self, lang: str) -> None:
        self._repo.set("language", lang)
        self._repo.save()

    def get_theme(self) -> str:
        return self._repo.get("ui_theme", "light")

    def set_theme(self, theme: str) -> None:
        self._repo.set("ui_theme", theme)
        self._repo.save()
```

#### `quickip/features/settings/presenter.py`

```python
class SettingsPresenter:
    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._repo = SettingsRepository(container)
        self._view: Optional[SettingsViewProtocol] = None

    def bind_view(self, view) -> None: ...

    def load_settings(self) -> None:
        """Load current lang + theme, push to view."""

    def save_language(self, lang: str) -> None:
        """
        Save language to settings.
        Show restart-required dialog.
        On confirm: restart via os.execv(sys.executable, [sys.executable] + sys.argv).
        """

    def save_theme(self, theme: str) -> None:
        """
        Save theme to settings.
        Apply immediately via ctk.set_appearance_mode(theme).
        Publish ThemeChanged event.
        """
```

Language change flow:
1. `self._repo.set_language(lang)`
2. Show dialog: "Для применения языка требуется перезапуск. Перезапустить сейчас?"
3. On Yes: `os.execv(sys.executable, [sys.executable] + sys.argv)`
4. On No: do nothing (language will apply on next manual restart)

#### `quickip/features/settings/view.py`

Constructor: `SettingsView(parent, presenter: SettingsPresenter)`
On init: `presenter.bind_view(self)`, then `presenter.load_settings()`.

Layout:
```
┌─────────────────────────────────────┐
│  Настройки                          │
├─────────────────────────────────────┤
│  Язык интерфейса:  [Русский ▼]      │
│                                     │
│  Тема оформления:  ● Светлая        │
│                    ○ Тёмная         │
│                                     │
│  [Сохранить]                        │
└─────────────────────────────────────┘
```

Language options: `{"ru": "Русский", "en": "English"}`
Theme options: `"light"` / `"dark"`

Subscribe to `ThemeChanged` event to update own colors.

### Validation:
Switch theme → immediate change. Switch language → restart dialog appears.

---

## STEP 6 — Feature: Tools

**Goal**: implement `quickip/features/tools/` — network diagnostics page with 4 tabs.

### Architecture:

```
quickip/features/tools/
    presenter.py
    repository.py
    view/
        tools_view.py        ← tab container
        connections_panel.py ← Tab 1: active TCP/UDP connections
        adapters_panel.py    ← Tab 2: adapter details
        console_panel.py     ← Tab 3: ping/tracert/nslookup
        scanner_panel.py     ← Tab 4: network scanner
    services/
        connections.py
        adapters.py
        console.py
        scanner.py
```

### `quickip/features/tools/repository.py`
Store tools settings (scan interval, last used target, etc.) to `get_tools_settings_file()`.
Inherit `BaseJsonRepository`. Keys: `scan_interval` (default 2), `dns_cache_ttl` (default 600).

### `quickip/features/tools/services/connections.py`

Data source: PowerShell via `process_runner`:
```python
command = [
    "powershell", "-NoProfile", "-NonInteractive", "-Command",
    """
    $tcp = Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,
           RemoteAddress,RemotePort,State,OwningProcess
    $udp = Get-NetUDPEndpoint | Select-Object LocalAddress,LocalPort,OwningProcess
    $procs = Get-Process | Select-Object Id,Name,Path
    @{tcp=$tcp; udp=$udp; procs=$procs} | ConvertTo-Json -Depth 3
    """
]
```

Parse JSON response. Merge process info by PID.

`ConnectionEntry` dataclass:
```python
@dataclass
class ConnectionEntry:
    pid: int
    process_name: str
    process_path: str
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    remote_host: str   # reverse DNS, filled lazily
    protocol: str      # "TCP" / "UDP"
    state: str         # "Established", "Listen", etc.
```

Reverse DNS:
- Lazy lookup: `socket.gethostbyaddr(ip)` in `ThreadPoolExecutor(max_workers=4)`
- Cache: `dict[str, tuple[str, float]]` → `(hostname, timestamp)`
- TTL: 600 seconds (from settings)
- On lookup failure: store `""` in cache to avoid retry storms

Process kill:
```python
def kill_process(self, pid: int, kill_tree: bool = False) -> bool:
    """Kill process by PID. If kill_tree=True, kill child processes first."""
    # Use taskkill /PID {pid} [/T] /F via process_runner
```

Monitoring: start/stop polling at 2s interval via `threading.Timer` (NOT `root.after` — service layer has no Tk reference). UI panel calls `root.after` to pull updates.

#### `quickip/features/tools/services/adapters.py`

```python
command = [
    "powershell", "-NoProfile", "-NonInteractive", "-Command",
    """
    Get-NetAdapter | ForEach-Object {
        $a = $_
        $ip = Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -ErrorAction SilentlyContinue
        $route = Get-NetRoute -InterfaceIndex $a.InterfaceIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue
        $dns = Get-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ErrorAction SilentlyContinue
        @{
            Name=$a.Name; Description=$a.InterfaceDescription; Status=$a.Status
            MacAddress=$a.MacAddress; LinkSpeed=$a.LinkSpeed; MTU=$a.MtuSize
            DriverVersion=$a.DriverVersion; DriverDate=$a.DriverDate
            InterfaceGuid=$a.InterfaceGuid; InterfaceIndex=$a.InterfaceIndex
            IpAddresses=$ip; DefaultGateway=$route.NextHop; DnsServers=$dns.ServerAddresses
            DhcpEnabled=(Get-NetIPInterface -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).Dhcp
        }
    } | ConvertTo-Json -Depth 4
    """
]
```

Parse into `AdapterDetail` dataclass with sections: Identification, State, Driver, IPv4, IPv6.

#### `quickip/features/tools/services/console.py`

Allowed commands (whitelist — no other commands permitted):
```python
ALLOWED_TOOLS = {
    "ping":      ["ping", "{target}", "-n", "{count}"],
    "tracert":   ["tracert", "{target}"],
    "nslookup":  ["nslookup", "{target}"],
    "netstat":   ["netstat", "{flags}"],
    "ipconfig":  ["ipconfig", "{flags}"],
}
```

Target validation — reject if contains any of: ` `, `"`, `'`, `|`, `;`, `&`, `>`, `<`, `\n`, `\r`.
On validation failure: return error string, do NOT run command.

Presets per tool:
```python
PRESETS = {
    "ping":     ["8.8.8.8", "1.1.1.1", "google.com"],
    "tracert":  ["8.8.8.8", "google.com"],
    "nslookup": ["google.com", "cloudflare.com"],
    "netstat":  ["-an", "-b", "-o"],
    "ipconfig": ["/all", "/release", "/renew", "/flushdns"],
}
```

Run via `process_runner.run()` with `timeout=60`. Return `CommandResult`.

#### `quickip/features/tools/services/scanner.py`

Three scan modes:

**Mode 1 — ICMP ping sweep**:
- Input: CIDR (`192.168.1.0/24`) or range (`192.168.1.1-192.168.1.50`)
- Warn if range > 254 hosts
- Use `ThreadPoolExecutor(max_workers=50)`, ping each host with `process_runner`
- Results: `ScanResult(ip, status, rtt_ms, hostname, mac)`
- MAC: attempt ARP lookup after ping

**Mode 2 — ARP table**:
- Parse `arp -a` output via `process_runner`
- Supplement with `Get-NetNeighbor | ConvertTo-Json` for richer data
- Results: IP | MAC | Type (dynamic/static)

**Mode 3 — TCP port scan**:
- Input: target IP/host + comma-separated port list
- Max 100 concurrent connections (socket connect with 1s timeout)
- Use `socket.create_connection((host, port), timeout=1)`
- Warn user if port list > 1000 ports
- Results: Port | Status (open/closed/filtered) | Banner (first 64 bytes if open)

Export to CSV: `features/tools/services/scanner.py` provides `export_csv(results, path)`.

### `quickip/features/tools/presenter.py`

```python
class ToolsPresenter:
    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._repo = ToolsRepository()
        self._connections_svc = ConnectionsService(container.process_runner)
        self._adapters_svc = AdaptersService(container.process_runner)
        self._console_svc = ConsoleService(container.process_runner)
        self._scanner_svc = ScannerService(container.process_runner)
        self._view: Optional[ToolsViewProtocol] = None

    def bind_view(self, view) -> None: ...

    # Connections
    def start_monitoring(self) -> None: ...
    def stop_monitoring(self) -> None: ...
    def get_connections(self) -> list[ConnectionEntry]: ...
    def kill_process(self, pid: int, kill_tree: bool) -> bool: ...

    # Adapters
    def refresh_adapters(self) -> None: ...
    def get_adapter_detail(self, name: str) -> AdapterDetail: ...

    # Console
    def run_command(self, tool: str, target: str, flags: str) -> str: ...

    # Scanner
    def start_scan(self, mode: str, target: str, ports: str) -> None: ...
    def stop_scan(self) -> None: ...
    def export_scan_results(self, path: Path) -> None: ...
```

### `quickip/features/tools/view/tools_view.py`

Tab container using `CTkTabview` with tabs:
1. "Подключения"
2. "Адаптеры"
3. "Консоль"
4. "Сканер"

Constructor: `ToolsView(parent, presenter: ToolsPresenter)`
On init: `presenter.bind_view(self)`, instantiate panels, pass `presenter` to each.

### `quickip/features/tools/view/connections_panel.py`

Table columns: Process | Local IP:Port | Remote IP:Port | Remote Host | Protocol | State | PID | Path

Controls:
- [▶ Start] / [■ Stop] monitoring buttons
- Protocol filter: `CTkSegmentedButton` → TCP / UDP / All
- Search field (filters by process name or IP)

Diff-update algorithm: on each poll compare new snapshot with current rows by `(pid, local_port, remote_port, protocol)` — add new, remove gone. Do NOT rebuild entire table on each update.

Context menu (right-click on row):
- Copy Row
- Copy IP:Port
- Copy PID
- Copy Path
- Kill Process (with confirmation dialog)
- Kill Process Tree (with confirmation dialog)
- Filter by this Process

Pull updates via `root.after(2000, self._poll)` when monitoring is active.

### `quickip/features/tools/view/adapters_panel.py`

Layout: left `CTkScrollableFrame` with adapter list | right `CTkScrollableFrame` with key-value table.

Right panel sections (expandable/collapsible `CTkFrame` with toggle button):
- Identification (Description, GUID, MAC, Interface Index)
- State (Enabled, Link Speed, MTU)
- Driver (Version, Date)
- IPv4 (DHCP, Addresses, Gateway, DNS)
- IPv6 (Addresses, DNS)

Refresh button top-right.

### `quickip/features/tools/view/console_panel.py`

Layout:
```
[Tool dropdown] [Preset dropdown] [Target input] [Flags input] [Run ▶]
─────────────────────────────────────────────────────────────────────
[Output: CTkTextbox, read-only, monospace, scrollable]
[Clear]                                            [Copy Output]
```

- Tool selection updates preset dropdown options
- Output textbox: `CTkTextbox(state="disabled")` — enable temporarily to insert, then disable
- Font: monospace (`Courier New` or `Consolas`, size 11)

### `quickip/features/tools/view/scanner_panel.py`

Layout:
```
Mode: [● ICMP Ping] [○ ARP Table] [○ TCP Ports]

ICMP/TCP: Target: [___________] Ports (TCP only): [____________]
          [▶ Scan]  [■ Stop]  [Export CSV]

Progress: [████████░░░░░░░] 45%

Results table
```

Results table columns per mode:
- ICMP: IP | Status | RTT (ms) | Hostname | MAC
- ARP: IP | MAC | Type
- TCP: Port | Status | Banner

### Validation:
- Connections tab: Start monitoring → rows populate, Stop → polling stops
- Console tab: ping 8.8.8.8 → output appears
- Scanner tab: ICMP scan of /30 subnet → results appear

---

## STEP 7 — Feature: Wi-Fi

**Goal**: implement `quickip/features/wifi/` — Wi-Fi management page.

### Models (define in `quickip/features/wifi/repository.py`):

```python
@dataclass
class WifiNetworkSnapshot:
    ssid: str
    bssid: str
    signal_pct: int
    auth: str
    cipher: str
    channel: int
    freq_ghz: float   # calculated from channel
    mbps: int         # max rate from netsh output
    protocol: str     # 802.11n/ac/ax etc.

@dataclass
class WifiProfile:
    id: str
    ssid: str
    auth: str         # see AUTH_OPTIONS below
    cipher: str
    key_protected: str  # DPAPI base64 blob, "" if open network
    auto_connect: bool
    connect_hidden: bool
    is_adhoc: bool
    created_at: str

@dataclass
class WifiOptions:
    disable_wifi_when_lan: bool = False
    roam_strongest_same_ssid: bool = False
    enable_logging: bool = False
```

Auth options (10 total):
```python
AUTH_OPTIONS = [
    "Open",
    "WEP",
    "WPA-Personal",
    "WPA2-Personal",
    "WPA3-Personal",
    "WPA-Enterprise",
    "WPA2-Enterprise",
    "WPA3-Enterprise",
    "WPA2/WPA3-Transition",
    "OWE",
]
```

### `quickip/features/wifi/repository.py`

Two repositories in one file:

`WifiProfileRepository(BaseJsonRepository)`:
- File: `get_wifi_profiles_file()`
- Methods: `list()`, `get(id)`, `save(profile)`, `delete(id)`, `find_by_ssid(ssid)`

`WifiOptionsRepository(BaseJsonRepository)`:
- File: `get_wifi_options_file()`
- Methods: `load() -> WifiOptions`, `save(options: WifiOptions) -> None`

### `quickip/features/wifi/netsh_parser.py`

Parse `netsh wlan show networks mode=bssid` output.

Frequency calculation from channel number:
```python
# 2.4 GHz band
if 1 <= channel <= 13:
    freq_ghz = round(2.412 + (channel - 1) * 0.005, 3)
elif channel == 14:
    freq_ghz = 2.484
# 5 GHz band — full channel→frequency table
_5GHZ_CHANNELS = {
    36: 5.180, 40: 5.200, 44: 5.220, 48: 5.240,
    52: 5.260, 56: 5.280, 60: 5.300, 64: 5.320,
    100: 5.500, 104: 5.520, 108: 5.540, 112: 5.560,
    116: 5.580, 120: 5.600, 124: 5.620, 128: 5.640,
    132: 5.660, 136: 5.680, 140: 5.700, 144: 5.720,
    149: 5.745, 153: 5.765, 157: 5.785, 161: 5.805,
    165: 5.825,
}
```

Mbps: extract from "Basic rates (Mbps)" and "Other rates (Mbps)" lines, return max value.

Parse `netsh wlan show interfaces` for:
- Adapter name, State (connected/disconnected), SSID, Signal%, Auth, Channel

### `quickip/features/wifi/xml_builder.py`

Build WLANProfile XML for `netsh wlan add profile`.

Auth → XML mapping:
```python
AUTH_XML_MAP = {
    "Open":               ("open",          "none"),
    "WEP":                ("open",          "WEP"),
    "WPA-Personal":       ("WPAPSK",        "TKIP"),
    "WPA2-Personal":      ("WPA2PSK",       "AES"),
    "WPA3-Personal":      ("WPA3SAE",       "AES"),
    "WPA-Enterprise":     ("WPA",           "TKIP"),
    "WPA2-Enterprise":    ("WPA2",          "AES"),
    "WPA3-Enterprise":    ("WPA2",          "AES"),   # Assumption: fallback to WPA2, warn user
    "WPA2/WPA3-Transition":("WPA2PSK",      "AES"),   # Windows handles transition mode
    "OWE":                ("OWE",           "AES"),   # Windows 10 1903+ only
}
```

For WPA3-Enterprise: add `# Assumption: WPA3-Enterprise maps to WPA2 XML — not fully supported by Windows netsh` comment and show warning in UI.

For OWE: add comment `# Assumption: OWE requires Windows 10 build 1903+`.

XML template:
```xml
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID><name>{ssid}</name></SSID>
        <nonBroadcast>{connect_hidden}</nonBroadcast>
    </SSIDConfig>
    <connectionType>{adhoc_or_ESS}</connectionType>
    <connectionMode>{auto_or_manual}</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>{auth}</authentication>
                <encryption>{cipher}</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password_plaintext}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
```

`keyMaterial` receives the **decrypted** password. The XML is written to a temp file, used for `netsh wlan add profile filename=<tmp>`, then deleted immediately.
**Never log or persist the decrypted password.**

### `quickip/features/wifi/service.py`

```python
class WifiService:
    def __init__(self, container: ServiceContainer) -> None:
        self._runner = container.process_runner
        self._vault_available = container.vault_available

    def scan_networks(self) -> list[WifiNetworkSnapshot]:
        """Run netsh wlan show networks mode=bssid, parse, return list."""

    def get_interface_status(self) -> dict:
        """Run netsh wlan show interfaces, parse adapter name/state/SSID."""

    def connect(self, ssid: str, profile: WifiProfile) -> bool:
        """
        1. Decrypt password via vault.unprotect_text(profile.key_protected)
        2. Build XML via xml_builder
        3. Write XML to temp file (tempfile.NamedTemporaryFile)
        4. netsh wlan add profile filename=<tmp>
        5. netsh wlan connect name=<ssid>
        6. Delete temp file
        7. Return success bool
        On VaultPortabilityError: raise (presenter shows error dialog)
        """

    def disconnect(self) -> bool:
        """netsh wlan disconnect"""

    def get_saved_netsh_profiles(self) -> list[str]:
        """netsh wlan show profiles → list of SSID names"""

    def delete_netsh_profile(self, ssid: str) -> bool:
        """netsh wlan delete profile name=<ssid>"""
```

### `quickip/features/wifi/presenter.py`

```python
class WifiPresenter:
    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._profile_repo = WifiProfileRepository()
        self._options_repo = WifiOptionsRepository()
        self._service = WifiService(container)
        self._view: Optional[WifiViewProtocol] = None
        self._status_poll_id = None  # root.after handle

    def bind_view(self, view) -> None: ...

    def scan(self) -> None: ...
    def connect(self, ssid: str) -> None: ...
    def disconnect(self) -> None: ...

    def start_status_polling(self, root) -> None:
        """Poll interface status every 3s via root.after()."""

    def stop_status_polling(self) -> None: ...

    # Profiles
    def load_profiles(self) -> None: ...
    def save_profile(self, profile: WifiProfile) -> None: ...
    def delete_profile(self, profile_id: str) -> None: ...
    def import_profiles(self, path: Path) -> None: ...
    def export_profiles(self, path: Path) -> None: ...

    # Options
    def load_options(self) -> None: ...
    def save_options(self, options: WifiOptions) -> None: ...
```

Connect flow:
1. Look up `WifiProfile` for SSID in `profile_repo.find_by_ssid(ssid)`
2. If found → `service.connect(ssid, profile)`
3. If not found → show dialog "Профиль не найден. Создать новый?", switch to Profiles panel with SSID pre-filled
4. On `VaultPortabilityError` → show error: "Пароль зашифрован на другом устройстве. Введите пароль повторно."

Export format (JSON schema v1):
```json
{
  "schema_version": 1,
  "portable": false,
  "exported_at": "ISO datetime",
  "profiles": [ { ...WifiProfile fields... } ]
}
```
On import: catch `VaultPortabilityError` per profile, collect errors, show summary.

Publish events:
- `WifiNetworksUpdated(networks: list[WifiNetworkSnapshot])`
- `WifiStatusUpdated(status: dict)`
- `WifiProfileSaved(profile: WifiProfile)`
- `WifiProfileDeleted(profile_id: str)`

Add these events to `quickip/core/events/types.py`.

### `quickip/features/wifi/view/wifi_view.py`

Constructor: `WifiView(parent, presenter: WifiPresenter)`
On init: `presenter.bind_view(self)`, build layout, call `presenter.scan()`, `presenter.start_status_polling(root)`.

Top bar:
```
[Adapter: Intel Wi-Fi 6] [Status: Connected — MySSID] [Networks: 12]
                                         [🔍 Scan] [Connect] [Disconnect]
[Search: _____________]
```

Networks table: Signal% | SSID | MAC | Encryption | Channel | GHz | Mbps | Protocol

Signal% column: show as colored bar + number (green ≥ 70%, yellow 40–70%, red < 40%).

Bottom: `CTkSegmentedButton` → "Профили Wi-Fi" | "Параметры Wi-Fi"
Show corresponding panel below.

### `quickip/features/wifi/view/profiles_panel.py`

Left: `CTkScrollableFrame` — saved profiles list, each row: SSID + auth badge (colored label).
Right: form
```
SSID:          [_____________]
Аутентификация:[WPA2-Personal ▼]
Шифрование:    [AES ▼]
Пароль:        [_____________] [👁]
☑ Подключаться автоматически
☐ Скрытая сеть (Hidden SSID)
☐ Ad-hoc сеть

[Добавить] [Удалить] [Импорт] [Экспорт] [Сохранить]
```

Password field: `show="*"` by default, toggle with eye button.
On Save: `vault.protect_text(password)` → store `key_protected` blob.
If `vault_available == False`: show warning "Шифрование паролей недоступно (pywin32 не установлен). Сохранение невозможно." — disable Save button.

Cipher options per auth:
```python
CIPHER_OPTIONS = {
    "Open":                 ["None"],
    "WEP":                  ["WEP"],
    "WPA-Personal":         ["TKIP", "AES"],
    "WPA2-Personal":        ["AES"],
    "WPA3-Personal":        ["AES"],
    "WPA-Enterprise":       ["TKIP", "AES"],
    "WPA2-Enterprise":      ["AES"],
    "WPA3-Enterprise":      ["AES"],
    "WPA2/WPA3-Transition": ["AES"],
    "OWE":                  ["AES"],
}
```
Update cipher dropdown when auth selection changes.

### `quickip/features/wifi/view/options_panel.py`

Three checkboxes:
```
☑ Отключать Wi-Fi при подключении LAN
☐ Автоматически переключаться на более сильный сигнал того же SSID
☐ Включить журналирование Wi-Fi событий

[Сохранить параметры]
```

### Validation:
- Scan → networks table populates
- Status bar updates every 3s
- Save profile → appears in list
- Connect to saved profile (if Wi-Fi available on test machine) → connects

---

## CLEANUP NOTES

After all 7 steps are complete:

1. **Remove v2 legacy directories** (no longer needed):
   - `quickip/domain/`
   - `quickip/events/`
   - `quickip/infrastructure/`
   - `quickip/presenters/`
   - `quickip/shared/`
   - `quickip/ui/` (root-level)

2. **Keep only**:
   - `quickip/core/`
   - `quickip/features/`
   - `quickip/app/`
   - `quickip/__init__.py`
   - `quickip/__main__.py`

3. **Update `__main__.py`**:
   ```python
   from quickip.app.main_window import main
   if __name__ == "__main__":
       main()
   ```

4. **Final smoke test**:
   ```bash
   python -m quickip
   # Navigate all 5 tabs
   # Apply a profile
   # Check history entry created
   # Switch theme
   # Run ping in console
   ```
