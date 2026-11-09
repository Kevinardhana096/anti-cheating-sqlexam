# Audit ketepatan penilaian — 8 November 2026

> Catatan historis sebelum/selama perbaikan. Status terbaru: [laporan lanjutan](GRADING_FAIRNESS_FIXES.md) dan [panduan aktif](../README.md). Temuan serta jumlah tes di bawah berlaku pada putaran saat laporan dibuat.

## Kesimpulan

Belum aman untuk menyatakan bahwa semua jawaban benar pasti diterima dan semua
jawaban salah pasti ditolak. Audit menjalankan 34 kasus pada PostgreSQL sementara:
13 hasil berbeda dari ekspektasi probe. Ini **bukan 13 bug terpisah**: 10 perbedaan
mewakili delapan kelompok celah implementasi; tiga lainnya merupakan risiko kebijakan,
keterbatasan satu dataset, dan ambiguitas spesifikasi. Seluruh 16 kasus kontrol sesuai.
Audit adalah pengukuran perilaku saat ini, bukan regresi yang menyatakan semuanya lulus.

Perubahan pada pekerjaan ini hanya script audit dan dokumentasi. Temuan di bawah
belum diperbaiki. Nilai, soal dan database ujian utama tidak diubah. Konfigurasi soal
utama hanya dibaca melalui koneksi SQLite read-only.

## Temuan terkonfirmasi

| Prioritas | Celah | Bukti | Dampak |
| --- | --- | --- | --- |
| P1 | Kunci urutan seri belum dipetakan untuk ordinal, ekspresi atau nama qualified | `ORDER BY 1,3 DESC`, `(bulan+0),total DESC`, `t.bulan,total DESC` menolak variasi urutan sah dalam kelompok seri | Jawaban benar menjadi wrong_order |
| P1 | Toleransi angka tidak diterapkan pada pencocokan multiset untuk urutan seri | Grup berkunci sama dengan baris ditukar dan nilai berbeda 0.001 pada toleransi 0.01 menjadi wrong_data | Jawaban dalam toleransi menjadi salah |
| P1 | NULL JSON dan NULL SQL kehilangan pembedaan | `SELECT 'null'::jsonb AS v` dan `SELECT NULL::jsonb AS v` diterima sama | Jawaban berbeda diterima |
| P1 | Presisi pecahan JSON hilang pada decoding | JSONB bernilai 0.12345678901234567891 dan 0.12345678901234567892 diterima sama | Nilai berbeda diterima sebelum comparator sempat memeriksa |
| P1 | Semantik NULL pada unique index tidak masuk signature | UNIQUE INDEX biasa diterima untuk kunci UNIQUE INDEX NULLS NOT DISTINCT | Struktur yang memperbolehkan beberapa NULL dianggap memenuhi aturan yang melarangnya |
| P1 | Kolom INCLUDE tidak dibedakan dari kolom key index | UNIQUE(a,b) diterima untuk kunci UNIQUE(a) INCLUDE(b) | Jawaban mengizinkan a berulang selama b berbeda, padahal kunci melarangnya |
| P2 | CHECK ekuivalen masih dibandingkan menurut bentuk ekspresi | CHECK(0<id) ditolak untuk CHECK(id>0) | Salah bila soal menguji aturan nilai, bukan bentuk ekspresi tertentu |
| P2 | Metadata batas bawah array hilang pada decoding | ARRAY[1,2] dan '[0:1]={1,2}'::int[] diterima sama | Salah untuk soal yang menguji semantik array PostgreSQL termasuk bounds |

P1 berarti berpotensi memengaruhi keputusan nilai dan perlu didahulukan; bukan
pernyataan bahwa seluruh soal aktif memakai fitur tersebut. Soal array dan JSON
memerlukan perhatian terutama jika materi atau keluaran memang memakai tipe itu.

## Risiko kebijakan dan spesifikasi

1. **Floating point tanpa toleransi.** `0.1::float8 + 0.2::float8` ditolak terhadap
   `0.3::numeric`. Nilai komputer memang berbeda sedikit. Ini perlu kebijakan toleransi
   sesuai materi; melonggarkan seluruh soal secara otomatis bisa menerima kesalahan
   nominal uang yang seharusnya ditolak.
