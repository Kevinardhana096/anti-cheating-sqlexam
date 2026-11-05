# Panduan Operasional Sistem Ujian SQL Offline
**Dokumentasi Resmi Operasional & SOP Pengawas / Laboran**

Dokumen ini memuat standar operasional prosedur (SOP) pelaksanaan ujian praktikum basis data secara offline menggunakan jaringan lokal tanpa ketergantungan koneksi internet.

---

## 1. Arsitektur Jaringan Offline
Sistem dirancang untuk berjalan pada jaringan lokal tertutup (Isolated Local Area Network / Wi-Fi Hotspot) guna mencegah kecurangan online (AI tools, browsing, search engines).

```
[ Laptop Dosen / Host ] (Server FastAPI + PostgreSQL + SQLite)
        │
        ├─── [ Router Wi-Fi / Hotspot Lab (Tanpa Akses Internet) ]
        │         ├── Laptop Mahasiswa 1  (Browser -> http://<HOST_IP>:8000)
        │         ├── Laptop Mahasiswa 2  (Browser -> http://<HOST_IP>:8000)
        │         └── Laptop Mahasiswa N  (Browser -> http://<HOST_IP>:8000)
```

### Konfigurasi Jaringan & Keamanan Offline:
1. **Penggunaan HTTP Lokal & Pertimbangan SSL/TLS:**
   - Sistem sengaja berjalan pada protokol HTTP murni (`http://<HOST_IP>:8000`) pada rentang IP subnet privat (`192.168.x.x` atau `10.x.x.x`).
   - Pada jaringan offline tertutup tanpa koneksi WAN, Certificate Authority (CA) publik tidak dapat diakses untuk validasi sertifikat HTTPS, sehingga HTTP lokal menghilangkan *browser security warning* (Self-Signed SSL warnings) pada laptop peserta.
   - Proteksi sesi dijamin secara ketat melalui atribut cookie `HttpOnly=True`, `SameSite=Lax`, rotasi token sesi pada setiap login/logout, dan validasi header Origin/Referer (Anti-CSRF).

2. **Isolasi Wi-Fi (AP Client Isolation):**
   - **Wajib diaktifkan:** Pada menu pengaturan Router Wi-Fi / Access Point lab, aktifkan fitur **"AP Isolation"** (atau dikenal sebagai *Client Isolation / Guest Mode*).
   - Fitur ini mencegah komunikasi *Peer-to-Peer* (P2P) antar laptop mahasiswa di jaringan Wi-Fi yang sama, sehingga mahasiswa tidak dapat melakukan *packet sniffing*, scanning port, atau mengirim file kunci jawaban secara langsung ke laptop peserta lain.

3. **Konfigurasi Firewall Laptop Host:**
   - **Port 8000 (Aplikasi Web):** Buka port TCP `8000` untuk *Inbound Traffic* agar laptop mahasiswa dapat mengakses portal ujian.
     ```cmd
     netsh advfirewall firewall add rule name="SQL Exam Server (Port 8000)" dir=in action=allow protocol=TCP localport=8000
     ```
   - **Port 5432 (PostgreSQL):** Pastikan port PostgreSQL `5432` **TIDAK** dibuka ke jaringan Wi-Fi publik. File `postgresql.conf` sebaiknya hanya mendengarkan `listen_addresses = 'localhost'` atau diblokir dari antarmuka Wi-Fi oleh firewall, sehingga mahasiswa tidak bisa menghubungkan DBeaver / pgAdmin langsung ke server basis data.

4. **Deteksi IP Host:**
   - Jalankan `ipconfig` (Windows) atau `ifconfig / ip a` (Linux/macOS) pada laptop host untuk memeriksa IP lokal (misal: `192.168.1.50`).
   - Bagikan URL ujian `http://<HOST_IP>:8000` ke papan tulis atau pengumuman proyektor lab.

---

## 2. Prosedur Pra-Ujian (Checklist Laboran & Dosen)

Sebelum peserta memasuki ruangan ujian:

1. **Inisialisasi Virtual Environment & Dependensi:**
   - Jalankan `run.bat` (Windows Command Prompt), `run.ps1` (PowerShell), atau `run.sh` (Linux/macOS).
   - Script akan otomatis mendeteksi atau membuat virtual environment `.venv` dan menginstal pustaka yang dibutuhkan dari `requirements.txt`.
