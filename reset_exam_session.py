#!/usr/bin/env python3
"""
================================================================================
SCRIPT RESET SESI UJIAN BASIS DATA (OPERATIONAL UTILITY)
================================================================================
Deskripsi:
  Utility CLI bagi Dosen & Pengawas Lab untuk membersihkan / me-reset data sesi ujian:
  1. Membersihkan data mahasiswa (tabel 'users' di SQLite).
  2. Membersihkan seluruh jawaban/submisi mahasiswa (tabel 'submissions' di SQLite).
  3. Reset per NIM juga menghapus schema dan role pribadi; --all hanya membersihkan SQLite.
  4. (Opsional) Membersihkan riwayat audit anti-cheat ('exam_logs' di SQLite).
  5. (Opsional) Me-reset sesi individu mahasiswa tertentu via --nim <NIM>.
  
  KEAMANAN:
  - Bank Soal (tabel 'questions') dan Paket Ujian ('exam_packages') TETAP UTUH 100%.
  - Database master 'pagila' dan 'classicmodels' TIDAK DISENTUH.
  - Password master admin TETAP AMAN.

Penggunaan:
  python reset_exam_session.py --check          # Cek status data ujian saat ini (read-only)
  python reset_exam_session.py --all            # Reset seluruh sesi mahasiswa di SQLite (ada konfirmasi)
  python reset_exam_session.py --all --yes      # Reset seluruh sesi langsung tanpa konfirmasi (force)
  python reset_exam_session.py --all --clear-logs -y  # Reset sesi + hapus log audit anti-cheat
  python reset_exam_session.py --nim 220101666  # Reset sesi mahasiswa tertentu (misal PC crash/hang)
================================================================================
"""

import sys
import os
import argparse
import sqlite3

# Import fungsi database internal
try:
    import database
except ImportError:
    # Append workspace root if needed
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import database


def get_current_stats():
    """Mengambil ringkasan statistik database ujian saat ini."""
    conn = database.get_sqlite_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users;")
    student_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM submissions;")
    submission_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM exam_logs;")
    log_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM questions;")
    question_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM exam_packages WHERE is_active = 1;")
    package_count = cur.fetchone()[0]
    
    conn.close()
    
    # Cek jumlah sandbox schemas di PostgreSQL
    sandbox_schemas = []
    try:
        pg_conn = database.get_pg_admin_connection(dbname=database.DEFAULT_EXAM_DB)
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'sandbox_%';")
        sandbox_schemas = [r[0] for r in pg_cur.fetchall()]
        pg_cur.close()
        pg_conn.close()
    except Exception as e:
        sandbox_schemas = [f"Error checking PG: {e}"]
        
    return {
        "students": student_count,
        "submissions": submission_count,
        "logs": log_count,
        "questions": question_count,
        "packages": package_count,
        "sandbox_schemas": sandbox_schemas,
    }


def print_banner():
    print("=" * 72)
    print("   UTILITY PEMBERSIH & RESET SESI UJIAN - BASIS DATA 2026")
    print("   Anti-Cheating SQL Exam Platform | Proctor & Lecturer Tool")
    print("=" * 72)


def display_status():
    print_banner()
    stats = get_current_stats()
    print("\n[INFO] STATUS DATA UJIAN SAAT INI:")
    print(f"  * Total Mahasiswa Terdaftar : {stats['students']} orang")
    print(f"  * Total Jawaban/Submisi     : {stats['submissions']} submisi")
    print(f"  * Total Log Audit Aktivitas : {stats['logs']} baris log")
    print(f"  * Total Bank Soal Tersedia  : {stats['questions']} soal (Aman / Tidak Terhapus)")
    print(f"  * Total Paket Ujian Aktif   : {stats['packages']} paket (Aman / Tidak Terhapus)")
    print(f"  * Schema Sandbox Mahasiswa  : {len(stats['sandbox_schemas'])} schema di PostgreSQL")
    if stats['sandbox_schemas']:
        print(f"    -> Daftar Schema: {', '.join(stats['sandbox_schemas'][:5])}{'...' if len(stats['sandbox_schemas']) > 5 else ''}")
    print("\n" + "=" * 72)


def reset_single_student(nim: str):
    print_banner()
    print(f"\n[ACTION] Mereset sesi mahasiswa individual dengan NIM: '{nim}' ...")
    res = database.reset_student_by_nim(nim)
    if not res["success"]:
        print(f"\n[GAGAL] {res.get('message', 'Reset gagal.')}")
        sys.exit(1)
    
    print("\n[BERHASIL] Sesi mahasiswa berhasil direset:")
    print(f"  * NIM Mahasiswa        : {res['nim']}")
    print(f"  * Submisi Dihapus      : {res['submissions_cleared']} jawaban")
    print(f"  * Schema Sandbox PG    : {'Dihapus' if res['schema_dropped'] else 'Tidak ditemukan'}")
    print("\n[SELESAI] Mahasiswa sekarang dapat login kembali dengan bersih di browser.")
    print("=" * 72)


