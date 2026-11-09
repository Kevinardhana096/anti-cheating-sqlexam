# Implementasi IDE admin — 8 November 2026

> Catatan historis sebelum/selama perbaikan. Status terbaru: [laporan lanjutan](ADMIN_BEHAVIOR_FIXES.md) dan [panduan aktif](../README.md). Temuan serta jumlah tes di bawah berlaku pada putaran saat laporan dibuat.

IDE admin memakai template dan controller mahasiswa yang sama. Adapter transport menambahkan autentikasi sesi admin/CSRF dan mengarahkan API ke dispatcher admin; dispatcher memanggil fungsi mahasiswa yang sama dalam konteks SQLite terisolasi. ContextVar menjaga pemilihan database per permintaan tanpa mengganti environment global.

Snapshot hanya menyalin soal, paket dan revisi dataset. Tidak ada salinan identitas, skor atau sesi mahasiswa. Identitas sandbox simulasi memakai namespace NIM khusus yang ditolak pada login mahasiswa biasa. Berkas database latihan diturunkan dari lokasi database utama dan ID sesi admin. Semua akses API tetap memvalidasi sesi admin, termasuk setelah sesi dicabut. Antrean penilaian latihan tidak masuk antrean ujian; worker latihan memakai implementasi worker penilaian yang sama dan berhenti sebelum pool PostgreSQL ditutup.

Perbaikan bersama yang ditemukan saat verifikasi:

- Header IDE mengikuti tinggi aktual saat membungkus sehingga tidak menimpa editor.
- Pemilihan ulang paket mengembalikan submission yang sudah ada, agar status tersimpan tidak sementara tampil belum disubmit.
- Pembatasan log menggunakan NIM unik, sehingga ID pengguna SQLite latihan yang sama angkanya dengan mahasiswa tidak berbagi kuota.

## Bukti pengujian

Tes khusus mencakup otorisasi admin, CSRF/origin, kesamaan template/controller, penggunaan executor/evaluator mahasiswa, pemisahan nilai/log, dua admin independen, konteks database pada permintaan bersamaan, larangan pemalsuan identitas simulasi melalui login mahasiswa, retensi skor setelah ganti paket, maintenance/revisi dataset, pencabutan sesi, serta pemisahan kuota log.

Integrasi PostgreSQL nyata pada cluster sementara membandingkan hasil admin dan mahasiswa untuk jawaban benar, salah dan numeric; membuktikan isolasi tabel sandbox dan penolakan akses lintas schema; serta memproses jawaban admin pending melalui worker latihan.

Pemeriksaan browser dilakukan pada server sementara, termasuk login admin, masuk melalui tautan dashboard, fullscreen, pilihan paket, Format SQL, Run Query, submit benar/salah, retensi skor terbaik, pending manual dan ganti paket. Pada lebar viewport 1036px, tinggi header dan posisi awal IDE sama sehingga tidak bertumpuk. Pemeriksaan browser terakhir tidak menghasilkan error JavaScript; skor 10 tetap ditampilkan setelah pemilihan ulang paket.

Regresi aplikasi dari salinan sumber bersih lulus **29/29 pemeriksaan**, mencakup **291 tes Python dan 16 tes perilaku JavaScript**. Tes khusus admin berjumlah 12 tes isolasi/admission dan 3 tes PostgreSQL nyata. Pemeriksaan sintaks, dependensi dan whitespace lulus.

Wrapper verifikasi juga membandingkan hash database utama dan `.env`; hasil gabungannya **False**, sehingga wrapper keluar dengan kode 1 meskipun runner aplikasi lulus. Server utama port 8000 sudah berjalan sebelum pengujian dan tetap aktif; pembacaan diagnostik menunjukkan aktivitas sesi admin utamanya terus diperbarui. Karena ada penulisan bersamaan dari server aktif, hash tidak dipakai sebagai bukti invariansi database utama. Tes API dan PostgreSQL tetap dijalankan pada lokasi sementara. Server pengujian browser sudah dihentikan; server utama tidak dihentikan atau direstart oleh pekerjaan ini.

## Perbaikan lanjutan: EXTRACT

Laporan query pendapatan pada screenshot pengguna ditolak sebelum eksekusi karena parser menerjemahkan `EXTRACT(YEAR FROM ...)` menjadi `pg_catalog.extract`, sedangkan daftar fungsi aman sebelumnya hanya mencakup `date_part`. `extract` sekarang diizinkan pada kebijakan bersama; fungsi di schema lain dan fungsi berbahaya tetap ditolak. Regresi kebijakan SQL lulus 10 tes. Integrasi PostgreSQL lulus 4 tes, termasuk eksekusi laporan dengan JOIN payment/rental/inventory/film/film_category/category, EXTRACT, DATE_PART dan agregasi sesuai pola screenshot. Pengujian ini membuktikan query dapat dieksekusi, bukan bahwa jawabannya pasti cocok dengan kunci soal pengguna. Server perlu direstart untuk memuat kebijakan baru.
