# Manual instalasi Windows, macOS dan Linux

Panduan aktif, diperiksa 8 November 2026. Untuk daftar panduan lain lihat [indeks dokumentasi](docs/README.md).

## Prasyarat

- Git, Python **3.11+** dengan venv/pip, dan service PostgreSQL lokal.
- PostgreSQL 14+ merupakan target dukungan aplikasi; pengujian terbaru memakai PostgreSQL 18.6 dan Python 3.14.6 pada Windows. Ini bukan bukti pengujian setiap kombinasi versi atau instalasi macOS baru.
- Kebutuhan Python 3.11 berasal dari `pillow==13.0.0` dalam requirements.txt.
- Akun administrator PostgreSQL yang dapat membuat database/role serta mengatur hak akses. Username tidak selalu `postgres`.
- Internet untuk mengunduh dependensi saat setup. Pelaksanaan memakai aset lokal.

Ganti `<URL-repository>` dengan URL repo sebenarnya dan sesuaikan nama direktori hasil clone. Jangan memasukkan placeholder password apa adanya.

## Windows: PowerShell

Pastikan PostgreSQL berjalan di `services.msc`. Pada PowerShell:

```powershell
git clone <URL-repository>
cd anti-cheating-sqlexam
$env:PG_HOST = "localhost"
$env:PG_PORT = "5432"
$env:PG_ADMIN_USER = "postgres"
$env:PG_ADMIN_PASS = "password_postgresql_anda"
$env:ADMIN_MASTER_KEY = "master_key_pilihan_anda"
.\setup.bat
.\run.bat
```

Gunakan master key minimal 12 karakter agar memenuhi ketentuan penggantian key. Alternatif runner PowerShell adalah `.\run.ps1`. `setup.bat` membuat `.venv`, memasang dependensi dan menjalankan setup SQLite; tidak memasang PostgreSQL. Pada CMD gunakan `set "PG_ADMIN_USER=postgres"` dan pola yang sama untuk variabel lain, kemudian `setup.bat` dan `run.bat`.

## macOS / Linux: Terminal

Jalankan service PostgreSQL melalui pengelola instalasi yang digunakan. Nama service Homebrew dapat berversi; jangan mengasumsikan satu nama service untuk semua laptop.

```bash
git clone <URL-repository>
cd anti-cheating-sqlexam
export PG_HOST="localhost"
export PG_PORT="5432"
export PG_ADMIN_USER="postgres"
export PG_ADMIN_PASS="password_postgresql_anda"
export ADMIN_MASTER_KEY="master_key_pilihan_anda"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/setup_sqlite.py
bash run.sh
```

File `.bat` hanya untuk Windows. Tidak ada `setup.sh`; langkah Python di atas merupakan padanannya.

## Environment dan startup

Environment harus tersedia pada terminal/proses yang menjalankan server. Aplikasi **tidak memuat `.env` otomatis**. Variabel dari satu PowerShell tidak otomatis tersedia pada double-click dari File Explorer atau terminal baru. Tidak perlu mengedit kredensial dalam database.py atau memasukkannya ke script yang disimpan di repo.

`ADMIN_MASTER_KEY` hanya bootstrap ketika SQLite belum menyimpan key. Untuk key yang sudah ada gunakan dashboard atau [pemulihan lokal](docs/operations/ADMIN_SECURITY.md); mengganti environment tidak meresetnya.

Startup menginisialisasi database master `pagila`/`classicmodels`, dataset yang diperlukan, role terbatas dan ACL. `sandbox_pribadi` adalah pilihan database virtual; **jangan membuat database fisik atau menjalankan GRANT manual lama**. Script opsional [setup_postgres.sql](setup_postgres.sql) hanya menyiapkan dua master; aplikasi mengurus role/ACL. Jangan mengimpor ulang dataset sebagai pemeriksaan rutin karena dapat mengganti data.

## Menjalankan kembali dan upgrade

Pada terminal baru, atur kembali koneksi PostgreSQL, masuk folder proyek, lalu `run.bat` di Windows atau `bash run.sh` di macOS/Linux. Master key bootstrap tidak perlu diatur ulang. Jika `.venv` lama menggunakan Python 3.10, buat ulang virtual environment dengan Python 3.11+ tanpa menghapus database ujian. Untuk upgrade, hentikan server, buat backup lengkap, perbarui dependensi dan jalankan setup/migrasi. Setup mempertahankan skor dan membuat snapshot SQLite sebelum migrasi versi lama; snapshot itu bukan backup PostgreSQL/unggahan.

Port runner adalah 8000. `APP_PORT`/`APP_HOST` bukan opsi yang dibaca runner. Untuk menjalankan manual pada port lain gunakan Python `.venv` dan argumen Uvicorn:

```bash
python -m uvicorn main:app --no-proxy-headers --host 0.0.0.0 --port 8000
```

Perintah manual mengasumsikan virtual environment sudah diaktifkan. Jangan memakai `--reload` atau menambah worker untuk ujian tanpa pengujian arsitektur dan kapasitas.

## Pemeriksaan setelah startup

1. Baca output startup; URL yang tercetak saja belum membuktikan semua pemeriksaan berhasil. Periksa `/health` dan `/ready`.
2. Buka `http://localhost:8000/admin`, login dan periksa Database tanpa menekan Reset sebagai tes koneksi.
3. Atur soal/paket saat persiapan, gunakan IDE Pengujian, lalu gladi bersih login–lobby–mulai–submit–stop pada perangkat peserta.
4. Peserta mengakses `http://IP-LAPTOP-SERVER:8000`. Izinkan inbound Python/port 8000 pada jaringan ujian; PostgreSQL tidak perlu dibuka ke perangkat peserta.
5. Hentikan server dengan Ctrl+C. Jangan membiarkan laptop tidur saat dipakai sebagai server.

Rincian pelaksanaan: [SOP pengawas](docs/operations/OPERATIONS_GUIDE.md). Backup dan restore: [kesiapan operasional](docs/operations/RELEASE_READINESS.md). Tes otomatis memakai database sementara: [pengujian](docs/operations/TESTING.md).
