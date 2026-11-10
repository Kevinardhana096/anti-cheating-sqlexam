# Indeks dokumentasi

Panduan aktif diperiksa terhadap kode pada 8 November 2026. Mulai dari manual instalasi
dan SOP; laporan pengujian adalah bukti pada versi tertentu, bukan instruksi terbaru.

## Instalasi dan operasi

| Dokumen | Isi |
|---|---|
| [README proyek](../README.md) | Ringkasan fitur dan setup singkat |
| [Manual instalasi](<../INSTALLATION MANUAL.md>) | Windows, macOS/Linux, environment, PostgreSQL, verifikasi |
| [SOP pengawas](operations/OPERATIONS_GUIDE.md) | Pra-ujian, Mulai/Hentikan, pemulihan peserta dan arsip |
| [Kendali sesi](operations/EXAM_CONTROL.md) | Waiting/active/finished, token, cutoff, NAT dan proxy |
| [Keamanan admin](operations/ADMIN_SECURITY.md) | Admin ganda, CSRF, revisi paket/soal dan pemulihan key |
| [IDE admin](operations/ADMIN_IDE.md) | Simulasi dengan controller mahasiswa dan data terpisah |
| [Sandbox](operations/SANDBOX_SECURITY.md) | Role, daftar larangan fungsi dan batas sumber daya |
| [Penilaian](operations/GRADING.md) | Hasil lengkap, toleransi, seri, tipe data dan review |
| [Antrean penilaian](operations/GRADING_QUEUE.md) | Retry, keputusan manual/regrade dan revisi |
| [Readiness, backup dan restore](operations/RELEASE_READINESS.md) | Batas bukti kapasitas dan pemulihan terverifikasi |
| [Pengujian](operations/TESTING.md) | Runner, fixture sementara dan skema migrasi |
| [Arsitektur](design/ARCHITECTURE_EVALUATION.md) | Komponen saat ini dan rencana yang belum diimplementasikan |

## Audit dan status perbaikan

| Audit/laporan awal | Kelanjutan |
|---|---|
| [Notulensi final test](reports/FINAL_TEST_MINUTES_ANALYSIS.md) | [Perbaikan final test](reports/FINAL_TEST_FIXES.md) |
| [Kasus awal sesi](reports/EXAM_START_FAILURE_TESTS.md) | Bukti race/failure terkontrol; bukan uji mati listrik/Wi-Fi |
| [Implementasi IDE admin](reports/ADMIN_IDE_IMPLEMENTATION.md) | [Perbaikan perilaku admin](reports/ADMIN_BEHAVIOR_FIXES.md) |
| [Audit fairness](reports/GRADING_FAIRNESS_AUDIT.md) | [Perbaikan fairness](reports/GRADING_FAIRNESS_FIXES.md) |
| [Urutan seri](reports/ORDER_BY_TIES.md) | Dilanjutkan perbaikan fairness |
| [Daftar larangan fungsi](reports/SQL_FUNCTION_DENYLIST.md) | Kebijakan aktif dijelaskan di panduan sandbox |
| [Audit admin](reports/ADMIN_BEHAVIOR_AUDIT.md) | [Perbaikan admin](reports/ADMIN_BEHAVIOR_FIXES.md) |

Laporan fase 1–7 dalam `reports/PHASE*.md` adalah catatan historis. Angka jumlah tes,
hash dan benchmark hanya berlaku pada putaran yang disebut; jangan menjumlahkan atau
mengartikannya sebagai ukuran pengujian terbaru. Hasil JSON menyertai laporan terkait.

Belum tersedia: fixture tersembunyi beberapa dataset per soal, cache hasil acuan lintas
submit, form keputusan manual khusus di dashboard, penjadwalan sesi otomatis dan
pembuktian kapasitas pada seluruh kombinasi laptop/jaringan. Gladi bersih tetap perlu.

`antislop.md` dan salinannya adalah aturan kerja agen, bukan panduan menjalankan ujian.
Dokumen dalam `static/vendor` adalah atribusi/panduan pihak ketiga dan tidak mengatur
alur aplikasi. Tidak ada klaim seluruh tautan internet atau seluruh platform telah
diuji langsung pada audit dokumentasi.
