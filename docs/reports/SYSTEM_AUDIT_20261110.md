# Audit aplikasi — 10 November 2026

Audit kode dan regresi pada working tree saat ini; perubahan pengguna yang sudah ada dipertahankan. Bukan sertifikasi keamanan atau audit visual seluruh browser. Tidak mengubah implementasi.

## Temuan

1. **P1 — Arsip CSV/ZIP melewatkan jawaban pending pertama.** `database.py:1922` menyimpan setiap jawaban di submission_attempts, tetapi submissions hanya diisi jika graded. Ekspor CSV (`database.py:2128`) dan ZIP (`database.py:2174`) membaca submissions. Jawaban pending tanpa nilai sebelumnya tidak masuk CSV dan tidak tersedia sebagai SQL jawaban pada ZIP. Pisahkan ekspor nilai terbaik dari arsip seluruh percobaan; sertakan status pending dan query terakhir.
2. **P1 — Password admin bawaan masih dapat digunakan.** `admin_security.py:35` membuat admin123 jika bootstrap kosong. `main.py:46` hanya memperingatkan. Berlaku pada instalasi baru tanpa kunci eksplisit; bukan klaim bahwa instalasi aktif memakai password itu. Wajibkan secret awal atau perubahan password sebelum ujian.
3. **P1 — Login awal tidak membuktikan identitas mahasiswa.** `main.py:380` dan `database.py:648` menerima NIM/nama dan identitas perangkat dari klien. Kunci sesi melindungi sesi yang sudah aktif, tetapi orang lain dapat lebih dahulu mendaftarkan identitas peserta. Tambahkan daftar peserta dan kode masuk individual atau persetujuan pengawas. Device ID bukan bukti perangkat fisik.
4. **P2 — Pembatasan upload SQL terlambat.** Middleware pembatas body (`main.py:86`) hanya mencakup gambar. Endpoint SQL (`main.py:1349`) memakai UploadFile, sehingga multipart diproses sebelum autentikasi di dalam handler dan pemeriksaan 25 MB. Permintaan besar dapat memakai penyimpanan sementara sebelum ditolak. Terapkan batas streaming body dan autentikasi sebelum parsing multipart; validasi juga batas di proxy jika digunakan. Temuan inspeksi kode, tidak diuji dengan pengisian disk.
5. **P2 — Hasil antrean tidak tersinkron otomatis ke peserta.** Submit memperbarui state satu kali (`static/js/student.js:1407`), sedangkan heartbeat tidak mengambil status hasil baru. Peserta bisa terus melihat menunggu penilaian setelah worker selesai. Poll status percobaan pending dengan backoff dan hentikan ketika final.
6. **P2 — Upload SQL memblokir event loop.** Handler async (`main.py:1349`) memanggil reset_target_database secara sinkron. Operasi PostgreSQL yang lama dapat menahan respons lain, termasuk ruang tunggu dan admin. Pindahkan operasi blocking ke threadpool. Reset saat ujian aktif sudah ditolak; dampak terutama tahap persiapan.

## Batas operasional

- HTTP LAN tidak mengenkripsi cookie dan kredensial. Offline tidak otomatis berarti jaringan tepercaya. HTTPS lokal dapat digunakan tanpa internet.
- Deteksi blur/visibility berada di browser peserta; tidak membuktikan tidak adanya kecurangan atau penggunaan perangkat lain.
- Draf disimpan di localStorage; draf belum disubmit bukan jawaban yang sudah diterima server.
- Benchmark 30 peserta sebelumnya memakai loopback dan PostgreSQL fsync/synchronous_commit nonaktif. Hasil tidak mengukur Wi-Fi, render 30 browser, atau durabilitas produksi.
- Static assets diberi no-store oleh middleware; pemuatan ulang mengunduh ulang aset. Ukur ukuran transfer dan pertimbangkan cache aset berversi.

## Validasi

Regresi lengkap dijalankan dengan scripts/run_regression_tests.py menggunakan SQLite dan PostgreSQL sementara. Log: scratch/audit-regression-20261110.log. Hasil akhir dilaporkan di chat setelah proses selesai. Tes yang lulus tidak meniadakan temuan inspeksi di atas.
`nHasil akhir: 33/33 pemeriksaan regresi lulus. Seluruh tahap integrasi PostgreSQL selesai.

## Tindak lanjut

Temuan 1, 4, 5, dan 6 telah ditangani: arsip menyertakan seluruh percobaan, unggahan dibatasi sebelum parsing, status antrean diperbarui melalui heartbeat, dan impor memakai threadpool. Temuan 2 dan 3 tidak diimplementasikan atas permintaan pengguna. Regresi perbaikan: 33/33 pemeriksaan lulus; tes khusus tambahan frontend 18/18, akses 46/46, admin 19/19 lulus.
