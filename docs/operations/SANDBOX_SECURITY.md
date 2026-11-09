# Sandbox PostgreSQL dan batas eksekusi SQL

## Identitas dan hak akses

Database master `pagila` dan `classicmodels` memakai login `PG_STUDENT_USER` untuk
SELECT. Role ini tidak memiliki superuser, CREATEDB, CREATEROLE, replication, bypass
RLS, atau keanggotaan role lain. Hak tulis tabel, perubahan sequence, CREATE schema,
dan TEMP tidak diberikan. Transaksi eksekusi master juga ditetapkan read-only.

Setiap mahasiswa memiliki login PostgreSQL tersendiri untuk `sandbox_pribadi`, dengan
nama role `exam_s_<digest>` dan schema `sandbox_<digest>`. Digest berasal dari SHA-256
NIM yang dinormalisasi huruf kecil dan dienkode base32. Seluruh digest dipakai; nama
tetap kurang dari batas 63 byte PostgreSQL dan tanda titik/tanda hubung tidak dihapus.
Sebagai contoh, `AB-12` dan `ab.12` memperoleh workspace berbeda, sedangkan variasi
huruf besar/kecil dari NIM yang sama tetap menunjuk satu workspace.

Role pribadi hanya diberi CONNECT ke database kerja serta USAGE/CREATE pada schema
sendiri. Role tersebut tidak mewarisi role master. Mengubah `search_path` tidak
memberikan hak pada schema peserta lain. LOGIN dilakukan langsung sebagai role
pribadi; kegagalan login tidak pernah beralih ke koneksi admin atau SET ROLE admin.

Password role pribadi diturunkan menggunakan HMAC-SHA256 dan secret acak dalam
`system_settings.sandbox_role_secret`. Password tidak dikirim ke browser. Sertakan
SQLite dan konfigurasi PostgreSQL dalam prosedur backup; jangan membagikan file SQLite
atau kredensial admin kepada peserta. Port PostgreSQL tetap hanya untuk host aplikasi.

## Koneksi dan transaksi

- Koneksi sandbox dibuat baru untuk setiap permintaan dan ditutup setelah selesai.
  Identitas mahasiswa tidak pernah diganti pada satu koneksi yang dipakai bersama.
- Koneksi master memakai pool. Sebelum dan sesudah pemakaian, transaksi dibatalkan dan
  `DISCARD ALL` membersihkan setting sesi, prepared statement, cursor, dan advisory lock.
  Koneksi yang gagal dibersihkan ditutup.
- Seluruh skrip sandbox berjalan dalam satu transaksi. Error pada statement terakhir
  membatalkan perubahan PostgreSQL dari statement sebelumnya dalam permintaan tersebut.
- CREATE DATABASE / USE / DROP DATABASE adalah emulasi label satu database virtual.
  Perintah itu tidak membuat database PostgreSQL fisik. DROP membersihkan tabel schema
  sendiri; metadata SQLite baru diperbarui setelah commit PostgreSQL berhasil.
- SQLite dan PostgreSQL bukan satu transaksi terdistribusi. Kegagalan penyimpanan
  metadata virtual setelah commit PostgreSQL masih memerlukan pemulihan operasional.

## SQL yang didukung

