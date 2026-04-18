@echo off
setlocal

:: Ensure we are always in the project root, regardless of how the bat was launched
cd /d "%~dp0"

echo ============================================
echo  NetConneXion v2.0 -- PyInstaller build
echo ============================================
echo.

:: Активируем venv
call .venv\Scripts\activate.bat

:: Проверяем pyinstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not found, installing...
    pip install pyinstaller
)

:: Проверяем pywin32
python -c "import win32crypt" >nul 2>&1
if errorlevel 1 (
    echo [INFO] pywin32 not found, installing...
    pip install pywin32
    python Scripts\pywin32_postinstall.py -install 2>nul
)

:: Завершаем процесс если запущен.
:: NetConneXion.exe запускается с UAC (admin), поэтому taskkill требует прав admin.
:: Если скрипт уже запущен от admin — используем taskkill напрямую.
:: Если нет — поднимаем только taskkill через PowerShell RunAs.
echo [INFO] Terminating running instance (if any)...
net session >nul 2>&1
if not errorlevel 1 (
    taskkill /f /t /im NetConneXion.exe >nul 2>&1
) else (
    powershell -NoProfile -Command "Start-Process taskkill -ArgumentList '/f /t /im NetConneXion.exe' -Verb RunAs -Wait -WindowStyle Hidden" >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: Очищаем предыдущую сборку
echo [INFO] Cleaning previous build...
if exist build\NetConneXion rmdir /s /q build\NetConneXion
if exist dist\NetConneXion  rmdir /s /q dist\NetConneXion

:: Сборка
echo [INFO] Building...
python -m PyInstaller NetConneXion.spec --clean

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [OK] Build complete: dist\NetConneXion\NetConneXion.exe
echo.

:: Проверяем размер
for %%F in (dist\NetConneXion\NetConneXion.exe) do (
    echo EXE size: %%~zF bytes
)

pause
