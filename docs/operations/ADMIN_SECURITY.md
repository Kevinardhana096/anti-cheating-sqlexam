# Admin ganda, master key, dan log

Perbaikan audit terbaru dijelaskan di [laporan perbaikan admin](../reports/ADMIN_BEHAVIOR_FIXES.md).
Paket dibekukan selama ujian aktif. Edit/hapus paket memakai token revisi untuk menolak
form lama dari pengawas lain. Nama mahasiswa diperlakukan sebagai data, bukan handler
JavaScript. Unggahan menerima PNG/JPEG/WEBP/GIF tervalidasi, maksimal 8 MiB per gambar,
32 MiB dan 20 gambar per batch, dengan batas piksel; SVG baru ditolak.

Fase 5, 7 November 2026. Dua pengawas memakai master key yang sama dan sesi independen.

## Menggunakan dua admin

1. Jalankan server seperti biasa.
2. Buka `/admin/login` dari dua perangkat atau dua profil/konteks browser terpisah.
3. Login dengan master key yang sama. Keduanya dapat memantau, memulai/mengakhiri ujian,
   mengelola peserta, serta menjalankan fungsi admin yang tersedia.
4. Logout satu admin tidak memutus admin lainnya. Login ulang mengganti sesi browser
   itu sendiri dan tidak membatalkan sesi browser lain.

Tab biasa dalam satu profil browser berbagi cookie, sehingga merupakan satu sesi.
Gunakan perangkat/profil terpisah jika ingin dua sesi yang benar-benar independen.
Kedua admin memiliki kewenangan penuh yang sama. Ini bukan akun bernama, pembagian
hak akses, atau persetujuan dua orang untuk satu tindakan.

Setiap sesi memiliki token acak tersendiri. SQLite hanya menyimpan SHA-256 token,
ID sesi, IP login, serta waktu pembuatan/kedaluwarsa/aktivitas terakhir. Sesi berlaku
maksimal 8 jam dan berakhir setelah 1 jam tanpa aktivitas. Polling dashboard dihitung
sebagai aktivitas. Pemeriksaan aktivitas diperbarui paling sering setiap 30 detik.
Sesi tetap dapat dipakai setelah proses aplikasi dimulai ulang, selama belum dicabut
atau kedaluwarsa. Mengganti alamat IP tidak langsung membatalkan sesi admin.

## Konflik tindakan

Saat menyimpan soal, HTTP 400 dapat berarti kunci SQL, query setup atau kebijakan
penilaian ditolak. Ini bukan gangguan koneksi. Dashboard menampilkan alasan validasi
dan mempertahankan isi form. Kalimat bebas diletakkan pada judul/deskripsi; kolom
kunci jawaban otomatis memerlukan SQL valid, misalnya `SELECT 1 AS uji` pada pagila.

Kondisi ujian bersifat bersama: jika admin A mengakhiri ujian, admin B melihat status
yang sama melalui polling berikutnya. Validasi kesiapan dijalankan terpisah sebelum
mulai dan hasilnya dibagikan ke semua admin. Hasil tidak disimpan jika konfigurasi
atau status/revisi ujian berubah selama validasi. Perintah mulai hanya memeriksa
kesiapan tersimpan dan memperbarui status dalam satu transaksi; SQL acuan tidak
dijalankan saat mulai.

Soal memiliki `edit_revision` terpisah dari revisi penilaian. Form edit menyertakan
revisi yang dibaca ketika dibuka. Penyimpanan atau penghapusan berdasarkan revisi
lama menghasilkan HTTP 409; muat ulang soal dan periksa perubahan admin lain sebelum
mengulang. Penyimpanan/penghapusan soal ditolak ketika ujian aktif.

Klien API yang mengubah soal harus mengirim `expected_edit_revision` dalam JSON.
Untuk penghapusan gunakan
`DELETE /api/admin/questions/{id}?expected_edit_revision={revisi}`.
Revisi tersedia pada API soal admin. Penyimpanan konflik tidak menimpa perubahan
admin lain. Tindakan global seperti mengakhiri ujian atau membersihkan sesi tetap
merupakan tindakan langsung dari admin yang berwenang, bukan sistem persetujuan.

## Revisi paket dan penguncian

Soal dan paket tidak diubah saat ujian aktif. GET `/api/admin/packages` dan
`/api/admin/questions` menyertakan `edit_revision` paket berupa token hash konten.
Kirim sebagai `expected_edit_revision` pada body PUT atau query DELETE paket.
Token ini berbeda dari revisi integer soal. Revisi lama mendapat 409, entitas hilang
404 dan nama kosong ditolak. Pemeriksaan peserta yang mengunci paket dan penghapusan
berada dalam transaksi yang sama. Konflik berarti muat ulang dan tinjau perubahan.

## Master key dan pemulihan

Master key disimpan sebagai hash scrypt dengan salt acak, bukan plaintext. Saat upgrade,
nilai plaintext lama dikonversi dengan mempertahankan kata sandi yang sama.
`ADMIN_MASTER_KEY` hanya dipakai ketika belum ada kredensial dalam database. Restart
tidak mengembalikan password ke nilai `.env` dan tidak menimpa perubahan dari dashboard.

