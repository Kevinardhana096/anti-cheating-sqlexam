# Pemeriksaan dokumentasi — 8 November 2026

## Ruang lingkup

Panduan produk di README, manual instalasi, docs/operations, dokumen arsitektur dan
laporan docs/reports diperiksa terhadap source code. Dokumen vendor dan aturan kerja
agen diinventarisasi, tetapi isinya tidak diubah menjadi instruksi aplikasi.

## Koreksi utama

- Minimum Python menjadi 3.11+, sesuai metadata pillow 13.0.0 yang dipin. Pesan bantuan
  ketiga runner diselaraskan; tidak ada perubahan perilaku runner atau dependensi.
- Setup Windows dibedakan dari macOS/Linux, environment terminal dibedakan dari .env,
  dan bootstrap master key dibedakan dari perubahan/pemulihan key yang sudah tersimpan.
- Pembuatan database fisik sandbox_pribadi dan GRANT manual lama dihapus dari panduan
  aktif. Startup mengurus master, role dan ACL; sandbox merupakan pilihan virtual.
- Mulai, Hentikan Ujian, Hentikan Semua, Bebaskan Sesi, Reset Paket dan Bersihkan Sesi
  dijelaskan menurut efek sebenarnya. Reset dataset bukan restore nilai atau tes koneksi.
- Instruksi rutin menimpa SQLite dan menghapus WAL/SHM diganti dengan backup/restore
  tervalidasi. Snapshot SQLite dan ekspor CSV/ZIP bukan backup seluruh layanan.
- Klaim kapasitas 80/500 peserta, bebas contention dan recovery 100% instan dibuang dari
  dokumen arsitektur/SOP aktif. Bukti loopback 24 peserta diberi batas konteksnya.
- AP isolation tidak lagi diwajibkan universal, HTTP tidak dianggap terenkripsi, dan
  NAT bersama tidak dianggap login ganda. Firewall tidak dianjurkan dimatikan rutin.
- Kebijakan fungsi, review penilaian, data JSON/array, index, revisi paket, batas gambar,
  snapshot admin dan fencing penyimpanan diselaraskan dengan perbaikan terakhir.
- Polling dibedakan: monitoring admin 10 detik, panel lobby admin 20 detik; lobby peserta
  memeriksa status 3 detik/daftar 6 detik/heartbeat 15 detik; IDE heartbeat 12 detik.
- Laporan historis diberi penanda dan rujukan ke panduan aktif atau laporan perbaikan.
  Bukti hasil pengujian lama tidak ditulis ulang menjadi klaim tes terbaru.
- Tautan lokal, anchor dan path script dibuat portabel. Indeks dokumentasi ditambahkan
  untuk menunjukkan panduan aktif serta urutan audit dan perbaikan.

## Verifikasi

`scripts/check_documentation.py` memeriksa keberadaan tautan/anchor lokal dan script
yang dirujuk. Jalankan ulang setelah menambah dokumen. Pemeriksaan CLI --help pada
setup SQLite, backup, review grading dan reset sesi cocok dengan opsi yang didokumentasikan.
Metadata Python paket terpasang dipakai untuk memeriksa minimum versi, bukan perkiraan.
Hasil pemeriksaan: 32 dokumen produk, 118 tautan lokal/anchor dan 21 rujukan script,
dengan nol kesalahan. Inventaris juga mencatat empat dokumen vendor dan dua berkas
aturan agen yang tidak diubah.
Diff whitespace diperiksa. Regresi lengkap aplikasi tidak diulang karena hanya
dokumentasi, alat pengecekan dokumentasi, dan teks pesan versi runner yang berubah.

Tautan internet tidak diuji ketersediaannya. Instalasi baru Windows/macOS tidak dijalankan
ulang, tidak ada klaim kapasitas baru, dan database/server utama tidak diubah.
Keterbatasan fitur yang masih ada tetap dicantumkan dalam [indeks aktif](../README.md).
