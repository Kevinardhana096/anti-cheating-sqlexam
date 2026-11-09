# Fase 1: baseline, migrasi, dan regresi terisolasi

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal verifikasi: 7 November 2026 (Asia/Makassar).

## Baseline sebelum perubahan

Pada SQLite kosong, `init_system_db()` menghasilkan tabel `submissions` tanpa kolom
`score`, `is_correct`, `eval_status`, dan `feedback`. Instalasi lama dapat menyembunyikan
masalah ini jika kolom tersebut pernah ditambahkan manual.

| Suite pada database kosong | Hasil awal |
|---|---|
| Submission | 29 tes dijalankan, 1 error |
| Rekap dan ZIP | Gagal pada setup, 0 tes dijalankan |
| Retensi skor | 7 tes dijalankan, 6 error |
| Sesi dan mahasiswa terlambat | 7 tes dijalankan, 1 error |

Runner lama juga bergantung pada enam skrip dalam `scratch/` yang tidak dilacak Git.
Health/readiness dipanggil tanpa mempersiapkan database pengujian. Tes lama dapat
mengubah SQLite utama dan schema PostgreSQL yang sedang digunakan aplikasi.

## Implementasi

- `database.py`: definisi kolom penilaian untuk instalasi baru, migrasi versi 1 dan 2
  memakai `PRAGMA user_version`, transaksi migrasi, validasi kolom, penolakan versi
  lebih baru, dan penutupan koneksi saat inisialisasi gagal.
- `scripts/test_system_migrations.py`: tes instalasi baru, upgrade lama dan parsial,
  pelestarian jawaban/nilai, idempotensi, rollback, serta versi tidak kompatibel.
- `scripts/test_support.py`: cluster PostgreSQL sementara, fixture SQLite, konfigurasi
  tes eksplisit, verifikasi identitas cluster, dan pembersihan proses/data sementara.
- Empat suite lama menggunakan fixture tersebut, termasuk jika dijalankan langsung.
- `scripts/test_operations.py`: pengganti pemeriksaan health, recovery, penampil tabel,
  dan konkurensi dari `scratch/`, ditambah guard fixture.
- `scripts/test_known_risks.py`: reproduksi enam temuan terbuka sebagai expected failure.
- `scripts/run_regression_tests.py`: perintah subprocess tanpa shell, direktori kerja
  eksplisit, timeout, hasil setiap suite, serta opsi `--sqlite-only`.

Audit sumber lama di `scratch/` yang bergantung pada potongan kode dan asumsi database
pengembang tidak dipindahkan sebagai klaim keamanan. Pengganti operasional memeriksa
perilaku aplikasi. Temuan keamanan yang belum diperbaiki tetap dinyatakan terbuka.

## Lingkungan verifikasi

| Komponen | Versi |
|---|---|
| OS | Windows |
| Python | 3.14.6 |
| PostgreSQL | 18.6 |
| Node.js | 22.23.2 |
| FastAPI / Uvicorn | 0.162.0 / 0.54.0 |
| psycopg2-binary | 2.9.13 |
| Jinja2 / python-multipart | 3.1.6 / 0.0.33 |
| Pydantic / Pillow / httpx | 2.14.2 / 13.0.0 / 0.28.1 |

`pip check` lulus. Versi dependensi terpasang sesuai `requirements.txt`.
Pengujian macOS/Linux dan versi Python/PostgreSQL lain belum dilakukan.

## Bukti verifikasi

Regresi lengkap dijalankan pada salinan sumber dari file repositori beserta perubahan
fase ini, tanpa `.env`, `scratch/`, file SQLite lama, maupun virtual environment dalam
salinan tersebut. Interpreter/dependensi berasal dari virtual environment yang sudah
terpasang; ini bukan pengujian unduhan dependensi dari internet.

Hasil regresi salinan bersih: 12/12 pemeriksaan runner lulus, dengan 64 tes biasa lulus
dan 6 expected failure. Suite operasional terakhir lulus 7/7, termasuk dua guard fixture
dan pemulihan sesi/nilai melalui interpreter Python baru. Total cakupan akhir adalah
66 tes biasa lulus dan 6 expected failure; dua tes guard ditambahkan setelah regresi
salinan bersih. Pengujian langsung juga berhasil membersihkan fixture tanpa error.

Hash SHA-256 file SQLite utama (`*.db`) dan `.env` sama sebelum dan sesudah regresi
salinan bersih. Cluster tes memakai direktori dan port sendiri, kemudian dihentikan.
Tidak ada migrasi yang dijalankan pada database utama dalam pelaksanaan fase ini.
Migrasi database aplikasi akan berjalan saat startup berikutnya.

Pemeriksaan sintaks Python, kedua file JavaScript, dependensi, dan `git diff --check`
juga lulus. Starlette menampilkan peringatan deprecation penggunaan httpx pada
TestClient; pengujian tetap berhasil, dependensi belum diubah dalam fase ini.

## Temuan yang tetap terbuka

Enam expected failure merekam: penguncian query ketika ujian menunggu, pengambilalihan
sesi pada IP bersama, benturan schema NIM, perbandingan hasil di atas 500 baris,
normalisasi kode teks, dan log tanpa sesi valid. Temuan lainnya dari audit awal,
termasuk privilege sandbox bersama, keamanan admin/CSRF, dan handler dashboard,
tetap merupakan pekerjaan fase berikutnya. Regresi yang lulus tidak menghapus temuan ini.

Tes konkurensi menggunakan 36 query dengan 12 worker. Hasilnya hanya pemeriksaan
regresi ringan, bukan dasar klaim kapasitas ujian.

Panduan perintah dan migrasi: [TESTING.md](../operations/TESTING.md).

## Penutupan fase

Kriteria fase 1 terpenuhi: instalasi kosong mendukung penyimpanan/rekap/ekspor,
upgrade mempertahankan data lama, migrasi ulang aman, kegagalan migrasi terlihat dan
di-rollback, serta regresi tidak membutuhkan database utama atau file `scratch/`.
Perbaikan aturan ujian, privilege sandbox, dan ketepatan grader tetap mengikuti fase
2 dan seterusnya. Sebelum startup aplikasi berikutnya, siapkan backup database utama
sesuai panduan migrasi.
