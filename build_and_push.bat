@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT=C:\Users\mishamv\Project Python\NetConneXion-claude"
cd /d "%PROJECT%"

echo ============================================================
echo  NetConneXion — Git Push + PyInstaller Build
echo ============================================================
echo.

:: ── 1. Снимаем lock если остался ────────────────────────────
if exist ".git\index.lock" (
    echo [1/5] Removing stale git index.lock...
    del /f ".git\index.lock"
)

:: ── 2. Git commit ────────────────────────────────────────────
echo [2/5] Staging all changes...
git add -A

echo [2/5] Committing...
git commit -m "Vault v3: remove hardcoded entropy seed + security hardening

Vault v3 entropy scheme:
- Remove hardcoded _APP_ENTROPY_SEED from source code and binary
- Per-installation 32-byte random seed stored in
  %PROGRAMDATA%\NetConneXion\entropy_seed.bin (generated at first launch)
- Entropy = HMAC-SHA256(file_seed, HKCU_user_key) - nothing useful in source
- Backward compat: dpapi2: blobs fallback to legacy seed, then VaultPortabilityError
- New blobs use dpapi3: prefix; protect_text() always writes v3
- Tests: TestGetOrCreateAppSeed (5 tests) + TestVaultEntropy extended

P0 Security (previous commits):
- Block b64 credentials (T1552.001) - require re-save
- Remove WEP from supported auth options
- SSID quoting in all netsh commands
- IPv4 validation in NetshClient
- Secure wipe of temp XML before unlink
- netsh success check: exit_code only (no substring match)

P1 Performance / Reliability:
- ScannerService: MAX_SCAN_HOSTS limit, lazy generator, bounded TCP pool
- ManagedProcess: terminate-wait-kill cleanup (no zombies)
- scan_networks: return cache during active scan
- Keyring vault: UUID-keyed secrets (no SSID collisions)
- Keyring backend validation: verify actual backend class

Features:
- Auto-switch service with SSID-based profile matching
- privilege_check.py: elevation detection + UAC split-token explanation
- Elevation warning banner in UI (post-UAC-cancel scenario)
- Access Denied detection in NetshClient with actionable message

Multi-user DPAPI fix:
- ConnectResult.needs_reauth for VaultPortabilityError cross-user
- WifiPresenter.reauth_connect(): reconnect + re-encrypt under current account
- WifiPage: reauth_needed signal + password dialog with account explanation

spec: add quickip.shared.privilege_check + auto_switch hiddenimports"

if errorlevel 1 (
    echo.
    echo [WARN] Nothing to commit or commit failed - continuing to push...
)

:: ── 3. Git push ──────────────────────────────────────────────
echo.
echo [3/5] Pushing to GitHub...
git push origin main
if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Check your GitHub credentials.
    echo Tip: run 'git credential-manager' or set up a Personal Access Token.
    pause
    exit /b 1
)
echo [OK] Pushed to https://github.com/mishamv/NetConneXion

:: ── 4. Reproducible locked build ────────────────────────────
echo.
echo [4/5] Building exe...
call build.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above.
    pause
    exit /b 1
)

:: ── 5. Done ──────────────────────────────────────────────────
echo.
echo ============================================================
echo  [OK] Build complete!
echo  Exe: %PROJECT%\dist\NetConneXion\NetConneXion.exe
echo ============================================================
echo.
explorer "%PROJECT%\dist\NetConneXion"
pause
