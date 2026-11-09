# Antrean persisten dan review penilaian

Fase 7, 8 November 2026. Antrean dijalankan oleh worker aplikasi, dengan kontrol admin
melalui API dan `scripts/review_grading.py`. Tidak ada formulir dashboard baru dalam
fase ini. Monitor nilai yang sudah ada tetap membaca tabel jawaban terbaik.

## Kapan retry otomatis berjalan

Jawaban diterima melalui pemeriksaan sesi, paket, cutoff, dan revisi fase 2/4.
Jika evaluator mengembalikan `evaluation_limit` atau `evaluation_error`, penyimpanan
percobaan dan pekerjaan antrean dilakukan dalam transaksi SQLite yang sama.
Tidak ada pekerjaan jika submit ditolak sesudah cutoff.

Retry otomatis memerlukan acuan otomatis yang bisa direplay. Master SELECT memenuhi
syarat jika SQL tidak bergantung waktu/identitas sesi. Sandbox harus memiliki
`setup_query` eksplisit. CURRENT_DATE/SQLValueFunction, now/transaction_timestamp,
age dengan tanggal implisit, dan skrip yang tidak dapat diperiksa sebagai SQL biasa
tidak direplay otomatis. Termasuk skrip database virtual yang parser replay tidak
dapat memverifikasi. Teks literal yang kebetulan berisi nama fungsi bukan fungsi SQL.

Sandbox tanpa setup masuk review, karena snapshot workspace saat submit tidak disimpan
secara persisten. Worker tidak menganggap workspace mahasiswa yang berubah kemudian
sebagai baseline aslinya. Acuan bermasalah, mode manual, dan pending lama hasil migrasi
juga masuk review, bukan langsung diberi nol.

Worker antrean ujian mulai sesudah inisialisasi PostgreSQL berhasil, satu thread per proses aplikasi.
Worker simulasi admin memakai thread terpisah; keduanya berbagi batas slot evaluator.
Ia memeriksa antrean sekitar setiap 0,5 detik. Evaluator tetap memakai batas empat slot
per proses; worker tidak membuat eksekutor tanpa batas. Pending sementara dicoba
maksimal tiga kali, dengan backoff 2 dan 4 detik sebelum retry berikutnya. Sesudah itu
status menjadi review. Kesalahan evaluator tetap NULL, bukan nilai nol.

## Lease, restart, dan cutoff

Pengambilan pekerjaan memakai transaksi `BEGIN IMMEDIATE`, token lease acak, dan lease
90 detik. Dua worker tidak dapat mengambil lease aktif yang sama. Jika proses mati,
worker lain dapat mengambil pekerjaan setelah lease kedaluwarsa. Evaluasi dapat
diulang setelah crash; token mencegah hasil worker lama dikomit setelah lease diganti.
Ini bukan jaminan tepat satu eksekusi SQL, melainkan commit yang difencing.

Worker dihentikan dan dijoin sebelum pool PostgreSQL ditutup. Jika belum berhenti
dalam batas shutdown, pool tidak ditutup di bawah koneksi yang masih dipakai.

Jawaban yang sudah diterima saat aktif boleh diselesaikan setelah stop normal, tanpa
submit ulang. Submit baru dan API soal mahasiswa tetap ditolak sesudah stop; pengawas
dapat melihat hasil melalui API/admin/export. Selama ujian aktif, mahasiswa memuat
ulang soal untuk melihat hasil terbaru; tidak ada push/polling nilai baru pada UI.

Pekerjaan menjadi stale jika revisi soal, siklus ujian, revisi dataset, atau konteks
paket peserta berubah. Reset lalu memilih ulang paket yang sama juga tidak menghidupkan
pekerjaan lama. Penghapusan peserta/soal menghapus pekerjaan terkait lewat FK; hasil
worker yang masih berjalan tidak dapat menciptakan kembali baris tersebut.

## Riwayat dan pemilihan nilai terbaik

`submission_attempts` menyimpan hasil submit asli. Penilaian ulang ditulis ke
`grading_decisions`: percobaan/revisi soal, hasil, nilai/NULL, feedback, sumber,
ID sesi admin jika relevan, dan waktu. API tidak menyediakan update/delete keputusan.
Reset peserta/kelas yang menghapus data tetap dapat menghapus histori terkait lewat FK.

`latest_attempt` tetap menunjuk percobaan terbaru; hasil efektifnya memakai keputusan graded terbaru pada revisi sekarang, dan
menyertakan `initial_result` untuk membedakannya dari hasil asli. Keputusan pending
baru tidak menghapus keputusan graded sebelumnya. `decision_id` adalah versi yang
harus dibaca sebelum admin membuat keputusan baru.

Skor terbaik dihitung ulang dari percobaan dan keputusan graded yang sah pada revisi
soal sekarang. Nilai tertinggi menang; nilai sama memprioritaskan benar lalu percobaan
terbaru. Koreksi manual boleh menurunkan nilai suatu percobaan: nilai tinggi yang
dinyatakan salah tidak terus dipertahankan sebagai best. Jika percobaan lain masih
memiliki nilai tinggi yang sah, percobaan itulah yang menjadi best.

Regrade dengan acuan revisi baru harus diminta admin secara eksplisit. Keputusan
lama tidak dipindahkan diam-diam ke revisi baru. Penilaian manual menerima nilai
bulat 0..bobot soal dan alasan 1..2.000 karakter; nilai parsial dimungkinkan. Label
benar diberikan jika nilainya sama dengan bobot. Alasan ditampilkan sebagai feedback.

## Workflow pengawas dari CLI

