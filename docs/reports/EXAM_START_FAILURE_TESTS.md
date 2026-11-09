# Pengujian awal sesi ujian — 8 November 2026

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Pengujian tambahan memakai SQLite sementara, klien HTTP in-process FastAPI, dua sesi admin independen, dan sinkronisasi thread untuk memaksa urutan benturan. Sambungan PostgreSQL nyata dilarang dalam suite ini. Ini pemeriksaan konsistensi aplikasi, bukan tolok ukur kapasitas jaringan atau ketahanan listrik.

## Sepuluh skenario tambahan

| Skenario | Hasil yang diverifikasi |
| --- | --- |
| Admin kedua menghentikan saat admin pertama memvalidasi Mulai | Hentikan berhasil; Mulai ditolak; status akhir finished |
| Dua admin memvalidasi Mulai bersamaan | Satu berhasil, satu mendapat konflik konfigurasi; satu transisi tambahan tercatat |
| PostgreSQL terputus ketika validasi | Kesalahan OperationalError disuntikkan; Mulai ditolak, status tetap waiting, soal belum dapat diakses |
| Eksekusi terhenti sebelum transaksi aktivasi | Penghentian disimulasikan dengan BaseException; status tetap waiting; percobaan berikutnya dapat berhasil |
| Kegagalan setelah perubahan status sebelum commit | Seluruh transaksi dibatalkan dan status kembali waiting |
| 24 peserta dari IP sama masuk dari waiting | Semua membaca status active, membuka halaman ujian, mengunci paket dan mengambil soal melalui permintaan serentak |
| Respons penguncian paket hilang setelah server menyimpan | Respons pertama dibuang; pengulangan berhasil memulihkan paket yang sama |
| Respons submit hilang setelah server menyimpan | Jawaban ditemukan melalui pembacaan submission; pengulangan mempertahankan satu skor terbaik dan dua riwayat percobaan |
| Cookie sesi sebelumnya digunakan setelah Bersihkan Sesi dan Mulai | Metadata dan submit ditolak 401; evaluator tidak dipanggil |
| Hentikan terjadi antara autentikasi dan transaksi penguncian paket | Penguncian ditolak 403; pilihan paket tetap kosong |

Suite `scripts/test_exam_start_failures.py` lulus **10/10 tes** dan ditambahkan ke runner regresi. Pada pemeriksaan awal, 43 tes akses yang sudah ada juga dijalankan ulang dan lulus. Tidak ditemukan bug aplikasi baru dalam skenario tambahan ini; perubahan berupa pengujian dan dokumentasi.

Pemeriksaan terkait juga lulus: 26 tes keamanan/sesi admin, 7 tes peserta terlambat dan penguncian sesi (menggunakan PostgreSQL sementara), serta 15 tes perilaku JavaScript. `git diff --check` lulus. Regresi lengkap seluruh proyek tidak diulang pada pekerjaan ini karena kode aplikasi tidak berubah; angka regresi lengkap sebelumnya tetap merujuk pengujian sebelum penambahan suite ini.

## Temuan dan batas bukti

Pengiriman ulang submit belum memakai kunci idempotensi: jika permintaan pertama sudah tersimpan namun responsnya hilang, pengiriman ulang menambahkan percobaan baru. Skor terbaik tidak berlipat atau turun. Pemulihan yang diuji pada suite ini adalah pembacaan data server dan pengiriman ulang, bukan pemulihan otomatis browser.

Mulai/Hentikan mengikuti urutan transaksi: Hentikan yang masuk ketika Mulai sedang memvalidasi membatalkan Mulai tersebut. Jika pengawas mengirim Mulai baru setelah Hentikan selesai, itu merupakan perintah membuka kembali dan tetap diizinkan. Saat mengganti kelas, Hentikan saja tidak membersihkan sesi lama; gunakan Bersihkan Sesi untuk mencabut sesi peserta sebelumnya.

Simulasi exception bukan penghentian proses OS, pemadaman listrik, atau PostgreSQL yang benar-benar dimatikan. Respons yang dibuang bukan gangguan TCP/Wi-Fi nyata. Klien in-process tidak menjalankan JavaScript lobby atau fullscreen. Uji perangkat, jaringan Wi-Fi, kehilangan daya dan jumlah peserta sebenarnya tetap memerlukan gladi bersih terpisah. Hasil ini tidak memberikan angka kapasitas produksi.
