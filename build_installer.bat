@echo off
setlocal
chcp 65001 > nul

echo ============================================
echo  NetConneXion v2.0 -- Full installer build
echo ============================================
echo.

:: ── 1. PyInstaller build ────────────────────────────────────────────────────

call build.bat
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed — installer not created.
    pause
    exit /b 1
)

:: ── 2. Verify build output exists ───────────────────────────────────────────

if not exist "dist\NetConneXion\NetConneXion.exe" (
    echo [ERROR] dist\NetConneXion\NetConneXion.exe not found.
    pause
    exit /b 1
)

:: ── 3. Create output directory ───────────────────────────────────────────────

if not exist installer mkdir installer

:: ── 4. Find Inno Setup compiler ──────────────────────────────────────────────

set ISCC=
for %%P in (
    "%ProgramFiles(x86)%\Inno Setup 6\iscc.exe"
    "%ProgramFiles%\Inno Setup 6\iscc.exe"
    "%ProgramFiles(x86)%\Inno Setup 5\iscc.exe"
    "%ProgramFiles%\Inno Setup 5\iscc.exe"
) do (
    if exist %%P (
        set ISCC=%%P
        goto :found_iscc
    )
)

echo [ERROR] Inno Setup compiler (iscc.exe) not found.
echo         Install Inno Setup from https://jrsoftware.org/isinfo.php
pause
exit /b 1

:found_iscc
echo [INFO] Using Inno Setup: %ISCC%
echo.

:: ── 5. Compile installer ─────────────────────────────────────────────────────

echo [INFO] Compiling installer...
%ISCC% NetConneXion.iss
if errorlevel 1 (
    echo.
    echo [ERROR] Inno Setup compilation failed.
    pause
    exit /b 1
)

:: ── 6. Done ──────────────────────────────────────────────────────────────────

echo.
echo ============================================
echo  [OK] Installer ready:
echo       installer\NetConneXion_Setup_v2.0.0.exe
echo ============================================
echo.

for %%F in (installer\NetConneXion_Setup_v2.0.0.exe) do (
    echo Size: %%~zF bytes
)

pause