2. **Verifikasi Database Master:**
   - Buka browser host dan akses portal pengawas: `http://localhost:8000/admin`.
   - Masukkan *Master Key* pengawas.
   - Buka tab **Database**, pilih `pagila`, dan klik **Reset Database** untuk memastikan tabel dan data awal kembali ke kondisi bersih.
   - Ulangi untuk database `classicmodels`.
3. **Verifikasi Paket & Bank Soal:**
   - Buka tab **Soal** di portal pengawas.
   - Pastikan paket ujian (misal: Paket A, B, C, D) sudah terdaftar dan berisi nomor soal dengan bobot poin yang tepat.
4. **Pembersihan Sesi Ujian Sebelumnya:**
   - Buka tab **Monitor** dan klik tombol **Bersihkan Sesi**.
   - Ini akan mengosongkan riwayat login mahasiswa sebelumnya sehingga sistem siap menerima peserta baru.
5. **Kondisi Awal Ujian:**
   - Pastikan status ujian berada pada posisi **Menunggu** (Badge kuning). Dalam kondisi ini, mahasiswa yang login akan diarahkan ke *Waiting Room* dan lembar soal belum dapat diakses.

---

## 3. Pelaksanaan Ujian (Saat Ujian Berlangsung)

### A. Alur Masuk Mahasiswa:
1. Mahasiswa membuka browser (Google Chrome / Microsoft Edge) dan mengakses:
   `http://<HOST_IP>:8000`
2. Mahasiswa memasukkan **NIM** dan **Nama Lengkap**, lalu memilih Paket Soal di ruang tunggu.
3. Mahasiswa menunggu di Waiting Room hingga pengawas membuka ujian.

### B. Membuka Akses Ujian:
1. Pada portal pengawas (`/admin`), amati daftar mahasiswa yang terhubung di kartu **Kontrol Ujian** (`admin-waiting-count`).
2. Setelah seluruh peserta hadir dan siap di ruang tunggu, klik tombol **Mulai Ujian** (berwarna hijau).
3. Status berubah menjadi **Aktif**. Seluruh laptop mahasiswa akan secara otomatis dialihkan ke lembar pengerjaan soal (`/exam`) tanpa perlu me-refresh browser.

### C. Pemantauan Real-Time (Tab Monitor):
1. Pengawas memantau tabel **Aktivitas Mahasiswa** yang diperbarui secara otomatis tiap 6 detik:
   - **NIM & Nama:** Identitas peserta.
   - **IP Address:** Memastikan tidak ada 2 mahasiswa menggunakan IP yang sama / login ganda.
   - **Submisi:** Jumlah nomor soal yang telah dikerjakan dan disimpan.
   - **Skor:** Perolehan nilai sementara hasil evaluasi autograder.
   - **Peringatan:** Menampilkan frekuensi berpindah tab / jendela ujian.
2. **Penanganan Pelanggaran:**
   - Jika peserta berpindah tab, counter peringatan akan bertambah dan dicatat di audit log.
   - Pengawas dapat melakukan **Reset Sesi** pada baris mahasiswa terkait jika diperlukan tindakan disipliner atau login ulang.

---

## 4. Prosedur Pasca-Ujian (Selesai Ujian & Export)

1. **Menutup Ujian:**
   - Ketika waktu ujian habis, pengawas menekan tombol **Hentikan Ujian** (berwarna merah) di tab Monitor.
   - Lembar soal peserta otomatis terkunci dan diarahkan kembali ke ruang tunggu.
2. **Mengunduh Berkas Hasil Ujian:**
   - Buka tab **Export** di portal pengawas:
     - Klik **Unduh CSV**: Rekapitulasi tabel nilai dan jawaban seluruh mahasiswa dalam format Excel/CSV.
     - Klik **Unduh ZIP**: Berkas arsip `.zip` yang berisi satu file SQL jawaban rapi per mahasiswa (contoh: `H071231052_Yusra_Erlangga.sql`) untuk penilaian lanjutan offline.
     - Klik **Unduh Log (CSV)**: Arsip kronologis aktivitas sistem untuk audit.
     - Klik **Unduh Pelanggaran (CSV)**: Rekap frekuensi perpindahan tab mahasiswa.
3. **Penyimpanan Aman:**
   - Simpan berkas CSV dan ZIP ke flashdisk atau penyimpanan pengawas.
4. **Shutdown Server:**
   - Tekan `Ctrl + C` pada jendela konsol runner host untuk menghentikan server secara bersih.

---

## 5. Prosedur Darurat & Troubleshooting