Pemeriksaan memakai AST PostgreSQL melalui [pglast](https://pglast.readthedocs.io/en/latest/index.html).
Seluruh skrip diperiksa sebelum statement pertama dieksekusi. Pemisahan statement
mengikuti scanner PostgreSQL sehingga literal, dollar quote, komentar bertingkat, dan
Unicode tidak diperlakukan sebagai batas statement yang salah.

Master menerima SELECT, termasuk subquery dan CTE SELECT. SELECT INTO, row locking,
dan CTE dengan perubahan data ditolak. Sandbox menerima SELECT, CREATE TABLE/AS SELECT,
INSERT, UPDATE, DELETE, TRUNCATE, DROP TABLE/INDEX, CREATE INDEX, serta subset ALTER TABLE
untuk kolom dan constraint. Kebijakan fungsi memakai **daftar larangan**, bukan daftar
fungsi yang diizinkan. Fungsi yang tidak terlarang diteruskan ke PostgreSQL tanpa
pendaftaran; jika fungsi tidak tersedia, PostgreSQL mengembalikan error SQL biasa.
Daftar nama dan keluarga fungsi terlarang ada pada `BLOCKED_FUNCTIONS` dan
`BLOCKED_FUNCTION_PREFIXES` di `sql_policy.py`. Pembatasan tipe data tetap terpisah.

Yang dilarang mencakup perubahan konfigurasi sesi, penghentian backend, akses berkas
dan large object, koneksi eksternal, advisory lock, sleep, kontrol backup/replication,
notifikasi dan statistik server, serta eksekusi SQL dari string melalui fungsi XML
atau `ts_rewrite`. Pemeriksaan membaca nama fungsi dari AST, termasuk pemanggilan
dengan `pg_catalog`, tanda kutip atau fungsi di dalam CTE. Literal dan komentar tidak
dicocokkan sebagai panggilan fungsi. Fungsi dengan schema eksplisit selain
`pg_catalog` tetap ditolak; extension dan fungsi buatan peserta tidak dibuka oleh
perubahan ini. Perilaku fungsi administrasi dan SQL dinamis dirujuk pada dokumentasi
[administrasi PostgreSQL](https://www.postgresql.org/docs/18/functions-admin.html),
[XML](https://www.postgresql.org/docs/18/functions-xml.html), dan
[text search](https://www.postgresql.org/docs/18/functions-textsearch.html).

Daftar larangan bukan satu-satunya batas keamanan: hak akses role PostgreSQL, transaksi
master read-only, isolasi schema, validasi statement dan batas sumber daya tetap
berlaku. Daftar ini perlu ditinjau saat versi PostgreSQL atau extension server berubah.
Fungsi acak/waktu boleh dipakai untuk Run Query, tetapi fungsi nondeterministik yang
dikenali tidak diterima sebagai acuan otomatis dan jawaban terkait tidak diputar ulang
otomatis oleh antrean penilaian.

SET/RESET, perubahan role/session authorization, DO, fungsi/prosedur/trigger buatan
peserta, COPY, extension, prepared statement, dan pengaturan timeout ditolak. Gunakan
SELECT terpisah untuk melihat hasil DML karena RETURNING tidak tersedia pada jalur ini.
Whitelist melengkapi privilege PostgreSQL; isolasi schema tidak bergantung pada regex.

## Batas sumber daya

| Batas | Nilai |
|---|---|
| Panjang query | 10.000 karakter |
| Jumlah statement | 20 per permintaan |
| Anggaran eksekusi | 5 detik untuk seluruh skrip, bukan 5 detik per statement |
| Lock timeout | 3 detik |
| Baris keluaran preview | Maksimal 500 |
| Kolom keluaran | Maksimal 64 |
| Panjang sel teks | 4.000 karakter, lalu penanda pemotongan |
| Data baris JSON preview | Anggaran 256 KiB, di luar metadata respons |
| Baris terpengaruh oleh DDL/DML | Maksimal 10.000 per permintaan; pelanggaran membatalkan transaksi |
| Koneksi sandbox bersamaan | Default 20 per proses, melalui `PG_SANDBOX_MAXCONN` |
| Koneksi per role pribadi | Maksimal 2 |
| `work_mem` / `maintenance_work_mem` | 4 MiB / 16 MiB |
| File temporary per backend | 32 MiB |

SELECT diambil melalui server-side cursor dalam batch kecil, sehingga semua baris
hasil tidak dikirim sekaligus ke proses Python. Deadline memakai statement timeout
yang disesuaikan dengan sisa waktu dan watchdog pembatalan. Penghentian watchdog
diselesaikan sebelum koneksi master dikembalikan ke pool.

Batas ini bukan hard quota untuk keseluruhan memori atau disk PostgreSQL. Satu nilai
hasil tetap harus dihitung oleh server, dan pemotongan sel dilakukan setelah nilainya
diambil. Work mem juga berlaku per operasi, bukan per seluruh permintaan. Provisioning,
commit, cleanup, dan komunikasi dapat menambah waktu respons di luar anggaran eksekusi;
profil kapasitas serta batas host tetap perlu diuji pada perangkat pelaksanaan.

## Upgrade workspace lama

Saat startup, hak PUBLIC dan `student_role` pada schema sandbox lama dicabut. Tabel
yang masih dimiliki role bersama dialihkan ke admin agar role bersama tidak tetap
memiliki hak kepemilikan. Data tidak dihapus oleh proses hardening ini.

Ketika workspace dibuka pertama kali, aplikasi mencocokkan nama schema lama dengan
daftar NIM SQLite. Jika tepat satu pemilik cocok, schema diubah namanya ke digest dan
kepemilikan tabel/sequence diberikan kepada role pribadi dalam satu transaksi.

Upgrade otomatis ditolak jika pemilik ambigu atau ditemukan fungsi, operator, tipe
khusus, trigger, view, foreign table, atau relasi tertentu lintas schema yang perlu
ditinjau. Transaksi provisioning dibatalkan; schema lama tetap tersedia untuk admin.
Jangan menghapus schema ambigu untuk sekadar menghilangkan error. Pengawas perlu
memetakan dan memulihkan data yang benar pada salinan backup terlebih dahulu.

Provisioning dan cleanup memakai advisory lock yang sama. Perubahan ACL database
diserialkan untuk mencegah konflik katalog saat beberapa role dibuat serentak.
Kegagalan setup keamanan membuat jalur eksekusi menolak koneksi; periksa `/ready` dan log.

## Pembersihan

`database.cleanup_student_sandbox_schema(nim)` menghapus schema dan role pribadi dalam
satu transaksi. Jika role masih memiliki dependency yang tidak diharapkan, cleanup
gagal dan di-rollback. Pemanggilan berikutnya dapat membuat workspace baru setelah
cleanup berhasil. Fungsi ini bersifat destruktif terhadap workspace peserta.

**Bersihkan Sesi** tetap mengikuti fase 2: menghapus peserta/jawaban SQLite. Tindakan
tersebut tidak menghapus semua workspace PostgreSQL secara otomatis. Bersihkan workspace
secara eksplisit saat menyiapkan dataset pribadi baru. `scripts/reset_exam_session.py`
memakai mekanisme reset per NIM yang juga memanggil cleanup sandbox; perhatikan bahwa
reset tersebut juga menghapus jawaban peserta.

`setup_postgres.sql` kini hanya membuat dua database master jika belum ada. Semua
setup role, ACL, dan dataset dilakukan aplikasi saat startup. Jangan menjalankan ulang
skrip GRANT lama yang memberikan `student_role` hak atas sandbox pribadi.

## Pengujian

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/test_sql_policy.py
.\.venv\Scripts\python.exe scripts/test_sandbox_security.py
.\.venv\Scripts\python.exe scripts/run_regression_tests.py
```

Tes privilege memakai koneksi mahasiswa langsung tanpa filter SQL aplikasi untuk
membuktikan penolakan lintas schema oleh PostgreSQL. Seluruh tes database tersebut
memakai cluster sementara sesuai [TESTING.md](TESTING.md).

Penilaian hasil lengkap dan isolasi evaluator telah diterapkan pada fase 4. Lihat
[GRADING.md](GRADING.md). Proteksi admin, sesi independen, CSRF, dan validasi log
mengikuti [ADMIN_SECURITY.md](ADMIN_SECURITY.md).
