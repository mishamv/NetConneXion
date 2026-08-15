@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Always run from the project root.
cd /d "%~dp0"

echo ============================================
echo  NetConneXion v2.0 -- Full installer build
echo ============================================
echo.

:: Step 1: PyInstaller build

call build.bat
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed -- installer not created.
    if not defined CI pause
    exit /b 1
)

:: Step 2: Verify build output

if not exist "dist\NetConneXion\NetConneXion.exe" (
    echo [ERROR] dist\NetConneXion\NetConneXion.exe not found.
    if not defined CI pause
    exit /b 1
)

:: Step 3: Create output directory

if not exist installer mkdir installer

:: Step 4: Find Inno Setup compiler
:: Pre-expand ProgramFiles paths before using inside for() to avoid bracket issues

set "PF=%ProgramFiles%"
set "PF86=%ProgramFiles(x86)%"

set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\iscc.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\iscc.exe"
if exist "%PF86%\Inno Setup 6\iscc.exe" set "ISCC=%PF86%\Inno Setup 6\iscc.exe"
if exist "%PF%\Inno Setup 6\iscc.exe"   set "ISCC=%PF%\Inno Setup 6\iscc.exe"
if exist "%PF86%\Inno Setup 5\iscc.exe" set "ISCC=%PF86%\Inno Setup 5\iscc.exe"
if exist "%PF%\Inno Setup 5\iscc.exe"   set "ISCC=%PF%\Inno Setup 5\iscc.exe"

if "!ISCC!"=="" (
    echo [ERROR] Inno Setup compiler ^(iscc.exe^) not found.
    echo         Install Inno Setup from https://jrsoftware.org/isinfo.php
    if not defined CI pause
    exit /b 1
)

echo [INFO] Inno Setup: !ISCC!
echo.

:: Step 5: Compile installer

echo [INFO] Compiling installer...
"!ISCC!" NetConneXion.iss
if errorlevel 1 (
    echo.
    echo [ERROR] Inno Setup compilation failed.
    if not defined CI pause
    exit /b 1
)

if not exist "installer\NetConneXion_Setup_v2.0.1.exe" (
    echo.
    echo [ERROR] Installer output was not created.
    if not defined CI pause
    exit /b 1
)

:: Step 6: Done

echo.
echo ============================================
echo  [OK] Installer ready:
echo       installer\NetConneXion_Setup_v2.0.1.exe
echo ============================================
echo.

for %%F in ("installer\NetConneXion_Setup_v2.0.1.exe") do (
    echo Size: %%~zF bytes
)

if not defined CI pause
