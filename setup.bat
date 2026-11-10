@echo off
setlocal
cd /d "%~dp0"
echo Hentikan server ujian sebelum menjalankan setup atau upgrade.
where py >nul 2>nul
if errorlevel 1 (
    set "BOOTSTRAP_PYTHON=python"
) else (
    set "BOOTSTRAP_PYTHON=py"
)
if not exist ".venv\Scripts\python.exe" (
    %BOOTSTRAP_PYTHON% -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts\setup_sqlite.py %*
if errorlevel 1 exit /b 1
echo Setup selesai. Gunakan run.bat untuk menjalankan server.
endlocal