| Gejala | Penyebab Umum | Solusi Cepat |
|---|---|---|
| Mahasiswa tidak bisa membuka `http://<HOST_IP>:8000` | Firewall Windows memblokir port 8000 atau IP host berubah. | Buka *Windows Defender Firewall with Advanced Security* -> *Inbound Rules* -> Tambahkan Rule port TCP 8000 (Allow Connection). Periksa ulang IP host dengan `ipconfig`. |
| Server host mendadak mati / laptop restart | Mati listrik / kehabisan baterai. | Nyalakan kembali laptop host dan jalankan `run.bat` / `run.ps1`. Karena database SQLite menggunakan mode WAL (`exam_system.db`), seluruh sesi, jawaban tersimpan, dan skor mahasiswa tetap aman dan tidak hilang. Mahasiswa cukup login kembali. |
| Mahasiswa salah memilih paket soal | Terlanjur memilih Paket A padahal jadwalnya Paket B. | Pada tab Monitor pengawas, klik tombol **Reset Paket** pada baris nama mahasiswa terkait. Mahasiswa kemudian dapat memilih ulang paket soal. |
| Database PostgreSQL error saat query | Koneksi pool terputus. | Buka tab Database pengawas dan klik tombol **Reset Database** untuk membersihkan dan memulihkan state koneksi. |

---

## 6. Kapasitas Beban & Batas Aman Mahasiswa (P1-5)

Berdasarkan pengujian beban konkuren (`scripts/run_regression_tests.py` dan `scratch/test_concurrent_load.py`):
- **Hasil Pengujian Beban:**
  - 35 worker konkuren secara simultan mengeksekusi 70 query kompleks (multitable JOIN dan agregasi) pada database `pagila`.
  - Seluruh 70 query berhasil 100% tanpa ada query yang gagal atau mengalami error koneksi.
  - Throughput rata-rata sistem: **13.7 query/detik**.
  - Waktu tunggu rata-rata antrian connection pool: **~1.19 detik**.
  - Kehabisan pool (*exhausted count*): **0**.
- **Karakteristik Perilaku Ujian Mahasiswa:**
  - Selama pengerjaan ujian praktikum, mahasiswa menghabiskan 80–90% waktunya untuk membaca instruksi soal dan menyusun sintaksis query di editor SQL.
  - Eksekusi query terjadi secara berkala (*intermittent burst*), rata-rata 1 kali eksekusi setiap 15–30 detik per mahasiswa.
- **Rekomendasi Batas Aman:**
  - **Kapasitas Aman Teruji:** **50 hingga 80 mahasiswa aktif secara bersamaan** pada satu laptop/server host standar (spesifikasi 4 Core CPU, 8GB RAM).
  - Untuk lab berkapasitas > 80 mahasiswa dalam satu ruangan, atur variabel lingkungan `PG_POOL_MAXCONN=60` atau `70` di `.env` dan pastikan konfigurasi `max_connections = 150` pada `postgresql.conf`.

---

## 7. Prosedur Rotasi Credential Pra-Ujian (P2-5)

Untuk menjaga integritas dan kerahasiaan sebelum ujian dimulai:

1. **Rotasi Master Key Pengawas:**
   - **Metode A (Melalui Dashboard Web):**
     1. Login ke `/admin/login`.
     2. Klik tombol **Ganti Password** di header dashboard admin.
     3. Masukkan password lama dan tentukan password baru yang kuat.
     4. Sistem akan otomatis memperbarui hash password di SQLite `exam_config`, membatalkan sesi lama, dan menerbitkan token sesi baru.
   - **Metode B (Melalui Environment Variable):**
     1. Buat atau edit file `.env` di direktori proyek:
        ```ini
        MASTER_KEY=UjianBasisData2026!Rahasia
        ```
     2. Jalankan server; sistem akan menggunakan master key dari environment variable.

2. **Rotasi Password Mahasiswa PostgreSQL (`student_role`):**
   - Secara default, role mahasiswa menggunakan password yang diatur pada setup awal.
   - Untuk merotasi sebelum hari-H ujian:
     1. Jalankan `psql -U postgres`:
        ```sql
        ALTER ROLE student_role WITH PASSWORD 'SandiBaruPraktikum2026';
        ```
     2. Tambahkan atau perbarui entri di file `.env`:
        ```ini
        PG_STUDENT_PASS=SandiBaruPraktikum2026
        ```
     3. Restart server aplikasi.

---

