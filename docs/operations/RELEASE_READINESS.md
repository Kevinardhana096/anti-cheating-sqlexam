# Menyiapkan dan memulihkan pelaksanaan ujian

Panduan aktif, diperiksa 8 November 2026. Tabel benchmark fase 6 di bawah adalah
snapshot historis, bukan pengukuran ulang setelah seluruh perbaikan. Profil fase 7
tersedia pada [laporan fase 7](../reports/PHASE7_PERSISTENT_GRADING.md).

## Bukti kapasitas

Jalankan pengukuran pada host yang akan dipakai, sebagai proses Python baru:

```powershell
.\.venv\Scripts\python.exe scripts/run_load_test.py --students 24 --workers 4 --burst-workers 24 --output scratch/load-new.json
```

Prasyarat sama dengan regresi: dependency, `initdb`, dan `pg_ctl`; `TEST_PG_BIN`
dapat menunjuk direktori PostgreSQL. Benchmark membuat cluster PostgreSQL, SQLite,
dan server HTTP Uvicorn sementara. Tidak ada opsi URL produksi. Berkas hasil harus
baru. Cluster/server dihentikan dan dibersihkan setelah selesai.

Profil yang diuji: login 24 peserta dari satu IP, pemilihan paket, mulai ujian dengan
validasi acuan, preview JOIN/agregasi master, pembuatan sandbox dingin, penilaian penuh
1.000 baris, lonjakan submit, retry bertahap, pelestarian skor/NULL pending, dan
penolakan submit setelah ujian diakhiri. Profil tidak melibatkan browser seluruh kelas,
Wi-Fi/LAN, logging dua jam, SQL terburuk, atau beban proses lain.

Hasil 8 November pada Windows, Python 3.14.6, PostgreSQL 18.6, 8 CPU logis, satu proses:

| Tahap | Paralel | Hasil | p95 |
|---|---:|---|---:|
| Login IP bersama | 24 | 24 berhasil | 768 ms |
| Preview master | 4 | 24 berhasil | 261 ms |
| Preview sandbox dingin | 4 | 24 berhasil | 652 ms |
| Penilaian penuh bertahap | 4 | 24 benar | 778 ms |
| Lonjakan submit | 24 | 4 benar, 20 pending | 962 ms |
| Retry bertahap | 4 | 24 benar | 763 ms |
| Submit sesudah stop | 4 | 24 ditolak | 45 ms |

Penilaian bertahap mencapai sekitar 6,35 jawaban/detik pada fixture ini. Angka request
per detik pada tahap lonjakan mencakup respons pending, sehingga bukan throughput
penilaian. Tahap lonjakan dilakukan setelah peserta memiliki jawaban terbaik; nilai
terbaik seluruhnya tetap tersimpan. Pada jawaban pertama yang pending, nilainya
tetap NULL sampai dinilai, sesuai tes regresi.

PostgreSQL fixture memakai `fsync=off`/`synchronous_commit=off`. Ini mempercepat data
sementara dan tidak dipakai sebagai konfigurasi produksi atau bukti durabilitas.
Klaim lama “50–80 peserta pasti aman” tidak berlaku. Hasil rinci:
[PHASE6_LOAD_RESULTS.json](../reports/PHASE6_LOAD_RESULTS.json).

## Penerimaan sebelum membuka kelas

1. Simpan versi kode/dependensi yang sama dengan yang diuji; buat backup sebelum upgrade.
2. Jalankan regresi lengkap. Ulangi benchmark pada host dan ukuran kelas yang direncanakan.
3. Periksa `/health` dan `/ready`. Readiness memeriksa skema SQLite serta koneksi admin
   dan mahasiswa pada kedua master; ini bukan bukti kelengkapan semua data soal.
4. Login kedua pengawas, validasi acuan melalui mulai ujian, dan lakukan simulasi dengan
   perangkat mahasiswa pada LAN/Wi-Fi sebenarnya. Pastikan firewall mengizinkan hanya
   jaringan yang dimaksud. Pengaturan TLS/proxy harus mengikuti infrastruktur setempat;
   HTTP lokal sendiri tidak mengenkripsi trafik.
5. Periksa ruang disk, service PostgreSQL, `max_connections`, dan batas role/temp file.
   Diagnosis admin tersedia pada `GET /api/admin/diagnostics` dengan autentikasi.
6. Lakukan latihan restore ke tujuan baru, periksa nilai/riwayat/workspace/gambar, dan
   login ulang setelah hardening. Jangan menganggap backup berhasil sebelum pemulihannya diuji.

