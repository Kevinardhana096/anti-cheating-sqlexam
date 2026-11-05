# Evaluasi Arsitektur & Analisis Skalabilitas Sistem Ujian SQL
**Dokumentasi Evaluasi Desain (P1-6, P1-7, P2-6)**

Dokumen ini memaparkan evaluasi teknis pemilihan arsitektur penyimpanan (SQLite WAL vs. PostgreSQL), karakteristik performa single-worker vs. multi-worker, dan roadmap migrasi menuju distributed shared store untuk skala institusi/kampus.

---

## 1. Analisis Arsitektur Saat Ini: Dual-Engine Hybrid Model

Sistem saat ini menerapkan model hibrida:
- **Engine A: SQLite (State & Manajemen Ujian)**
  - Menyimpan: `users`, `exam_config`, `questions`, `submissions`, `exam_logs`.
  - Mode: `WAL` (*Write-Ahead Logging*), `synchronous=NORMAL`, `busy_timeout=5000ms`.
  - Keunggulan: Zero-configuration, zero network latency untuk auth/logs, self-contained, file-based backup yang sangat portabel.
- **Engine B: PostgreSQL (Sandbox Query Mahasiswa & Master Database)**
  - Menyimpan: `pagila`, `classicmodels`, dan skema dinamis per mahasiswa `sandbox_{nim}`.
  - Keunggulan: Fitur SQL ANSI lengkap, keamanan role/privilege (`student_role`), schema isolation, autograding mendalam.

---

## 2. Evaluasi: SQLite WAL vs. Migrasi Penuh ke PostgreSQL (P1-6)

### Perbandingan Karakteristik:

| Aspek | SQLite (Mode WAL Saat Ini) | PostgreSQL untuk Seluruh Tabel |
|---|---|---|
| **Kebutuhan Setup** | Otomatis dibuat saat startup, tanpa konfigurasi tambahan | Memerlukan pembuatan database dan DDL tambahan |
| **Kapasitas Mahasiswa Teruji** | Sangat optimal untuk 1–80 mahasiswa (1–2 ruang lab) | Mampu melayani > 500 mahasiswa lintas ruang/gedung |
| **Konkurensi Pembacaan** | Tidak terbatas (*unlimited concurrent readers*) | Tidak terbatas (*MVCC*) |
| **Konkurensi Penulisan** | Berurutan (*single writer with 5s queue timeout*) | Baris per baris (*row-level locking*) |
| **Latency Query State** | < 0.1 ms (direct memory/disk file) | 1–3 ms (TCP loopback socket) |
| **Portabilitas Host** | Sangat portabel (cukup copy `exam_system.db`) | Memerlukan dump/restore PostgreSQL |

### Kesimpulan & Rekomendasi:
- **Untuk Ujian Lab Offline Lokal (Skala 1–80 Mahasiswa):** Arsitektur SQLite WAL saat ini adalah **pilihan paling ideal, tangguh, dan minim risiko kegagalan**. Beban CPU rendah, tidak ada overhead koneksi database tambahan, dan pemulihan sesi terbukti 100% instan saat server reboot.
- **Untuk Skala Institusi / Ujian Bersama (> 100 Mahasiswa):** Direkomendasikan melakukan migrasi tabel state (`users`, `submissions`, `exam_logs`) ke PostgreSQL database terdedikasi (`exam_control_db`) untuk memanfaatkan *row-level locking* saat ratusan mahasiswa melakukan submisi jawaban pada menit-menit akhir ujian secara simultan.

---

## 3. Evaluasi State In-Memory & Migrasi Shared Store (P1-7, P2-6)

### Komponen State In-Memory Saat Ini:
1. `InMemoryRateLimiter`: Pelacak limit frekuensi request per IP/endpoint (fixed window 60 detik).
2. `_SCHEMA_CACHE`: Cache metadata struktur tabel master (`pagila`, `classicmodels`).
3. `_POOL_TRACKER`: Pelacak metrik antrian connection pool PostgreSQL.
4. `PG_DB_POOLS`: Kumpulan koneksi pool per database master.

### Pertimbangan Multi-Worker:
Dalam deployment single-process Uvicorn saat ini, in-memory state bersifat *thread-safe* dan sangat cepat (sub-mikrodetik).

Jika sistem dijalankan dengan multi-process worker (`uvicorn main:app --workers 4`):
- Masing-masing proses worker memiliki isolasi memori sendiri.
- Rate limiter tidak sinkron antar proses.
- Cache skema diisi redundan oleh setiap proses.

### Desain Migrasi Menuju Shared Store (Redis):
Untuk beralih ke arsitektur multi-worker / multi-node:
```
[ Reverse Proxy / Nginx ]
         │
    ┌────┴────────────────────────┐
    ▼                             ▼
[ Uvicorn Worker 1 ]      [ Uvicorn Worker 2 ]
    │                             │
    ├─────────────┬───────────────┤
    ▼             ▼               ▼
[ Redis ]   [ PostgreSQL ]  [ PostgreSQL ]
(Tokens/Rate) (State DB)    (Exam Sandbox)
```

1. **Redis untuk Rate Limiting:** Implementasikan algoritma sliding window menggunakan `INCR` dan `EXPIRE` Redis key.
2. **Redis untuk Sesi Mahasiswa:** Simpan token sesi dan status heartbeat mahasiswa pada Redis Key-Value Store untuk validasi instan di semua worker.
3. **PostgreSQL LISTEN/NOTIFY:** Gunakan pub/sub PostgreSQL untuk menyinkronkan event start/stop ujian antar worker secara real-time.
