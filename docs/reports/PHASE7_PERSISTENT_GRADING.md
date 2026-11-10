# Fase 7: antrean persisten, review manual, dan regrade

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 8 November 2026, Asia/Makassar.

## Cakupan dan hasil

Belum ada definisi fase 7 dalam dokumen sebelumnya. Pelaksanaan memprioritaskan
kekurangan yang terukur pada fase 6: jawaban pending saat lonjakan masih memerlukan
submit ulang, serta belum ada jalur penilaian manual/regrade. Fase ini menyediakan
backend, API admin, dan CLI terautentikasi; tidak membuat formulir dashboard baru.

Jawaban pending sementara dan job disimpan atomik. Worker aplikasi memakai antrean
SQLite persisten, lease 90 detik, fencing token, dan maksimal tiga percobaan dengan
backoff. Pekerjaan tetap ada saat proses mati; lease dapat diambil ulang setelah
kedaluwarsa. Worker lama tidak dapat mengomit hasil setelah token diganti.

Jawaban yang sudah diterima dapat selesai setelah stop normal. Submit baru tetap
ditolak dan API soal mahasiswa tetap tertutup setelah stop. Worker berhenti sebelum
pool PostgreSQL ditutup. Job difencing ketika soal, siklus ujian, dataset, atau konteks
paket peserta berubah; penghapusan peserta tidak dapat dibatalkan oleh worker lama.

Retry otomatis dibatasi pada SQL yang dapat direplay. Sandbox memerlukan setup eksplisit;
snapshot workspace saat submit tidak dipersistenkan. SQL waktu/identitas sesi dan skrip
yang tidak dapat diverifikasi parser replay masuk review. Acuan bermasalah, mode
manual, dan pending hasil migrasi juga memerlukan pengawas. Kegagalan evaluator tetap
NULL, bukan otomatis bernilai nol.

Penilaian ulang menghasilkan keputusan baru di `grading_decisions`, tanpa mengubah
percobaan awal. Admin dapat memberi nilai parsial atau meminta regrade pada revisi
yang dibaca. Konflik dua admin mendapat HTTP 409. Keputusan manual membatalkan job
aktif untuk percobaan itu. Koreksi dapat menurunkan nilai suatu percobaan dan menghitung
ulang best dari keputusan sah, sehingga nilai tinggi yang salah tidak dipertahankan.

Reset/empty/upload dataset memakai fence persisten dan ditolak saat ujian aktif.
Mulai ujian juga memeriksa fence dan revisi dataset. Jika startup harus membangun ulang
master yang kosong, ujian dipindahkan ke waiting dan pekerjaan lama dibatalkan sebagai
stale. Restart dengan master utuh tetap dapat melanjutkan antrean.

## Komponen

| File | Peran |
|---|---|
| `grading_queue.py` | Job/lease, retry, fencing, keputusan, perhitungan ulang best, worker |
| `database.py` | Migrasi 5, enqueue atomik, hasil efektif, revisi paket, fence dataset |
| `main.py` | Lifespan worker, API review/manual/regrade, status antrean pada submit |
| `scripts/review_grading.py` | Login admin independen, inspeksi, manual, dan regrade tanpa password di argumen |
| `scripts/recover_grading_maintenance.py` | Pemulihan fence maintenance secara offline dengan pemeriksaan revisi |
| `exam_backup.py` | Dukungan skema 4/5, keputusan dipertahankan, job lama tidak dilanjutkan setelah restore |
| `scripts/run_load_test.py` | Profil `--automatic-drain` tanpa pengiriman ulang |

## Bukti uji beban

Fixture memakai satu Uvicorn, Windows 11, Python 3.14.6, PostgreSQL 18.6, 8 CPU logis,
loopback, dan PostgreSQL fsync/synchronous_commit nonaktif seperti fase 6.

| Tahap | Hasil |
|---|---|
| Login satu IP | 24 berhasil |
| Preview master dan sandbox dingin | Seluruh 24 berhasil pada masing-masing tahap |
| Submit bertahap, paralel 4 | 24 dinilai benar |
| Lonjakan 24 submit | 4 langsung benar, 20 pending-limit |
| Stop lalu tunggu worker, tanpa submit ulang | Seluruh 20 job completed; tambahan tunggu 1,711 detik setelah stop |
| Submit baru sesudah stop | Seluruh 24 ditolak |