2. **Satu dataset tidak membuktikan algoritma query.** `SELECT 2::bigint` diterima
   terhadap COUNT dua baris. Untuk penilaian berbasis output ini konsisten, tetapi
   mahasiswa dapat menulis konstanta atau filter salah yang kebetulan cocok. Perlu
   beberapa fixture tersembunyi dan variasi data, bukan pemeriksaan teks query semata.
3. **LIMIT pada batas seri.** Dua baris berbeda dengan nilai tertinggi sama dapat
   menjadi jawaban sah untuk satu baris teratas jika tie-breaker tidak ditentukan.
   Pembandingan satu hasil referensi menolak alternatif tersebut. Perjelas instruksi
   atau sediakan penanganan semantik khusus; jangan menganggap semua perbedaan LIMIT
   sebagai salah.
4. **Alias wajib persis.** Konfigurasi 20 soal aktif seluruhnya memakai default exact.
   Ini benar jika nama kolom merupakan bagian spesifikasi, tetapi berisiko tidak adil
   bila instruksi hanya menyebut isi laporan. Jangan mengabaikan alias global tanpa
   keputusan pengawas per soal.

Pembacaan konfigurasi menemukan 20 soal aktif: 16 mempunyai ORDER BY pada kunci,
satu mempunyai LIMIT tingkat teratas, dan enam menargetkan sandbox. Angka tersebut
menentukan prioritas review, bukan bukti bahwa setiap soal itu bermasalah. Audit ini
belum menilai kecocokan seluruh gambar expected output dengan seluruh kunci soal.

## Kasus kontrol yang sesuai

Pertukaran seri pada alias sederhana; salah urutan antarkelompok; perbedaan setelah
baris preview ke-500; jumlah duplikat; integer/numeric ekuivalen; teks berawalan nol;
boolean versus angka; NULL versus nol; hilangnya duplikat akibat UNION; CASE versus
COALESCE; CTE versus derived table; COUNT pada nilai NULL; waktu dengan timezone yang
mewakili saat sama; NULLS FIRST/LAST; primary key bernama versus anonim; dan constraint
tambahan yang mengubah struktur. Dua kontrol COUNT memisahkan formulasi ekuivalen
dari COUNT(*) yang memang salah ketika ada NULL.

## Arah perbaikan

1. Lengkapi pemetaan AST ORDER BY. Jika urutan tidak dapat dibuktikan dan multiset
   sama, kirim ke review alih-alih otomatis menganggap salah atau mengabaikan urutan.
2. Lakukan matching bertoleransi di dalam kelompok seri dengan batas sumber daya.
   Multiplicity dan urutan antarkelompok harus tetap diperiksa.
3. Pertahankan tipe dan nilai JSON sejak decoding: gunakan parsing angka presisi
   Decimal serta pembeda JSON null dari SQL NULL. Menambah toleransi setelah decoding
   tidak dapat mengembalikan presisi yang sudah hilang.
4. Tambahkan atribut null-distinctness dan pemisahan key/include ke signature index,
   dengan kompatibilitas versi PostgreSQL yang didukung.
5. Untuk CHECK ekuivalen, gunakan fixture constraint atau review ketika belum dapat
   membuktikan ekuivalensi; jangan menerima seluruh perbedaan CHECK begitu saja.
6. Tetapkan dukungan metadata array, kebijakan alias/toleransi per soal, dan beberapa
   fixture penilaian sebelum menyatakan cakupan materi itu siap.

## Reproduksi dan batas pengujian

Jalankan `.venv/Scripts/python.exe scripts/audit_grading_edge_cases.py scratch/audit.json`.
Fixture menggunakan PostgreSQL dan SQLite sementara dari test_support; hasil rinci,
query dan keputusan tersedia di `GRADING_EDGE_CASES_RESULTS.json`. Script sengaja
melaporkan mismatch sebagai temuan audit, bukan keluar gagal ketika menemukan bug.

Audit ini tidak menjalankan atau mengubah submission mahasiswa nyata. Ini belum
merupakan pembuktian matematis ekuivalensi seluruh SQL, pengujian seluruh dataset
alternatif, atau pengujian beban server. Regresi lengkap tidak diulang karena belum
ada perubahan kode penilaian pada pekerjaan analisis ini.
