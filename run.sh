#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python tidak ditemukan. Install Python 3.10+ dulu."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "==> Membuat virtualenv..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Install dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Install Playwright Chromium (skip kalau sudah ada)..."
python -m playwright install chromium

if [ ! -f ".env" ]; then
  echo "==> Membuat .env dari template..."
  cp .env.example .env
fi

echo "==> Menjalankan scraper..."
python main.py