Server harus berjalan. Master key diminta melalui input tersembunyi, tidak lewat argumen.
Setiap pemanggilan membuat sesi admin sendiri dan logout sesi itu saja. Admin lain
dengan master key sama tetap login. Untuk server lain, berikan `--url`; HTTPS memakai
verifikasi sertifikat bawaan dan tidak ada opsi menonaktifkannya.

```powershell
.\.venv\Scripts\python.exe scripts/review_grading.py list --status review
.\.venv\Scripts\python.exe scripts/review_grading.py show 123
```

Periksa ID percobaan, soal, revisi sekarang, hasil asli, dan `decision_id`. Kemudian:

```powershell
.\.venv\Scripts\python.exe scripts/review_grading.py manual 123 --revision 2 --decision-id 0 --score 6 --reason "JOIN benar; filter belum lengkap."
.\.venv\Scripts\python.exe scripts/review_grading.py regrade 124 --revision 2 --decision-id 0
```

Angka pada contoh harus diganti dengan data yang baru dibaca. Jika dua admin memakai
versi keputusan yang sama, hanya satu dapat menyimpan. Yang lain mendapat HTTP 409
dan harus membaca ulang, bukan mengulang otomatis dengan versi baru. Keputusan manual
juga membatalkan pekerjaan queued/running untuk percobaan itu; hasil worker lama
tidak dapat menimpanya. Regrade yang sudah queued/running ditolak agar tidak digandakan.

Riwayat percobaan graded yang belum punya job dapat ditemukan melalui endpoint fase 5
`GET /api/admin/students/{nim}/attempts`. Gunakan ID tersebut dengan perintah show/regrade.
Untuk pending sandbox tanpa setup, pilih penilaian manual berdasarkan bukti/instruksi;
jangan menambahkan setup yang berbeda tanpa meninjau revisi dan dampaknya.

## API dan status

| Endpoint | Fungsi |
|---|---|
| `GET /api/admin/grading/jobs` | Hitungan status, metadata worker/maintenance, daftar 100 job |
| `GET /api/admin/grading/attempts/{id}` | Hasil efektif, hasil asli, soal/revisi, 100 keputusan terbaru |
| `POST /api/admin/grading/attempts/{id}/manual` | Nilai manual dengan alasan dan kontrol versi |
| `POST /api/admin/grading/attempts/{id}/regrade` | Meminta replay dengan revisi soal yang dipilih admin |

Daftar job mendukung `status` dan `before_id`, dengan `next_before_id` untuk halaman
berikutnya. Status: queued, running, completed, review, stale, cancelled. Semua endpoint
memerlukan sesi admin; POST juga memerlukan CSRF fase 5. Token lease/run tidak dikirim
oleh API review. Penilaian menyimpan ID sesi admin; audit request fase 5 tetap berjalan.

Body regrade: `question_revision` dan `expected_decision_id`. Body manual menambahkan
`score` dan `reason`. Semua angka harus integer; nilai di luar bobot ditolak. HTTP 409
menandakan konflik revisi/konteks atau pekerjaan sudah berjalan. Pihak mahasiswa tidak
dapat membuat keputusan penilaian melalui endpoint ini.

## Penggantian dataset dan pemulihan insiden

Reset, empty, dan upload dataset melalui jalur aplikasi ditolak saat ujian aktif.
Selama pemeliharaan, fence persisten memblokir claim/regrade/keputusan baru serta mulai
ujian. Revisi dataset dinaikkan dan pekerjaan lama ditandai stale sebelum PostgreSQL
diubah. Kegagalan reset tetap membatalkan replay konteks lama. Ini tidak melacak writer
PostgreSQL eksternal yang melewati aplikasi; jalankan perubahan eksternal secara offline
dan tinjau penilaian terkait.

Jika startup harus membangun ulang master yang kosong, ujian aktif dikembalikan waiting
dan pekerjaan lama difencing. Restart dengan master yang masih utuh tidak membatalkan
antrean. Periksa hasil reseed dan acuan sebelum membuka akses kembali.

Jika proses mati saat maintenance, fence tidak dibuka otomatis. Hentikan semua proses
aplikasi/writer, pastikan operasi PostgreSQL sudah berhenti, periksa data dan cadangan,
lalu gunakan revisi dataset yang terlihat pada API job:

```powershell
.\.venv\Scripts\python.exe scripts/recover_grading_maintenance.py --server-stopped --expected-dataset-revision 7
```

Perintah menolak revisi berbeda atau status ujian aktif, membatalkan pekerjaan lama,
dan mencatat pemulihan. `--server-stopped` adalah pernyataan operator, bukan deteksi
semua writer. Jangan menggunakannya untuk membuka fence reset yang masih berjalan.

## Upgrade dan backup

SQLite versi 5 menambah `grading_jobs`, `grading_decisions`, serta `users.grading_revision`.
Migrasi atomik dan idempoten; pending lama masuk review karena tidak ada konteks replay
yang dapat dibuktikan. Backup fase 6 mendukung skema 4 dan 5. Restore skema 5 menjaga
keputusan, tetapi menandai job queued/running stale dan mencabut sesi. Pengawas meminta
regrade baru secara eksplisit setelah pemeriksaan pemulihan.

Backup tetap offline lintas store; tidak ada PITR/enkripsi bundle/purge otomatis baru.
Antrean bukan jaminan semua jenis SQL aman direplay, kapasitas kelas produksi, atau
penilaian manual yang benar tanpa pemeriksaan manusia. Master key bersama membedakan
sesi pengawas, bukan identitas personal. Formulir review dashboard dan pembaruan nilai
langsung pada halaman mahasiswa belum ditambahkan.