Login mahasiswa dibatasi 6 percobaan per identitas/IP per menit dan 120 per IP per
menit. Identitas dibedakan setelah normalisasi huruf/spasi luar. Batas admin tetap
6 per IP per 30 detik. Rate limiter per proses; IP dari proxy hanya dipercaya sesuai
`TRUSTED_PROXY_CIDRS` fase 2. Input NIM/nama/device kini dibatasi panjangnya.

Jangan menaikkan `PG_POOL_MAXCONN` hanya untuk mengejar jumlah mahasiswa. Budget perlu
memperhitungkan pool tiap master dan tiap proses, slot sandbox, dua koneksi workspace
per evaluasi sandbox, koneksi provisioning/admin, serta cadangan monitoring. Empat
slot evaluator dan 20 slot sandbox per proses tetap berlaku. Query yang aktif serentak
berbeda dari jumlah peserta yang terdaftar. Statistik waktu acquire pool mengukur
`getconn`, bukan antrean terjamin; pool penuh dapat menolak permintaan.

## Backup lengkap

Backup mencakup SQLite melalui backup API (termasuk transaksi dalam WAL), custom dump
`pagila`/`classicmodels` termasuk schema sandbox, serta upload soal. Manifest menyimpan
SHA-256/ukuran setiap file dan versi skema. Format mendukung SQLite versi 4 dan 5.
Tidak ada perubahan skema baru pada fase 6.

Riwayat SQLite latihan di `admin_practice` tidak termasuk snapshot SQLite utama.
Bundle ini tidak menjamin pemulihan riwayat simulasi admin; nilai mahasiswa tetap
berasal dari database utama. Pertahankan konfigurasi environment secara terpisah.

Hentikan aplikasi dan writer lain lebih dahulu. Snapshot SQLite dan tiap PostgreSQL
masing-masing konsisten, tetapi tidak merupakan satu transaksi lintas database ketika
writer masih berjalan. `--server-stopped` adalah pernyataan operator; alat tidak dapat
membuktikan seluruh aplikasi/proses lain sudah berhenti.

```powershell
.\.venv\Scripts\python.exe scripts/exam_backup.py backup --bundle C:\exam-backups\exam-2026-11-08 --pg-bin "C:\Program Files\PostgreSQL\18\bin" --server-stopped
.\.venv\Scripts\python.exe scripts/exam_backup.py verify --bundle C:\exam-backups\exam-2026-11-08
```

`--sqlite` dan `--uploads` dapat mengganti lokasi sumber. Koneksi PostgreSQL memakai
konfigurasi aplikasi; password tidak dimasukkan ke argumen proses. Untuk macOS/Linux,
gunakan Python virtual environment dan direktori bin PostgreSQL yang sesuai.

Direktori tujuan harus baru. Bundle hanya dipublikasikan setelah semua file selesai.
Kegagalan meninggalkan direktori `.incomplete-*`, bukan backup sukses. Periksa dan
amankan direktori tersebut; jangan menafsirkan keberadaannya sebagai cadangan siap pakai.

Bundle berisi data peserta, nilai, token sesi lama, hash master key, dan secret turunan
role sandbox. Simpan di lokasi terbatas, gunakan perlindungan/enkripsi disk atau media
cadangan organisasi, dan simpan salinan terpisah dari laptop ujian. Mode direktori
tidak menggantikan ACL NTFS; periksa hak akses folder induk. `.env`, sertifikat TLS,
password admin PostgreSQL, dan source code tidak disalin. Simpan konfigurasi rahasia
dan rilis kode yang cocok melalui prosedur terpisah.

Checksum mendeteksi korupsi, bukan autentikasi terhadap penyerang yang dapat mengubah
file dan manifest. PostgreSQL restore menjalankan isi dump sebagai admin: hanya gunakan
backup yang dipercaya. Role/login PostgreSQL tidak diekspor; kepemilikan/ACL dump tidak
diterapkan agar kredensial lama tidak disebarkan ke cluster baru.

## Pemulihan ke tujuan baru

Siapkan cluster PostgreSQL terpisah dengan versi yang kompatibel, admin yang sesuai,
dan koneksi/config mengarah ke cluster tersebut. Nama `pagila` dan `classicmodels`
harus belum ada. Siapkan checkout rilis aplikasi yang cocok, terpisah dari host lama.

