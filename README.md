# Offline SQL Exam System

Panduan terkini tersedia di [indeks dokumentasi](docs/README.md) dan [manual instalasi](<INSTALLATION MANUAL.md>). Laporan pengujian di `docs/reports` adalah catatan hasil pada versi saat laporan dibuat.
Untuk menyiapkan dependensi Python dan database skor SQLite di Windows, hentikan server lalu jalankan `setup.bat` dari folder proyek. Instalasi dependensi membutuhkan internet pada setup awal; aplikasi tetap memakai aset lokal saat ujian. Script mempertahankan skor yang ada dan membuat snapshot SQLite sebelum migrasi versi lama. PostgreSQL tetap perlu disiapkan sesuai panduan instalasi di bawah. Setelah setup, jalankan `run.bat`.

**Sistem Ujian SQL Praktikum Basis Data — Local Network, No Internet Required (Multiplatform: macOS, Linux & Windows)**

Platform ujian SQL berbasis web yang dirancang untuk digunakan dalam jaringan Wi-Fi lokal (offline). Dosen/pengawas menjalankan server dari satu laptop (macOS, Linux, atau Windows), dan mahasiswa mengakses melalui browser di perangkat masing-masing tanpa membutuhkan koneksi internet.

---

## Daftar Isi

- [Fitur Utama](#fitur-utama)
- [Teknologi](#teknologi)
- [Struktur Proyek](#struktur-proyek)
- [Prasyarat](#prasyarat)
- [Instalasi & Setup Awal](#instalasi--setup-awal)
  - [Setup di macOS / Linux](#setup-di-macos--linux)
  - [Setup di Windows](#setup-di-windows)
- [Menjalankan Server](#menjalankan-server)
  - [Di macOS / Linux](#di-macos--linux)
  - [Di Windows (CMD / Double Click)](#di-windows-command-prompt--double-click)
  - [Di Windows (PowerShell)](#di-windows-powershell)
- [Akses Sistem](#akses-sistem)
- [Cara Mengganti Password Master](#cara-mengganti-password-master)
- [Panduan Pengawas (Admin)](#panduan-pengawas-admin)
- [Panduan Mahasiswa](#panduan-mahasiswa)
- [Keamanan & Anti-Kecurangan](#keamanan--anti-kecurangan)
- [Konfigurasi Environment](#konfigurasi-environment)
- [Troubleshooting](#troubleshooting)

---

## Fitur Utama

- **IDE Pengujian Admin:** buka **IDE Pengujian** dari dashboard untuk mencoba tampilan dan alur pengerjaan mahasiswa dengan sandbox serta nilai latihan terpisah. Lihat [panduan IDE admin](docs/operations/ADMIN_IDE.md).

### Untuk Mahasiswa
- Editor SQL dengan syntax highlighting (CodeMirror) dan autocomplete
- Eksekusi SELECT pada database master dan DDL/DML pada sandbox pribadi terisolasi
- Tampilan hasil query dalam tabel responsif
- Submit jawaban per soal, bisa diperbarui hingga ujian selesai
- Pemilihan database master atau sandbox pribadi sesuai soal

### Untuk Dosen / Pengawas

| Fitur | Deskripsi |
|---|---|
| **Live Monitoring** | Pantau status online/offline mahasiswa secara real-time (auto-refresh 10 detik) |
| **Hentikan Semua Sesi** | Paksa logout seluruh mahasiswa sekaligus dengan satu klik |
| **Bersihkan Sesi Sebelumnya** | Hapus seluruh data mahasiswa & jawaban untuk mempersiapkan sesi ujian baru |
| **Bebaskan Sesi** | Lepas kunci perangkat peserta tanpa menghapus jawaban |
| **Ganti Password Master** | Ubah password master admin melalui dashboard; environment hanya untuk instalasi pertama |
| **Manajemen Soal** | CRUD soal ujian dengan bobot nilai dan kunci jawaban query referensi |
| **Reset Database Sandbox** | Kembalikan master `pagila` atau `classicmodels` ke baseline saat ujian tidak aktif |
| **Upload SQL Custom** | Unggah file `.sql` untuk skema dan dataset ujian yang berbeda |
| **Log Aktivitas & Deteksi** | Rekam semua kejadian: login, submit, perpindahan tab, percobaan pembajakan NIM |
| **Bersihkan Log** | Hapus riwayat log aktivitas sebelum sesi ujian baru dimulai |
| **Export CSV** | Unduh seluruh jawaban mahasiswa dalam format spreadsheet siap nilai |
| **Export ZIP (.sql)** | Unduh satu file `.sql` per mahasiswa untuk arsip dan penilaian offline |
| **Rekap Log (CSV)** | Unduh rekaman lengkap seluruh aktivitas sistem ujian (audit trail) dalam format CSV |
| **Rekap Pindah Tab (CSV)** | Unduh rekapitulasi data frekuensi dan riwayat waktu perpindahan tab/jendela setiap mahasiswa |

---

## Teknologi

Panduan regresi, fixture database sementara, dan pembaruan skema tersedia di
[Pengujian dan migrasi database](docs/operations/TESTING.md).

Aturan status persiapan/aktif/selesai, pemulihan sesi, dan konfigurasi reverse proxy:
[Kendali ujian dan sesi](docs/operations/EXAM_CONTROL.md).

Hak akses role pribadi, upgrade schema lama, dan batas SQL:
[Keamanan sandbox](docs/operations/SANDBOX_SECURITY.md).

| Layer | Teknologi |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn (ASGI) |
| **Database Sistem** | SQLite (`exam_system.db` untuk user, soal, submisi, log, password) |
| **Database Ujian** | PostgreSQL 14+ (`classicmodels` sandbox dataset) |
| **Database Driver** | `psycopg2-binary` |
| **Frontend** | HTML5, Vanilla CSS (Dark mode responsive), Vanilla JavaScript |
| **Editor SQL** | CodeMirror (self-hosted offline, tanpa CDN internet) |

---

## Struktur Proyek

```
anti-cheating-sqlexam/
│
├── main.py                  # Routing FastAPI: mahasiswa, admin, REST API
├── database.py              # State, migrasi dan akses database
├── grading_engine.py        # Evaluator hasil lengkap dan DDL/DML
├── grading_queue.py         # Retry dan keputusan persisten
├── admin_practice.py        # Konteks simulasi admin terpisah
├── setup_postgres.sql       # Opsional: buat dua master; role/ACL diurus startup
├── requirements.txt         # Dependensi Python
├── setup.bat                # Setup dependensi dan SQLite Windows
├── run.sh                   # Runner macOS & Linux setelah konfigurasi environment
├── run.bat                  # Runner satu-klik untuk Windows (Command Prompt)
├── run.ps1                  # Runner untuk Windows (PowerShell)
├── .gitignore               # Konfigurasi ignore file db lokal, pycache, OS files
│
├── data/                    # Termasuk pagila-schema.sql dan pagila-data.sql
│   └── classicmodels.sql    # Schema & dataset master PostgreSQL (classicmodels)
│
├── templates/
│   ├── login.html           # Halaman login mahasiswa (dengan pesan validasi NIM)
│   ├── student.html         # Workspace ujian mahasiswa (CodeMirror + preview)
│   ├── admin.html           # Dashboard pengawas & live monitoring
│   └── admin_login.html     # Halaman login dosen dengan Master Key
│
└── static/
    ├── css/style.css        # Stylesheet modern (Dark theme, glassmorphism)
    ├── js/student.js        # Controller interaktif ujian & anti-cheat
    ├── js/admin.js          # Controller dashboard monitoring pengawas
    └── vendor/              # CodeMirror dan SQL Formatter lokal
```

---

## Prasyarat

Pastikan perangkat **host (laptop dosen/pengawas)** sudah terpasang:

1. **Python 3.11** atau lebih baru
2. **PostgreSQL 14** atau lebih baru, berjalan sebagai service lokal
3. **pip** (Python package manager)

---

## Instalasi & Setup Awal

### Setup di macOS / Linux

File `setup.bat` dan `run.bat` hanya untuk Windows. Di macOS/Linux, buka Terminal dan jalankan:

```bash
git clone <URL-repository>
cd anti-cheating-sqlexam

export PG_ADMIN_USER="postgres"
export PG_ADMIN_PASS="password_postgresql_anda"
export ADMIN_MASTER_KEY="password_admin_ujian"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/setup_sqlite.py

bash run.sh
```

Ganti `<URL-repository>` dengan alamat repo dan sesuaikan nama folder hasil clone. Sesuaikan akun PostgreSQL dengan instalasi laptop; username tidak selalu `postgres`. Akun ini harus dapat membuat database dan role serta mengatur hak akses. Pastikan service PostgreSQL sudah berjalan melalui pengelola instalasinya. Tidak perlu mengubah kredensial di `database.py`.

### Setup di Windows

Pastikan service PostgreSQL berstatus **Running** di `services.msc`. Buka **PowerShell**, lalu jalankan:

```powershell
git clone <URL-repository>
cd anti-cheating-sqlexam

$env:PG_ADMIN_USER = "postgres"
$env:PG_ADMIN_PASS = "password_postgresql_anda"
$env:ADMIN_MASTER_KEY = "password_admin_ujian"

.\setup.bat
.\run.bat
```

Ganti URL repo, nama folder dan password sesuai instalasi laptop. Jalankan konfigurasi dan kedua script dalam jendela PowerShell yang sama. `setup.bat` membuat `.venv`, memasang dependensi Python dan menyiapkan SQLite. Script ini tidak memasang atau menjalankan service PostgreSQL.

### Setelah setup dan untuk pemakaian berikutnya

- Setup awal membutuhkan internet untuk mengunduh dependensi. Aset aplikasi disediakan lokal untuk penggunaan ujian.
- Saat startup, aplikasi menyiapkan database master `pagila` dan `classicmodels`, dataset serta role dan hak akses PostgreSQL. Akun PostgreSQL harus memiliki izin yang sesuai.
- Admin membuka `http://localhost:8000/admin`. Mahasiswa membuka `http://IP-LAPTOP-SERVER:8000` pada jaringan yang sama; izinkan koneksi server pada firewall jaringan lokal jika diperlukan.
- Gunakan master key yang dipilih saat instalasi pertama. `ADMIN_MASTER_KEY` tidak menimpa password admin yang sudah tersimpan.
- Pada terminal baru, atur kembali `PG_ADMIN_USER` dan `PG_ADMIN_PASS`, pastikan PostgreSQL berjalan, lalu jalankan `.\run.bat` di Windows atau `bash run.sh` di macOS/Linux dari folder proyek. Tidak perlu mengulang setup setiap kali.
- Script saat ini tidak memuat `.env` otomatis. Contoh di atas memakai environment terminal; membuat `.env` saja belum cukup.
- Hentikan server dengan `Ctrl+C` sebelum setup/upgrade. Setup SQLite mempertahankan skor dan membuat snapshot sebelum migrasi versi lama; ini bukan pengganti backup lengkap PostgreSQL, SQLite dan unggahan.

---

## Menjalankan Server

Sistem menyediakan runner otomatis untuk semua sistem operasi yang akan otomatis mendeteksi IP Wi-Fi lokal dan menampilkan URL yang siap dibagikan ke mahasiswa.

### Di macOS / Linux

Beri hak eksekusi dan jalankan `run.sh`:

```bash
chmod +x run.sh
./run.sh
```

---

### Di Windows (Command Prompt / Double Click)

Setelah setup, jalankan `run.bat` pada terminal yang sudah memiliki environment PostgreSQL. Double-click hanya cukup jika environment telah dikonfigurasi pada akun Windows; variabel dari PowerShell lain tidak ikut diwariskan:

```cmd
run.bat
```

---

### Di Windows (PowerShell)

Jalankan script PowerShell:

```powershell
.\run.ps1
```

*(Jika muncul peringatan ExecutionPolicy di PowerShell, jalankan `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` terlebih dahulu).*

---

### Contoh Tampilan Terminal Saat Server Berjalan

```
==========================================================
    OFFLINE SQL EXAM SYSTEM (PRAKTIKUM BASIS DATA)        
==========================================================
Status Jaringan   : Siap (Offline Local Network)
Akses Mahasiswa   : http://192.168.1.15:8000
Akses Dosen/Admin : http://localhost:8000/admin
Master Key Admin  : [Tersimpan Aman di Database/Config]
Database Master   : PostgreSQL (pagila, classicmodels)
Sandbox Pribadi   : PostgreSQL (sandbox_pribadi virtual)
==========================================================
Tekan Ctrl+C untuk menghentikan server.
```

---

## Akses Sistem

| Pengguna | URL | Kredensial |
|---|---|---|
| **Mahasiswa** | `http://<IP_HOST>:8000` | NIM + Nama Lengkap |
| **Pengawas/Admin** | `http://localhost:8000/admin` | Master Key: `admin123` (atau sesuai konfigurasi) |

> **Catatan:** Ganti `<IP_HOST>` dengan IP lokal Wi-Fi yang tercetak di jendela terminal saat server dijalankan (misal `http://192.168.1.15:8000`).

---

## Cara Mengganti Password Master

Password default master admin saat pertama kali diinstal adalah **`admin123`**. Dashboard dan pemulihan lokal mengubah key yang sudah ada. Environment hanya menentukan key instalasi pertama:

### Metode 1: Melalui Web Dashboard Admin (Paling Praktis)
1. Buka `http://localhost:8000/admin` di browser laptop dosen dan login.
2. Di pojok kanan atas header dashboard, klik tombol **"Ganti Password"**.
3. Masukkan password saat ini, password baru (minimal 12 karakter), dan konfirmasi password baru.
4. Klik **"Simpan Password"**. Perubahan langsung tersimpan ke database SQLite.

---

### Metode 2: Environment Variable untuk Instalasi Pertama
`ADMIN_MASTER_KEY` hanya dipakai ketika database belum memiliki master key. Nilai ini tidak menimpa password yang sudah diganti saat restart. Untuk instalasi pertama:

- **Di macOS / Linux (`run.sh`):**
  Jalankan pada Terminal sebelum `bash run.sh`:
  ```bash
  export ADMIN_MASTER_KEY="password_baru_anda"
  ```
- **Di Windows (`run.bat`):**
  Jalankan pada CMD sebelum `run.bat`:
  ```cmd
  set "ADMIN_MASTER_KEY=password_baru_anda"
  ```
- **Di Windows (`run.ps1`):**
  Jalankan pada PowerShell sebelum `.\run.ps1`:
  ```powershell
  $env:ADMIN_MASTER_KEY = "password_baru_anda"
  ```

---

### Metode 3: Pemulihan Lokal
Hentikan server, lalu jalankan perintah berikut. Master key diminta secara interaktif
agar tidak masuk riwayat perintah terminal. Semua sesi admin dicabut.

```powershell
.\.venv\Scripts\python.exe scripts/reset_admin_key.py
```

Linux/macOS: `.venv/bin/python scripts/reset_admin_key.py`.

---

## Panduan Pengawas (Admin)

Dua pengawas dapat masuk dengan master key yang sama dari browser/perangkat berbeda.
Setiap login memiliki sesi independen; login/logout satu admin tidak memutus admin
lain. Penggantian master key mencabut sesi admin lain. Detail proteksi, masa berlaku,
konflik edit, dan audit tersedia di [ADMIN_SECURITY.md](docs/operations/ADMIN_SECURITY.md).


### Alur Kerja Ujian

1. Siapkan environment dan jalankan server. Masuk sebagai admin.
2. Arsipkan hasil kelas sebelumnya, selesaikan review, dan buat backup sebelum **Bersihkan Sesi**. Tombol ini menghapus peserta, jawaban dan riwayat terkait kelas sebelumnya.
3. Dalam status persiapan, atur paket aktif, soal, alias output, kunci dan kebijakan penilaian. Paket dan soal tidak dapat diubah selama ujian aktif.
4. Gunakan **IDE Pengujian** dan gladi bersih perangkat. Pemeriksaan IDE tidak menggantikan tes transisi lobby/jaringan.
5. Bagikan URL; peserta login ke ruang tunggu. Tekan **Mulai Ujian** untuk memvalidasi acuan dan membuka akses.
6. Pantau peserta dan status jawaban. Pending/review berarti belum ada keputusan nilai; bukan jawaban salah.
7. Tekan **Hentikan Ujian** saat waktu habis. Pekerjaan penilaian sah yang sudah diterima dapat selesai setelah stop; submit baru ditolak.
8. Tinjau antrean review, kemudian ekspor hasil dan buat backup. CSV/ZIP bukan pengganti backup layanan lengkap.

### Tombol Aksi Cepat Pengawas

| Tombol | Fungsi |
|---|---|
| **Mulai Ujian** | Validasi acuan lalu buka akses; setelah selesai, membuka kembali ujian yang sama |
| **Hentikan Ujian** | Tutup soal/query/submit; pertahankan token dan jawaban |
| **Hentikan Semua** | Cabut sesi peserta; berbeda dari mengakhiri ujian normal |
| **Bebaskan Sesi** | Lepas ikatan perangkat dan cabut token lama; jawaban/nilai tetap ada |
| **Reset Paket** | Izinkan peserta memilih ulang paket; konteks penilaian berubah |
| **Bersihkan Sesi** | Hapus data kelas sebelumnya dan kembali ke persiapan |
| **Bersihkan Log** | Hapus log aktivitas ujian; berbeda dari audit permintaan admin |
| **Reset Database** | Ganti dataset master; bukan restore nilai atau backup |
| **IDE Pengujian** | IDE mahasiswa dengan sandbox dan skor latihan admin terpisah |

Lihat [SOP pengawas](docs/operations/OPERATIONS_GUIDE.md) dan [kendali sesi](docs/operations/EXAM_CONTROL.md).

## Panduan Mahasiswa

1. Hubungkan laptop ke jaringan ujian dan buka URL pengawas.
2. Login memakai NIM dan nama. Tunggu di lobby jika ujian belum aktif.
3. Setelah ujian dibuka, masuk fullscreen dan pilih paket sesuai arahan pengawas.
4. Pilih soal dan database, lalu tulis SQL. **Format SQL** merapikan query; **Run Query** atau Ctrl+Enter menjalankan query/seleksi.
5. **Submit Answer** mengirim seluruh jawaban editor untuk soal aktif. Submit sandbox dinilai pada workspace evaluator terpisah; gunakan Run Query untuk mengubah workspace percobaan.
6. Baca status **Tersimpan • Benar/Salah** atau **Menunggu penilaian**. Hasil terbaru dan skor terbaik adalah dua hal berbeda.
7. Draft lokal membantu saat koneksi putus, tetapi bukan bukti jawaban sudah tersimpan di server. Jika respons hilang, periksa status sebelum mengirim ulang; retry dapat menambah percobaan.

---

## Keamanan & Anti-Kecurangan

Sistem menyediakan pembatas akses dan catatan untuk membantu pengawasan. Log browser sendiri tidak membuktikan kecurangan:

| Mekanisme | Implementasi |
|---|---|
| **Unique NIM Enforcement** | 1 NIM hanya dapat aktif pada 1 perangkat. Percobaan login ganda dari perangkat lain ditolak otomatis. |
| **Anti-Joki (Name Matching)** | Jika login dengan NIM yang sudah terdaftar tetapi nama berbeda, sistem langsung menolak dan mencatat insiden `nim_hijack_attempt`. |
| **Anti-Joki Multi-Account IP**| Beberapa peserta boleh berbagi IP saat `ALLOW_SHARED_IP=true`; penguncian perangkat dan NIM tetap berlaku. |
| **Isolasi PostgreSQL** | Database master memakai role read-only; sandbox memakai LOGIN tersendiri per mahasiswa dengan hak pada schema sendiri. |
| **Kebijakan SQL** | Parser AST memeriksa seluruh skrip, jenis perintah, fungsi, dan referensi schema sebelum eksekusi. |
| **Batas Eksekusi** | Anggaran SQL 5 detik untuk seluruh skrip, maksimal 20 statement, dengan batas hasil dan koneksi sandbox. |
| **Pendeteksi Blur Tab** | Jika mahasiswa berpindah jendela/tab browser, sistem otomatis mencatat peringatan dan menghitung frekuensi perpindahan tab di dashboard pengawas. |
| **Internal Web Dialog** | Konfirmasi keluar menggunakan modal DOM internal web (bukan `window.confirm` bawaan browser) untuk mencegah false-positive deteksi window blur saat mahasiswa menekan tombol keluar ujian. |

NIM dan nama pada pendaftaran awal berasal dari peserta; ini bukan verifikasi identitas
akademik atau roster kampus. Pembatasan browser dan log fokus mendukung pengawasan,
bukan jaminan bahwa seluruh bentuk kecurangan dapat dicegah atau dibuktikan.

---

## Konfigurasi Environment

Variabel environment berikut dibaca aplikasi. `.env` tidak dimuat otomatis. Port HTTP runner tetap 8000; perubahan port memakai argumen Uvicorn, bukan `APP_PORT`:

| Variable | Default | Keterangan |
|---|---|---|
| `ADMIN_MASTER_KEY` | `admin123` | Master key untuk instalasi pertama; tidak menimpa perubahan password saat restart |
| `PG_HOST` | `localhost` | Host database PostgreSQL |
| `PG_PORT` | `5432` | Port database PostgreSQL |
| `DEFAULT_EXAM_DB` | `pagila` | Database kerja default dan lokasi schema sandbox pribadi |
| `PG_DB` | `pagila` | Variabel lama; gunakan `DEFAULT_EXAM_DB` untuk memilih database kerja |
| `PG_ADMIN_USER` | `postgres` | User superuser/admin PostgreSQL |
| `PG_ADMIN_PASS` | *(kosong)* | Password user admin PostgreSQL |
| `PG_STUDENT_USER` | `student_role` | Login read-only untuk dataset master |
| `PG_STUDENT_PASS` | `student123` | Password login master read-only |
| `EXAM_SQLITE_PATH` | `exam_system.db` di folder proyek | Lokasi SQLite utama; latihan admin terpisah di sampingnya |
| `PG_POOL_MAXCONN` | `50` | Batas pool per master per proses; bukan jumlah peserta |
| `PG_SANDBOX_MAXCONN` | `20` | Batas koneksi sandbox pribadi bersamaan per proses |
| `ALLOW_SHARED_IP` | `true` | Izinkan beberapa peserta pada IP/NAT yang sama |
| `TRUSTED_PROXY_CIDRS` | *(kosong)* | IP/CIDR proxy tepercaya untuk membaca `X-Forwarded-For` |

---

## Troubleshooting

#### 1. Mahasiswa tidak bisa membuka halaman web (`Connection timed out` / `Site cannot be reached`)
- Pastikan laptop pengawas dan mahasiswa berada pada **jaringan Wi-Fi yang sama**.
- **Di Windows:** Buka **Windows Defender Firewall** → izinkan Python melalui Private Network, batasi aturan ke jaringan ujian; jangan menonaktifkan firewall sebagai prosedur rutin.
- **Di macOS:** Buka **System Settings → Network → Firewall** → pastikan koneksi masuk untuk `python3` diizinkan.
- Jika menggunakan Wi-Fi publik/kampus yang menerapkan **Client Isolation / AP Isolation**, perangkat tidak bisa saling berkomunikasi. **Solusi:** Nyalakan **Personal Hotspot** (Tethering) dari smartphone atau laptop pengawas, lalu minta mahasiswa terhubung ke hotspot tersebut.

#### 2. Mahasiswa mendapat pesan "NIM sedang aktif di perangkat lain"
- Terjadi jika mahasiswa sebelumnya sudah login, lalu laptopnya mati atau browser tertutup tanpa logout.
- **Solusi:** Pengawas membuka Tab **Monitoring** di dashboard admin, cari NIM mahasiswa tersebut, lalu klik tombol **"Bebaskan Sesi"**. Mahasiswa dapat login kembali.

#### 3. Error PostgreSQL di Windows saat menjalankan server
- Pastikan service PostgreSQL sudah berjalan di Windows. Buka Command Prompt Administrator dan ketik:
  ```cmd
  net start postgresql-x64-16
  ```
  *(sesuaikan versi 16/15/14 dengan yang terinstall).*
- Pastikan password admin `postgres` telah disesuaikan jika Anda menentukan password saat instalasi:
  ```cmd
  set "PG_ADMIN_PASS=password_anda"
  run.bat
  ```

---

Panduan uji beban, backup/pemulihan, pemeriksaan kesiapan, dan penanganan insiden:
[RELEASE_READINESS.md](docs/operations/RELEASE_READINESS.md).

Antrean penilaian persisten dan penilaian manual/regrade admin tersedia melalui
[GRADING_QUEUE.md](docs/operations/GRADING_QUEUE.md), termasuk CLI dengan master key
bersama dan sesi independen.

## Lisensi

Panduan penilaian hasil lengkap, kebijakan per soal, workspace evaluator, dan riwayat
percobaan tersedia di [GRADING.md](docs/operations/GRADING.md).

Proyek ini dikembangkan untuk kebutuhan internal **Praktikum Basis Data**. Bebas digunakan dan dikembangkan untuk keperluan akademik.
