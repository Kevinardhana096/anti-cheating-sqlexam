# Pengujian dan migrasi database

`test_admin_fixes.py` memeriksa penutupan temuan audit admin dan batas unggahan.
`test_admin_behaviors.cjs` memeriksa event dinamis, respons gagal dan polling yang
datang tidak berurutan. Keduanya masuk runner regresi; entry point audit admin lama
mengarahkan ke suite perbaikan.

`test_grading_fairness.py` menjalankan regresi audit penilaian pada PostgreSQL sementara:
urutan seri/ordinal/qualified/ekspresi, toleransi, JSON, array, index, CHECK dan keputusan
review. `audit_grading_edge_cases.py` adalah alat audit perilaku dengan ekspektasi awal;
hasil mismatch pada alat audit dapat berupa review yang sengaja menggantikan keputusan
otomatis. Gunakan suite regresi untuk menilai kelulusan perbaikan.

## Menjalankan regresi lengkap

Jalankan dari direktori proyek menggunakan Python pada virtual environment:

```powershell
.\.venv\Scripts\python.exe scripts/run_regression_tests.py
```

Linux/macOS:

```sh
.venv/bin/python scripts/run_regression_tests.py
```

Prasyarat: dependensi `requirements.txt`, Node.js untuk pemeriksaan sintaks dan pengujian perilaku JavaScript,
Git, serta executable PostgreSQL `initdb` dan `pg_ctl`. Service PostgreSQL utama tidak
perlu dijalankan. Di Linux, jalankan dengan pengguna biasa karena `initdb` menolak root.

IDE pengujian admin diperiksa oleh `test_admin_practice.py` untuk autentikasi dan isolasi penyimpanan, serta `test_admin_practice_postgres.py` untuk kesamaan penilaian nyata, sandbox PostgreSQL dan antrean latihan. Pengujian JavaScript memeriksa bahwa controller mahasiswa hanya mengganti transport API ketika mode simulasi admin aktif.

Regresi juga menjalankan `test_frontend_behaviors.cjs` (formatter, status submit, heartbeat, fokus, lobby dan nomor paket), `test_minutes_fixes.py` (konflik nomor dan edit bersamaan), serta `test_setup_sqlite.py` (setup berulang, snapshot migrasi, dan penolakan versi masa depan). Pengujian formatter memakai library lokal yang sama dengan browser. Tidak perlu instalasi npm.

Jika executable PostgreSQL tidak ditemukan otomatis, arahkan ke direktori `bin`:

```powershell
$env:TEST_PG_BIN = 'C:\Program Files\PostgreSQL\18\bin'
.\.venv\Scripts\python.exe scripts/run_regression_tests.py
```

Runner membuat cluster PostgreSQL sementara dengan direktori data baru, identitas unik,
port lokal acak, serta database `pagila` dan `classicmodels` dari dataset repositori.
SQLite terpisah dibuat untuk setiap suite. Konfigurasi koneksi tes menggantikan environment proses; `.env` tidak dimuat; cluster dan direktori sementara dibersihkan setelah pengujian.
Cluster tes memakai autentikasi trust pada loopback, `fsync=off`, dan
`synchronous_commit=off` untuk data sementara.
Konfigurasi ini tidak digunakan untuk menjalankan aplikasi ujian.

Suite PostgreSQL dan suite operasional juga dapat dijalankan langsung. Masing-masing
akan membuat fixture sendiri. Jika dipanggil sebagai subprocess runner, skrip memeriksa
lokasi SQLite dan identitas cluster sebelum melakukan pengujian.

Untuk memeriksa migrasi tanpa PostgreSQL:

```powershell
.\.venv\Scripts\python.exe scripts/test_system_migrations.py
```

Opsi `scripts/run_regression_tests.py --sqlite-only` menjalankan pemeriksaan sintaks,
dependensi, whitespace, migrasi, kendali akses, parser SQL, dan pembanding hasil bertipe.
Opsi tersebut bukan regresi aplikasi lengkap.

## Cakupan dan pembacaan hasil