```powershell
.\.venv\Scripts\python.exe scripts/exam_backup.py restore --bundle C:\exam-backups\exam-2026-11-08 --destination C:\exam-recovery\snapshot --pg-bin "C:\Program Files\PostgreSQL\18\bin" --server-stopped
```

Alat memverifikasi manifest, checksum, integritas/FK SQLite, versi skema, path, dan
seluruh nama database tujuan sebelum membuat database. Tidak ada DROP/overwrite database
lama. Pemulihan ditolak jika direktori tujuan atau salah satu database sudah ada.
Jika proses gagal sebagian, database baru yang sempat dibuat dibiarkan untuk diperiksa;
gunakan tujuan/prefix baru untuk percobaan berikutnya. Penghapusan sisa kegagalan harus
berdasarkan nama yang diperiksa operator, bukan wildcard atau penghapusan otomatis.

Untuk latihan dalam cluster yang sudah berisi database asli, gunakan
`--database-prefix drill_20261108_`. Hasilnya `drill_20261108_pagila` dan
`drill_20261108_classicmodels`; ini untuk inspeksi latihan, bukan konfigurasi aplikasi
standar. Untuk pemulihan layanan, gunakan cluster kosong dan nama standar.

SQLite dipulihkan menjadi `exam_system.db` dalam direktori tujuan. Atur
`EXAM_SQLITE_PATH` ke path itu. Salin `static/uploads/questions` hasil restore ke
direktori upload checkout baru sebelum melayani gambar. Source code/aset bawaan tetap
berasal dari checkout rilis, bukan bundle database.

Pemulihan mencabut semua sesi admin/mahasiswa, mempertahankan jawaban terbaik,
percobaan, audit, master-key hash, dan secret sandbox, lalu mengubah status ujian
menjadi waiting serta menaikkan revisi ujian. Pada backup skema 5, pekerjaan queued/running ditandai stale agar tidak dilanjutkan otomatis setelah restore. Jangan mengganti secret sandbox dengan
secret database kosong. Mulai aplikasi pada lingkungan terisolasi untuk inisialisasi
role/hardening master. Role pribadi dan kepemilikan tabel/sequence dibangun kembali
ketika workspace peserta diprovisioning. Pastikan akses role terbatas bekerja sebelum
membuka jaringan peserta; uji pemulihan mencakup SELECT/INSERT identity sebagai role
mahasiswa, bukan hanya pembacaan admin.

Opsi `--sqlite-only` harus dipilih eksplisit untuk pemulihan sebagian tanpa PostgreSQL.
Ini tidak memulihkan workspace/dataset dan bukan pemulihan layanan lengkap.

## Menangani ujian berjalan dan insiden

- Pending evaluator bukan jawaban salah. Jangan mengakhiri ujian hanya berdasarkan
  jumlah respons HTTP sukses; periksa status percobaan dan minta pengiriman ulang
  secara bertahap bila antrean meminta review. Setelah stop, submit baru ditolak,
  sedangkan pekerjaan sah yang sudah diterima dapat selesai melalui antrean fase 7.
  Retry otomatis hanya untuk konteks replay yang aman. Penilaian manual/regrade tersedia
  melalui API/CLI pada [GRADING_QUEUE.md](GRADING_QUEUE.md); formulir khusus belum ada.
- Gangguan PostgreSQL ditangani dengan pemeriksaan service/koneksi dan restart aplikasi
  jika diperlukan. Reset Database bukan cara memperbaiki pool/koneksi karena mengubah data.
- Setelah mati listrik, pertahankan file DB/WAL/SHM yang tersisa, periksa integritas dan
  jawaban tersimpan pada salinan, lalu pulihkan backup bila perlu. WAL/NORMAL tidak
  menjamin nol kehilangan transaksi pada kegagalan daya.
- RPO ditentukan waktu backup konsisten terakhir; belum ada backup online lintas store
  atau pengarsipan WAL/PITR. Durasi dump/restore fixture bukan RTO layanan penuh karena
  persiapan mesin, konfigurasi, hardening, dan pemeriksaan operator tetap diperlukan.

Tidak ada penghapusan otomatis log/audit/percobaan atau backup. Simpan arsip sesuai
kebijakan institusi dan jadwal keberatan nilai; setelah masa retensi disetujui, lakukan
pembersihan terencana dengan backup/pemulihan yang telah diuji. Sampai kebijakan itu
ditentukan, monitor ruang disk dan jangan menjalankan purge otomatis terhadap data ujian.
