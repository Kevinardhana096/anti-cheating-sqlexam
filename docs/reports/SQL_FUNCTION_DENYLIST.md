# Daftar larangan fungsi SQL — 8 November 2026

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Menindaklanjuti penolakan `EXTRACT` dan arahan pengguna, whitelist fungsi dihapus.
Fungsi yang tidak tercantum dalam nama/keluarga fungsi terlarang kini diteruskan ke
PostgreSQL. Fungsi yang belum dikenal aplikasi tidak memerlukan perubahan kode atau
pendaftaran. Admin dan mahasiswa memakai kebijakan yang sama pada Run dan penilaian.

Pembatasan schema fungsi tetap berlaku untuk mencegah eksekusi fungsi custom atau
extension melalui schema lain. Hak akses role, validasi seluruh skrip, master read-only,
isolasi sandbox dan timeout tetap berlaku. Fungsi yang menjalankan SQL dari string
masuk daftar larangan agar isi string tidak melewati pemeriksaan AST.

Fungsi acak/waktu dan fungsi keadaan sesi yang dikenali dipisahkan dari kebijakan
eksekusi: boleh dicoba, tetapi tidak dijadikan acuan deterministik atau diputar ulang
otomatis untuk memberikan nilai pada konteks yang berbeda. Ini bukan whitelist
fungsi eksekusi.

Pengujian mencakup fungsi umum yang sebelumnya tidak terdaftar, nama fungsi tak dikenal,
literal/komentar berisi nama terlarang, pemanggilan terlarang yang qualified/quoted/nested,
fungsi SQL dinamis, serta regresi penilaian ulang. Integrasi PostgreSQL memeriksa
REGEXP_REPLACE, TO_NUMBER, MD5 dan PG_TYPEOF pada master dan sandbox, serta penolakan
query_to_xml. Tes deadline sengaja menonaktifkan larangan pg_sleep hanya di mock tes
agar mekanisme timeout tetap diuji; produksi tetap melarang keluarga pg_sleep.

Kebijakan dapat ditinjau pada `sql_policy.py`; panduan lengkap ada di
`docs/operations/SANDBOX_SECURITY.md`. Server perlu direstart setelah perubahan.

Regresi lengkap lulus **29/29 pemeriksaan**, mencakup **297 tes Python dan 16 tes
JavaScript**. Ini termasuk 13 tes kebijakan SQL, 29 tes keamanan sandbox, pengujian
penilaian dan antrean, serta 4 tes integrasi IDE admin dengan PostgreSQL sementara.
