# Fase 5: penguatan admin dan dukungan admin ganda

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 7 November 2026, Asia/Makassar.

## Hasil

Sesuai pilihan pengguna, kedua pengawas memakai master key yang sama dengan sesi
independen. Token global yang sebelumnya membuat login baru mengusir admin lama
dihapus. Login, logout, kedaluwarsa, dan login ulang berlaku per sesi. Sesi tersimpan
di SQLite, token hanya disimpan sebagai hash, dan tetap berlaku lintas proses/restart.
Rotasi master key mencabut sesi lama dan mempertahankan akses pemrakarsa melalui sesi baru.

Master key disimpan sebagai hash scrypt dengan salt. Plaintext lama dikonversi saat
inisialisasi. Environment hanya menjadi bootstrap instalasi pertama sehingga restart
tidak membatalkan perubahan password. Pemulihan lokal menggunakan input tersembunyi
melalui `scripts/reset_admin_key.py`, dengan konfirmasi dan pencabutan seluruh sesi.

CSRF kini diperiksa pada semua mutasi, termasuk Referer yang sebelumnya bisa lolos.
Mutasi admin memerlukan token terikat sesi. Login memiliki token form, logout memakai
POST, dan halaman/API admin tidak di-cache. Dashboard menyertakan CSRF otomatis.

Admin ganda memiliki perlindungan konflik edit/hapus soal melalui `edit_revision`.
Perubahan berdasarkan revisi lama mendapat HTTP 409 dan tidak menimpa perubahan admin
lain. Revisi edit terpisah dari revisi penilaian. Audit mutasi mencatat ID sesi, status,
path, IP, dan waktu tanpa kredensial/body/query string.

Endpoint log mahasiswa tidak lagi menerima sesi palsu atau jenis aksi admin. Penulisan
memeriksa ulang sesi, status/revisi ujian, dan paket dalam transaksi. Detail dibatasi,
ditandai sebagai laporan klien, dan dibersihkan; flood dibatasi per mahasiswa. Token
soal di URL dihapus. Ekspor CSV menetralkan formula dan ZIP menolak path dari metadata.

## Komponen

| File | Tanggung jawab |
|---|---|
| `admin_security.py` | Hash master key, sesi, CSRF sesi, rotasi/logout, dan audit |
| `database.py` | Migrasi SQLite 4, revisi edit, log mahasiswa transaksional, ekspor |
| `main.py` | Guard CSRF/admin, login/logout, audit/session API, dan rate limit |
| `static/js/admin.js` | Header CSRF, revisi form, dan reload sesudah rotasi master key |
| Template admin/mahasiswa/waiting | Token form dan logout POST |
| `scripts/reset_admin_key.py` | Pemulihan lokal tanpa password dalam argumen shell |
| `scripts/test_admin_security.py` | Regresi admin ganda, keamanan, konflik, audit, dan pemulihan |

## Verifikasi

Regresi dari salinan sumber bersih lulus **18/18 pemeriksaan**, dengan **201 tes normal
lulus dan tanpa expected failure**. Salinan dibuat dari berkas Git tracked/untracked
yang tidak diabaikan, tanpa `.env`, SQLite lama, atau `scratch/`.

| Suite | Hasil |
|---|---|
| Migrasi SQLite | 10 lulus |
| Kendali ujian/sesi, riwayat, dan revisi | 43 lulus |
| Admin ganda, CSRF, kredensial, audit, log, dan pemulihan | 26 lulus |
| Parser SQL | 9 lulus |
| Pembanding hasil bertipe | 9 lulus |
| Submission | 29 lulus |
| Rekap/ZIP | 8 lulus |
| Retensi skor | 7 lulus |
| Sesi/mahasiswa terlambat | 7 lulus |
| Operasional | 7 lulus |
| Privilege dan sandbox | 28 lulus |
| Evaluator hasil lengkap | 12 lulus |
| Regresi temuan | 6 lulus |

Sintaks Python/JavaScript, konsistensi dependensi, dan whitespace Git lulus.
JavaScript inline template mahasiswa dan waiting room diperiksa terpisah dengan Node.
Hash SHA-256 database utama `*.db` dan `.env` tetap sama sebelum/sesudah regresi.
Fixture PostgreSQL sementara dibersihkan setelah tes. Pesan cleanup gagal pada suite
sandbox berasal dari dependency yang sengaja dibuat untuk menguji rollback.
Lingkungan pengujian: Windows, Python 3.14.6, PostgreSQL 18.6.

Uji browser pada cluster/database sementara memakai dua konteks independen:

- Kedua browser berhasil login dan mendapatkan status sesi HTTP 200.
- Admin kedua mengirim perintah akhir ujian dari halaman dashboard dengan CSRF otomatis;
  server mengembalikan HTTP 200.
- Logout melalui form admin pertama berhasil.
- Admin kedua tetap dapat mengakses daftar peserta, HTTP 200.
- Tidak ada JavaScript page error dalam alur yang diuji.

Uji browser merupakan smoke test alur tersebut, bukan audit visual seluruh halaman.
Seluruh enam regresi temuan kini berjalan sebagai tes biasa; expected failure fase 5
untuk log tanpa sesi telah dihapus.

## Batas dan pelaksanaan

Master key bersama memberikan hak penuh yang sama; tidak ada akun bernama, pembagian
peran, atau persetujuan dua orang. Audit mengidentifikasi sesi browser, bukan orang.
Tindakan global tetap langsung berlaku. Logout/rotasi menolak permintaan berikutnya,
tetapi tidak membatalkan permintaan yang sudah mulai diproses. Audit request tidak
atomik dengan seluruh perubahan bisnis dan tidak antirusak oleh pemilik server.

Sesi maksimal 8 jam dengan idle 1 jam. Rate limiter per proses; uji kapasitas kelas
dan retensi data tetap perlu dilakukan pada fase operasional. Log browser bukan bukti
kecurangan. Pengujian tidak mengubah database utama atau `.env`. Migrasi diterapkan
ketika aplikasi dijalankan kembali; perubahan belum dikomit.

Panduan penggunaan dan pemulihan: [ADMIN_SECURITY.md](../operations/ADMIN_SECURITY.md).
