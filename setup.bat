@echo off
echo Installing Driver Update Tool dependencies...
pip install -r requirements.txt
echo.
echo Done! To run the tool:
echo   python main.py            (scan only, no install)
echo   Run run_admin.bat         (scan + install, full features)
pause
