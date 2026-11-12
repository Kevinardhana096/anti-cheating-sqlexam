# Pemisahan validasi kesiapan dan mulai ujian

Pengujian: 10 November 2026.

## Perubahan perilaku

Validasi acuan dijalankan melalui **Validasi Kesiapan Ujian** sebelum ujian dimulai.
Hasil kesiapan disimpan di `system_settings` SQLite. Selama validasi, peserta tetap
menunggu. Tombol **Mulai Ujian** hanya memeriksa kesiapan yang masih berlaku dan
mengubah status dalam satu transaksi; SQL acuan tidak dijalankan ulang.

Kesiapan mencakup revisi/edit soal, kunci, target database, prasyarat, kebijakan
penilaian, bobot, nomor/kategori, susunan paket aktif, revisi dataset, konfigurasi
server PostgreSQL, dan anggaran evaluator. Perubahan membatalkan kesiapan. Status
dan konfigurasi diperiksa kembali sebelum hasil validasi disimpan. Validasi yang
bertabrakan dengan penghentian ujian tidak dapat membuka ujian atau menyimpan hasil
lama. Dua admin dapat memakai hasil kesiapan yang sama.

Tidak ada migrasi skema baru. Instalasi yang belum memiliki hasil kesiapan harus
menjalankan validasi sebelum memulai ujian berikutnya. Ujian yang sudah aktif tetap
aktif; permintaan mulai ulang bersifat idempoten.

## Bukti pengujian

| Pemeriksaan | Hasil |
|---|---|
| Regresi lengkap | 33/33 kelompok pemeriksaan lulus |
| Kasus kesiapan terbaru | 12 tes lulus |
| Perilaku JavaScript admin | 15 tes lulus |
| UI browser pada server pengujian terpisah | Menunggu → validasi → Siap, tetap Menunggu → Mulai → Aktif |
| Dokumentasi | Tautan dan referensi script diperiksa |

Uji integrasi menggunakan salinan SQLite yang berisi 20 soal aktif dan PostgreSQL
lokal. Tidak ada perubahan status ujian atau jawaban pada SQLite utama.

| Tahap | Durasi | HTTP | Status ujian sesudahnya |
|---|---:|---:|---|
| Validasi seluruh acuan | 100,040 detik | 200 | `waiting` |
| Mulai memakai hasil kesiapan | 0,0651 detik | 200 | `active` |

Saat permintaan mulai diuji, pemanggilan evaluator acuan sengaja dipasang agar
menghasilkan kegagalan tes jika dipanggil. Mulai tetap berhasil, sehingga waktu
tersebut tidak berasal dari validasi ulang. Durasi bergantung mesin dan beban;
pengujian ini tidak mengukur pengiriman jawaban mahasiswa secara serentak.

Kasus regresi tersedia di [test_exam_readiness.py](../../scripts/test_exam_readiness.py),
[test_exam_start_failures.py](../../scripts/test_exam_start_failures.py), dan
[test_admin_behaviors.cjs](../../scripts/test_admin_behaviors.cjs). Jalankan melalui
[run_regression_tests.py](../../scripts/run_regression_tests.py).

## Penerapan

Restart server untuk memuat endpoint baru, lalu refresh halaman admin. Jalankan
**Validasi Kesiapan Ujian** lebih awal dan tunggu status **Siap**. Pada waktu ujian,
tekan **Mulai Ujian**. Jika konfigurasi berubah, ulangi validasi kesiapan.
