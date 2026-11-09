# Analisis notulensi evaluasi final test

> Catatan historis sebelum/selama perbaikan. Status terbaru: [laporan lanjutan](FINAL_TEST_FIXES.md) dan [panduan aktif](../README.md). Temuan serta jumlah tes di bawah berlaku pada putaran saat laporan dibuat.

Tanggal pemeriksaan: 8 November 2026. Basis: working tree setelah implementasi fase 1–7.
Versi aplikasi yang dipakai ketika notulensi dibuat belum diketahui. Status kode saat
ini tidak membuktikan build yang sama sudah dijalankan di laptop pengawas/mahasiswa.
Audit ini tidak mengubah kode aplikasi atau database utama.

## Pemetaan seluruh notulensi

| No. | Catatan | Jenis dan status saat ini |
|---|---|---|
| 1 | Admin bersamaan bertabrakan | Bug lama autentikasi; token global sudah diganti sesi independen pada fase 5. Perlu memastikan server final test memakai build baru. |
| 2 | Setup SQLite score melalui setup.bat | Permintaan kemudahan instalasi. Startup sudah membuat/migrasikan tabel dan kolom nilai; launcher setup khusus belum ada. |
| 3 | Hint submit cukup benar/salah | Permintaan kebijakan feedback/UX, belum dipenuhi sepenuhnya; pesan masih membedakan kolom, urutan, data, dan error. |
| 4 | Pencocokan decimal/numeric | Masalah ketepatan yang sudah ditangani di pembanding fase 4; angka native/presisi/toleransi eksplisit diuji. Definisi pembulatan soal tetap perlu ditetapkan. |
| 5 | Kunci dijalankan lebih dahulu lalu output dipakai ulang | Permintaan optimasi yang belum diimplementasikan. Acuan masih dijalankan per evaluasi; validasi sebelum ujian bukan cache output. |
| 6 | Beri tahu tersubmit walaupun salah | Kekurangan UX terkonfirmasi: jawaban salah disimpan, tetapi toast menekankan ketidaksesuaian dan meminta mencoba lagi. Pesan harus memisahkan penyimpanan, hasil percobaan, dan skor terbaik. |
| 7 | Dua waiting room dalam satu IP | Gejala ambigu. Dua peserta berbeda di IP/NAT sama adalah perilaku sah. Belum terbukti ada duplikasi satu peserta/dua room logis. |
| 8 | Asisten memasukkan soal lebih awal | Prosedur persiapan. Penting karena mulai ujian memvalidasi acuan dan perubahan soal ditolak ketika aktif. |
| 9 | Expected output jelas/tidak terpotong | QA aset dan tampilan. Ada contain/lightbox, upload tidak melakukan crop; keterbacaan gambar asli dan ukuran viewport belum dibuktikan. |
| 10 | Popup merah di sebagian laptop | Laporan insiden yang belum memiliki teks/status/waktu/browser. Beberapa sumber merah sah maupun kegagalan teknis ada dalam kode; diagnosis tunggal belum dapat ditetapkan. |
| 11 | Format SQL tidak bekerja | Bug terkonfirmasi: handler memanggil formatQuery yang tidak didefinisikan. |
| 12 | Laptop server terus menyala | Prosedur infrastruktur: layar mati harus dibedakan dari sleep/hibernate/shutdown dan kestabilan jaringan. |
| 13 | ID/nomor soal saat pindah paket | Bug penomoran saat edit terkonfirmasi, ditambah error UNIQUE yang belum dipetakan ke respons ramah. ID global tetap saat edit justru benar. |
| 14 | Empat paket, tiap sesi dua | Konfigurasi/kebutuhan pengelolaan sesi. Empat paket dapat disimpan dan dua diaktifkan manual; belum ada entitas sesi/jadwal paket yang lengkap. |
| 15 | Tambah isi feedback | Spesifikasi belum jelas: feedback mahasiswa, diagnostik pengawas, atau form evaluasi. Field feedback penilaian dan alasan manual sudah ada. |
| 16 | Rapat lagi | Tindak lanjut koordinasi, bukan bug. |
| 17 | Testing web | Kebutuhan QA end-to-end. Regresi backend/sintaks tidak menggantikan pengujian tombol, laptop, browser, dan alur kelas. |

## Temuan teknis terkonfirmasi

### Format SQL

