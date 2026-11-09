# Perbaikan audit admin — 8 November 2026

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

## Perubahan

- Nama peserta, kode paket dan URL galeri tidak lagi menjadi kode onclick. Kontrol
  dinamis memakai data attribute dan event delegation; apostrof tetap utuh. Navigasi
  galeri menerima HTTP(S) dengan noopener dan menolak URL executable.
- Transport admin menolak HTTP gagal sebelum data dipakai UI: tidak ada sukses palsu
  atau kelas kosong akibat 403. Penolakan autentikasi mengarahkan ke login; peringatan
  akses dibatasi frekuensinya. Respons GET lama tidak menimpa respons yang lebih baru.
- Perubahan paket ditolak selama ujian aktif. State, keberadaan paket, revisi dan
  keterikatan peserta diperiksa dalam transaksi BEGIN IMMEDIATE bersama penulisan.
  Form lama mendapat 409. Token berupa hash konten paket; tidak perlu migrasi schema.
- Nama kosong ditolak dan entitas hilang menghasilkan 404. Instalasi baru tanpa row
  exam_state tetap dapat mengelola paket dalam persiapan.
- Hash snapshot simulasi mengabaikan reference_validation, sehingga Mulai tidak
  menghapus riwayat latihan. Perubahan soal/paket/dataset menolak snapshot lama.
- Revisi utama dan sesi admin diperiksa ulang sebelum skor atau keputusan worker
  simulasi disimpan, dengan write lock singkat yang tidak ditahan sepanjang evaluasi.
  Konteks berubah menghasilkan 409 tanpa menyimpan nilai; server sibuk mendapat 503.
- Gambar diverifikasi/didekode memakai Pillow. SVG baru ditolak; PNG/JPEG/WEBP/GIF
  didukung. Batasnya 8 MiB per berkas, 32 MiB per batch, 20 berkas, dan 20 juta piksel
  termasuk frame animasi. Request dibatasi sebelum parsing, termasuk stream chunked;
  budget multipart menambahkan 256 KiB di atas budget batch.
- Semua gambar batch divalidasi sebelum penulisan. Error penulisan membatalkan berkas
  baru batch; tabrakan nama tidak menghapus file lama. Response unggahan publik memakai
  CSP sandbox dan nosniff, termasuk untuk membatasi SVG lama. File lama tidak dihapus.

## Validasi

Regresi lengkap lulus **32/32 pemeriksaan**. Pemeriksaan tambahan terakhir lulus
**17 tes backend admin** dan **7 tes controller admin**, termasuk race edit dan
penguncian/penghapusan, instalasi baru, streaming, file valid/rusak dan tabrakan nama.

Browser pada server sementara membuktikan edit paket HTTP 200, revisi lama 409, modal
tertutup setelah sukses, serta nama berapostrof dan teks injeksi diteruskan sebagai
teks dalam konfirmasi. Tidak ada handler inline pada tabel peserta dan penanda injeksi
tidak berjalan. IDE menghasilkan skor 10; setelah Mulai dan reload, skor tetap 10.
Fixture server browser telah dihentikan. Database dan server utama tidak diubah oleh tes.

## Pemakaian

Restart server dan muat ulang halaman admin. Klien API PUT/DELETE paket perlu membaca
`edit_revision` dari GET `/api/admin/packages` atau `/api/admin/questions`, kemudian
mengirim `expected_edit_revision` pada body PUT atau query DELETE. Jika 409, muat ulang
dan tinjau perubahan sebelum mencoba lagi. Token paket berbeda dari revisi integer soal.

SVG perlu diekspor ke format raster sebelum upload. Tidak ada migrasi database, reset
nilai, penghapusan unggahan lama atau restart server utama otomatis. Script audit lama
kini mengarahkan ke tes regresi perbaikannya.
