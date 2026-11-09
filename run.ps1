# ==============================================================================
# Script Menjalankan Server Offline SQL Exam System (PowerShell Windows)
# Menggunakan virtual environment .venv tanpa --reload pada mode ujian
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    OFFLINE SQL EXAM SYSTEM (PRAKTIKUM BASIS DATA)        " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Deteksi Python Sistem Host
$sysPy = "python"
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $sysPy = "py"
    } else {
        Write-Error "Python tidak ditemukan! Pastikan Python 3.11+ sudah terpasang dan ada di PATH."
        exit 1
    }
}

# 2. Memeriksa dan Membuat .venv jika belum ada
$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "[INFO] Virtual environment '.venv' belum ditemukan. Membuat baru..." -ForegroundColor Yellow
    & $sysPy -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Gagal membuat virtual environment .venv!"
        exit 1
    }
    Write-Host "[INFO] Menginstal dependensi requirements.txt ke .venv..." -ForegroundColor Yellow
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Gagal menginstal dependensi requirements.txt!"
        exit 1
    }
}

# 3. Deteksi IP Lokal Wi-Fi Laptop Host
$hostIp = & $venvPy -c @"
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('10.255.255.255', 1))
    print(s.getsockname()[0])
except Exception:
    print('127.0.0.1')
finally:
    s.close()
"@
if (-not $hostIp) { $hostIp = "127.0.0.1" }

Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Status Jaringan   : Siap (Offline Local Network)" -ForegroundColor Green
Write-Host "Lingkungan Python : Terisolasi (.venv)" -ForegroundColor Green
Write-Host "Akses Mahasiswa   : http://${hostIp}:8000" -ForegroundColor White
Write-Host "Akses Dosen/Admin : http://localhost:8000/admin" -ForegroundColor White
Write-Host "Master Key Admin  : [Tersimpan Aman di Database/Config]" -ForegroundColor Magenta
Write-Host "Database Master   : PostgreSQL (pagila, classicmodels)" -ForegroundColor White
Write-Host "Sandbox Pribadi   : PostgreSQL (sandbox_pribadi)" -ForegroundColor White
Write-Host "Mode Server       : Production Exam Mode (Non-reload)" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Tekan Ctrl+C untuk menghentikan server.`n"

# 4. Memeriksa dan membersihkan proses lama yang masih mengunci port 8000
try {
    $busyPort = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($busyPort) {
        $procIds = $busyPort | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pidToKill in $procIds) {
            Write-Host "[INFO] Menutup proses server sebelumnya di port 8000 (PID: $pidToKill)..." -ForegroundColor Yellow
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }
} catch {
    # Lanjutkan jika WMI/TCP connection query tidak tersedia
}

# 5. Menjalankan server FastAPI (tanpa --reload demi stabilitas penuh ujian)
& $venvPy -m uvicorn main:app --no-proxy-headers --host 0.0.0.0 --port 8000
