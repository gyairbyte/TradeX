@echo off
REM TradeX Stop launcher (Windows)
REM Double-click to stop the TradeX Streamlit dashboard.
REM Hands off to TradeX-Stop.ps1 so we get proper process verification and cleanup.

setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%SCRIPT_DIR%TradeX-Stop.ps1"
endlocal
