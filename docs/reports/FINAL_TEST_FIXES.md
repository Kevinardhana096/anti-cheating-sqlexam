# Perbaikan evaluasi final test — 8 November 2026

> Catatan hasil pada versi/putaran tertentu. Untuk prosedur terkini gunakan [panduan aktif](../README.md); angka tes dan benchmark di bawah bukan hasil pengukuran ulang.

Catatan ini melanjutkan analisis di `FINAL_TEST_MINUTES_ANALYSIS.md`. Perubahan mempertahankan pekerjaan fase 1–7 yang sudah ada.

## Perubahan

- **Format SQL:** fungsi yang sebelumnya tidak tersedia kini memakai SQL Formatter 15.9.0 lokal, dengan dialek PostgreSQL. Undo tetap bekerja. Literal, komentar dan angka tidak diubah isinya; pemformatan seleksi ditolak jika dapat mengubah makna query. SQL yang tidak dapat diformat tetap utuh. Lisensi dan asal paket ada di `static/vendor/sql-formatter/README.md`.
- **Nomor soal antar paket:** perpindahan paket menyarankan nomor berikutnya dan pengembalian ke paket asal memulihkan nomor awal. Backend memeriksa konflik dalam transaksi; benturan menghasilkan HTTP 409 dengan pesan jelas, tanpa mengubah soal atau ID. Nomor harus bilangan bulat positif. Soal yang sudah dihapus menghasilkan 404.
- **Status submit:** jawaban salah yang berhasil diterima menampilkan “Tersimpan • Salah”. Hasil terbaru dipisahkan dari skor terbaik; salah setelah benar tetap ditampilkan salah, sementara skor terbaik dipertahankan. Pending tidak ditampilkan sebagai nilai nol. Detail petunjuk penilaian tidak ditampilkan pada banner submit. Draft disimpan sebelum pengiriman; respons yang hilang diberi status belum dapat dipastikan.
- **Popup koneksi dan fokus:** pemeriksaan heartbeat memakai satu permintaan bersama, batas waktu konsisten, dan validasi sesi eksplisit. Gangguan server atau pembatasan permintaan tidak dianggap sebagai pencabutan sesi. Peringatan fokus dideduplikasi untuk satu episode perpindahan. Pencatatan pengawasan tetap aktif.
- **Waiting room:** daftar kartu dinormalisasi berdasarkan NIM, termasuk pembersihan kartu duplikat. Dua peserta dengan NIM berbeda pada IP yang sama tetap sah.
- **Expected output:** lightbox menambahkan tombol “Ukuran asli” dengan area gulir untuk gambar panjang. Gambar sumber yang sudah terpotong tetap perlu diganti pengawas.
- **Setup Windows:** `setup.bat` menyiapkan virtual environment, dependensi, dan SQLite melalui `scripts/setup_sqlite.py`. Setup berulang mempertahankan skor; migrasi versi lama membuat snapshot SQLite terlebih dahulu. Snapshot ini bukan pengganti backup lengkap SQLite, PostgreSQL dan unggahan. Hentikan server sebelum setup/upgrade. Script tidak menginisialisasi PostgreSQL.

## Pemeriksaan browser

Pemeriksaan dilakukan pada server dan database sementara, melalui alur login sebenarnya:

- Konflik nomor antar paket menghasilkan 409, pesan terlihat dan form tetap terbuka. Perpindahan valid mempertahankan ID lalu berhasil dikembalikan ke paket asal.
- Format SQL mempertahankan literal `'select Foo'` dan angka `1.20`; Undo mengembalikan teks semula.
- Submit salah menerima HTTP 200 dan ditampilkan tersimpan. Urutan benar lalu salah tetap menampilkan hasil terbaru salah dengan skor terbaik 10/10.
- Submit soal manual tampil “Tersimpan • Menunggu penilaian” tanpa nilai nol.
- Gambar uji 1200×1800 tampil pada ukuran aslinya dan dapat digulir dalam lightbox.

Pengujian otomatis tambahan mencakup pending, kehilangan respons, gangguan heartbeat, deduplikasi fokus/lobby, konflik pembuatan bersamaan, dan setup SQLite. Regresi dari salinan sumber bersih lulus **26/26 pemeriksaan**, termasuk **266 tes Python dan 15 tes perilaku JavaScript**. Pemeriksaan sintaks, konsistensi dependensi, dan whitespace juga lulus. Hash database utama dan `.env` sebelum/sesudah identik. Server browser dan database uji sementara sudah dihentikan dan dibersihkan.

## Batas pekerjaan

Admin ganda dengan master key sama dan sesi independen, serta pembandingan numeric/desimal, sudah dikerjakan pada fase sebelumnya dan tetap masuk regresi. Cache hasil kunci jawaban lintas submit **belum ditambahkan**; ini optimasi terpisah yang memerlukan invalidasi terhadap revisi soal, kebijakan penilaian, setup dan dataset agar nilai tidak memakai referensi usang.

Empat paket dengan dua paket aktif per sesi dapat diatur melalui aktivasi paket yang sudah ada; penjadwalan sesi otomatis belum ditambahkan. Isi feedback baru memerlukan materi dari pengawas. Persiapan soal/gambar, pengaturan laptop server agar tidak tidur, rapat lanjutan, dan uji pada laptop peserta tetap merupakan tindakan operasional. Penyebab seluruh popup merah pada perangkat lapangan belum dapat dipastikan tanpa log perangkat tersebut.
