# Fase 3: isolasi PostgreSQL dan pembatasan SQL

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Tanggal: 7 November 2026 (Asia/Makassar).

## Hasil implementasi

Eksekusi pada dataset master dan sandbox pribadi sekarang memakai identitas serta
siklus koneksi yang berbeda. Master memakai login SELECT-only dan transaksi read-only.
Sandbox memakai LOGIN PostgreSQL tersendiri per NIM dengan privilege pada schema sendiri.
Role pribadi tidak menjadi anggota role master/admin. Fallback koneksi mahasiswa ke
admin dihapus.

Nama schema dan role menggunakan seluruh SHA-256 NIM yang dienkode base32. Nama cukup
pendek untuk identifier PostgreSQL tanpa menghapus titik/tanda hubung atau mengandalkan
pemotongan identifier. Kredensial role pribadi memakai HMAC dengan secret acak yang
disimpan di SQLite dan tidak dikirim ke browser.

PUBLIC dan role bersama kehilangan akses ke schema pribadi, CREATE/TEMP database,
serta hak tulis master. Kepemilikan lama oleh role bersama juga dipindahkan agar REVOKE
tidak meninggalkan hak implisit pemilik. Role pribadi hanya memperoleh CONNECT pada
database kerja; database master lain menolak koneksinya.

## Komponen kode

| File | Tanggung jawab |
|---|---|
| `sandbox_roles.py` | Identitas, kredensial, hardening role/ACL, dan provisioning/migrasi workspace |
| `sql_policy.py` | Scanner dan AST PostgreSQL, daftar perintah/fungsi/tipe, serta validasi seluruh skrip |
| `query_runner.py` | Transaksi, deadline, koneksi, server-side cursor, dan batas keluaran |
| `database.py` | Integrasi inisialisasi, query runner, cleanup, dan reset peserta |

