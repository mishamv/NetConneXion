# Quick IP Change — Architecture & Implementation Plan

## Architectural style

**Recommended: Hybrid MVP + Event-driven services**

- **MVP for Tkinter screens**:
  - `View` = Tkinter widgets only (no business rules).
  - `Presenter` = orchestrates UI state and calls domain services.
  - Keeps UI testable and easy to scale when tabs/features grow.
- **Event bus for cross-cutting flows**:
  - Network change detected, profile applied, history recorded, tray refresh, toast notify.
  - Avoids tight coupling between modules (e.g., tray module should not depend on profile editor).
- **Service layer** for all OS interactions:
  - `netsh`, `ipconfig`, `ping`, DNS checks, updater checks, adapter scan.
  - Isolate side effects and allow mocking in tests.

Why not pure MVC:
- Tkinter code often becomes controller-heavy and stateful.
- MVP keeps update logic in Presenter and allows deterministic tests.

Why not full async-only architecture:
- Tkinter main loop is not async-native.
- Worker threads + queue/event dispatch are simpler and more stable on Windows.

---

## Package-level modular architecture

### 1) `quickip/app`
Application bootstrap and composition root.

- Build dependency graph (services, repositories, presenters).
- Start Tkinter app, tray integration, background watchers.
- Load config (portable/installed mode).

### 2) `quickip/ui`
Tkinter views and UI-only state.

- `main_window.py` (tabs, layout, search/filter widgets).
- `profile_editor_view.py`, `summary_view.py`, `network_tools_view.py`.
- Theme switching hooks.
- Drag&drop integration points (import profiles).

### 3) `quickip/presenters`
MVP presenters per feature.

- `profiles_presenter.py`
- `auto_switch_presenter.py`
- `history_presenter.py`
- `network_tools_presenter.py`
- `settings_presenter.py`

Responsibilities:
- Validate user actions.
- Map UI events to use-cases.
- Subscribe/publish app events.

### 4) `quickip/domain`
Business models and use-cases (framework-agnostic).

- Entities: `Profile`, `AdapterConfig`, `NetworkFingerprint`, `ProfileHistoryEntry`.
- Use-cases:
  - Apply profile
  - Match network to profile
  - Import/export profiles
  - Rollback last apply
  - Gather profile stats
  - Validate IP conflicts

### 5) `quickip/infrastructure`
OS/system adapters and persistence.

- `system/netsh_client.py`
- `system/network_probe.py` (SSID/BSSID/MAC gateway detection)
- `system/process_runner.py`
- `storage/json_profile_repo.py`
- `storage/history_repo.py`
- `update/github_release_client.py`
- `notify/toast_service.py`
- `tray/tray_icon.py`

### 6) `quickip/events`
In-process event bus.

- Typed events:
  - `NetworkChanged`
  - `ProfileApplied`
  - `ProfileApplyFailed`
  - `ProfilesImported`
  - `ThemeChanged`
- Subscription API and thread-safe publish.

### 7) `quickip/shared`
Cross-cutting utilities.

- Logging setup (structured JSON + rotating files).
- DTO mappers.
- App constants / feature flags.
- Thread dispatch helpers (queue -> Tk main thread callbacks).

---

## Suggested directory structure

```text
Quick-IP-change/
├─ app.py                          # thin launcher
├─ quickip/
│  ├─ app/
│  │  ├─ bootstrap.py
│  │  ├─ config.py
│  │  └─ lifecycle.py
│  ├─ ui/
│  │  ├─ main_window.py
│  │  ├─ tabs/
│  │  │  ├─ home_tab.py
│  │  │  ├─ profile_tab.py
│  │  │  ├─ summary_tab.py
│  │  │  └─ tools_tab.py
│  │  ├─ dialogs/
│  │  │  ├─ import_dialog.py
│  │  │  └─ conflict_dialog.py
│  │  └─ dnd.py
│  ├─ presenters/
│  │  ├─ profiles_presenter.py
│  │  ├─ auto_switch_presenter.py
│  │  ├─ tray_presenter.py
│  │  ├─ history_presenter.py
│  │  └─ tools_presenter.py
│  ├─ domain/
│  │  ├─ models.py
│  │  ├─ services/
│  │  │  ├─ profile_apply_service.py
│  │  │  ├─ profile_match_service.py
│  │  │  ├─ import_export_service.py
│  │  │  ├─ history_service.py
│  │  │  └─ conflict_check_service.py
│  │  └─ interfaces.py
│  ├─ infrastructure/
│  │  ├─ system/
│  │  │  ├─ process_runner.py
│  │  │  ├─ netsh_client.py
│  │  │  ├─ network_probe.py
│  │  │  └─ diagnostics.py
│  │  ├─ storage/
│  │  │  ├─ json_profile_repo.py
│  │  │  ├─ json_history_repo.py
│  │  │  └─ settings_repo.py
│  │  ├─ tray/
│  │  │  └─ pystray_adapter.py
│  │  ├─ notify/
│  │  │  └─ win_toast_adapter.py
│  │  └─ update/
│  │     └─ github_updater.py
│  ├─ events/
│  │  ├─ bus.py
│  │  └─ event_types.py
│  └─ shared/
│     ├─ logging.py
│     ├─ threading.py
│     └─ paths.py
├─ profiles.json
├─ history.json
├─ settings.json
├─ installer.iss
├─ docs/
│  ├─ ARCHITECTURE_PLAN.md
│  └─ IMPLEMENTATION_ROADMAP.md
└─ tests/
   ├─ domain/
   ├─ presenters/
   └─ infrastructure/
```

