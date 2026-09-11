@echo off
rem ============================================================
rem  Start the browser bridge (bridge-agent) - http://127.0.0.1:8080
rem  ASCII-ONLY ON PURPOSE: cmd.exe parses .bat/.cmd with the OEM code
rem  page (GBK here), so non-ASCII comments can get garbled and break
rem  the script (see DSH upgrade report section 8.8, pitfall A).
rem  - auto-detects the conda env "lzstudy", falls back to system python
rem  - starts the server minimized, then health-checks it
rem  - keep the window open; close it or Ctrl+C to stop
rem ============================================================
chcp 65001 >nul
setlocal
cd /d %~dp0

set "PY="
set "CAND=%USERPROFILE%\miniconda3\envs\lzstudy\python.exe"
if exist "%CAND%" set "PY=%CAND%"
if not defined PY (
  set "CAND=%USERPROFILE%\Anaconda3\envs\lzstudy\python.exe"
  if exist "%CAND%" set "PY=%CAND%"
)
if not defined PY set "PY=python"

echo [bridge] python    : %PY%
echo [bridge] directory : %CD%
echo [bridge] starting  : 127.0.0.1:8080 ...
echo [bridge] keep this window open; close it or Ctrl+C to stop
echo ------------------------------------------------------------

start "dsh-bridge" /min "%PY%" bridge\server.py

rem health check (up to ~10s)
set "OK="
for /L %%i in (1,1,20) do (
  timeout /t 1 /nobreak >nul
  curl -s http://127.0.0.1:8080/api/health >nul 2>&1 && set OK=1 && goto :up
)
echo [bridge] HEALTH CHECK FAILED - see the minimized window for errors
pause
exit /b 1

:up
echo ------------------------------------------------------------
echo [bridge] UP - health check passed: http://127.0.0.1:8080/api/health
echo [bridge] The browser extension must be loaded from:
echo [bridge]   %CD%\extension   (edge://extensions / chrome://extensions
echo [bridge]    - developer mode - Load unpacked)
echo ------------------------------------------------------------
pause
