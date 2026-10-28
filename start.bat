@echo off
REM Creates the virtual environment on first run, installs requirements and starts SQMA.
cd /d "%~dp0"
if not exist venv (python -m venv venv)
call venv\Scripts\activate
pip install -r requirements.txt
python app.py
pause