Parser menggunakan [pglast 8.7](https://pypi.org/project/pglast/8.7/), dipasang dan
dipin pada `requirements.txt`. [Dokumentasi parser](https://pglast.readthedocs.io/en/latest/index.html)
menjelaskan representasi AST yang dipakai. Tidak ada akses internet saat eksekusi ujian.

## Eksekusi dan koneksi

Seluruh skrip divalidasi sebelum eksekusi dan dijalankan sebagai satu transaksi sandbox.
Kesalahan statement akhir membatalkan perubahan awal. Database virtual tetap emulasi,
tanpa CREATE/DROP database fisik; label SQLite diperbarui setelah commit PostgreSQL.

Koneksi sandbox dibuat langsung sebagai role pribadi dan ditutup setelah permintaan.
Koneksi master dibersihkan dengan rollback dan DISCARD ALL sebelum/sesudah pemakaian.
Watchdog dihentikan sebelum koneksi kembali ke pool sehingga pembatalan lama tidak
diteruskan ke permintaan berikutnya.

Batas yang ditetapkan: 20 statement, anggaran SQL 5 detik lintas statement, lock timeout
3 detik, 500 baris preview, 64 kolom, sel 4.000 karakter, anggaran data baris JSON 256 KiB,
dan 10.000 baris terpengaruh per permintaan. Role juga memiliki batas work mem/temp file
dan koneksi. SELECT memakai server-side cursor agar seluruh hasil tidak dimuat ke Python.

Provisioning dan cleanup memakai advisory lock. Perubahan ACL database diserialkan
untuk menghindari konflik katalog ketika beberapa role baru dibuat serentak.

## Workspace lama dan pembersihan

Workspace dengan satu pemilik SQLite yang jelas dapat diganti namanya dan dialihkan
kepemilikannya tanpa menghapus isi. Pemilik ambigu, fungsi/operator/tipe khusus,
trigger/view/foreign table, dan relasi tertentu lintas schema memerlukan pemeriksaan
pengawas. Upgrade yang gagal di-rollback; akses bersama tetap dicabut oleh hardening.

Cleanup menghapus schema dan role dalam satu transaksi PostgreSQL. Reset individual
baru menghapus mahasiswa/jawaban SQLite setelah cleanup PostgreSQL berhasil. Jika role
memiliki dependency lain, reset gagal dan data SQLite dipertahankan. Ini bukan transaksi
terdistribusi: kegagalan SQLite setelah commit cleanup PostgreSQL tetap memerlukan recovery.

Keterangan CLI `--all` diperbaiki agar menyatakan perilaku sebenarnya, yaitu pembersihan
SQLite. Untuk membersihkan workspace yang terdaftar, gunakan reset per NIM sebelum
menghapus daftar peserta. Sandbox lama ambigu tidak dihapus secara otomatis.

`setup_postgres.sql` hanya menyiapkan database master; hardening role dan ACL dilakukan
aplikasi. Dataset dan grant dasar tidak lagi mengasumsikan nama admin selalu `postgres`.

## Verifikasi

- Sembilan tes parser memeriksa komentar, kutip, Unicode, operasi terlarang, CTE, fungsi,
  schema eksplisit, serta batas statement dan emulasi database virtual.
- Dua puluh delapan tes PostgreSQL memeriksa privilege dengan login mahasiswa langsung,
  termasuk akses lintas schema dan perubahan search_path tanpa melewati filter aplikasi.
- Tes mencakup RESET/SET ROLE, atribut role, akses database lain, master write privilege,
  rollback skrip, timeout lintas statement, kapasitas koneksi, pembersihan setting/lock,
  batas keluaran, migrasi/serial lama, cleanup dan kegagalan reset, serta eksekusi serentak.
- Temuan benturan nama schema pada `test_known_risks.py` menjadi tes normal yang lulus.
  Tiga expected failure fase 4–5 tetap dipertahankan.

Regresi akhir dijalankan pada salinan sumber tanpa `.env`, `scratch/`, SQLite lama,
atau database ujian yang sudah ada. Interpreter/dependensi berasal dari virtual
environment proyek; PostgreSQL memakai cluster sementara terpisah.

| Pemeriksaan | Hasil |
|---|---|
| Runner lengkap | 15/15 pemeriksaan lulus, exit code 0 |
| Migrasi SQLite | 8 tes lulus |
| Kendali ujian/sesi | 34 tes lulus |
| Parser SQL | 9 tes lulus |
| Submission | 29 tes lulus |
| Rekap/ZIP | 8 tes lulus |
| Retensi skor | 7 tes lulus |
| Sesi/mahasiswa terlambat | 7 tes lulus |
| Operasional | 7 tes lulus |
| Privilege dan sandbox | 28 tes lulus |
| Regresi temuan | 3 tes normal lulus, 3 expected failure |

Total **140 tes normal lulus dan 3 expected failure**. Sintaks Python/JavaScript,
`pip check`, dan `git diff --check` lulus. Pesan kegagalan cleanup dalam suite keamanan
berasal dari dependency yang sengaja dibuat untuk membuktikan rollback, bukan kegagalan tes.

Hash SHA-256 seluruh file database utama `*.db` dan `.env` tetap sama sebelum/sesudah
regresi akhir. Cluster sementara dihentikan dan dibersihkan. Tidak ada hardening atau
migrasi yang dijalankan pada PostgreSQL utama dalam pelaksanaan pengujian ini; perubahan
tersebut diterapkan ketika aplikasi dijalankan kembali menggunakan kode baru.

## Batas yang tetap berlaku

Pembatasan ini tidak memberikan hard quota untuk seluruh memori atau disk PostgreSQL.
Nilai besar masih perlu dihitung di server, pemotongan sel dilakukan setelah fetch,
dan biaya provisioning/commit/cleanup dapat menambah waktu respons. Uji kapasitas host
dan mitigasi penyimpanan jangka panjang tetap mengikuti fase operasional.

Autograder masih menggunakan hasil preview untuk SELECT dan normalisasi lama. Ketepatan
hasil terpotong serta isolasi workspace evaluasi adalah pekerjaan fase 4. Keamanan admin,
CSRF, dan kualitas log tetap mengikuti fase berikutnya. Pengujian saat ini dilakukan
di Windows, Python 3.14.6, PostgreSQL 18.6; platform/versi lain belum diverifikasi.

Panduan pemasangan, privilege, upgrade, dan batas SQL:
[SANDBOX_SECURITY.md](../operations/SANDBOX_SECURITY.md).