Master key baru melalui dashboard harus sepanjang 12–1.024 karakter. Penggantian
memerlukan password lama. Penggantian mencabut semua sesi lama, termasuk sesi admin
lain, dan menerbitkan sesi baru bagi admin yang mengganti. Halaman admin pemrakarsa
dimuat ulang untuk memperoleh token CSRF sesi barunya. Pengawas lain perlu login
kembali dengan master key baru. Permintaan yang sudah mulai diproses sebelum pencabutan
tidak otomatis dibatalkan.

Untuk pemulihan lokal, hentikan server lalu jalankan:

```powershell
.\.venv\Scripts\python.exe scripts/reset_admin_key.py
```

Linux/macOS: `.venv/bin/python scripts/reset_admin_key.py`.
Masukkan key minimal 12 karakter dua kali. Skrip menolak database yang belum ada dan
konfirmasi yang tidak cocok. Semua sesi admin dicabut. Skrip tidak menampilkan key
atau memerlukannya sebagai argumen terminal. Password awal `admin123` tetap tersedia
untuk instalasi tanpa konfigurasi; ganti sebelum ujian.

## Proteksi permintaan dan audit

Semua mutasi HTTP memeriksa Origin/Referer jika dikirim dan menolak Fetch Metadata
`cross-site`. Referer tidak valid tidak lagi lolos melalui penanganan exception.
Mutasi admin juga memerlukan `X-CSRF-Token` yang terikat sesi. Dashboard mengirimkannya
otomatis. Form login memiliki token terikat cookie form; logout memakai POST dengan
token, untuk admin maupun mahasiswa. GET logout tidak mengubah sesi.

Untuk klien API admin, login memakai form dari `/admin/login`, lalu dapatkan token
CSRF melalui `GET /api/admin/session` pada sesi yang sama. Sertakan token tersebut
sebagai header setiap POST/PUT/PATCH/DELETE. Cookie admin memakai HttpOnly, SameSite=Lax,
dan Secure pada HTTPS. Halaman/API admin diberi `Cache-Control: no-store`.

`GET /api/admin/audit` menyediakan audit permintaan mutasi admin: ID sesi, metode,
path tanpa query, status HTTP, IP, dan waktu. Endpoint memerlukan sesi admin dan
menyediakan 100 baris per halaman dengan `before_id`/`next_before_id`. Login berhasil,
logout, penggantian master key, serta mutasi admin tercatat berdasarkan ID sesi.
Master key, token autentikasi, isi form, dan query string tidak disimpan dalam audit.
Audit request terpisah dari transaksi perubahan bisnis dan bukan log antirusak terhadap
orang yang memiliki akses langsung ke SQLite/server. Karena master key bersama,
ID sesi membedakan browser/perangkat, bukan membuktikan identitas personal pengawas.

## Log mahasiswa dan ekspor

Endpoint `/api/student/log-event` memerlukan sesi aktif dan paket yang sah. Sesi,
revisi ujian, dan batas akhir diperiksa kembali dalam transaksi penulisan. Sesi tidak
valid tidak dapat menambahkan baris log anonim. Jenis peristiwa hanya boleh:
`paste_attempt`, `devtools_attempt`, `blur_tab`, `focus_tab`, dan `exit_fullscreen`.
Mahasiswa tidak dapat mengirim `exam_started`, `change_password`, atau jenis aksi admin.

Detail dibatasi 1.000 karakter, karakter kontrol dibersihkan, dan diberi penanda
`Laporan klien:`. Batas 60 peristiwa per mahasiswa per menit menghasilkan HTTP 429
ketika terlampaui. Rate limiter memakai memori terbatas maksimum 10.000 key per proses.
Log klien tetap merupakan laporan browser; tidak membuktikan kecurangan dan bisa
hilang ketika jaringan putus atau permintaan dibatasi. Jumlah fokus/tab bukan bukti
individual yang dapat dipakai tanpa pemeriksaan pengawas.

Permintaan soal dari browser tidak lagi membawa token sesi di URL. Ekspor CSV memberi
awalan apostrof pada teks yang bisa dibaca sebagai formula spreadsheet. Nilai asli
di SQLite dan query pada berkas SQL tidak diubah. Nama berkas ZIP disanitasi agar tidak
mengandung path dari metadata peserta lama/impor.

## Upgrade dan batas

SQLite versi 4 menambah `admin_sessions`, `admin_audit`, dan `questions.edit_revision`.
Migrasi dilakukan otomatis pada startup setelah backup. Cookie admin dari versi token
global lama tidak lagi valid; kedua pengawas harus login ulang setelah upgrade.

Pengujian memakai SQLite/PostgreSQL sementara. Database utama tidak diubah selama
implementasi. Uji kapasitas kelas, TLS/jaringan produksi, rotasi kredensial PostgreSQL,
retensi audit, dan pengelolaan akun bernama belum dicakup. Rate limiter bersifat per
proses, sedangkan sesi dan revisi bersifat bersama melalui SQLite. Jangan menganggap
hasil tes sebagai hard quota memori/disk atau jaminan keamanan seluruh infrastruktur.