---

## Feature-by-feature design

### 1) Automatic profile switching

**Detection strategy**:
- Primary key: Wi-Fi SSID.
- Secondary key: BSSID/router MAC (or default gateway MAC where possible).
- Optional fallback: adapter name + gateway IP.

**Flow**:
1. `network_probe` polls or listens for connectivity changes.
2. Produces `NetworkFingerprint`.
3. `profile_match_service` resolves mapping `network -> profile_id`.
4. If match found and not already active, call `profile_apply_service`.
5. Publish `ProfileApplied` + write history + notify tray/toast.

**Data model additions**:
- `network_mappings` in settings:
  - `{ "ssid": "OfficeWiFi", "bssid": "AA:BB:...", "profile_id": "uuid" }`

### 2) System tray integration

**Capabilities**:
- Minimize-to-tray.
- Tray menu: show/hide, apply favorite profiles, open tools, exit.
- Dynamic tooltip: active profile and adapter status.
- Global hotkeys for quick apply (configurable).

**Flow**:
- Tray adapter runs own loop/thread.
- Presenter subscribes to `ProfileApplied`, `ProfileApplyFailed`, `NetworkChanged` to update icon/menu state.

### 3) Import/export profiles

**Export**:
- Export selected or all profiles to JSON package with metadata/version.

**Import**:
- File picker + drag&drop path entry.
- Preview conflicts (same name/id/subnet overlap).
- Merge strategies:
  - Skip duplicates
  - Rename imported
  - Replace existing

**Format**:
```json
{
  "schema_version": 1,
  "app": "quick-ip-change",
  "exported_at": "ISO-8601",
  "profiles": []
}
```

### 4) Profile application history

**Stored fields**:
- timestamp, profile_id/name, adapter, old/new config, result, duration, error_text.

**Features**:
- List with filters (success/fail/date/profile).
- One-click rollback (apply stored previous config snapshot).
- Stats: total applies, failure rate, most used profile, avg apply time.

### 5) Advanced network tools

Tools surface in separate tab with async execution:
- Ping (host + count + timeout).
- DNS resolution test (A/AAAA lookup + optional custom DNS server).
- Netstat snapshot (active connections / listening ports).
- FlushDNS (`ipconfig /flushdns`).
- TCP/IP reset (`netsh int ip reset`).

All commands routed via `diagnostics.py` to centralize command invocation and logging.

### 6) UX / UI enhancements

- Search + filter profile list (name, adapter, tags, type DHCP/static).
- Grouping (by adapter/site/custom tag).
- Dark theme toggle (persisted in settings).
- Duplicate profile action (copy with sanitized new name).

### 7) Technical improvements

- Structured logging with correlation id per operation.
- IP conflict pre-check before apply:
  - ARP/ping probe and local subnet collision heuristic.
- Auto-update via GitHub Releases:
  - Check latest version, prompt user, download installer/exe, restart flow.
- Portable mode:
  - If `portable.flag` exists near exe -> store config/history/profiles locally.
  - Otherwise use `%AppData%/QuickIPChange`.

---

## Delivery roadmap (with dependencies)

### Phase 0 — Foundation refactor (mandatory)
- Introduce package structure, MVP split, repositories, event bus.
- Move current monolith logic into services + presenters.
- Add structured logging and centralized process runner.

**Exit criteria**:
- Existing behavior parity preserved.
- Smoke tests pass for create/edit/apply/delete profile.

### Phase 1 — Core value MVP
- Auto profile switching by SSID.
- Tray minimize/show/exit + active profile indicator.
- Import/export JSON (file dialog).
- History logging (apply events + failures).

