@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python tidak ditemukan. Install Python 3.10+ dari https://www.python.org/downloads/ dulu.
  exit /b 1
)

if not exist ".venv" (
  echo ==^> Membuat virtualenv...
  python -m venv .venv
  if errorlevel 1 (
    echo Gagal bikin virtualenv.
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

echo ==^> Install dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo Gagal install requirements.
  exit /b 1
)

echo ==^> Install Playwright Chromium ^(skip kalau sudah ada^)...
python -m playwright install chromium
if errorlevel 1 (
  echo Gagal install Playwright Chromium.
  exit /b 1
)

if not exist ".env" (
  echo ==^> Membuat .env dari template...
  copy /Y ".env.example" ".env" >nul
)

echo ==^> Menjalankan scraper...
python main.py

endlocal