def reset_all_sessions(clear_logs: bool = False, force: bool = False):
    print_banner()
    stats = get_current_stats()
    
    print("\n[PERINGATAN] ANDA AKAN MENGHAPUS:")
    print(f"  - {stats['students']} data mahasiswa login.")
    print(f"  - {stats['submissions']} jawaban/submisi mahasiswa.")
    print("  - Workspace PostgreSQL tidak dihapus oleh --all; gunakan reset per NIM sebelum membersihkan daftar peserta.")
    if clear_logs:
        print(f"  - {stats['logs']} riwayat log audit anti-cheat.")
    else:
        print(f"  - Log audit anti-cheat ({stats['logs']} baris) AKAN TETAP DISIMPAN.")
    print("  * CATATAN: Bank soal dan paket ujian TIDAK AKAN DIHAPUS.\n")

    if not force:
        try:
            confirm = input("Apakah Anda yakin ingin melanjutkan reset? (ketik 'YA' untuk konfirmasi): ").strip()
            if confirm != "YA":
                print("\n[BATAL] Operasi reset dibatalkan oleh pengguna.")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\n\n[BATAL] Operasi dibatalkan.")
            sys.exit(0)

    print("\n[PROSES] Sedang membersihkan sesi mahasiswa di SQLite ...")
    result = database.clear_previous_sessions(clear_logs=clear_logs)
    
    print("\n[BERHASIL] Data sesi ujian telah berhasil dibersihkan!")
    print(f"  * Mahasiswa Dihapus    : {result['users_cleared']} orang")
    print(f"  * Submisi Dihapus      : {result['submissions_cleared']} jawaban")
    print(f"  * Sandbox PG Dihapus   : {result['schemas_dropped']} schema")
    if result.get("dropped_schemas"):
        print(f"    -> Schema dibersihkan: {', '.join(result['dropped_schemas'])}")
    if clear_logs:
        print("  * Log Audit Anti-Cheat : Dibersihkan (Tabel exam_logs dikosongkan)")
    else:
        print("  * Log Audit Anti-Cheat : Disimpan (Tercatat event 'clear_sessions')")
    
    print("\n[INFO] Sistem ujian kini BERSIH dan SIAP digunakan untuk sesi ujian berikutnya.")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Utility Pembersih & Reset Sesi Ujian Basis Data 2026",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Contoh:\n  python reset_exam_session.py --check\n  python reset_exam_session.py --all --yes\n  python reset_exam_session.py --nim 220101666"
    )
    
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--check", action="store_true", help="Tampilkan status ringkas database ujian saat ini (read-only)")
    group.add_argument("--all", action="store_true", help="Bersihkan seluruh sesi/jawaban SQLite; workspace PostgreSQL tetap disimpan")
    group.add_argument("--nim", type=str, help="Reset sesi untuk satu mahasiswa tertentu berdasarkan NIM")

    parser.add_argument("--clear-logs", action="store_true", help="Hapus seluruh log audit anti-cheat saat mereset semua sesi")
    parser.add_argument("-y", "--yes", "--force", action="store_true", dest="force", help="Lewati prompt konfirmasi interaktif")

    args = parser.parse_args()

    # Default to check if no action specified
    if args.check:
        display_status()
    elif args.nim:
        reset_single_student(args.nim)
    elif args.all:
        reset_all_sessions(clear_logs=args.clear_logs, force=args.force)
    else:
        # If run without arguments, display status and prompt
        display_status()
        print("\nPilih opsi tindakan:")
        print("  [1] Reset Seluruh Sesi Mahasiswa (Simpan Log Audit)")
        print("  [2] Reset Seluruh Sesi Mahasiswa + Hapus Log Audit")
        print("  [3] Reset Satu Mahasiswa Tertentu (Input NIM)")
        print("  [4] Keluar")
        try:
            choice = input("\nMasukkan pilihan (1/2/3/4): ").strip()
            if choice == "1":
                reset_all_sessions(clear_logs=False, force=False)
            elif choice == "2":
                reset_all_sessions(clear_logs=True, force=False)
            elif choice == "3":
                nim_input = input("Masukkan NIM mahasiswa yang ingin di-reset: ").strip()
                if nim_input:
                    reset_single_student(nim_input)
                else:
                    print("[BATAL] NIM tidak boleh kosong.")
            else:
                print("[INFO] Tidak ada perubahan dilakukan.")
        except KeyboardInterrupt:
            print("\n[INFO] Selesai.")


if __name__ == "__main__":
    main()
