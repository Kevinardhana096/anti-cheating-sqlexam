# Manual Instalasi & Panduan Setup Server
**Offline SQL Exam System – Praktikum Basis Data**

Manual ini memuat panduan instalasi teknis dan langkah konfigurasi server secara mandiri untuk persiapan lingkungan ujian praktikum basis data berbasis offline local network.

---

## 1. Prasyarat Sistem & Perangkat Lunak

Sebelum memulai instalasi, pastikan laptop host telah terpasang:
* **Sistem Operasi:** Windows 10/11, Ubuntu 20.04/22.04 LTS, atau macOS 12+
* **Python:** Versi 3.10 atau lebih baru (disertai modul `venv` dan `pip`)
* **PostgreSQL:** Versi 14, 15, atau 16
* **Browser:** Google Chrome atau Microsoft Edge versi modern

---

## 2. Persiapan Repositori Proyek

Buka terminal / Command Prompt dan pastikan berada pada direktori utama proyek:
```bash
cd c:\project\anti-cheating-sqlexam
```

---

## 3. Konfigurasi Lingkungan Virtual Python (`.venv`)

Gunakan virtual environment terisolasi untuk menghindari konflik pustaka global:

### Windows (Command Prompt / PowerShell):
```cmd
:: 1. Buat virtual environment
python -m venv .venv

:: 2. Aktivasi virtual environment
:: Command Prompt:
.venv\Scripts\activate.bat
:: PowerShell:
.venv\Scripts\Activate.ps1

:: 3. Upgrade pip dan instal dependensi
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. Verifikasi pustaka terpasang bersih tanpa konflik
pip check
```

### Linux / macOS (Bash / Zsh):
```bash
# 1. Buat virtual environment
python3 -m venv .venv

# 2. Aktivasi virtual environment
source .venv/bin/activate

# 3. Upgrade pip dan instal dependensi
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verifikasi pustaka terpasang bersih tanpa konflik
pip check
```

---

## 4. Konfigurasi File Lingkungan (`.env`)

Buat atau perbarui file `.env` pada root repositori dengan parameter koneksi PostgreSQL lokal:

```ini
# Port dan Host Aplikasi
APP_HOST=0.0.0.0
APP_PORT=8000

# Kredensial Administrator PostgreSQL Lokal Host
PG_HOST=localhost
PG_PORT=5432
PG_ADMIN_USER=postgres
PG_ADMIN_PASS=postgres

# Kredensial Terbatas Mahasiswa (student_role)
PG_STUDENT_USER=student_user
PG_STUDENT_PASS=student_pass

# Password Master Portal Pengawas / Dosen
ADMIN_MASTER_KEY=admin123
```

---

## 5. Konfigurasi Database PostgreSQL Master

Buka `psql` atau terminal query PostgreSQL dengan akun superuser (`postgres`):

```sql
-- 1. Buat role terbatas untuk mahasiswa (hanya SELECT di master DB, DDL di sandbox pribadi)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'student_role') THEN
        CREATE ROLE student_role WITH LOGIN PASSWORD 'student_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

-- 2. Buat database master ujian
CREATE DATABASE pagila;
CREATE DATABASE classicmodels;
CREATE DATABASE sandbox_pribadi;

-- 3. Berikan hak akses terbatas ke student_role pada seluruh database master
\connect pagila
GRANT CONNECT ON DATABASE pagila TO student_role;
GRANT USAGE ON SCHEMA public TO student_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO student_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO student_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO student_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO student_role;

\connect classicmodels
GRANT CONNECT ON DATABASE classicmodels TO student_role;
GRANT USAGE ON SCHEMA public TO student_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO student_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO student_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO student_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO student_role;

\connect sandbox_pribadi
GRANT CONNECT ON DATABASE sandbox_pribadi TO student_role;
GRANT USAGE ON SCHEMA public TO student_role;
```

### Inisialisasi Dataset Awal:
Dataset dapat dimuat via CLI atau menggunakan tombol **Reset Database** pada Portal Pengawas (`/admin`):
```bash
# Inisialisasi database classicmodels
psql -U postgres -d classicmodels -f data/classicmodels.sql

# Inisialisasi database pagila dari direktori berversi
psql -U postgres -d pagila -f data/pagila-0.10.1/pagila-schema.sql
psql -U postgres -d pagila -f data/pagila-0.10.1/pagila-data.sql
```

---

## 6. Menjalankan Server Ujian

### Opsi A: Menggunakan Script Runner Otomatis (Direkomendasikan)
Runner script otomatis mendeteksi/membuat `.venv`, menginstal dependensi jika belum ada, dan menjalankan server tanpa mode `--reload`:
* **Windows (CMD):** Klik ganda `run.bat` atau jalankan `run.bat` di terminal.
* **Windows (PowerShell):** Jalankan `.\run.ps1`.
* **Linux / macOS:** Jalankan `chmod +x run.sh && ./run.sh`.

### Opsi B: Menjalankan Manual melalui Terminal:
Pastikan virtual environment telah aktif:
```bash
# Windows
.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000

# Linux / macOS
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
> **Catatan Stabilitas Ujian:** Jangan menyertakan argumen `--reload` saat ujian berlangsung demi menjaga stabilitas worker dan menghindari restart server yang tidak diinginkan.

---

## 7. Verifikasi Operasional Server

1. **Akses Portal Mahasiswa:**
   Buka browser dan buka `http://localhost:8000/login`. Pastikan formulir login mahasiswa tampil rapi.
2. **Akses Portal Pengawas / Dosen:**
   Buka `http://localhost:8000/admin/login`. Masukkan Master Key (default: `admin123`).
3. **Pemeriksaan Tab Database Pengawas:**
   Klik tab **Database**, pilih `pagila`, klik **Reset Database**. Pastikan preview skema tabel berhasil dimuat.
4. **Pemeriksaan Utilitas CLI:**
   Jalankan pemeriksaan statistik sesi ujian:
   ```bash
   python scripts/reset_exam_session.py --check
   ```