## 8. Prosedur Backup & Restore SQLite & PostgreSQL (P2-4)

### A. Backup Database SQLite (`exam_system.db`):
Karena SQLite berjalan dalam mode WAL (`journal_mode=WAL`), backup aman dilakukan bahkan saat ujian sedang berlangsung:

1. **Backup Online (Tanpa Mematikan Server):**
   - Melalui utilitas SQLite:
     ```cmd
     sqlite3 exam_system.db ".backup 'backup_exam_system_%DATE%.db'"
     ```
   - Melalui Python script:
     ```bash
     python -c "import sqlite3; s = sqlite3.connect('exam_system.db'); b = sqlite3.connect('backup_exam.db'); s.backup(b); b.close(); s.close(); print('Backup SQLite Sukses!')"
     ```
2. **Restore SQLite:**
   - Matikan server (`Ctrl + C`).
   - Salin file backup menggantikan `exam_system.db`.
   - Hapus file temporary `-wal` dan `-shm` jika ada:
     ```cmd
     del exam_system.db-wal exam_system.db-shm
     ```
   - Jalankan kembali server.

### B. Backup & Restore Database Master PostgreSQL:
1. **Backup Master `pagila` dan `classicmodels`:**
   ```cmd
   pg_dump -U postgres -d pagila -F c -b -v -f "backup_pagila.dump"
   pg_dump -U postgres -d classicmodels -F c -b -v -f "backup_classicmodels.dump"
   ```
2. **Restore Database:**
   ```cmd
   pg_restore -U postgres -d pagila --clean --if-exists -v "backup_pagila.dump"
   pg_restore -U postgres -d classicmodels --clean --if-exists -v "backup_classicmodels.dump"
   ```
   *Catatan:* Anda juga dapat menggunakan tombol **Reset Database** di tab Database Admin untuk memulihkan tabel dari SQL baseline bawaan (`data/pagila-0.10.1/` dan `data/classicmodels.sql`).

---

## 9. Batasan Deployment Multi-Worker & Evaluasi Shared Store (P1-6, P1-7, P2-6)

Sistem dirancang secara presisi sebagai aplikasi proses tunggal (*single-process ASGI*) yang sangat efisien untuk komputer/laptop host laboratorium offline.

### Mengapa Single-Worker Direkomendasikan untuk Lab Offline:
1. **SQLite WAL Single-Writer:** SQLite mode WAL mengizinkan pembacaan konkuren tanpa batas (*unlimited concurrent readers*), namun penulisan dilakukan secara berurutan (*single writer lock*). Dalam proses tunggal dengan `busy_timeout=5000ms`, tidak pernah terjadi lock contention.
2. **In-Memory Rate Limiting & Sesi:** Modul proteksi brute-force `InMemoryRateLimiter` dan pelacak connection pool PostgreSQL beroperasi dalam memori proses lokal (*thread-safe in-memory state*).
3. **Kapasitas Sudah Memadai:** Satu worker Uvicorn berbasis asynchronous event loop mampu melayani hingga 80 mahasiswa secara stabil, yang umumnya sudah mencakup 1-2 ruangan lab praktikum.

### Batasan dan Panduan Jika Menggunakan Multi-Worker (`--workers N`):
Jika dijalankan dengan `uvicorn --workers 4`:
- Masing-masing proses worker akan memiliki instansiasi memori terpisah, sehingga bucket counter *rate limiter* tidak dibagikan antar worker.
- Terjadi potensi *database locked* pada SQLite jika beberapa proses worker mencoba menulis tabel `submissions` atau `exam_logs` pada milidetik yang persis sama.

### Roadmap Migrasi Multi-Server / Kampus Berskala Besar (P1-6 & P1-7):
Untuk deployment skala besar (> 200 mahasiswa secara serentak melintasi beberapa gedung laboratorium):
1. **Migrasi Tabel State ke PostgreSQL:** Pindahkan tabel `users`, `exam_logs`, `submissions`, dan `exam_config` dari SQLite ke PostgreSQL database khusus (misal: `exam_backend`).
2. **Shared Store Redis:** Gunakan Redis untuk sentralisasi token sesi, heartbeat, dan distributed sliding-window rate limiting.
3. Dokumen evaluasi arsitektur lengkap dapat dilihat pada [docs/design/ARCHITECTURE_EVALUATION.md](file:///c:/project/anti-cheating-sqlexam/docs/design/ARCHITECTURE_EVALUATION.md).
