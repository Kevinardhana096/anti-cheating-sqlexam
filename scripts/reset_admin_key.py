"""Local master-key recovery; run while the application is stopped."""
from pathlib import Path
import getpass
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database


def main():
    path = Path(os.environ.get('EXAM_SQLITE_PATH', database.SQLITE_DB_PATH)).resolve()
    if not path.is_file():
        raise SystemExit('Database ujian tidak ditemukan; pemulihan dibatalkan.')
    key = getpass.getpass('Master key baru (minimal 12 karakter): ').strip()
    confirmation = getpass.getpass('Ulangi master key baru: ').strip()
    if key != confirmation or not 12 <= len(key) <= 1024:
        raise SystemExit('Konfirmasi atau panjang master key tidak sesuai; tidak ada perubahan.')
    database.init_system_db()
    database.update_admin_master_key(key)
    print('Master key diperbarui. Seluruh sesi admin dicabut.')


if __name__ == '__main__':
    main()
