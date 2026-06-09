@echo off
cd /d "%~dp0"
python updater.py
python pdfmailDeliver.py
pause
