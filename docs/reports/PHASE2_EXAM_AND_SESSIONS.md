# Fase 2: kendali ujian dan keamanan sesi

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 7 November 2026 (Asia/Makassar).

## Perubahan perilaku

Ujian memiliki tiga status: `waiting`, `active`, dan `finished`. Pengawas mengakhiri
ujian melalui endpoint stop; peserta melihat “Ujian Selesai”. Memulai kembali membuka
ujian yang sama dengan jawaban yang tetap tersimpan. Membersihkan kelas menghapus
peserta/jawaban dan mengembalikan status ke persiapan secara atomik.

Validasi sesi berada di `database.require_student_access()` dan dipakai melalui
`main.require_student()`. API soal, pemilihan paket, eksekusi, submit, dan metadata
memeriksa status aktif. Query/submit/metadata juga memerlukan paket aktif yang telah
dipilih. Paket kosong dan nonaktif tidak ditawarkan. Respons ujian memakai `no-store`.

Saat penyimpanan submit, sesi, paket, keanggotaan soal, status ujian, dan revisi ujian
diperiksa kembali dalam transaksi yang sama dengan penyimpanan jawaban/nilai. Revisi
menutup kasus ujian dihentikan lalu dibuka kembali selama evaluator masih berjalan.
Permintaan yang ditolak tidak mengganti jawaban atau skor sebelumnya.

## Sesi dan perangkat

- Kesamaan IP tidak memberikan hak mengambil alih NIM. Login ulang sesi terkunci
  memerlukan token sebelumnya dan kecocokan device ID yang telah tersimpan.
- Kepemilikan sesi bertahan saat heartbeat terlambat. Browser baru/cookie hilang perlu
  tindakan Bebaskan Sesi. Pemilik yang masih memiliki token dapat login ulang setelah
  IP berubah, dengan token baru menggantikan token sebelumnya.
- Peserta berbeda tetap dapat berbagi IP ketika `ALLOW_SHARED_IP=true`.
- Login diproses dengan `BEGIN IMMEDIATE` untuk mencegah dua pemilik pada login serentak.
- Kick mencabut sesi dan memblokir login ulang; Bebaskan Sesi mengizinkan perangkat
  pengganti dengan mempertahankan jawaban. Hentikan Semua Sesi juga mencakup ruang tunggu.
- Heartbeat dan perubahan lokasi mahasiswa memvalidasi ulang token dalam transaksi,
  sehingga permintaan lama tidak dapat menghidupkan sesi yang dicabut.
- Logout dengan token lama tidak mencabut sesi yang sudah dirotasi.

Runner menonaktifkan penanganan forwarded header otomatis Uvicorn. Aplikasi memakai
peer koneksi kecuali IP tersebut termasuk `TRUSTED_PROXY_CIDRS`. Rantai header dibaca
dari proxy terdekat; header tidak valid kembali menggunakan alamat peer.

## Integrasi halaman

Heartbeat membawa status ujian dan revisinya. Ketika status tidak aktif, editor
dikunci, draf soal aktif disimpan ke localStorage, dan mahasiswa diarahkan ke ruang
tunggu. Respons API 401 menampilkan pemulihan sesi; penolakan status atau revisi tidak
ditampilkan sebagai keberhasilan submit. Dashboard membedakan label Menunggu/Aktif/Selesai.

## Pengujian

`scripts/test_exam_access.py` memiliki 34 tes yang mencakup:

- Penolakan seluruh API ujian sebelum mulai dan setelah selesai, tanpa memanggil evaluator.
- Jalur aktif, autentikasi metadata, pemilihan paket, soal lintas paket, dan cache.
- Penutupan ketika evaluator masih berjalan melalui sinkronisasi dua thread.
- Stop/start, kick, dan reset paket selama penilaian; pelestarian skor lama.
- Login HTTP dengan cookie sebelumnya, rotasi token, IP berubah, NAT, dan login serentak.
- Heartbeat lama setelah kick/clear, logout dengan token lama, dan reset kelas.
- Proxy tepercaya/tidak tepercaya serta header IP tidak valid.

Suite ini memakai SQLite sementara dan memblokir koneksi PostgreSQL. Suite submission
dan retensi skor lama kini secara eksplisit memulai ujian; fixture status mahasiswa
menggunakan `online` alih-alih status tidak dikenal `active`.

Dua temuan fase 2 dalam `test_known_risks.py` sudah menjadi tes normal. Empat expected
failure tetap merekam pekerjaan fase 3–5.

Hasil akhir dari salinan sumber bersih tanpa `.env`, `scratch/`, atau SQLite lama:

| Pemeriksaan | Hasil |
|---|---|
| Runner lengkap | 13/13 pemeriksaan lulus; exit code 0 |
| Migrasi SQLite | 8 tes lulus |
| Kendali ujian dan sesi | 34 tes lulus |
| Submission PostgreSQL | 29 tes lulus |
| Rekap/ZIP | 8 tes lulus |
| Retensi skor | 7 tes lulus |
| Sesi dan mahasiswa terlambat | 7 tes lulus |
| Operasional | 7 tes lulus |
| Regresi temuan audit | 2 tes lulus, 4 expected failure |

Total: **102 tes normal lulus dan 4 expected failure**. Sintaks Python/JavaScript,
dependensi, dan whitespace juga lulus. Pengujian memakai Windows, Python 3.14.6,
PostgreSQL 18.6, serta dependensi yang sama dengan laporan fase 1.

Hash SHA-256 file database utama (`*.db`) dan `.env` tidak berubah selama verifikasi
salinan bersih. Fixture PostgreSQL dan server browser menggunakan direktori terpisah;
proses pengujian dihentikan setelah selesai.

Alur browser diuji pada server sementara: login mahasiswa, ruang tunggu, login pengawas,
mulai ujian, fullscreen, pemilihan paket, run query, submit, penutupan dari dashboard,
pengalihan mahasiswa ke “Ujian Selesai”, penyimpanan draf lokal, dan respons soal 403.
Untuk pemeriksaan browser tersebut, eksekutor/evaluator PostgreSQL diganti fixture;
eksekusi database nyata diperiksa terpisah melalui regresi PostgreSQL sementara.

## Batas fase ini

Query yang telah diterima dapat selesai setelah pengawas menutup ujian. Mutasi sandbox
oleh evaluator belum diisolasi dari workspace mahasiswa; pemeriksaan akhir menjaga
penyimpanan jawaban/nilai, bukan membatalkan efek PostgreSQL. Perbaikan privilege sandbox,
pembanding hasil lengkap, serta keamanan admin/CSRF/log tetap mengikuti fase berikutnya.

Token/device ID merupakan bukti kelanjutan sesi, bukan verifikasi identitas akademik
pada pendaftaran pertama. Tidak ada perubahan struktur tabel pada fase ini; status dan
revisi memakai tabel `system_settings` yang sudah tersedia.

Panduan operasional: [EXAM_CONTROL.md](../operations/EXAM_CONTROL.md).
