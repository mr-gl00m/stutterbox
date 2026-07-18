@echo off
REM Build the distributable one-folder Windows release of Stutterbox.
REM Output: dist\Stutterbox\  (Stutterbox.exe + _internal\ + READ-ME-FIRST.txt
REM         + sample_coding_session.stut) and dist\Stutterbox-v<version>-win64.zip
REM shortcut: version hardcoded; bump together with APP_VERSION in core\config.py
set VERSION=0.2.0
cd /d "%~dp0"

uv run python -m PyInstaller stutterbox.spec --noconfirm
if errorlevel 1 exit /b 1

copy /y packaging\READ-ME-FIRST.txt dist\Stutterbox\ >nul
if errorlevel 1 exit /b 1
copy /y samples\sample_coding_session.stut dist\Stutterbox\ >nul
if errorlevel 1 exit /b 1
copy /y LICENSE dist\Stutterbox\LICENSE.txt >nul
if errorlevel 1 exit /b 1
copy /y THIRD_PARTY_NOTICES.md dist\Stutterbox\ >nul
if errorlevel 1 exit /b 1
xcopy /e /i /y packaging\LICENSES dist\Stutterbox\LICENSES >nul
if errorlevel 1 exit /b 1

set ZIP=dist\Stutterbox-v%VERSION%-win64.zip
if exist %ZIP% del %ZIP%
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Stutterbox' -DestinationPath '%ZIP%'"
if errorlevel 1 exit /b 1

echo Release ready: %ZIP%
