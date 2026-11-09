# Fase 6: pengujian operasional, backup, dan pemulihan

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 8 November 2026, Asia/Makassar.

## Pekerjaan yang diselesaikan

Fase ini menutup pekerjaan operasional yang tersisa dalam laporan fase sebelumnya:
pengukuran HTTP yang dapat diulang, backup/pemulihan yang diuji, pemeriksaan kesiapan,
dan runbook pelaksanaan/insiden. Tidak ada deployment atau mutasi database utama.

### Backup dan pemulihan

`exam_backup.py` dan CLI `scripts/exam_backup.py` membuat bundle SQLite, dua dump
PostgreSQL custom, dan upload soal. SQLite memakai backup API sehingga transaksi
dalam WAL ikut tercakup. Manifest menyimpan versi, checksum, ukuran file, dan waktu
operasi. File `.env` serta kredensial admin PostgreSQL tidak disalin.

Backup dipublikasikan hanya setelah selesai. Restore memverifikasi checksum,
integritas/FK SQLite, versi skema, dan path. Direktori/database yang sudah ada tidak
ditimpa. Backup yang gagal diberi nama `.incomplete-*`. Restore sebagian yang gagal
tidak menghapus database lama atau otomatis menghapus hasil parsial.

Pemulihan mempertahankan nilai terbaik, riwayat, audit, hash master key, dan secret
sandbox. Seluruh sesi dicabut; ujian kembali waiting dan revisinya dinaikkan. Role
PostgreSQL/ACL lama tidak diimpor; aplikasi membangun kembali akses melalui hardening
dan provisioning workspace. Uji nyata mencakup master `pagila`/`classicmodels`, tabel
sandbox, identity/sequence, serta SELECT/INSERT memakai login mahasiswa setelah restore.

Pengukuran akhir pada fixture: backup sekitar 2,25 detik, restore sekitar 5,39 detik,
bundle sekitar 4,77 MB. Ini bukan RTO layanan: persiapan mesin, konfigurasi, hardening,
dan pemeriksaan operator tidak termasuk. PostgreSQL fixture memakai fsync nonaktif.

### Login kelas dan observabilitas

Batas lama 15 login per IP per menit dapat menolak sebagian kelas yang memakai NAT.
Batas sekarang dipisahkan: 6 per identitas/IP per menit serta 120 per IP per menit.
Input NIM/nama/device dibatasi panjang. Batas login admin tetap sama.

`/ready` memeriksa versi SQLite serta koneksi admin/mahasiswa ke kedua database master.
Kegagalan database kedua menghasilkan 503. Respons publik tidak lagi memuat detail
exception atau statistik pool. `GET /api/admin/diagnostics` menyediakan status, pool,
dan batas evaluator untuk sesi admin yang sah. Readiness tetap pemeriksaan koneksi,
bukan pengganti validasi acuan atau kelengkapan seluruh dataset.

### Uji beban HTTP

`scripts/run_load_test.py` selalu membangun cluster, SQLite, dan server HTTP sementara.
Tidak menerima URL produksi. Hasil JSON terpisah dari regresi rutin agar pengukuran
dapat diulang sesuai host dan ukuran kelas.

| Tahap | Request/paralel | Hasil | p95 |
|---|---|---|---:|
| Login IP bersama | 24/24 | 24 berhasil | 768 ms |
| Preview master | 24/4 | 24 berhasil | 261 ms |
| Sandbox dingin | 24/4 | 24 berhasil | 652 ms |
| Penilaian penuh 1.000 baris | 24/4 | 24 benar | 778 ms |
| Lonjakan submit | 24/24 | 4 benar, 20 pending-limit | 962 ms |
| Retry bertahap | 24/4 | 24 benar | 763 ms |
| Submit sesudah stop | 24/4 | 24 ditolak | 45 ms |

Tidak ada error tak terduga. Seluruh skor terbaik bertahan dan percobaan pending
memiliki nilai/kebenaran NULL. Lonjakan diuji setelah tahap penilaian benar; skor
terbaik yang sudah ada tidak hilang. Kecepatan penilaian bertahap sekitar 6,35 jawaban
per detik; throughput respons pending tidak dihitung sebagai throughput penilaian.

