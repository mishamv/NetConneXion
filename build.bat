@echo off
setlocal

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

:: Очищаем предыдущую сборку
echo [INFO] Cleaning previous build...
if exist build\NetConneXion rmdir /s /q build\NetConneXion
if exist dist\NetConneXion  rmdir /s /q dist\NetConneXion

:: Сборка
echo [INFO] Building...
python -m PyInstaller NetConneXion.spec --clean --noconfirm

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