**Dependencies**:
- Requires event bus + history repo + settings repo from Phase 0.

### Phase 2 — Productivity UX
- Search/filter/grouping.
- Duplicate profile.
- Dark theme.
- Import drag&drop + conflict resolution dialog.

### Phase 3 — Reliability & diagnostics
- Rollback support from history snapshot.
- Ping/DNS/Netstat/FlushDNS/TCP reset tools tab.
- IP conflict checks before apply.

### Phase 4 — Distribution/operations
- Auto-update from GitHub Releases.
- Portable mode support.
- Installer refinements for update path and migration.

---

## Testing strategy

### Unit tests
- Domain services (matching, import conflict merge, history stats).
- Presenters with mocked repositories/services.
- JSON schema compatibility tests for import/export.

### Integration tests
- `netsh_client` and diagnostics command parsing (with recorded fixtures/mocks).
- Event bus thread-safety behavior.
- Portable vs installed path resolution.

### End-to-end smoke (Windows CI/self-hosted)
- Launch app, create profile, apply, verify history entry.
- Simulate network change event and ensure mapped profile auto-applies.

### Non-functional checks
- Logging schema validation.
- Startup time and apply latency benchmarks.

---

## Recommended libraries (minimal set)

- **Tray**: `pystray` (+ `Pillow` for icon handling).
- **Toast notifications**: `win10toast` (lightweight) or `winotify` (richer actions).
- **Auto-update**: no heavy framework; use `httpx`/`requests` + GitHub Releases API.
- **Dark theme switch**:
  - Minimal dependency path: `ttk.Style` custom themes.
  - Optional: `ttkbootstrap` if faster polished theming is needed.
- **Drag & Drop in Tkinter**: `tkinterdnd2` (only if native DnD needed).
- **Hotkeys**: `keyboard` (requires care with privileges) or app-local hotkeys only when focused.

Keep optional dependencies behind feature flags to preserve lean base install.

---

## Async / multithreading plan

Use **Tkinter main thread + worker thread pool**:

Run in worker threads:
- Network monitoring loop (SSID/BSSID polling or event listener).
- Any OS command that can block (`netsh`, `ipconfig`, `ping`, `netstat`).
- Update check/download.
- Conflict probes.

Run on Tk main thread:
- All widget updates.
- Modal dialogs and notifications bound to UI.

Communication model:
- Thread-safe queue/event bus.
- `after(...)` callbacks to marshal updates to UI thread.
- Cancel tokens for long-running tools.

---

## Inter-module API examples (contracts, no implementation)

### Domain models
- `Profile(id, name, adapter, mode, ipv4, mask, gateway, dns, tags)`
- `NetworkFingerprint(ssid, bssid, gateway_ip, adapter_name)`
- `ApplyResult(success, message, duration_ms, previous_config, new_config)`

### Repository interfaces
- `ProfileRepository`
  - `list() -> list[Profile]`
  - `get(profile_id: str) -> Profile | None`
  - `save(profile: Profile) -> None`
  - `delete(profile_id: str) -> None`

- `HistoryRepository`
  - `append(entry: ProfileHistoryEntry) -> None`
  - `query(filter: HistoryFilter) -> list[ProfileHistoryEntry]`
  - `stats() -> HistoryStats`

### Service interfaces
- `ProfileApplyService`
  - `apply(profile_id: str) -> ApplyResult`
  - `rollback(entry_id: str) -> ApplyResult`

- `NetworkMonitorService`
  - `start() -> None`
  - `stop() -> None`
  - emits `NetworkChanged`

- `ProfileMatchService`
  - `resolve(fingerprint: NetworkFingerprint) -> str | None`

- `ImportExportService`
  - `export_profiles(path: str, profile_ids: list[str] | None) -> None`
  - `import_profiles(path: str, strategy: ImportStrategy) -> ImportReport`

- `DiagnosticsService`
  - `ping(host, count, timeout) -> CommandResult`
  - `dns_check(hostname, dns_server=None) -> DnsResult`
  - `netstat() -> CommandResult`
  - `flush_dns() -> CommandResult`
  - `tcp_reset() -> CommandResult`

### Event bus
- `subscribe(event_type, handler) -> Subscription`
- `publish(event) -> None`

Event examples:
- `NetworkChanged(fingerprint)`
- `ProfileApplied(profile_id, result)`
- `ProfileApplyFailed(profile_id, error)`
- `HistoryUpdated(entry_id)`

This contract-first approach allows parallel development of UI, services, and infrastructure.
