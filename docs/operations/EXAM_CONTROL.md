# Kendali ujian dan sesi mahasiswa

## Status ujian

| Status | Akses mahasiswa |
|---|---|
| `waiting` | Login, ruang tunggu, heartbeat, dan status ujian |
| `active` | Akses di atas, pemilihan paket, soal, metadata database, query, dan submit |
| `finished` | Ruang tunggu bertuliskan “Ujian Selesai”; soal, query, dan submit ditutup |

Status awal adalah `waiting`. **Mulai Ujian** menetapkan `active`; **Hentikan Ujian**
menetapkan `finished`. Menekan Mulai Ujian setelah selesai membuka kembali ujian yang
sama dan mempertahankan jawaban. **Bersihkan Sesi** menghapus peserta/jawaban kelas
sebelumnya sekaligus mengembalikan status ke `waiting` dalam satu transaksi.

Soal dan pemilihan paket hanya tersedia setelah ujian dimulai. Query, submit, dan
metadata database memerlukan paket aktif yang sudah dipilih. Paket kosong atau nonaktif
tidak ditawarkan; pemilihan langsung melalui API juga ditolak. Submit harus merujuk
soal dalam paket peserta. Respons ujian diberi header `no-store`.

## Batas penerimaan permintaan

Server memeriksa sesi dan status sebelum menerima pekerjaan ujian. Query PostgreSQL
yang sudah diterima sebelum penutupan dapat menyelesaikan eksekusinya sesuai timeout
yang berlaku. Fase ini tidak membatalkan pekerjaan PostgreSQL yang sedang berjalan.

Submit diperiksa lagi **sesudah penilaian, sebelum penyimpanan jawaban dan nilai**.
Pemeriksaan serta penyimpanan memakai satu transaksi SQLite `BEGIN IMMEDIATE`, sehingga
penutupan tidak dapat masuk di antara pemeriksaan terakhir dan commit. Penutupan dan
penyimpanan diserialkan: jawaban yang sudah commit sebelum penutupan tetap sah.

Setiap perubahan status menaikkan `exam_revision` dalam `system_settings`. Jika ujian
ditutup lalu dibuka kembali selama penilaian, submit dari revisi lama tetap ditolak.
Pencabutan token, reset paket, atau pemindahan paket selama penilaian juga diperiksa
ulang. Penolakan mempertahankan jawaban/nilai yang sudah tersimpan sebelumnya.

Submit DDL/DML memakai workspace evaluator terpisah dan tidak mengubah workspace Run.
Run Query tetap dapat mengubah sandbox aktif. Detail penilaian ada di [GRADING.md](GRADING.md).
Soal dan paket tidak dapat diubah ketika ujian aktif; edit/hapus paket juga memerlukan
token revisi, sesuai [ADMIN_SECURITY.md](ADMIN_SECURITY.md).

## Login dan pemulihan perangkat

- Beberapa peserta dapat berbagi IP/NAT ketika `ALLOW_SHARED_IP=true` (default).
- Satu NIM dengan sesi terkunci tidak boleh diambil alih berdasarkan kesamaan IP atau
  `device_id` saja. Login ulang memerlukan cookie token sesi sebelumnya yang masih sah,
  serta kecocokan device ID apabila ID tersebut sudah tersimpan.
- Login ulang yang sah merotasi token. Token lama langsung tidak berlaku.
- Ketika IP berubah, peserta dapat login ulang dari browser yang masih menyimpan token
  dan device ID. Browser/perangkat baru atau cookie yang hilang memerlukan bantuan
  pengawas melalui **Bebaskan Sesi**.
- Kunci sesi tidak hilang hanya karena heartbeat terlambat. Status aktivitas pada
  monitoring tetap dihitung dari waktu aktivitas; itu berbeda dari kepemilikan sesi.
- Login memakai transaksi agar dua permintaan serentak tidak sama-sama mendapatkan
  kepemilikan NIM/perangkat.

NIM dan nama pada pendaftaran awal tetap berasal dari peserta. Perubahan ini tidak
menambahkan roster, password peserta, atau verifikasi identitas akademik.

## Tindakan pengawas

| Tindakan | Efek |
|---|---|
| Akhiri ujian (`/api/admin/exam/stop`) | Menutup soal/query/submit; jawaban dan token tetap tersimpan |
| Kick satu peserta (`/api/admin/kick-student`) | Mencabut sesi dan memblokir login sampai sesi dibebaskan |
| Hentikan semua sesi | Mencabut sesi online dan ruang tunggu; peserta lama perlu dibebaskan sebelum login ulang |
| Bebaskan Sesi (`/api/admin/clear-session-lock`) | Mencabut token lama dan melepas ikatan perangkat; jawaban/nilai tetap ada |
| Bersihkan Sesi | Menghapus peserta/jawaban kelas sebelumnya dan mengembalikan ujian ke persiapan |

Heartbeat dan pemuatan halaman memvalidasi token lagi dalam transaksi sebelum
memperbarui aktivitas. Permintaan lama tidak dapat menghidupkan kembali sesi yang
sudah di-kick atau dibebaskan.

Halaman ujian memeriksa status melalui heartbeat setiap 12 detik. Ketika status tidak
aktif, editor dikunci, draf soal aktif disimpan lokal, dan browser diarahkan ke ruang
tunggu. Penolakan API berlaku langsung tanpa menunggu heartbeat.

## Alamat IP dan reverse proxy

Ketiga runner memakai `--no-proxy-headers` agar Uvicorn tidak mengganti alamat peer
sebelum aplikasi memeriksanya. Untuk menjalankan manual:

```sh
python -m uvicorn main:app --no-proxy-headers --host 0.0.0.0 --port 8000
```

Secara default aplikasi mengabaikan `X-Forwarded-For`. Jika memakai reverse proxy yang
dikelola sendiri, isi `TRUSTED_PROXY_CIDRS` dengan IP/CIDR proxy tersebut, misalnya
`127.0.0.1/32,::1/128`. Jangan masukkan jaringan peserta sebagai proxy tepercaya.

Aplikasi menelusuri rantai forwarded dari kanan dan memilih alamat terdekat yang tidak
termasuk proxy tepercaya. Header dengan alamat tidak valid kembali menggunakan peer
koneksi. Proxy harus meneruskan alamat klien dengan konfigurasi yang benar.

## Pengujian

```powershell
.\.venv\Scripts\python.exe scripts/test_exam_access.py
.\.venv\Scripts\python.exe scripts/run_regression_tests.py
```

Suite akses menggunakan SQLite sementara dan memblokir koneksi PostgreSQL. Regresi
lengkap memakai cluster PostgreSQL sementara sesuai [TESTING.md](TESTING.md).

## Interval tampilan

Dashboard admin memuat ulang monitoring sekitar 10 detik ketika tab monitoring aktif,
dan panel lobby sekitar 20 detik. Pada halaman lobby peserta, pemeriksaan status ujian
sekitar 3 detik, daftar peserta 6 detik dan heartbeat 15 detik. Angka ini interval
polling, bukan jaminan latensi jaringan. Halaman IDE memeriksa heartbeat sekitar 12 detik.