| Suite | Cakupan |
|---|---|
| `test_admin_fixes.py` | Transaksi/revisi paket, race penghapusan/pilihan peserta, snapshot/fence admin dan unggahan |
| `test_admin_behaviors.cjs` | Event dinamis, injeksi, HTTP gagal, navigasi galeri dan polling |
| `test_frontend_behaviors.cjs` | Formatter, submit, draft, heartbeat, fokus, nomor paket dan lobby |
| `test_admin_practice.py` | Otorisasi, CSRF dan isolasi simulasi |
| `test_admin_practice_postgres.py` | Kesamaan evaluator, sandbox dan worker simulasi nyata |
| `test_grading_fairness.py` | Seri, toleransi, JSON, array, index, CHECK dan review |
| `test_exam_start_failures.py` | Benturan Mulai/Hentikan, masuk serentak dan respons hilang |
| `test_minutes_fixes.py` | Konflik nomor soal dan perpindahan paket |
| `test_setup_sqlite.py` | Setup idempoten, snapshot migrasi dan versi masa depan |
| `test_system_migrations.py` | Instalasi kosong, upgrade lama/parsial, pelestarian data, idempotensi, rollback, versi tidak kompatibel |
| `test_exam_access.py` | Status ujian, batas submit, paket, pencabutan sesi, login serentak, dan IP |
| `test_admin_security.py` | Admin serentak, sesi persisten/kedaluwarsa, hash master key, CSRF, konflik edit, audit, log mahasiswa, ekspor aman, dan pemulihan lokal |
| `test_sql_policy.py` | AST, literal/komentar/Unicode, pembatasan perintah, daftar larangan fungsi, dan database virtual |
| `test_grading_queue.py` | Lease, restart proses, konflik dua admin, history/koreksi skor, cutoff, fencing revisi/dataset, migrasi, dan restore antrean |
| `test_grading_queue_postgres.py` | Evaluator nyata, selesai setelah stop, sandbox setup, worker lifespan/recovery, dan pemulihan master yang hilang |
| `test_grading_results.py` | Tipe native, presisi, duplikat, urutan, toleransi, dan batas hasil lengkap |
| `test_grading_engine.py` | Preview versus hasil lengkap, error acuan, snapshot DDL/DML, sequence/index/FK, setup, dan cleanup evaluator |
| `test_exam_submission_suite.py` | DDL, DML, SELECT, submit API, dan pemeriksaan SQL yang sudah tersedia |
| `test_leaderboard_and_zip_export.py` | Perhitungan rekap dan ekspor ZIP |
| `test_score_retention.py` | Penyimpanan jawaban dan skor terbaik |
| `test_latecomer_and_session_lock.py` | Login, NAT bersama, dan pembebasan sesi |
| `test_backup.py` | Snapshot WAL, integritas/checksum, path, pencegahan overwrite, pencabutan sesi, dan pelestarian riwayat |
| `test_backup_postgres.py` | pg_dump/pg_restore nyata, kedua master, workspace/sequence, rekonstruksi role, dan pencegahan overwrite |
| `test_operational_controls.py` | Login NAT 24 peserta, pembatasan identitas, readiness publik, dan diagnostics admin |
| `test_operations.py` | Health/readiness, siklus startup/shutdown, pemulihan sesi, penampil tabel, dan query serentak |
| `test_sandbox_security.py` | Privilege PostgreSQL langsung, migrasi sandbox, rollback, deadline, dan kebersihan pool |
| `test_known_risks.py` | Temuan terbuka dan regresi temuan yang sudah ditutup |

Seluruh enam tes di `test_known_risks.py` kini berjalan sebagai tes biasa. Tidak ada
penanda expected-failure yang tersisa dalam suite. Cakupan ini tidak mencakup seluruh
skenario keamanan atau menggantikan uji beban kelas.