`static/js/student.js:91` mendaftarkan `formatQuery` pada tombol, tetapi pencarian
seluruh sumber tidak menemukan definisi atau penyedia fungsi global itu. Reproduksi
callback DOMContentLoaded dengan dependency awal distub menghasilkan:

```text
ReferenceError: formatQuery is not defined
```

Error terjadi pada bagian akhir callback. Run/Submit dan sejumlah inisialisasi sudah
dijalankan sebelum baris tersebut; tidak tepat menyimpulkan seluruh IDE selalu gagal.
Tombol Format tidak memiliki handler yang berfungsi. `node --check` tetap dapat lulus
karena referensi global yang tidak didefinisikan merupakan error runtime, bukan syntax.

Perbaikan yang diperlukan: formatter PostgreSQL yang tersedia lokal, handler terdefinisi,
dukungan selection/full query, pelestarian string/comment, dan tes klik di browser.
Jangan memakai penggantian regex sederhana yang dapat mengubah literal SQL.

### Pindah paket saat edit dan benturan nomor

`updateNextQuestionNumber()` hanya bekerja ketika `modal-q-id` kosong. Saat edit,
field itu berisi ID, sehingga mengganti A ke B tidak menghitung nomor berikutnya.
Reproduksi fungsi JavaScript:

```text
Paket A: maksimum 9; paket B: maksimum 3
Edit A → B: nomor tetap 9
Tambah baru B: nomor menjadi 4
```

Nomor 9 tidak otomatis salah jika belum dipakai B; masalahnya perilaku pindah paket
tidak memberi saran/validasi yang jelas. Jika nomor itu sudah ada di B, constraint
`UNIQUE(category, question_number)` menolak operasi. Reproduksi pada SQLite sementara:

```text
IntegrityError: UNIQUE constraint failed: questions.category, questions.question_number
```

Transaksi menjaga soal asal tetap utuh. Namun jalur `api_admin_save_question` tidak
menerjemahkan IntegrityError ini menjadi error validasi; pada server dapat menjadi 500.
Frontend save juga membaca `data.message` tanpa fallback `data.detail`, sehingga
sejumlah error 400/409 yang sebenarnya jelas hanya tampil sebagai “Gagal menyimpan soal”.

Perbaikan: pertahankan ID global, bedakan nomor tampilan per paket, tawarkan nomor
valid ketika paket berubah, tangani benturan secara atomik dan ramah (409/422), serta
tampilkan detail konflik pada frontend. Kontrol edit_revision untuk dua admin tetap perlu.

### Status tersimpan versus hasil jawaban

`database.save_submission()` menyimpan percobaan salah maupun pending, selama submit
lolos pemeriksaan sesi/soal/cutoff. Salah tidak sama dengan gagal menyimpan. Akan tetapi
toast frontend untuk jawaban salah berbunyi “belum sesuai”, tanpa afirmasi tersimpan.
Banner meminta submit kembali, sehingga pengguna dapat mengira jawaban belum masuk.

Pisahkan tiga hal: penerimaan/penyimpanan, hasil percobaan terbaru, dan skor terbaik.
Contoh pesan yang memenuhi poin 3 dan 6:

- “Jawaban tersimpan. Hasil: benar.”
- “Jawaban tersimpan. Hasil: salah.”
- “Jawaban tersimpan. Menunggu penilaian.”
- “Jawaban belum tersimpan. Sesi berakhir/koneksi gagal.” hanya jika diketahui demikian.

Jika koneksi putus setelah commit, klien belum tentu mengetahui apakah tersimpan.
Status seperti itu perlu rekonsiliasi melalui riwayat, bukan klaim pasti gagal.
Nilai terbaik yang dipertahankan juga harus diberi label terpisah dari verdict terbaru.

## Hal yang memerlukan kebijakan atau bukti tambahan

### Numeric dan cache kunci

Pembanding sekarang memakai native number/Decimal, keluarga tipe numerik, presisi
asli, multiset duplikat, serta toleransi absolut/relatif yang eksplisit. Sembilan tes
`test_grading_results.py` dijalankan ulang dan lulus. `1` dan `1.00` dapat ekuivalen
sebagai angka; teks kode "001" tidak disamakan dengan angka/teks "1".
DDL tetap memeriksa presisi/skala struktur, berbeda dari nilai hasil SELECT.

Sebelum menambah pembulatan, tentukan apakah soal menilai nilai matematis, scale kolom,
atau tampilan jumlah desimal. Ini tiga kebijakan berbeda.

