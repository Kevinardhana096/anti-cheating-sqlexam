# Penilaian hasil lengkap dan riwayat jawaban

Perbaikan audit 8 November 2026 dijelaskan di [catatan perbaikan](../reports/GRADING_FAIRNESS_FIXES.md).
ORDER BY mendukung permutasi dalam kelompok seri untuk kunci output yang dapat dipetakan.
Kasus urutan/LIMIT/CHECK yang belum dapat dipastikan dapat masuk review dengan skor NULL.
Codec evaluator mempertahankan presisi JSON, pembedaan JSON null dan SQL NULL, serta bounds
array; signature index membedakan key/INCLUDE dan NULLS NOT DISTINCT.

Fase 4, 7 November 2026. Panduan ini menjelaskan evaluator pada `grading_engine.py`,
`grading_results.py`, dan `grading_workspace.py`.

## Preview dan penilaian

Run Query tetap menjalankan skrip di workspace aktif. Submit menilai skrip dalam
workspace evaluator terpisah dan tidak menerapkan perubahan ke workspace aktif.
DDL/DML yang sudah dinilai benar dapat dipakai sebagai prasyarat soal berikutnya
dalam paket yang sama, berdasarkan nomor soal dan revisi jawaban terbaik.
Mahasiswa juga dapat menjalankan DDL/DML melalui Run Query untuk eksperimen langsung.

Preview dibatasi 500 baris, 4.000 karakter per sel, dan 256 KiB data baris JSON.
Pemotongan ini tidak memengaruhi perbandingan. `row_count` pada respons penilaian
menyatakan jumlah hasil lengkap; `preview_row_count` menyatakan jumlah yang ditampilkan.

Evaluator membaca hasil melalui server-side cursor. Perbandingan persis tanpa urutan
memakai multiset dalam berkas SQLite sementara, sehingga jumlah kemunculan duplikat
tetap diperiksa. Nilai PostgreSQL dibandingkan sebelum diubah menjadi JSON preview.
Teks dibandingkan persis, termasuk kapitalisasi, spasi, dan nol di depan. NULL,
boolean, angka, teks, tanggal, array, JSON, dan data biner dibedakan. Angka native
dibandingkan menurut nilainya tanpa pembulatan tampilan.

## Kebijakan per soal

Field opsional pada `POST /api/admin/questions`:

```json
{
  "grading_policy": {
    "mode": "automatic",
    "row_order": "auto",
    "column_order": true,
    "column_names": "exact",
    "numeric_absolute_tolerance": "0",
    "numeric_relative_tolerance": "0"
  },
  "setup_query": ""
}
```

Field ini tersedia melalui API admin; formulir admin lama mempertahankan nilai yang
sudah tersimpan ketika tidak mengirim kedua field tersebut.

| Field | Arti |
|---|---|
| `mode` | `automatic` atau `manual`; manual menghasilkan status menunggu pengawas |
| `row_order` | `auto` mengikuti ORDER BY pada SELECT terluar; `required` selalu memeriksa urutan; `ignore` mengabaikannya |
| `column_order` | Default `true`; jika `false`, kolom dipasangkan berdasarkan nama unik |
| `column_names` | `exact`, `case_insensitive`, atau `ignore`; nama diabaikan hanya ketika urutan kolom tetap diperiksa |
| Toleransi | Default nol; hanya berlaku pada nilai angka native, bukan teks angka |
| `setup_query` | Skrip prasyarat sandbox yang dijalankan identik sebelum kedua jawaban |

Selisih angka diterima jika tidak melebihi maksimum toleransi absolut dan toleransi
relatif dikalikan maksimum nilai absolut kedua angka. Pencocokan tanpa urutan dengan
toleransi memakai pencocokan satu lawan satu, bukan pembulatan atau greedy matching.
Gunakan ORDER BY dengan pemutus seri yang stabil jika urutan memang dinilai.

Satu soal SELECT memerlukan satu SELECT acuan. Soal perubahan state dapat berisi
beberapa DDL/DML atau perintah database virtual. Pisahkan acuan yang mencampur SELECT
dan perubahan state menjadi soal terpisah. Seluruh SQL tetap mengikuti policy fase 3.

## DDL/DML dan prasyarat

Evaluator membuat dua schema beserta LOGIN terbatas sementara. Acuan dijalankan di
satu workspace dan jawaban di workspace lainnya. Semua perubahan dibatalkan dan
schema/role dibersihkan sesudah evaluasi.

Baseline dipilih dari `setup_query`, lalu jawaban terbaik prasyarat yang masih cocok
revisinya, atau snapshot workspace aktif jika keduanya tidak tersedia. Validasi acuan
sebelum ujian menggunakan acuan soal sebelumnya sebagai prasyarat, bukan data mahasiswa.
Saat snapshot diperlukan, admin hanya membaca katalog dan data. Default, constraint,
dan SQL rekonstruksi dijalankan sebagai role evaluator terbatas setelah validasi AST.

Untuk soal CREATE TABLE, tabel sasaran dibuat ulang hanya dalam kedua workspace
evaluator. Untuk soal INSERT, tabel sasaran yang sudah ada dikosongkan dalam kedua
workspace evaluator dengan `TRUNCATE ... RESTART IDENTITY CASCADE`. Tabel yang sekaligus
dibuat dalam skrip tidak ditruncate terlebih dahulu. Karena itu soal INSERT dinilai
sebagai pengisian ulang sasaran; gunakan setup eksplisit untuk membuat fixture yang
diperlukan. UPDATE dan DELETE bekerja pada baseline tanpa pengosongan awal.

