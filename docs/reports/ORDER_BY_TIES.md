# Perbaikan urutan seri — AEP1G

> Catatan historis sebelum/selama perbaikan. Status terbaru: [laporan lanjutan](GRADING_FAIRNESS_FIXES.md) dan [panduan aktif](../README.md). Temuan serta jumlah tes di bawah berlaku pada putaran saat laporan dibuat.

Percobaan terbaru bukan lagi column_mismatch, melainkan wrong_order. Pemeriksaan
read-only pada PostgreSQL menunjukkan hasil kunci dan jawaban masing-masing 192 baris.
Pada posisi 141 dan 142, NEW dan DRAMA pada bulan 9 memiliki nilai lain yang sama:
93 pembayaran, total 264.07, dan rata-rata 2.84. Keduanya hanya bertukar posisi.
ORDER BY bulan, total_pendapatan DESC tidak menentukan urutan kategori pada kondisi ini.

Evaluator sekarang dapat memetakan kunci ORDER BY yang merujuk alias/nama kolom output
unik. Ia menerima pertukaran baris seri jika urutan kunci seluruh baris dan multiset
seluruh isi baris tetap sama. Data berbeda atau urutan antarkelompok yang berubah tetap
ditolak. ORDER BY dengan ekspresi atau kolom yang belum dapat dipetakan tetap memakai
pembandingan posisi ketat; perbaikan ini tidak menebak kunci yang tidak tersedia.

Verifikasi pada hasil nyata: pembanding lama menghasilkan (False, wrong_order, 192),
pembanding baru menghasilkan (True, correct, 192). Tidak ada perubahan nilai atau data
ujian pada verifikasi ini. Regresi hasil bertipe lulus 10 tes, integrasi evaluator pada
PostgreSQL sementara lulus 13 tes, dan diff whitespace lulus. Regresi lengkap tidak
diulang; pengujian difokuskan pada pembanding dan integrasi evaluator yang berubah.

Restart server lalu submit ulang untuk menerapkan hasil baru. Percobaan lama tidak
diubah otomatis oleh perubahan kode ini.
