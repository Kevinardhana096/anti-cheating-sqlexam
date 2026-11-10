# Arsitektur dan batas skalabilitas

Diperiksa 8 November 2026. Dokumen ini menggantikan klaim kapasitas dan waktu pemulihan lama yang tidak didukung pengukuran. Untuk prosedur operator gunakan [SOP](../operations/OPERATIONS_GUIDE.md).

## Komponen saat ini

| Komponen | Tanggung jawab |
|---|---|
| SQLite utama | users, questions, exam_packages, system_settings, submissions, submission_attempts, exam_logs, admin_sessions, admin_audit, grading_jobs dan grading_decisions |
| PostgreSQL pagila/classicmodels | Dataset master untuk role read-only |
| Schema sandbox berbasis digest NIM | Role LOGIN tersendiri dan workspace peserta; sandbox_pribadi adalah pilihan virtual |
| Workspace evaluator sementara | Menjalankan acuan dan jawaban terpisah; tidak menerapkan Submit ke workspace Run |
| SQLite simulasi admin | Snapshot dan riwayat latihan per sesi admin, terpisah dari nilai peserta |
| Worker ujian dan simulasi | Memproses antrean masing-masing dengan mesin evaluasi dan batas slot bersama |

SQLite memakai WAL, synchronous NORMAL dan busy_timeout 5 detik. Banyak reader dapat berjalan bersama, tetapi hanya satu writer. Contention tetap mungkin pada satu proses. Backup tidak cukup berupa copy file SQLite ketika WAL masih aktif, dan satu file SQLite tidak mencakup PostgreSQL/unggahan.

Sesi, revisi dan pekerjaan tersimpan di SQLite; rate limiter, pool PostgreSQL, tracker dan cache sebagian berada di memori proses. Rate limiter memakai sliding window berbasis timestamp. Tidak ada Redis atau shared limiter yang sudah diimplementasikan.

## Model pelaksanaan

Runner menjalankan satu proses Uvicorn tanpa reload. Ini baseline operasional, bukan bukti bahwa satu worker selalu bebas lock atau cukup untuk jumlah peserta tertentu. Bukti yang tersedia berasal dari simulasi 24 peserta pada loopback dengan fsync nonaktif di fixture. Jangan menyimpulkan batas 80, 200 atau 500 peserta dari pilihan teknologi saja.

Menambah worker membuat limiter/cache/pool dan worker grading tambahan per proses. SQLite menyerialkan writer dan lease job mencegah commit worker lama setelah fencing berubah; hal itu tidak otomatis memberi kapasitas atau durabilitas lintas node. Tidak ada jaminan pemulihan instan atau nol kehilangan nilai setelah kegagalan daya.

## Arah pengembangan, belum implementasi

Untuk kelas lebih besar atau beberapa server, ukur profil query/submit dan latensi terlebih dahulu. Perubahan yang mungkin diperlukan meliputi control database PostgreSQL terdedikasi, rate limiter bersama, budget pool per node, pembagian worker penilaian, storage unggahan bersama, koordinasi maintenance serta backup/pemulihan lintas store. Redis/pub-sub adalah pilihan desain, bukan dependensi saat ini.

Migrasi teknologi tidak dengan sendirinya membuktikan aplikasi mendukung ratusan peserta. Benchmark, uji LAN/browser kelas, beban terburuk dan latihan recovery tetap diperlukan. Lihat [readiness](../operations/RELEASE_READINESS.md), [keamanan sandbox](../operations/SANDBOX_SECURITY.md) dan [antrean](../operations/GRADING_QUEUE.md).
