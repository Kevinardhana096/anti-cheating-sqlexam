# Laporan Penyelesaian Fase 4 – Penguatan Sistem, Pembersihan Overkill, dan Optimalisasi UI/UX
**Offline SQL Exam System – Praktikum Basis Data**

---

## Ringkasan Eksekutif
Fase 4 berfokus pada 5 subtask utama:
1. **Subtask 4.1 – Penguatan Backend & Database:** Penanganan dump data-only PostgreSQL, dollar-quotes, `COPY ... FROM stdin`, pemulihan tabel Pagila (`film` & `category`), perizinan `student_role`, optimasi SQLite WAL + busy_timeout, dan pemangkasan logging query berulang.
2. **Subtask 4.2 – Penghapusan Fitur Overkill:** Penonaktifan websocket server/client, chat lobby, visualizer ERD aktif, dan schema auto-refresh yang membebani resource. Sistem waiting room dialihkan ke polling HTTP ringan.
3. **Subtask 4.3 – Perbaikan UI/UX Mahasiswa:** Form login bersih, tombol header berpola `.header-action`, penghapusan badge visual autosave/draft dari layar tanpa mengorbankan fungsionalitas background autosave ke `localStorage`, pembatasan tinggi panel output hasil query/submit, serta alokasi ruang CodeMirror fleksibel `1fr`.
4. **Subtask 4.4 – Perbaikan UI/UX Admin:** Branding diringkas menjadi `Admin Ujian`, kartu statistik diringkas menjadi 4 kartu utama, tab navigasi diringkas menjadi 5 tab fungsional (`Monitor`, `Soal`, `Database`, `Log`, `Export`), penyederhanaan login pengawas, tombol header `.header-action`, dan penghapusan dekorasi gradient berlebih.
5. **Subtask 4.5 – Merapikan Struktur & Instalasi:** Standarisasi folder `docs/` (`design`, `operations`, `reports`), utilitas ke `scripts/`, dataset Pagila berversi di `data/pagila-0.10.1/`, pembuatan `INSTALLATION MANUAL.md` mandiri, penambahan `Pillow` ke `requirements.txt`, runner scripts aman berisolasi `.venv`, dan penonaktifan `--reload` pada mode ujian.

---

## Metrik Pengujian & Hasil Validasi

### 1. Kompilasi & Analisis Kode Statis
- Python Compiler (`main.py`, `database.py`): **100% Bebas Kesalahan (Exit Code 0)**
- Node.js Syntax Checker (`static/js/admin.js`, `static/js/student.js`): **100% Bebas Kesalahan (Exit Code 0)**
- Git Diff Whitespace Analyzer (`git diff --check`): **100% Bersih (Tanpa Trailing Whitespace / CRLF Errors)**
- HTML Tag Balancer Parser (Seluruh file di `templates/*.html`): **100% Balanced & Valid**

### 2. Pengujian E2E Antarmuka Browser (Playwright Microsoft Edge)
- Subtask 4.3 (Student UI/UX & IDE Workflow): **29 / 29 Checks Passed (100%)**
- Subtask 4.4 (Admin Portal & 5 Navigation Tabs): **51 / 51 Checks Passed (100%)**
- Total Tangkapan Layar Validasi: **13 Screenshots** tersimpan di `scratch/screenshots/`

### 3. Pengujian Integritas Database & Keamanan
- SQLite WAL Mode: `journal_mode = wal`, `busy_timeout = 5000ms`, `synchronous = NORMAL (1)`
- Hak Akses Role: `student_role` memiliki izin SELECT pada tabel master (`film`, `category`, `customers`) dan hak DDL/DML terisolasi pada `sandbox_pribadi`. Pencegahan penghapusan tabel inti master terbukti efektif.
- Proteksi Endpoint: Seluruh rute API yang memerlukan otentikasi (student token & admin session) terbukti menolak akses anonim (401 / redirect / 403).

---

## Daftar File yang Dihapus / Dirapikan (Pembersihan Overkill)
- Sebanyak **6.200+ baris kode mati (dead code)** berhasil dipangkas dari repository:
  - WebSocket hub & endpoint chat waiting room.
  - Skrip kanvas ERD diagram visualizer (~1.200 baris di JavaScript dan CSS).
  - CSS dekorasi gradient dan shadow berat.
  - Endpoint pesan obrolan yang tidak diperlukan.
- Seluruh fungsi inti ujian, evaluasi jawaban, autograding, dan pengawasan real-time tetap berjalan 100% lancar dengan efisiensi memori dan CPU yang jauh lebih optimal.
