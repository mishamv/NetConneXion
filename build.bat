@echo off
chcp 65001 >nul
setlocal

:: Ensure we are always in the project root, regardless of how the bat was launched
cd /d "%~dp0"

echo ============================================
echo  NetConneXion v2.0 -- PyInstaller build
echo ============================================
echo.

:: Use the project-local interpreter directly. Activation scripts may contain
:: stale absolute paths when a workspace has been moved or copied.
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Project virtual environment not found: %PYTHON%
    if not defined CI pause
    exit /b 1
)

if not exist "%CD%\requirements.lock" (
    echo [ERROR] Dependency lockfile not found: %CD%\requirements.lock
    if not defined CI pause
    exit /b 1
)

:: Synchronize every build with the reviewed dependency lockfile.
echo [INFO] Installing locked dependencies...
"%PYTHON%" -m pip install --requirement "%CD%\requirements.lock"
if errorlevel 1 (
    echo [ERROR] Locked dependency installation failed.
    if not defined CI pause
    exit /b 1
)

"%PYTHON%" -m pip check
if errorlevel 1 (
    echo [ERROR] Installed dependencies are inconsistent.
    if not defined CI pause
    exit /b 1
)

:: Stop a running application before replacing its executable.
:: Use the current elevated token when available; otherwise elevate taskkill only.
echo [INFO] Terminating running instance (if any)...
tasklist /FI "IMAGENAME eq NetConneXion.exe" /NH | find /I "NetConneXion.exe" >nul
if not errorlevel 1 (
    net session >nul 2>&1
    if not errorlevel 1 (
        taskkill /f /t /im NetConneXion.exe >nul 2>&1
    ) else (
        powershell -NoProfile -Command "Start-Process taskkill -ArgumentList '/f /t /im NetConneXion.exe' -Verb RunAs -Wait -WindowStyle Hidden" >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

:: Clean previous build output.
echo [INFO] Cleaning previous build...
if exist build\NetConneXion rmdir /s /q build\NetConneXion
if exist dist\NetConneXion  rmdir /s /q dist\NetConneXion

:: Build the application.
echo [INFO] Building...
"%PYTHON%" -m PyInstaller NetConneXion.spec --clean -y

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    if not defined CI pause
    exit /b 1
)

echo.
echo [OK] Build complete: dist\NetConneXion\NetConneXion.exe
echo.

:: Report executable size.
for %%F in (dist\NetConneXion\NetConneXion.exe) do (
    echo EXE size: %%~zF bytes
)

if not defined CI pause