Perbandingan struktur mencakup tabel/kolom, urutan kolom, tipe dan panjang/presisi,
NULL, default, identity/generated, konfigurasi sequence milik kolom, PK, UNIQUE,
CHECK, FK lengkap, dan index biasa. Nama constraint/index bukan kriteria. Data seluruh
tabel dibandingkan setelah struktur cocok. Sebuah SELECT tidak bisa menggantikan
perintah UPDATE/DELETE yang diminta, termasuk ketika perubahan acuannya tidak mengubah data.

## Validasi dan status tertunda

Tombol **Validasi Kesiapan Ujian** memvalidasi seluruh acuan dalam paket aktif sebelum
waktu mulai ujian, tanpa membuka akses mahasiswa. Acuan kosong pada mode
otomatis, acuan yang tidak dapat dieksekusi, prasyarat tidak lengkap, atau hasil yang
melewati batas menghalangi ujian dimulai. Mode manual harus dipilih eksplisit.
Hasil kesiapan disimpan di SQLite beserta sidik konfigurasi dan waktu validasi.
Tombol **Mulai Ujian** hanya memeriksa bahwa hasil tersebut masih berlaku dalam
transaksi sebelum status menjadi aktif; SQL acuan tidak dijalankan ulang.
Perubahan soal, paket aktif, dataset, atau anggaran evaluasi membatalkan kesiapan.
Penyimpanan perubahan soal ditolak selama ujian aktif.

`reference_error`, `evaluation_error`, `evaluation_limit`, dan `manual_review`
menghasilkan `graded=false`. Nilai dan kebenaran percobaan tersebut adalah NULL.
Jawaban tetap disimpan; skor terbaik yang sudah ada dipertahankan. Kesalahan SQL
mahasiswa yang benar-benar teridentifikasi tetap dinilai nol. Acuan yang kosong tidak
pernah memberi poin otomatis.

| Batas evaluator | Nilai |
|---|---|
| Anggaran evaluasi SQL/perbandingan | 60 detik, diatur melalui `EXAM_GRADE_SECONDS` |
| Slot evaluasi per proses | 4 |
| Baris hasil lengkap | 100.000 per sisi per perbandingan |
| Ukuran hasil lengkap | 32 MiB per sisi dalam encoding pembanding |
| Kolom hasil | 64 |
| Matching permutasi dengan toleransi, termasuk kelompok seri | 1.000 |
| Tabel snapshot | 64 |
| Baris terpengaruh per statement mutasi | 10.000 |

`EXAM_GRADE_SECONDS` berlaku untuk validasi acuan sebelum ujian dan penilaian
jawaban mahasiswa, termasuk simulasi admin. Nilainya harus lebih dari 0 dan maksimal
60 detik agar tetap berada di bawah lease pekerjaan penilaian 90 detik.
Untuk memakai 60 detik di PowerShell, jalankan `$env:EXAM_GRADE_SECONDS="60"`
sebelum `./run.bat`. Di macOS/Linux, jalankan `EXAM_GRADE_SECONDS=60 bash run.sh`.
Restart server setelah mengubah nilai. Aplikasi tidak memuat `.env` otomatis.
Anggaran ini berlaku untuk satu evaluasi, bukan per statement SQL. Batas Run Query
di IDE diatur terpisah; menaikkan anggaran penilaian tidak mengubah batas tersebut.

Batas terlampaui menghasilkan penilaian tertunda, bukan perbandingan fallback pada
preview. Provisioning, koneksi, dan cleanup dapat menambah durasi respons. Batas ini
bukan hard quota seluruh memori/disk server. Uji kapasitas serentak tetap diperlukan.

## Riwayat dan revisi

SQLite versi 3 menambah `submission_attempts` untuk setiap percobaan yang diterima.
Tabel `submissions` menyimpan jawaban terbaik. Respons submit memisahkan
`latest_attempt`, `best_submission`, `new_score`, dan skor efektif `score`.
`GET /api/admin/students/{nim}/attempts` menampilkan riwayat 100 percobaan terbaru;
gunakan `before_id` dari `next_before_id` untuk halaman berikutnya. Endpoint wajib
autentikasi admin.

Migrasi mengimpor jawaban terbaik lama satu kali sebagai `source=legacy_best`.
Percobaan sebelum migrasi yang sudah tertimpa tidak dapat direkonstruksi.
Perubahan acuan, setup, kebijakan, bobot, database, paket, atau nomor soal menaikkan
revisi penilaian. Skor lama ditandai `needs_regrade` dan dikeluarkan dari skor berjalan;
nilai historis tetap ada dalam riwayat. Pengiriman yang selesai setelah revisi/sesi
berubah ditolak sebelum menyimpan percobaan.

Fase 7 menyediakan antrean retry persisten serta penilaian manual/regrade melalui
API admin dan CLI terautentikasi. Formulir dashboard khusus belum ditambahkan.
Status tertunda tetap bukan nilai final. Aturan retry, provenance, dan konflik dua
admin dijelaskan dalam [GRADING_QUEUE.md](GRADING_QUEUE.md). Penguatan admin/CSRF/log
sudah tersedia melalui fase 5.

Fase 7 menambah skema SQLite versi 5 (`grading_jobs`, `grading_decisions`, serta revisi
konteks paket peserta). Percobaan asli tidak diubah; respons `latest_attempt` menampilkan
keputusan efektif sekaligus `initial_result` jika sudah dinilai ulang. Penilaian manual
boleh parsial; koreksi manual dapat menurunkan nilai suatu percobaan, dan jawaban terbaik
dihitung ulang dari keputusan sah pada revisi soal sekarang.
