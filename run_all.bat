@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem ============================================================
rem  One-click runner for jd-resume-matcher (Windows)
rem  Prefers the official Python on PATH; falls back to the
rem  Python bundled with WorkBuddy if PATH has none.
rem  Double-click this file, or run it from cmd / PowerShell.
rem ============================================================

set "PYBASE=%USERPROFILE%\.workbuddy\binaries\python\versions"
set "PY="

python -V >nul 2>&1
if not errorlevel 1 (
  set "PY=python"
) else (
  if exist "%PYBASE%" (
    for /f "delims=" %%V in ('dir /b /ad "%PYBASE%" 2^>nul') do (
      if exist "%PYBASE%\%%V\python.exe" set "PY=%PYBASE%\%%V\python.exe"
    )
  )
)

if not defined PY goto NOPY

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ============================================================
echo  OFFLINE DEMO ONLY - this script always adds --offline,
echo  so NO model API is called and no API Key is needed.
echo  For real model calls, run the commands manually in the
echo  SAME PowerShell window where you set the API Key.
echo ============================================================
echo.
echo ============================================================
echo  Python in use:
"%PY%" --version
echo ============================================================
echo.
echo  [1/3] DEMO - sample AI intern JD
echo ------------------------------------------------------------
"%PY%" matcher.py --demo --offline
if errorlevel 1 goto FAIL

echo.
echo  [2/3] EVAL - 25 cases, writes reports/eval_report.md
echo ------------------------------------------------------------
"%PY%" matcher.py --eval --offline
if errorlevel 1 goto FAIL

echo.
echo  [3/3] NEGATIVE CASE - should report NO EVIDENCE
echo ------------------------------------------------------------
"%PY%" matcher.py --jd-file sample_jd_negative.txt --offline
if errorlevel 1 goto FAIL

echo.
echo ============================================================
echo  ALL THREE COMMANDS FINISHED.
echo  Reports saved in the "reports" folder.
echo ============================================================
echo.
pause
exit /b 0

:NOPY
echo [ERROR] No usable Python on PATH, and no bundled copy under:
echo   %PYBASE%
echo Install Python 3 from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" during setup)
echo.
pause
exit /b 1

:FAIL
echo [ERROR] A command failed. Read the message above.
echo.
pause
exit /b 1
