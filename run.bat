@echo off
setlocal enabledelayedexpansion
title Offline SQL Exam System Server

echo ==========================================================
echo     OFFLINE SQL EXAM SYSTEM (PRAKTIKUM BASIS DATA)
echo ==========================================================

:: 1. Memeriksa instalasi Python di sistem host
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python tidak ditemukan di PATH sistem Windows!
        echo Silakan unduh dan pasang Python 3.11+ dari https://www.python.org/
        pause
        exit /b 1
    ) else (
        set "SYS_PY=py"
    )
) else (
    set "SYS_PY=python"
)

:: 2. Memeriksa dan menginisialisasi virtual environment (.venv)
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment '.venv' belum ditemukan.
    echo [INFO] Membuat '.venv' baru...
    %SYS_PY% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal membuat virtual environment .venv!
        pause
        exit /b 1
    )
    echo [INFO] Menginstal dependensi dari requirements.txt ke .venv...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal menginstal dependensi requirements.txt!
        pause
        exit /b 1
    )
)

set "PY_CMD=.venv\Scripts\python.exe"

:: 3. Deteksi IP lokal Wi-Fi Laptop Host
for /f "delims=" %%i in ('%PY_CMD% -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1)); print(s.getsockname()[0]); s.close()" 2^>nul') do set "HOST_IP=%%i"
if "%HOST_IP%"=="" set "HOST_IP=127.0.0.1"

echo ----------------------------------------------------------
echo Status Jaringan   : Siap (Offline Local Network)
echo Lingkungan Python : Terisolasi (.venv)
echo Akses Mahasiswa   : http://%HOST_IP%:8000
echo Akses Dosen/Admin : http://localhost:8000/admin
echo Master Key Admin  : [Tersimpan Aman di Database/Config]
echo Database Master   : PostgreSQL (pagila, classicmodels)
echo Sandbox Pribadi   : PostgreSQL (sandbox_pribadi)
echo Mode Server       : Production Exam Mode (Non-reload)
echo ----------------------------------------------------------
echo Tekan Ctrl+C untuk menghentikan server.
echo.

:: 4. Memeriksa dan membersihkan proses lama yang masih mengunci port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /i ":8000" ^| findstr /i "LISTENING"') do (
    echo [INFO] Menutup proses server sebelumnya di port 8000 - PID %%a
    taskkill /F /PID %%a >nul 2>nul
    timeout /t 1 /nobreak >nul
)

:: 5. Menjalankan server FastAPI (tanpa --reload demi stabilitas penuh ujian)
%PY_CMD% -m uvicorn main:app --no-proxy-headers --host 0.0.0.0 --port 8000
pause
