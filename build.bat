@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher not found. Install Python 3.12 for development.
  exit /b 1
)

if not exist .venv (
  py -3.12 -m venv .venv
  if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1

python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building and smoke-testing onedir first...
python -m PyInstaller --noconfirm --clean --windowed --onedir --name XHSCommentCleaner app\main.py
if errorlevel 1 exit /b 1
dist\XHSCommentCleaner\XHSCommentCleaner.exe --smoke-test
if errorlevel 1 exit /b 1

echo Building final onefile executable...
python -m PyInstaller --noconfirm --clean XHSCommentCleaner.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\XHSCommentCleaner.exe
echo Validated onedir: dist\XHSCommentCleaner\XHSCommentCleaner.exe
echo Microsoft Edge is required on the target PC. No Playwright browser is downloaded.
endlocal
