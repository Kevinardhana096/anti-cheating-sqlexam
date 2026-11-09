# SOP pengawas dan laboran

Panduan aktif, diperiksa 8 November 2026. Setup: [manual instalasi](<../../INSTALLATION MANUAL.md>). Detail teknis: [indeks dokumentasi](../README.md).

## Jaringan dan laptop server

Server memerlukan service PostgreSQL dan environment koneksi yang benar. Windows memakai `setup.bat` untuk setup dan `run.bat`/`run.ps1` untuk menjalankan. macOS/Linux memakai langkah setup Python di manual lalu `bash run.sh`. Runner memakai satu proses Uvicorn dan port 8000.

Peserta harus dapat mengakses IP laptop server. Client/AP isolation bergantung topologi: fitur ini dapat memblokir peserta ke host jika keduanya berada pada Wi-Fi yang sama. Uji konektivitas tiap segmen terlebih dahulu; jangan mengaktifkannya sebagai aturan universal. Bila ada segmentasi peserta, pastikan aturan jaringan tetap mengizinkan akses ke server ujian.

Izinkan inbound port 8000 hanya pada jaringan yang dimaksud. Biarkan PostgreSQL hanya di localhost atau dibatasi firewall; peserta tidak memerlukan akses langsung port 5432. HTTP tidak mengenkripsi trafik. Cookie/CSRF tidak menggantikan perlindungan jaringan atau TLS; pengaturan TLS mengikuti infrastruktur institusi. Jangan mematikan firewall sebagai prosedur rutin.

Laptop host harus menyala, terhubung daya dan tidak tidur. Mematikan layar berbeda dari sleep. Uji pengaturan lid/power pada laptop yang dipakai sebelum pelaksanaan.

## Sebelum kelas

1. Hentikan/arsipkan kelas sebelumnya sebelum upgrade. Selesaikan review nilai, unduh hasil/log dan buat backup lengkap sebelum Bersihkan Sesi.
2. Jika memulai kelas baru, Bersihkan Sesi menghapus peserta, jawaban dan riwayat terkait serta kembali ke persiapan. Tombol ini bukan sekadar membersihkan daftar online. Workspace PostgreSQL tidak seluruhnya dibersihkan oleh tindakan ini.
3. Periksa `/health`, `/ready` dan panel Database. Reset Database hanya jika memang perlu mengganti dataset; bukan cara tes koneksi dan bukan restore nilai.
4. Atur paket aktif dan soal saat persiapan. Nomor harus unik dalam paket. Tinjau kunci, prasyarat DDL/DML, alias yang diwajibkan, toleransi, urutan seri dan batas LIMIT.
5. Soal/paket dibekukan selama ujian aktif. Dua admin dapat bekerja bersamaan; konflik revisi berarti form perlu dimuat ulang, bukan dipaksa menimpa.
6. Uji soal dengan [IDE admin](ADMIN_IDE.md), lalu gunakan perangkat mahasiswa untuk gladi bersih lobby, fullscreen, jaringan dan pergantian sesi.
7. Siapkan rencana backup/pemulihan dan ukur kapasitas pada host/jaringan kelas. Angka simulasi 24 peserta bukan jaminan kapasitas kelas nyata.

## Mulai dan pantau

Peserta login dengan NIM dan nama lalu menunggu di lobby. Setelah siap, tekan **Mulai Ujian**. Acuan paket aktif divalidasi; kegagalan tidak membuka akses. Login peserta terlambat saat aktif langsung menuju ujian. Setelah masuk fullscreen, peserta memilih paket sesuai arahan pengawas.

Monitoring peserta diperbarui sekitar 10 detik; daftar waiting room pada dashboard sekitar 20 detik. Angka IP sama dapat sah karena NAT bersama (`ALLOW_SHARED_IP=true`). Kepemilikan NIM/perangkat berbeda dari status online. Log fokus/tab berasal dari browser dan perlu interpretasi pengawas; jangan menyimpulkan kecurangan dari satu angka saja.

Perhatikan status tersimpan, hasil terbaru, skor terbaik dan pending. Pending/review bukan nol. Gangguan respons tidak membuktikan jawaban belum tersimpan; ulang submit dapat menambah riwayat percobaan.

| Tindakan | Efek |
|---|---|
| Hentikan Ujian | Tutup akses soal/query/submit, pertahankan jawaban dan token |
| Hentikan Semua | Cabut sesi peserta; berbeda dari stop normal |
| Bebaskan Sesi | Cabut token dan lepas ikatan perangkat tanpa menghapus nilai |
| Reset Paket | Izinkan pemilihan ulang, ubah konteks penilaian dan batalkan pekerjaan konteks lama |
| Bersihkan Sesi | Hapus data kelas sebelumnya dan kembali ke persiapan |
| Bersihkan Log | Hapus log ujian, bukan audit permintaan admin |

Detail transisi: [EXAM_CONTROL.md](EXAM_CONTROL.md). Admin memakai master key sama dengan sesi independen; perubahan password mencabut admin lain. Lihat [ADMIN_SECURITY.md](ADMIN_SECURITY.md).

## Akhiri, review dan arsipkan

Tekan **Hentikan Ujian**. Submit baru ditolak, tetapi antrean sah yang sudah diterima dapat menyelesaikan penilaian setelah stop. Menekan Mulai lagi membuka kembali ujian yang sama; bukan membuat kelas baru.

Selesaikan pending/review lewat [API/CLI penilaian](GRADING_QUEUE.md). Form keputusan khusus di dashboard belum tersedia. Perbaikan kode tidak otomatis menilai ulang percobaan lama; minta regrade eksplisit sesuai revisi/keputusan terbaru.

Ekspor CSV/ZIP/log untuk arsip. ZIP SQL dan CSV bukan backup layanan lengkap. Hentikan server/writer lain dan buat bundle SQLite, PostgreSQL dan unggahan sesuai [RELEASE_READINESS.md](RELEASE_READINESS.md). Jangan mengganti SQLite secara manual dan menghapus WAL/SHM sebagai prosedur pemulihan rutin; pertahankan bukti insiden dan gunakan restore tervalidasi ke tujuan baru.

## Kredensial dan konfigurasi

Aplikasi tidak membaca `.env` otomatis. Atur environment pada terminal yang menjalankan server. Rotasi `PG_STUDENT_PASS` dilakukan pada environment sebelum restart; startup mengonfigurasi role dengan kredensial tersebut. Untuk master key yang sudah ada, gunakan dashboard atau pemulihan lokal, bukan environment bootstrap. Jangan menyimpan password pada script yang dibagikan.

## Insiden dan kapasitas

Jika akses gagal, periksa service, log, `/ready`, IP/port, firewall dan jalur router. Reset Database mengganti dataset dan bukan perbaikan pool/koneksi. Saat mati listrik, simpan file DB/WAL/SHM yang tersisa dan lakukan diagnosis pada salinan. WAL/NORMAL tidak menjamin nol kehilangan transaksi.

SQLite tetap memiliki satu writer; satu proses aplikasi pun dapat mengalami contention. Rate limiter, pool dan sebagian cache bersifat per proses. Menambah `--workers` melipatgandakan resource dan tidak otomatis meningkatkan kapasitas dengan aman. Sistem belum menyediakan shared rate limiter atau deployment multi-node. Gunakan [panduan pengukuran dan restore](RELEASE_READINESS.md); jangan memakai klaim angka peserta tanpa benchmark dan gladi bersih.
