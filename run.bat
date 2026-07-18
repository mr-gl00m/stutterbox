@echo off
REM Launch Stutterbox using the project virtualenv, from anywhere.
REM Double-click this instead of main.py: clicking main.py uses the system
REM Python, which does not have PySide6/mss/numpy installed.
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" main.py
) else (
    echo .venv not found in "%~dp0".
    echo Falling back to 'uv run' ^(run 'uv sync' first if this fails^).
    uv run python main.py
)

REM Keep the window open only if the app exited with an error, so a crash or
REM traceback stays readable instead of vanishing.
if errorlevel 1 (
    echo.
    echo Stutterbox exited with code %errorlevel%. See logs\stutterbox.log.
    pause
)
endlocal
