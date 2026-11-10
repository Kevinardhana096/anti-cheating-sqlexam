#!/usr/bin/env bash
# ==============================================================================
# Script Menjalankan Server Offline SQL Exam System (Linux / macOS)
# Menggunakan virtual environment .venv tanpa --reload pada mode ujian
# ==============================================================================

set -e

echo "=========================================================="
echo "    OFFLINE SQL EXAM SYSTEM (PRAKTIKUM BASIS DATA)        "
echo "=========================================================="

# 1. Deteksi Python Sistem Host
if command -v python3 >/dev/null 2>&1; then
    SYS_PY="python3"
elif command -v python >/dev/null 2>&1; then
    SYS_PY="python"
else
    echo "[ERROR] Python tidak ditemukan! Pastikan Python 3.11+ sudah terpasang."
    exit 1
fi

# 2. Memeriksa dan Membuat .venv jika belum ada
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"

if [ ! -f "$VENV_PY" ]; then
    echo "[INFO] Virtual environment '.venv' belum ditemukan. Membuat baru..."
    "$SYS_PY" -m venv "$VENV_DIR"
    echo "[INFO] Menginstal dependensi requirements.txt ke .venv..."
    "$VENV_PY" -m pip install --upgrade pip
    "$VENV_PY" -m pip install -r "${SCRIPT_DIR}/requirements.txt"
fi

# 3. Deteksi IP Lokal Wi-Fi Laptop Host
HOST_IP=$("$VENV_PY" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('10.255.255.255', 1))
    print(s.getsockname()[0])
except Exception:
    print('127.0.0.1')
finally:
    s.close()
")

echo "----------------------------------------------------------"
echo "Status Jaringan   : Siap (Offline Local Network)"
echo "Lingkungan Python : Terisolasi (.venv)"
echo "Akses Mahasiswa   : http://${HOST_IP}:8000"
echo "Akses Dosen/Admin : http://localhost:8000/admin"
echo "Master Key Admin  : [Tersimpan Aman di Database/Config]"
echo "Database Master   : PostgreSQL (pagila, classicmodels)"
echo "Sandbox Pribadi   : PostgreSQL (sandbox_pribadi)"
echo "Mode Server       : Production Exam Mode (Non-reload)"
echo "----------------------------------------------------------"
echo "Tekan Ctrl+C untuk menghentikan server."
echo ""

# 4. Menjalankan server FastAPI pada 0.0.0.0 (tanpa --reload demi stabilitas)
exec "$VENV_PY" -m uvicorn main:app --no-proxy-headers --host 0.0.0.0 --port 8000
