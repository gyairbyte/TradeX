@echo off
REM TradeX launcher (Windows)
REM Double-click to start the Streamlit dashboard and open the browser.
REM Hands off to TradeX.ps1 so we get proper port-wait + browser-open logic.

setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%SCRIPT_DIR%TradeX.ps1"
endlocal