Skrip lama dalam `scratch/` bukan dependensi regresi lagi. Pemeriksaan operasionalnya
diganti dengan pengujian perilaku di `test_operations.py`; jumlah baris dataset dibaca
dari fixture, bukan diasumsikan sama dengan database lokal pengembang. Audit sumber
lama yang mencari potongan teks tertentu tidak dipakai sebagai bukti keamanan.
Regresi lulus tidak menyatakan seluruh temuan keamanan atau penilaian telah selesai.

## Versi skema SQLite

Versi disimpan dalam `PRAGMA user_version`:

| Versi | Perubahan |
|---|---|
| 0 | Database lama tanpa versi, termasuk yang pernah ditambah kolom manual |
| 1 | Kolom sesi/paket, database virtual, metadata soal, dan metadata paket |
| 2 | Kolom `is_correct`, `score`, `eval_status`, dan `feedback` pada `submissions` |
| 3 | Kebijakan/setup/revisi soal, status validasi acuan, revisi jawaban terbaik, dan tabel `submission_attempts` |
| 4 | `admin_sessions`, `admin_audit`, dan `edit_revision` soal; master key plaintext lama dikonversi ke hash saat inisialisasi |
| 5 | `grading_jobs`, `grading_decisions`, dan `users.grading_revision`; pending lama masuk review |

`init_system_db()` menjalankan migrasi saat startup aplikasi. Kolom yang sudah ada
dipertahankan. Jawaban lama tanpa nilai diberi nilai awal 0 dengan status `pending`;
migrasi tidak menilai ulang jawaban atau menebak nilai yang belum pernah tersimpan.
Nilai, feedback, ID, dan jawaban yang sudah tersimpan tidak ditimpa oleh migrasi.
Versi 3 mengimpor jawaban terbaik lama sekali ke riwayat dengan sumber `legacy_best`.
Perubahan penilaian soal setelah migrasi memiliki aturan revisi tersendiri dalam
[GRADING.md](GRADING.md).

Seluruh langkah migrasi versi berjalan dalam satu transaksi `BEGIN IMMEDIATE`. Jika
satu langkah gagal, perubahan kolom dan versi dibatalkan, error diteruskan, dan startup
gagal. Pembuatan tabel/index dasar dan seeding berada di luar transaksi migrasi versi.
Versi lebih baru ditolak sebelum inisialisasi tabel. Versi yang mengklaim sudah terbaru
tetapi kehilangan kolom wajib juga ditolak; penyebab kerusakan perlu diperiksa.

Sebelum memperbarui server ujian, hentikan aplikasi dan buat backup database. Gunakan
SQLite backup API agar isi WAL ikut tercakup, atau salin database setelah semua koneksi
ditutup. Uji pemulihan pada salinan sebelum menggunakan pembaruan untuk ujian.

## Memeriksa dari salinan bersih

Gunakan checkout baru, pasang `requirements.txt` dalam virtual environment, lalu jalankan
runner. Tidak diperlukan `.env`, `scratch/`, SQLite lama, atau database PostgreSQL lama.
Dataset SQL dalam `data/` harus tersedia. Jangan menambahkan database, rahasia `.env`,
atau direktori cluster sementara ke Git.

## Pengukuran HTTP terpisah

```powershell
.\.venv\Scripts\python.exe scripts/run_load_test.py --students 24 --workers 4 --burst-workers 24 --output scratch/load-new.json
```

Benchmark selalu membuat cluster dan server HTTP sementara; tidak menerima URL server
produksi. Output harus berkas baru. `pending_limit` adalah jawaban tersimpan tanpa
nilai final dan dihitung terpisah dari penilaian benar. Benchmark bukan bagian runner
regresi harian, dan tidak menggantikan uji LAN/ketahanan jangka panjang. Lihat
[RELEASE_READINESS.md](RELEASE_READINESS.md).

Untuk menguji antrean otomatis tanpa submit ulang, tambahkan `--automatic-drain` pada
benchmark dan gunakan output baru. Profil ini mengakhiri ujian sesudah lonjakan,
menunggu antrean selesai, lalu memeriksa penilaian efektif dari sisi server/admin;
API soal mahasiswa tetap tertutup sesudah stop.
