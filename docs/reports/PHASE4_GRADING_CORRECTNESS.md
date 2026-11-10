# Fase 4: ketepatan penilaian dan isolasi evaluasi

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 7 November 2026, Asia/Makassar.

## Hasil implementasi

Penilaian SELECT kini membaca hasil lengkap melalui server-side cursor. Preview
500 baris tidak lagi dipakai sebagai kebenaran penilaian. Pembanding mempertahankan
tipe native, presisi angka, kapitalisasi/spasi/nol depan teks, NULL, dan kemunculan
duplikat. Urutan mengacu pada AST ORDER BY terluar atau kebijakan eksplisit per soal.
Toleransi angka tidak diterapkan secara diam-diam.

DDL/DML dinilai di dua schema sementara dengan LOGIN terbatas tersendiri. Evaluator
membandingkan struktur dan isi akhir tanpa menerapkan jawaban ke workspace aktif.
Snapshot menyalin data, constraint lengkap, identity/sequence, dan index. Rekonstruksi
ekspresi tidak dijalankan sebagai admin. FK ditambahkan sesudah seluruh PK/UNIQUE,
sehingga urutan nama tabel tidak merusak proses salin.

Sebelum mulai ujian, seluruh acuan paket aktif divalidasi. Perubahan manifest/revisi
selama validasi membatalkan aktivasi. Penyimpanan perubahan soal memeriksa status
aktif dalam transaksi SQLite. Acuan kosong tidak lagi memberi poin otomatis.

Kegagalan acuan, evaluator, atau batas sumber daya menghasilkan `graded=false`,
dengan skor/kebenaran percobaan NULL. Kesalahan jawaban yang teridentifikasi tetap
dinilai nol. Skor terbaik sebelumnya tetap dipertahankan.

SQLite versi 3 memisahkan `submission_attempts` dari jawaban terbaik pada `submissions`.
Setiap percobaan menyimpan query, status, feedback, skor, dan revisi soal. Jawaban terbaik
lama diimpor sekali sebagai `legacy_best`. Respons API memisahkan percobaan terbaru
dan jawaban terbaik; endpoint admin menyediakan riwayat berpaginasi. Editor memulihkan
query percobaan terbaru dan menampilkan status penilaian tertunda.

Perubahan acuan, setup, policy, bobot, database, paket, atau nomor soal menaikkan revisi
dan menandai skor lama `needs_regrade`; sejarah nilai tetap tersimpan. Pemeriksaan sesi,
batas waktu ujian, dan revisi soal dilakukan kembali sebelum percobaan disimpan.

## Komponen

| File | Perubahan |
|---|---|
| `grading_results.py` | Policy bertipe, pembanding native, multiset di disk, toleransi, dan batas hasil |
| `grading_workspace.py` | Workspace sementara, snapshot konsisten, AST rebind, dan signature struktur |
| `grading_engine.py` | Orkestrasi evaluasi, klasifikasi error, prasyarat, dan validasi acuan |
| `database.py` | Migrasi versi 3, riwayat/best, revisi soal, dan aktivasi tervalidasi |
| `main.py` | Integrasi respons/status, field policy/setup admin, dan endpoint riwayat |
| `static/js/student.js` | Pending, pemisahan latest/best, dan penanda preview |

## Verifikasi

Runner lengkap dijalankan dari salinan seluruh sumber Git tracked/untracked yang
tidak diabaikan, tanpa `.env`, SQLite lama, atau `scratch/`. Hasilnya **17/17 pemeriksaan
lulus**, exit code 0.

| Suite | Hasil |
|---|---|
| Migrasi SQLite | 10 lulus |
| Kendali ujian/sesi, riwayat, revisi, dan validasi mulai | 43 lulus |
| Parser SQL | 9 lulus |
| Pembanding hasil bertipe | 9 lulus |
| Submission | 29 lulus |
| Rekap/ZIP | 8 lulus |
| Retensi skor | 7 lulus |
| Sesi/mahasiswa terlambat | 7 lulus |
| Operasional | 7 lulus |
| Privilege dan sandbox | 28 lulus |
| Evaluator hasil lengkap dan workspace sementara | 12 lulus |
| Regresi temuan | 5 lulus, 1 expected failure fase 5 |

Total **174 tes normal lulus dan 1 expected failure**. Sintaks Python/JavaScript,
konsistensi dependensi, dan whitespace Git juga lulus. Pesan cleanup gagal pada suite
keamanan merupakan dependency sengaja yang menguji rollback, bukan kegagalan tes.
Hash SHA-256 database utama `*.db` dan `.env` sama sebelum/sesudah pengujian. Cluster
PostgreSQL dan direktori fixture sementara sudah dibersihkan. Pengujian dilakukan
di Windows, Python 3.14.6, dan PostgreSQL 18.6; pengujian visual browser dan uji kapasitas
kelas belum dilakukan dalam fase ini.

Pengujian lama yang bergantung pada efek samping penilaian DDL/DML kini menyiapkan
workspace secara eksplisit melalui Run Query. Pemeriksaan tetap menilai benar/salah,
struktur, FK violation, data, skor, sesi, dan isolasi; kalimat feedback lama bukan
kontrak penilaian. Kedua expected failure fase 4 dihapus karena masalahnya sudah
diregresikan sebagai tes normal. Expected failure endpoint log tetap untuk fase 5.

## Batas pelaksanaan

Evaluator memiliki anggaran 10 detik, 4 slot per proses, 100.000 baris/32 MiB per sisi,
64 kolom, dan batas 1.000 baris untuk pencocokan tanpa urutan dengan toleransi. Melewati
batas menghasilkan status tertunda; tidak ada fallback pada preview. Provisioning dan
cleanup dapat menambah waktu respons dan belum merupakan hard quota host.

Soal INSERT memakai pengisian ulang tabel sasaran hanya dalam workspace evaluator.
Gunakan setup eksplisit untuk fixture yang diperlukan. Acuan SELECT dicampur perubahan
state belum didukung dalam satu soal. Policy/setup tersedia lewat API admin; formulir
khususnya belum ditambahkan. Penilaian manual/regrade melalui formulir khusus juga
belum tersedia. Uji beban kelas dan penguatan admin/CSRF/log tetap pekerjaan berikutnya.

Database utama dan `.env` tidak dimigrasikan selama pengujian. Migrasi/hardening baru
berlaku ketika aplikasi dijalankan kembali. Perubahan belum dikomit.

Panduan operator: [GRADING.md](../operations/GRADING.md).