Seluruh nilai terbaik dan hasil efektif percobaan terakhir benar. Percobaan pending
asli tetap memiliki nilai/kebenaran NULL; keputusan hasil retry tercatat terpisah.
Sebagian pekerjaan bisa mulai sebelum stop, sehingga 1,711 detik adalah waktu tunggu
tambahan sesudah stop, bukan durasi total seluruh penilaian. Tidak ada error tak terduga.

Pemeriksaan pertama benchmark sempat memakai API soal mahasiswa setelah stop, yang
memang ditolak oleh fase 2. Harness dikoreksi untuk memeriksa hasil dari sisi server
terotorisasi sambil tetap menguji penolakan akses mahasiswa. Hasil pengukuran akhir
lulus; batas cutoff tidak dilonggarkan untuk membuat tes lolos.

Data: [PHASE7_LOAD_RESULTS.json](PHASE7_LOAD_RESULTS.json).
Hasil ini membuktikan alur otomatis pada fixture, bukan kapasitas kelas produksi atau
perbandingan throughput identik dengan fase 6.

## Regresi akhir

Salinan sumber bersih lulus **23/23 pemeriksaan**, exit code 0: **256 tes normal lulus,
tanpa expected failure**. Tidak memakai `.env`, SQLite lama, atau `scratch/` sebagai
dependensi pengujian. Hash SHA-256 database utama `*.db` dan `.env` tetap sama.

| Suite | Hasil |
|---|---|
| Migrasi SQLite | 10 |
| Kendali ujian/sesi, riwayat, revisi | 43 |
| Keamanan admin/CSRF/log | 26 |
| Backup SQLite | 10 |
| Kontrol operasional | 4 |
| Antrean/keputusan manual/migrasi/fencing | 30 |
| Parser SQL | 9 |
| Pembanding bertipe | 9 |
| Submission | 29 |
| Rekap/ZIP | 8 |
| Retensi skor | 7 |
| Sesi/mahasiswa terlambat | 7 |
| Operasional/readiness | 8 |
| Backup PostgreSQL | 4 |
| Privilege/sandbox | 28 |
| Evaluator hasil lengkap | 12 |
| Antrean dengan PostgreSQL nyata | 6 |
| Regresi temuan | 6 |

Sintaks Python/JavaScript, konsistensi dependency, dan whitespace Git lulus. Uji baru
mencakup proses claim yang keluar, pengambilan lease baru, stale worker, cutoff,
perubahan soal/paket/dataset, konflik admin, koreksi best, restore, serta worker startup/
shutdown dan master yang harus direseed. Fixture PostgreSQL/server HTTP dibersihkan.
Pesan cleanup gagal pada suite keamanan berasal dari dependency sengaja untuk tes rollback.

## Upgrade dan batas yang tetap berlaku

SQLite versi 5 menambah job/keputusan dan revisi konteks paket. Pending lama masuk
review secara idempoten. Backup format yang ada mendukung SQLite versi 4 dan 5;
restore 5 membatalkan queued/running lama dan mempertahankan keputusan.

Tidak ada formulir review dashboard atau push nilai mahasiswa baru. Gunakan API/CLI;
selama ujian aktif mahasiswa memuat ulang soal, dan sesudah stop hasil dilihat pengawas.
Penilaian manual tetap memerlukan pemeriksaan manusia. Tidak ada retry otomatis
untuk sandbox yang tidak memiliki baseline replay yang aman. Perubahan PostgreSQL
eksternal di luar aplikasi tidak dilacak sebagai revisi dataset.

Lease menjamin fencing commit, bukan tepat satu eksekusi setelah crash. Rate/slot tetap
per proses, dan backlog dapat memerlukan waktu/review. Tidak ada PITR, enkripsi bundle,
purge otomatis, atau deployment TLS baru. Uji LAN/kelas nyata dan kebijakan retensi
tetap mengikuti runbook fase 6.

Perubahan belum dikomit dan aplikasi utama tidak dijalankan ulang. Panduan lengkap:
[GRADING_QUEUE.md](../operations/GRADING_QUEUE.md).
