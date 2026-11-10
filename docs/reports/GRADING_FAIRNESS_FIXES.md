# Perbaikan hasil audit penilaian — 8 November 2026

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Menindaklanjuti `GRADING_FAIRNESS_AUDIT.md`. Implementasi tidak mengubah soal, kebijakan
atau nilai pada database ujian utama. Perubahan kode berlaku setelah restart server.

## Perbaikan otomatis

- ORDER BY sekarang memetakan ordinal kolom, nama qualified pada proyeksi yang aman,
  serta ekspresi yang sama dengan ekspresi kolom output. Normalisasi qualifier hanya
  dilakukan ketika sumber relasi tunggal tidak ambigu. Kunci pada JOIN tidak ditebak.
- Kelompok seri dapat dicocokkan sebagai multiset dengan toleransi angka yang dikonfigurasi,
  tanpa mengabaikan multiplicity atau urutan antarkelompok. Matching permutasi dibatasi
  1.000 baris; pasangan yang semuanya cocok sesuai posisi tidak membutuhkan matching ini.
  Pelampauan batas menghasilkan penilaian tertunda, bukan nilai nol.
- Codec lokal cursor evaluator mempertahankan JSON null versus SQL NULL, pecahan JSON
  sebagai Decimal, serta bounds array. Array JSON juga mempertahankan pembedaan null.
  Nilai preview diubah ke teks setelah pembandingan, bukan sebelumnya.
- Snapshot workspace menyalin nilai sebagai teks PostgreSQL dengan cast eksplisit ke
  tipe tujuan. Ini mencegah JSON/array kehilangan informasi ketika disalin dari sandbox.
- Signature index memisahkan kolom key dan INCLUDE serta merekam null-distinctness.
  Pembacaan atribut null-distinctness memakai metadata JSON katalog untuk kompatibilitas
  versi PostgreSQL yang belum memiliki kolom tersebut.

## Kasus yang diarahkan ke review

- Hasil sama sebagai multiset tetapi berbeda urutan, sementara ekspresi kunci urutan
  belum dapat dipetakan dari output.
- Hasil berbeda pada query acuan dengan LIMIT/OFFSET. Evaluator belum membuktikan
  alternatif pada batas seri, sehingga tidak otomatis menganggapnya salah atau benar.
- Struktur hanya berbeda pada ekspresi CHECK dengan jumlah CHECK yang sama. Baik CHECK
  ekuivalen maupun CHECK berbeda arti membutuhkan keputusan pengawas; constraint hilang
  atau perbedaan struktur lainnya tetap diperiksa sebagai jawaban salah.
- Jawaban tanpa sumber data yang hasilnya cocok dengan acuan bersumber data, misalnya
  SELECT 2 untuk COUNT dua baris. Ini deteksi konservatif, bukan pembuktian lengkap bahwa
  semua bentuk hardcoding telah ditemukan. Jawaban konstanta yang memang berbeda hasil
  tetap dapat ditolak melalui pembandingan normal.

Status tersebut adalah `manual_review`, graded=false, score=NULL dan is_correct=NULL.
Jawaban tersimpan, masuk antrean review, dan tidak otomatis menggantikan skor terbaik
dengan nol. Tinjau melalui fasilitas keputusan pengawas pada `GRADING_QUEUE.md` atau
`scripts/review_grading.py`; jangan mengartikan pending sebagai benar.

## Kebijakan yang tetap eksplisit

Toleransi angka dan pencocokan alias tetap mengikuti kebijakan per soal. Hasil floating
point yang berbeda pada toleransi nol tetap dianggap berbeda; soal yang menerima galat
pembulatan harus menetapkan toleransi. Instruksi harus menyebut alias jika nama kolom
wajib persis. Nilai dan kebijakan 20 soal aktif tidak diubah otomatis.

Beberapa fixture tersembunyi per soal **belum ditambahkan**. Perubahan ini tidak dapat
menjamin ekuivalensi logika seluruh SQL dari satu dataset. Fixture perlu ditentukan
berdasarkan aturan soal, termasuk NULL, duplikat, batas tanggal dan kelompok seri.

## Validasi

- Regresi lengkap: **30/30 pemeriksaan**, termasuk 310 tes Python dan 16 tes JavaScript.
- Suite khusus `test_grading_fairness.py`: **11 tes lulus**, menggunakan PostgreSQL sementara.
- Tes tambahan setelah putaran penuh: **12 tes pembandingan hasil** dan **44 tes akses/submit**
  lulus. Termasuk toleransi pada hasil panjang dan pembuktian bahwa review tidak disimpan nol.
- Kasus ordinal/qualified, toleransi seri, JSON null/presisi, bounds array dan atribut
  unique index yang gagal pada audit telah diuji. Kasus yang belum dapat dibuktikan
  secara otomatis diuji menghasilkan review tanpa skor.
- Regresi juga memeriksa bahwa jawaban berbeda, duplikat yang salah, urutan antarkelompok
  yang salah dan constraint yang hilang tetap ditolak.

Percobaan dan keputusan lama tidak dimodifikasi. Setelah restart, peserta dapat submit
ulang; penilaian ulang percobaan lama dilakukan secara eksplisit oleh pengawas.
