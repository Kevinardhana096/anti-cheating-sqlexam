# Audit admin — 8 November 2026

> Catatan historis sebelum/selama perbaikan. Status terbaru: [laporan lanjutan](ADMIN_BEHAVIOR_FIXES.md) dan [panduan aktif](../README.md). Temuan serta jumlah tes di bawah berlaku pada putaran saat laporan dibuat.

## Hasil dan ruang lingkup

Audit membaca backend, database, controller dashboard dan adapter IDE admin. Sebanyak
11 tes reproduksi backend dijalankan pada SQLite dan direktori unggahan sementara,
ditambah tujuh probe controller JavaScript dengan DOM/transport mock. Semua berhasil
mereproduksi perilaku bermasalah yang ditargetkan. Ini bukan kelulusan keamanan:
tes audit sengaja mengharapkan perilaku cacat yang ada agar bukti dapat diulang.

Sebagai kontrol, 26 tes keamanan admin, 12 tes isolasi IDE admin dan 16 tes perilaku
JavaScript yang sudah ada juga lulus. Tidak ada perubahan kode aplikasi pada pekerjaan
analisis ini, dan tidak ada tindakan destruktif terhadap server atau database utama.
Regresi lengkap tidak diulang. Probe injeksi hanya mengubah penanda pada objek window
terisolasi, tanpa melakukan permintaan admin atau mengakses kredensial.

## Temuan terkonfirmasi

| Prioritas | Masalah | Bukti dan dampak |
| --- | --- | --- |
| P1 | Nama mahasiswa masuk ke kode handler tombol | loadDashboardData menyisipkan escapeHtml(name) di onclick. Setelah decoding entity HTML, nama berapostrof menghasilkan SyntaxError; nama yang disusun khusus menjalankan penanda JavaScript. HTML escaping tidak memisahkan data dari konteks kode JavaScript. Ini dapat menjadi jalur aksi dalam konteks admin ketika pengawas menekan tombol terkait. Tidak diperlukan pencurian cookie untuk risiko ini. |
| P1 | Penguncian konten ujian dilewati melalui paket | PUT paket dapat mengaktifkan soal yang belum tervalidasi ketika ujian aktif. DELETE paket dengan delete_questions=true menghapus soal saat API penghapusan soal langsung seharusnya menolak. |
| P1 | Penghapusan paket tidak atomik dengan penguncian peserta | Reproduksi menghentikan DELETE tepat sebelum penulisan, membiarkan peserta mengunci paket, lalu melanjutkan DELETE. API tetap 200, paket hilang dan selected_category peserta masih menunjuk kode tersebut. |
| P1 | Revisi dataset simulasi hanya diperiksa sebelum evaluasi | Revisi dataset utama diubah di tengah evaluator mock. Hasil simulasi masih tersimpan sebagai graded, sementara permintaan berikutnya baru ditolak 409. Belum ada pemeriksaan ulang revision utama pada commit skor simulasi. |
| P2 | Edit paket dua admin dapat menimpa perubahan | Admin A mengganti nama. Form lama B mengirim nama lama dan deskripsi baru; API menerima keduanya, menghilangkan perubahan A. CAS/revisi edit soal belum diterapkan pada paket. |
| P2 | Aksi gagal ditampilkan sukses | HTTP 403 pada hapus semua soal, bersihkan log dan bersihkan sesi tetap menghasilkan toast sukses. Handler tidak memeriksa res.ok dan memakai pesan fallback sukses ketika respons hanya memuat detail. |
| P2 | Sesi admin ditolak terlihat seperti kelas kosong | HTTP 403 pada daftar mahasiswa merender jumlah 0 dan pesan belum ada mahasiswa, bukannya status autentikasi bermasalah. Ini dapat menyesatkan pengawas; backend tetap menolak akses. |
| P2 | Respons polling lama menimpa yang baru | Probe menyelesaikan permintaan baru dahulu, lalu permintaan lama. Tabel akhirnya menampilkan data lama. Tidak ada sequence guard atau pembatalan request sebelumnya. |
| P2 | Mulai ujian dapat mengosongkan riwayat simulasi tanpa edit soal | Validasi Mulai memperbarui reference_validation. Hash snapshot mencakup seluruh baris soal, sehingga membuka ulang simulasi menghapus pengguna latihan dan riwayat terkait walaupun isi soal tidak diedit. |
| P2 | Snapshot kunci simulasi dapat tertinggal | Setelah kunci utama diedit, API simulasi tetap 200 dengan snapshot lama. Dokumentasi mengharuskan buka ulang halaman, tetapi API tidak memberi penanda bahwa soal telah berubah; ini mengurangi ketepatan reproduksi masalah mahasiswa. |
| P2 | Validasi unggahan hanya berdasarkan ekstensi | Berkas bukan gambar bernama .png dan SVG dengan atribut aktif diterima lalu ditulis. Tes hanya membuktikan penerimaan/penyimpanan, bukan eksekusi skrip SVG dari komponen img. Dampak SVG bergantung cara berkas diakses dan disajikan. |
| P2 | Unggahan batch gagal meninggalkan berkas parsial | Berkas pertama sudah ditulis ketika berkas berikutnya ditolak. API 400 tetapi satu berkas tetap berada di direktori unggahan. |
| P2 | Entitas hilang dan nama kosong dapat mendapat sukses | PUT kode paket tidak ada dan reset kategori NIM tidak ada memberi 200 tanpa perubahan. Update paket menerima nama whitespace dan menyimpan string kosong. |

Temuan statik tambahan: endpoint gambar memanggil read() tanpa batas aplikasi untuk
ukuran, jumlah gambar, dimensi atau total byte. Audit tidak melakukan stress test atau
mencoba membuat server kehabisan memori/disk. Ini risiko kapasitas, bukan insiden OOM
yang sudah direproduksi.

## Prioritas perbaikan

1. Hilangkan handler inline untuk data nama/kode. Gunakan event listener/delegation dan
   data attribute yang dibaca sebagai data; jangan menyelesaikannya hanya dengan mengganti
   entity HTML atau menghapus apostrof dari nama.
2. Terapkan penjagaan state dan revision paket dalam transaksi yang sama dengan penulisan.
   Penghapusan harus mengambil write lock sebelum memeriksa keterikatan peserta. Aktivasi
   paket saat aktif perlu ditolak atau melalui validasi yang setara dengan mulai ujian.
3. Lakukan fencing revisi dataset/soal utama sampai commit simulasi. Snapshot sebaiknya
   memakai hash semantik, tidak mencakup metadata validasi yang tidak mengubah soal.
4. Terapkan penanganan HTTP gagal/autentikasi secara konsisten, dan lindungi polling dari
   respons yang datang tidak berurutan. Jangan menampilkan sukses atau kelas kosong ketika
   status sebenarnya belum diketahui.
5. Validasi isi dan batas unggahan, tangani SVG secara eksplisit, serta rollback berkas
   batch jika salah satu item gagal. Tambahkan pemeriksaan rowcount/404 dan validasi nama.

## Reproduksi

- `.venv/Scripts/python.exe scripts/audit_admin_edge_cases.py`
- `node scripts/audit_admin_behaviors.cjs`
- Hasil controller: `ADMIN_UI_AUDIT_RESULTS.json`.

Script audit terpisah dari runner regresi karena perilaku yang sekarang dibuktikan
adalah bug. Setelah perbaikan, ekspektasi harus dibalik dan dimasukkan ke suite regresi.
Temuan pada laporan ini **belum diperbaiki**.