Cache kunci cocok untuk SELECT master yang deterministik, dengan hasil lengkap bertipe,
bukan screenshot/preview 500 baris. Key minimal mencakup revisi soal/policy dan dataset;
cache harus dibatalkan pada perubahan acuan, policy, setup, atau dataset. Hasil DDL/DML
dan sandbox tidak boleh digunakan ulang tanpa identitas baseline yang tepat. SQL waktu
atau identitas sesi memerlukan kebijakan khusus. Validasi kunci sebelum ujian yang
sekarang tersedia belum menghilangkan eksekusi ulang acuan saat submit.

### Lobby dan popup

Waiting room merupakan daftar global peserta; query backend memakai baris user/NIM
dan heartbeat sekitar 20 detik, sedangkan UI memakai `dataset.nim`, bukan IP sebagai
identitas kartu. ALLOW_SHARED_IP=true memang mengizinkan beberapa peserta satu IP.

Untuk membuktikan bug poin 7, bedakan: dua NIM satu IP, satu NIM dua kartu, dua sesi
browser satu pemilik, atau peserta ghost sesaat sesudah browser ditutup. Catat NIM,
waktu, token yang disamarkan, respons participants, dan jejak heartbeat. Jangan
memperbaikinya dengan aturan “satu IP satu peserta” karena merusak kelas NAT.

Popup merah dapat berasal dari submit salah, offline/timeout heartbeat, tab berpindah,
keluar fullscreen, atau shortcut/paste yang ditolak. Pemeriksaan koneksi manual memiliki
timeout 4 detik dan pesan generik; gangguan autentikasi perlu dibedakan dari jaringan.
`visibilitychange` dan `window.blur` sama-sama mencatat blur_tab, sehingga satu interaksi
dapat menghasilkan dua log. Ini kandidat inflasi hitungan, bukan bukti penyebab semua popup.
Log klien tidak boleh diperlakukan sebagai bukti kecurangan otomatis.

Poin 10 membutuhkan teks persis popup, browser/OS/resolusi, waktu, status HTTP, dan
error console/network. Tidak ada cukup bukti untuk menyebutnya masalah laptop atau
masalah server saja. Error Format di console juga tidak otomatis berarti popup merah.

### Gambar, sesi, dan feedback

Gambar memakai `object-fit: contain` dan lightbox dengan batas viewport. Screenshot
panjang dapat utuh tetapi sangat kecil; gambar yang sudah terpotong saat diambil tidak
dapat dipulihkan oleh CSS. Periksa file asli, semua kolom, zoom/DPI, dan viewport laptop
sebenarnya. Kandidat perbaikan adalah zoom/pan/tampilan ukuran asli, setelah bug terbukti.

Empat paket dengan dua aktif dapat diatur sebelum ujian menggunakan is_active. Jangan
sekadar mengubah paket aktif di tengah ujian: peserta yang paketnya dinonaktifkan bisa
ditolak oleh guard paket. Entitas sesi dan pemetaan dua paket per sesi diperlukan jika
ingin jadwal/histori sesi formal, bukan toggle manual. Jangan mereset ID global soal.

Poin 3 dan 15 dapat dipenuhi bersamaan: mahasiswa mendapat verdict singkat saat ujian,
pengawas mendapat diagnostik lengkap, feedback rinci dapat dibuka setelah ujian sesuai
kebijakan. Jika yang dimaksud form evaluasi, itu kebutuhan berbeda yang belum dijelaskan.

## Prioritas tindak lanjut

1. Perbaiki Format SQL dan benturan penomoran/pesan error; keduanya sudah direproduksi.
2. Perjelas status tersimpan dan pisahkan verdict terbaru dari skor terbaik.
3. Instrumentasikan popup/lobby, lalu reproduksi berdasarkan laptop/browser dan request.
4. Tambah QA browser lintas perangkat: semua tombol, perpindahan paket, submit salah,
   pending/retry, koneksi terputus, gambar panjang, dan dua admin bersamaan.
5. Setelah aturan feedback/numeric disepakati, rancang cache kunci yang terversi.
6. Jadikan setup, persiapan soal, pemilihan paket, power/network, dan uji kelas sebagai SOP.

Bug yang terkonfirmasi di sini belum diperbaiki dalam audit ini. Pengujian berupa
reproduksi fungsi JavaScript terisolasi, SQLite sementara, dan unit pembanding numeric;
bukan rekonstruksi browser/laptop pada hari final test.
