#!/usr/bin/env bash
# Creates the virtual environment on first run, installs requirements and starts SQMA.
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
