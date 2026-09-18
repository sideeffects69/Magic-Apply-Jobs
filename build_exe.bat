@echo off
REM
REM Author:  Om Abhyankar
REM License: MIT License
REM          https://opensource.org/license/mit
REM GitHub:  https://github.com/sideeffects69
REM
REM Builds the portable MagicApply.exe (one file, no installer) into dist\MagicApply.exe
REM Run this once on a Windows PC that has Python. The exe it makes needs nothing installed
REM except Google Chrome.
REM
REM NOTE: flat `goto` control flow on purpose (see the note in start.bat).

setlocal
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :have_python
echo Run start.bat once first, so the Python environment exists, then run this again.
pause
exit /b 1

:have_python
echo Installing the build tool (PyInstaller)...
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :failed

echo.
echo Building MagicApply.exe - this takes a few minutes...
"%VENV_PY%" -m PyInstaller --noconfirm --clean --onefile --name MagicApply ^
  --add-data "templates;templates" ^
  --add-data "modules/images;modules/images" ^
  --add-data "modules/javascript;modules/javascript" ^
  --hidden-import runAiBot --hidden-import app ^
  --collect-submodules langchain_openai --collect-submodules langchain_google_genai ^
  --collect-submodules langchain --collect-submodules langgraph ^
  --collect-submodules undetected_chromedriver ^
  --exclude-module rendercv --exclude-module pytest --exclude-module pylint --exclude-module pyflakes ^
  magic_apply.py
if errorlevel 1 goto :failed

echo.
echo Checking the exe from the inside...
dist\MagicApply.exe --selftest
if errorlevel 1 goto :failed

echo.
echo Done:  %CD%\dist\MagicApply.exe
echo Copy that single file anywhere and double-click it. It needs Google Chrome on the PC, nothing else.
pause
exit /b 0

:failed
echo.
echo The build failed - scroll up for the reason.
pause
exit /b 1
