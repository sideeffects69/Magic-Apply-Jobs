@echo off
REM
REM Author:  Om Abhyankar
REM License: MIT License
REM          https://opensource.org/license/mit
REM GitHub:  https://github.com/sideeffects69
REM
REM One-click launcher for Windows. Double-click this file. The first time, it
REM checks your computer and installs anything that is missing (Python, Google
REM Chrome and the tool's packages), then opens the control panel in your web
REM browser. Safe to run again any time.
REM
REM NOTE: This script deliberately avoids nested `if ( ... )` blocks. cmd.exe's
REM parser for parenthesized blocks is fragile once you nest one `if ( ... )`
REM inside another (fails with "... was unexpected at this time." on some
REM Windows/cmd.exe builds) - flat `if ... goto` control flow works everywhere.

setlocal
cd /d "%~dp0"

echo.
echo ========================================================
echo   Magic Apply - Jobs - starting your control panel
echo ========================================================
echo.

REM 1) Find Python 3.10+ (prefer the "py" launcher, fall back to "python").
REM    If it is missing or too old, install Python 3.12 automatically.
:detect_python
set "PYLAUNCH="
py -3 --version >nul 2>&1 && set "PYLAUNCH=py -3"
if not defined PYLAUNCH python --version >nul 2>&1 && set "PYLAUNCH=python"
if not defined PYLAUNCH goto :python_missing
%PYLAUNCH% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto :python_found

:python_missing
if defined PY_INSTALL_TRIED goto :python_manual
set "PY_INSTALL_TRIED=1"
echo Python 3.10 or newer was not found on this computer.
echo Installing Python 3.12 for you - a one-time step that can take a few minutes...
echo.

REM 1a) winget ships with Windows 10 (1809+) and Windows 11.
where winget >nul 2>&1
if errorlevel 1 goto :python_download
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :refresh_python_path
python --version >nul 2>&1
if not errorlevel 1 goto :detect_python

REM 1b) No winget (or it failed): download the official installer from python.org.
:python_download
echo Downloading the official Python installer from python.org...
set "PY_INSTALLER=%TEMP%\python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%PY_INSTALLER%'"
if errorlevel 1 goto :python_manual
if not exist "%PY_INSTALLER%" goto :python_manual
echo Installing Python 3.12...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_pip=1
del "%PY_INSTALLER%" >nul 2>&1
call :refresh_python_path
goto :detect_python

:python_manual
echo.
echo Could not install Python automatically (no internet connection, or the
echo installer was blocked). Please install Python 3.12 yourself from
echo   https://www.python.org/downloads/
echo make sure "Add python.exe to PATH" is ticked, then double-click this file again.
echo.
pause
exit /b 1

:python_found
set "VENV_PY=.venv\Scripts\python.exe"

REM 2) Create a private Python environment the first time. A venv is tied to
REM    the exact folder it was created in - renaming/moving this project, or
REM    sending it to someone else, leaves a venv that looks present but no
REM    longer actually works. Detect that and rebuild automatically instead
REM    of failing with a confusing "path not found" error.
if not exist "%VENV_PY%" goto :need_venv
"%VENV_PY%" --version >nul 2>&1
if not errorlevel 1 goto :venv_ready
echo Found a Python environment from a different computer or folder - rebuilding it...
rmdir /s /q .venv

:need_venv
echo Setting up for the first time (this can take a minute)...
%PYLAUNCH% -m venv .venv
if not errorlevel 1 goto :venv_ready
echo Could not create the Python environment.
pause
exit /b 1

:venv_ready
REM 3) Install the required packages (quietly) - the first time, and again whenever requirements.txt changed
REM    (for example after an update), so an old setup never runs against a newer version of the tool.
if not exist ".venv\.deps_installed" goto :install_deps
"%VENV_PY%" -c "import os, sys; sys.exit(1 if os.path.getmtime('requirements.txt') > os.path.getmtime('.venv/.deps_installed') else 0)"
if not errorlevel 1 goto :deps_ready

:install_deps
echo Installing required packages (first run, or the package list changed - this can take several minutes)...
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check --upgrade pip
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :deps_failed
echo done> ".venv\.deps_installed"

REM Optional: powers the "Generate ATS Resume" button. Needs Python 3.12+, so
REM this is best-effort - it must never fail the setup for everyone else.
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r requirements-resume.txt >nul 2>&1
goto :deps_ready

:deps_failed
echo Could not install required packages. Check your internet connection and try again.
pause
exit /b 1

:deps_ready
REM 4) Google Chrome is what the tool drives to apply for jobs. Install it if
REM    it is missing - but never block the control panel over it.
call :chrome_installed
if not errorlevel 1 goto :chrome_ready
echo.
echo Google Chrome was not found. The tool needs it to apply for jobs.
where winget >nul 2>&1
if errorlevel 1 goto :chrome_manual
echo Installing Google Chrome - you may be asked to approve a Windows prompt...
winget install -e --id Google.Chrome --silent --accept-package-agreements --accept-source-agreements
call :chrome_installed
if not errorlevel 1 goto :chrome_ready

:chrome_manual
echo.
echo Could not install Chrome automatically. Please get it from
echo   https://www.google.com/chrome/
echo before starting a run. You can still set everything up in the control panel now.
echo.

:chrome_ready
REM 5) Start the control panel. It chooses a free port, prints the address, and
REM    opens your browser to it.
set "PANEL_OPEN_BROWSER=1"

echo.
echo Starting the control panel and opening it in your browser...
echo Keep this window open while you use the tool. Close it to stop the server.
echo.

REM 6) Start the local control panel (runs until you close this window).
"%VENV_PY%" app.py

echo.
echo The control panel has stopped.
pause
exit /b 0

REM --- Subroutines ---------------------------------------------------------

REM A fresh Python install updates PATH for NEW windows only, so add its
REM default per-user locations to this window's PATH to use it right away.
:refresh_python_path
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"
exit /b 0

REM Sets errorlevel 0 if Google Chrome is installed, 1 if not.
:chrome_installed
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" exit /b 0
exit /b 1