Lingkungan: Windows 11, Python 3.14.6, PostgreSQL 18.6, 8 CPU logis, satu Uvicorn,
loopback, PostgreSQL fsync/synchronous_commit nonaktif. Tidak mencakup Wi-Fi kelas,
browser serentak, soal terberat, gangguan daya, atau beban berkepanjangan. Klaim lama
“50–80 mahasiswa aman” dihapus; tidak ada klaim kapasitas kelas produksi baru.

Data pengukuran: [PHASE6_LOAD_RESULTS.json](PHASE6_LOAD_RESULTS.json).

## Regresi akhir

Runner dari salinan sumber bersih lulus **21/21 pemeriksaan**, exit code 0, dengan
**220 tes normal lulus dan tanpa expected failure**. Salinan mencakup sumber Git
tracked/untracked yang tidak diabaikan, tanpa `.env`, SQLite lama, dan `scratch/`.

| Suite | Hasil |
|---|---|
| Migrasi SQLite | 10 lulus |
| Kendali ujian/sesi, riwayat, revisi | 43 lulus |
| Keamanan admin/CSRF/log | 26 lulus |
| Backup/integritas/pemulihan SQLite | 10 lulus |
| Kontrol operasional/NAT/diagnostics | 4 lulus |
| Parser SQL | 9 lulus |
| Pembanding hasil bertipe | 9 lulus |
| Submission | 29 lulus |
| Rekap/ZIP | 8 lulus |
| Retensi skor | 7 lulus |
| Sesi/mahasiswa terlambat | 7 lulus |
| Operasional/readiness database kedua | 8 lulus |
| Backup/pemulihan PostgreSQL nyata | 4 lulus |
| Privilege dan sandbox | 28 lulus |
| Evaluator hasil lengkap | 12 lulus |
| Regresi temuan | 6 lulus |

Sintaks Python/JavaScript, konsistensi dependensi, dan whitespace Git lulus. Hash
SHA-256 seluruh database utama `*.db` dan `.env` tetap sama sebelum/sesudah regresi.
Cluster/direktori fixture serta server HTTP benchmark telah dihentikan/dibersihkan.
Pesan cleanup gagal pada suite keamanan adalah dependency sengaja yang menguji rollback.

Suite baru mencakup backup/WAL/checksum/path, pencegahan overwrite, kegagalan dump,
pencabutan sesi, restore PostgreSQL nyata, login NAT, serta diagnostics. Regresi
operasional juga menguji kegagalan database sekunder dan penyembunyian detail publik.

## Panduan dan batas

Runbook [RELEASE_READINESS.md](../operations/RELEASE_READINESS.md) memuat prosedur
pra-ujian, budget koneksi, penanganan pending, backup offline, restore ke tujuan baru,
latihan pemulihan, retensi, serta insiden daya/koneksi. Klaim WAL menjamin nol kehilangan
data dan anjuran Reset Database untuk memperbaiki koneksi juga dikoreksi.

Backup lengkap memerlukan aplikasi/writer lain dihentikan; tidak ada transaksi snapshot
lintas SQLite/PostgreSQL saat writer masih aktif. Checksum bukan tanda tangan. Bundle
mengandung data/secret dan memerlukan perlindungan akses serta penyimpanan terpisah.
Saat ini format memerlukan SQLite versi 4; fase 6 tidak menambah versi skema.

Belum ada PITR, enkripsi bundle bawaan, purge otomatis, antrean pending otomatis,
atau regrade lewat formulir. Retensi mengikuti kebijakan institusi, sehingga data ujian
tidak dihapus otomatis. Deployment TLS, uji LAN/kapasitas host sebenarnya, dan latihan
operator tetap harus dilakukan sebelum menyatakan satu kelas siap dilayani.

Perubahan belum dikomit. Database utama dan `.env` tidak dipakai sebagai fixture.
