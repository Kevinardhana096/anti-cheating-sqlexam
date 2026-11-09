# IDE pengujian admin

Buka dashboard admin, lalu pilih **IDE Pengujian**. Halaman tersedia di `/admin/practice` setelah login admin.

## Pemakaian

1. Masuk mode fullscreen seperti peserta.
2. Pilih paket aktif dan konfirmasikan pilihan.
3. Pilih soal, tulis SQL, lalu gunakan **Format SQL**, **Run Query**, atau **Submit Answer**.
4. Lihat tabel hasil, pesan kesalahan, status benar/salah atau menunggu penilaian, serta skor terbaik.
5. Gunakan **Ganti paket** untuk membuka pilihan paket kembali. Riwayat latihan dan sandbox tidak dihapus oleh tombol ini.
6. Gunakan **Kembali ke admin** untuk kembali ke dashboard.

## Kesamaan dengan mahasiswa

Admin menggunakan `student.html` dan `student.js` yang sama, bukan salinan IDE. Editor CodeMirror, formatter lokal, draft, shortcut, pembatasan paste, fullscreen, lightbox gambar, tabel hasil dan status submit memakai implementasi yang sama. Permintaan latihan diteruskan ke fungsi endpoint mahasiswa yang sama, termasuk pemeriksaan panjang query, database yang diizinkan, batas frekuensi, executor sandbox, evaluator, riwayat percobaan dan retensi skor terbaik. Antrean latihan memakai mesin penilaian ulang yang sama.

Paket aktif dan soal disalin sebagai snapshot ketika halaman pengujian dibuka. Admin tidak memperoleh akses eksekusi PostgreSQL yang lebih tinggi lewat IDE ini. SELECT master memakai dataset master yang sama. DDL/DML memakai identitas sandbox khusus simulasi sehingga tabel mahasiswa tidak tersentuh. Sandbox admin tidak otomatis berisi tabel yang sebelumnya dibuat mahasiswa: untuk reproduksi kasus, jalankan prasyarat SQL yang sama terlebih dahulu.

## Perbedaan akses dan penyimpanan

- Simulasi dapat digunakan sebelum, selama, dan sesudah ujian tanpa mengubah status ujian sebenarnya.
- Header menandai mode simulasi dan menyediakan navigasi admin. Kontrol pengerjaan soal tetap sama.
- Nilai, riwayat, log pengawasan dan antrean simulasi disimpan dalam SQLite terpisah di direktori `admin_practice` di samping database utama. Data tersebut tidak masuk daftar mahasiswa, ekspor nilai atau leaderboard.
- Dua sesi admin mempunyai identitas, sandbox dan database latihan yang berbeda. Logout atau pencabutan sesi admin menolak akses berikutnya ke simulasi tersebut.
- Saat soal atau konfigurasi paket berubah, API menolak snapshot lama; buka ulang IDE. Snapshot baru mengosongkan riwayat latihan sebelumnya; draft lokal dan tabel sandbox dapat tetap ada. Perubahan metadata validasi saat Mulai tidak mereset riwayat.
- Penggantian dataset mengharuskan halaman dibuka ulang. Selama maintenance dataset, API simulasi menolak eksekusi.
- Konteks utama dan sesi admin diperiksa ulang sebelum commit skor/keputusan worker. Perubahan selama evaluasi membatalkan penyimpanan, bukan menyimpan nilai dari konteks lama.
- Penilaian otomatis tertunda diproses worker latihan selama sesi admin masih aktif. Soal manual tetap menampilkan menunggu penilaian, sama seperti pada mahasiswa; halaman ini tidak menambahkan form keputusan manual.

Karena akses dan sandbox memang terpisah, simulasi ini memeriksa perilaku pengerjaan soal. Untuk memeriksa penguncian perangkat mahasiswa, transisi lobby, atau penghentian sesi peserta, gunakan sesi mahasiswa dalam gladi bersih.

Simulasi memakai proses server, pool PostgreSQL dan kapasitas evaluator yang sama dengan ujian. Pengujian query berat ketika ujian berlangsung tetap menggunakan kapasitas server; lakukan pengujian massal sebelum peserta mulai.
