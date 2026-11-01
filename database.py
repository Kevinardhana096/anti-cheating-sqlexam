import os

import uuid

import sqlite3

import datetime

import re

import time

import zipfile

import io

import csv

import threading

from typing import Optional, Dict, Any, List, Tuple, Set

import psycopg2

from psycopg2 import sql, extras, pool



# Paths

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SQLITE_DB_PATH = os.path.join(BASE_DIR, "exam_system.db")

CLASSICMODELS_SQL_PATH = os.path.join(BASE_DIR, "data", "classicmodels.sql")



# Load .env file automatically if present

env_file = os.path.join(BASE_DIR, ".env")

if os.path.exists(env_file):

    try:

        with open(env_file, "r", encoding="utf-8") as f:

            for line in f:

                line = line.strip()

                if line and not line.startswith("#") and "=" in line:

                    k, v = line.split("=", 1)

                    k = k.strip()

                    v = v.strip().strip("'\"")

                    if k and k not in os.environ:

                        os.environ[k] = v

    except Exception:

        pass



# PostgreSQL Configuration

PG_HOST = os.getenv("PG_HOST", "localhost")

PG_PORT = int(os.getenv("PG_PORT", 5432))

DEFAULT_EXAM_DB = os.getenv("DEFAULT_EXAM_DB", "pagila")

PG_DB = os.getenv("PG_DB", DEFAULT_EXAM_DB)

PG_ADMIN_USER = os.getenv("PG_ADMIN_USER", "postgres")

PG_ADMIN_PASS = os.getenv("PG_ADMIN_PASS", "")

PG_STUDENT_USER = os.getenv("PG_STUDENT_USER", "student_role")

PG_STUDENT_PASS = os.getenv("PG_STUDENT_PASS", "student123")



# Multi-Database Whitelist & Metadata (pgAdmin-style selector)

ALLOWED_DATABASES = [

    {

        "name": "pagila",

        "label": "pagila (Rental Film)",

        "description": "Database resmi praktikum rental film & DVD (15 tabel master)",

        "type": "master_readonly"

    },

    {

        "name": "sandbox_pribadi",

        "label": "sandbox_pribadi (DDL / DML)",

        "description": "Kamar database pribadi Anda untuk latihan CREATE, INSERT, & DROP tabel",

        "type": "sandbox_student"

    },

    {

        "name": "classicmodels",

        "label": "classicmodels (Retail & Sales)",

        "description": "Database praktikum penjualan model skala & pelanggan (8 tabel)",

        "type": "master_readonly"

    }

]



def get_allowed_databases() -> List[Dict[str, Any]]:

    """Returns list of allowed databases for students and proctors."""

    return ALLOWED_DATABASES



# ==============================================================================

# SQLite System Database Management

# ==============================================================================



def get_sqlite_conn() -> sqlite3.Connection:

    conn = sqlite3.connect(SQLITE_DB_PATH, timeout=30.0)

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON;")

    return conn



def init_system_db():

    conn = get_sqlite_conn()

    with conn:

        conn.executescript("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nim TEXT UNIQUE NOT NULL,

            name TEXT NOT NULL,

            ip_address TEXT,

            session_token TEXT,

            status TEXT DEFAULT 'offline',

            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        );



        CREATE TABLE IF NOT EXISTS questions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            category TEXT NOT NULL DEFAULT 'A',

            question_number INTEGER NOT NULL,

            title TEXT NOT NULL,

            description TEXT NOT NULL,

            score_weight INTEGER DEFAULT 10,

            expected_query TEXT,

            target_database TEXT DEFAULT 'pagila',

            difficulty_level TEXT DEFAULT 'Medium',

            expected_output_image TEXT DEFAULT '',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(category, question_number)

        );



        CREATE TABLE IF NOT EXISTS submissions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,

            submitted_query TEXT NOT NULL,

            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            status TEXT DEFAULT 'submitted',

            UNIQUE(user_id, question_id)

        );



        CREATE TABLE IF NOT EXISTS exam_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            action_type TEXT NOT NULL,

            details TEXT,

            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        );



        CREATE TABLE IF NOT EXISTS system_settings (

            key TEXT PRIMARY KEY,

            value TEXT NOT NULL

        );



        CREATE TABLE IF NOT EXISTS waiting_room_messages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nim TEXT NOT NULL,

            name TEXT NOT NULL,

            message TEXT NOT NULL,

            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        );

        """)



        # Insert or sync default master key

        cur = conn.cursor()

        env_master_key = os.getenv("ADMIN_MASTER_KEY")

        cur.execute("SELECT value FROM system_settings WHERE key = 'admin_master_key';")

        existing_row = cur.fetchone()

        if not existing_row:

            initial_key = env_master_key.strip() if env_master_key else "admin123"

            cur.execute(

                "INSERT INTO system_settings (key, value) VALUES ('admin_master_key', ?);",

                (initial_key,)

            )

        elif env_master_key and env_master_key.strip():

            # Jika user mendefinisikan ADMIN_MASTER_KEY eksplisit via env/script, sinkronkan ke database

            cur.execute(

                "UPDATE system_settings SET value = ? WHERE key = 'admin_master_key';",

                (env_master_key.strip(),)

            )



        # Migrations for newer columns

        try:

            conn.execute("ALTER TABLE users ADD COLUMN virtual_db TEXT DEFAULT NULL;")

            conn.commit()

        except Exception:

            pass



        try:

            conn.execute("ALTER TABLE users ADD COLUMN selected_category TEXT DEFAULT NULL;")

            conn.commit()

        except Exception:

            pass



        # Seed initial exam questions if empty

        cur.execute("SELECT COUNT(*) FROM questions;")

        if cur.fetchone()[0] == 0:

            seed_default_questions(conn)



    conn.close()



def get_admin_master_key() -> str:

    """Mengambil password master admin saat ini dari tabel system_settings."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT value FROM system_settings WHERE key = 'admin_master_key';")

    row = cur.fetchone()

    conn.close()

    return row["value"] if row else "admin123"



def update_admin_master_key(new_key: str) -> bool:

    """Memperbarui password master admin dan mencatatnya ke log aktivitas."""

    new_key = new_key.strip()

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute(

            """

            INSERT INTO system_settings (key, value) VALUES ('admin_master_key', ?)

            ON CONFLICT(key) DO UPDATE SET value = excluded.value;

            """,

            (new_key,)

        )

        cur.execute(

            "INSERT INTO exam_logs (action_type, details) VALUES ('change_master_key', 'Password master admin berhasil diperbarui.');"

        )

    conn.close()

    return True



def seed_default_questions(conn: sqlite3.Connection):

    sample_questions = [

        (

            1,

            "Daftar Pelanggan San Francisco",

            "Tampilkan kolom **customer_name**, **contact_first_name**, **phone**, dan **credit_limit** dari tabel `customers` untuk semua pelanggan yang berada di kota ('city') **'San Francisco'**. Urutkan hasilnya berdasarkan **customer_name** secara ascending (A-Z).",

            15,

            "SELECT customer_name, contact_first_name, phone, credit_limit FROM customers WHERE city = 'San Francisco' ORDER BY customer_name ASC;"

        ),

        (

            2,

            "Produk dengan Stok Terbatas",

            "Manajemen membutuhkan informasi stok produk yang menipis. Tampilkan **product_code**, **product_name**, **product_line**, **quantity_in_stock**, dan **buy_price** dari tabel `products` yang memiliki **quantity_in_stock** kurang dari 3000 unit. Urutkan dari stok yang paling sedikit.",

            15,

            "SELECT product_code, product_name, product_line, quantity_in_stock, buy_price FROM products WHERE quantity_in_stock < 3000 ORDER BY quantity_in_stock ASC;"

        ),

        (

            3,

            "Rata-rata Harga Beli per Lini Produk",

            "Hitung rata-rata harga beli (**buy_price**) dan jumlah varian produk untuk setiap lini produk (**product_line**). Tampilkan kolom **product_line**, **total_produk** (hitung jumlah produk), dan **rata_rata_harga** (dibulatkan 2 desimal menggunakan `ROUND(AVG(buy_price), 2)`). Urutkan dari rata-rata harga tertinggi ke terendah.",

            20,

            "SELECT product_line, COUNT(*) AS total_produk, ROUND(AVG(buy_price), 2) AS rata_rata_harga FROM products GROUP BY product_line ORDER BY rata_rata_harga DESC;"

        ),

        (

            4,

            "Pelanggan dan Sales Representative",

            "Tampilkan data relasi antara pelanggan dan karyawan sales representative mereka. Kolom yang harus ditampilkan: **customer_name**, **city**, nama lengkap sales rep (**first_name** digabung dengan **last_name** sebagai **sales_rep_name**), serta email sales rep. Gunakan `INNER JOIN` antara tabel `customers` dan `employees` berdasarkan relasi `sales_rep_employee_number` = `employee_number`.",

            25,

            "SELECT c.customer_name, c.city, CONCAT(e.first_name, ' ', e.last_name) AS sales_rep_name, e.email FROM customers c INNER JOIN employees e ON c.sales_rep_employee_number = e.employee_number ORDER BY c.customer_name ASC;"

        ),

        (

            5,

            "Total Pendapatan Pesanan per Status",

            "Hitung total nilai penjualan pesanan untuk setiap **status** pesanan. Tampilkan kolom **status** dari tabel `orders` dan kolom kalkulasi **total_nilai** (`SUM(quantity_ordered * price_each)`). Gunakan relasi antara tabel `orders` dan `orderdetails`. Urutkan dari total nilai terbesar ke terkecil.",

            25,

            "SELECT o.status, SUM(od.quantity_ordered * od.price_each) AS total_nilai FROM orders o INNER JOIN orderdetails od ON o.order_number = od.order_number GROUP BY o.status ORDER BY total_nilai DESC;"

        )

    ]

    cur = conn.cursor()

    cur.executemany(

        """

        INSERT INTO questions (question_number, title, description, score_weight, expected_query)

        VALUES (?, ?, ?, ?, ?);

        """,

        sample_questions

    )



# ------------------------------------------------------------------------------

# Student User & Session Management (IP Binding, Anti-Joki & Unique NIM)

# ------------------------------------------------------------------------------



def is_user_active(last_active_str: Optional[str], status: str, timeout_seconds: int = 90) -> bool:

    if status != "online" or not last_active_str:

        return False

    try:

        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        dt = datetime.datetime.fromisoformat(last_active_str.replace("Z", ""))

        return (now - dt).total_seconds() < timeout_seconds

    except Exception:

        return status == "online"



def login_student(nim: str, name: str, ip_address: str, session_token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:

    nim = nim.strip()

    name = name.strip()



    if not nim or not name:

        return False, None, "NIM dan Nama Lengkap wajib diisi!"



    if not re.match(r'^[A-Za-z0-9_\-\.]+$', nim):

        return False, None, "Format NIM tidak valid. Gunakan huruf dan angka tanpa spasi."



    conn = get_sqlite_conn()

    try:

        cur = conn.cursor()



        # 1. Anti-Joki: Pastikan satu IP tidak menjalankan lebih dari 1 mahasiswa aktif sekaligus (kecuali localhost)

        if ip_address not in ("127.0.0.1", "localhost", "::1"):

            cur.execute(

                "SELECT * FROM users WHERE ip_address = ? AND LOWER(nim) != LOWER(?) AND status = 'online';",

                (ip_address, nim)

            )

            other_active_on_ip = cur.fetchall()

            for other_user in other_active_on_ip:

                if is_user_active(other_user["last_active"], other_user["status"]):

                    conn.execute(

                        """

                        INSERT INTO exam_logs (user_id, action_type, details)

                        VALUES (?, 'multi_account_blocked', ?);

                        """,

                        (

                            other_user["id"],

                            f"Percobaan login dengan NIM {nim} ditolak: Perangkat (IP: {ip_address}) sedang aktif untuk NIM {other_user['nim']}"

                        )

                    )

                    conn.commit()

                    return False, None, f"Perangkat ini (IP: {ip_address}) masih memiliki sesi aktif untuk NIM {other_user['nim']}. Satu perangkat hanya boleh digunakan oleh satu mahasiswa!"



        # 2. Cek apakah NIM ini sudah terdaftar sebelumnya

        cur.execute("SELECT * FROM users WHERE LOWER(nim) = LOWER(?);", (nim,))

        existing_user = cur.fetchone()



        if existing_user:

            user_id = existing_user["id"]

            reg_nim = existing_user["nim"]

            reg_name = existing_user["name"]

            old_ip = existing_user["ip_address"]

            user_status = existing_user["status"]

            last_active = existing_user["last_active"]



            # 2a. Verifikasi Nama (Mencegah mahasiswa login dengan NIM orang lain)

            if reg_name.strip().lower() != name.lower():

                conn.execute(

                    """

                    INSERT INTO exam_logs (user_id, action_type, details)

                    VALUES (?, 'nim_hijack_attempt', ?);

                    """,

                    (

                        user_id,

                        f"Percobaan login NIM {reg_nim} ditolak: Nama '{name}' tidak cocok dengan nama terdaftar '{reg_name}' (IP: {ip_address})"

                    )

                )

                conn.commit()

                return False, None, f"NIM {reg_nim} sudah terdaftar atas nama '{reg_name}'. Nama yang Anda masukkan tidak cocok. Pastikan Anda tidak menggunakan NIM mahasiswa lain!"



            # 2b. Enforce Unique Active NIM: Cek apakah NIM sedang aktif di sesi ujian

            active = is_user_active(last_active, user_status)

            if active:

                # Jika login dari perangkat/IP yang sama persis: izinkan melanjutkan sesi (misal refresh/tab tertutup)

                if old_ip == ip_address:

                    conn.execute(

                        """

                        UPDATE users

                        SET session_token = ?, status = 'online', last_active = CURRENT_TIMESTAMP

                        WHERE id = ?;

                        """,

                        (session_token, user_id)

                    )

                    conn.execute(

                        """

                        INSERT INTO exam_logs (user_id, action_type, details)

                        VALUES (?, 'resume_session', ?);

                        """,

                        (user_id, f"Mahasiswa {reg_nim} melanjutkan sesi pada IP {ip_address}")

                    )

                else:

                    # Perangkat/IP LAIN mencoba login dengan NIM yang SEDANG AKTIF!

                    # TOLAK login ini untuk melindungi mahasiswa yang sah yang sedang ujian

                    conn.execute(

                        """

                        INSERT INTO exam_logs (user_id, action_type, details)

                        VALUES (?, 'duplicate_nim_blocked', ?);

                        """,

                        (

                            user_id,

                            f"Percobaan login ganda NIM {reg_nim} dari IP {ip_address} DITOLAK karena sedang aktif di IP {old_ip}"

                        )

                    )

                    conn.commit()

                    return False, None, f"NIM {reg_nim} sedang aktif digunakan dalam sesi ujian pada perangkat lain (IP: {old_ip}). Setiap mahasiswa hanya dapat aktif pada 1 sesi ujian dengan NIM unik. Hubungi pengawas jika Anda perlu reset sesi."



            else:

                # 2c. Mahasiswa offline / direset pengawas / timeout: Izinkan login ulang dengan data yang cocok

                conn.execute(

                    """

                    UPDATE users

                    SET ip_address = ?, session_token = ?, status = 'online', last_active = CURRENT_TIMESTAMP

                    WHERE id = ?;

                    """,

                    (ip_address, session_token, user_id)

                )

                conn.execute(

                    """

                    INSERT INTO exam_logs (user_id, action_type, details)

                    VALUES (?, 'login', ?);

                    """,

                    (user_id, f"Mahasiswa {reg_nim} login kembali dari IP {ip_address}")

                )



        else:

            # 3. Registrasi Mahasiswa Baru dengan NIM unik

            cur.execute(

                """

                INSERT INTO users (nim, name, ip_address, session_token, status, last_active)

                VALUES (?, ?, ?, ?, 'online', CURRENT_TIMESTAMP);

                """,

                (nim, name, ip_address, session_token)

            )

            user_id = cur.lastrowid

            cur.execute(

                """

                INSERT INTO exam_logs (user_id, action_type, details)

                VALUES (?, 'login', ?);

                """,

                (user_id, f"Registrasi awal dan login NIM {nim} ({name}) dari IP {ip_address}")

            )



        conn.commit()

        cur.execute("SELECT * FROM users WHERE id = ?;", (user_id,))

        user_row = dict(cur.fetchone())

        return True, user_row, None



    except Exception as e:

        conn.rollback()

        raise e

    finally:

        conn.close()



def validate_student_session(nim: str, session_token: str, request_ip: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE LOWER(nim) = LOWER(?);", (nim,))

    user = cur.fetchone()

    conn.close()



    if not user:

        return False, None, "Pengguna tidak ditemukan."



    user_dict = dict(user)



    # Cek apakah sesi dihentikan atau di-reset oleh pengawas

    if user_dict.get("session_token") == "KICKED_BY_ADMIN":

        return False, user_dict, "Sesi ujian Anda telah dihentikan oleh pengawas."



    if user_dict.get("status") == "offline":

        return False, user_dict, "Sesi Anda telah berakhir atau berstatus offline."



    # Verifikasi token sesi unik

    if user_dict.get("session_token") != session_token:

        return False, user_dict, "NIM Anda sedang dibuka dari perangkat atau tab browser lain!"



    # Verifikasi IP binding

    if user_dict.get("ip_address") != request_ip:

        return False, user_dict, f"Alamat IP Anda berubah ({request_ip} vs {user_dict.get('ip_address')}). Silakan login ulang."



    return True, user_dict, "Valid"



def update_student_heartbeat(user_id: int):

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            """

            UPDATE users 

            SET last_active = CURRENT_TIMESTAMP, status = 'online'

            WHERE id = ?;

            """,

            (user_id,)

        )

    conn.close()



def logout_student(nim: str, session_token: str):

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE LOWER(nim) = LOWER(?) AND session_token = ?;", (nim, session_token))

        row = cur.fetchone()

        if row:

            user_id = row["id"]

            conn.execute("UPDATE users SET status = 'offline', session_token = NULL WHERE id = ?;", (user_id,))

            conn.execute(

                "INSERT INTO exam_logs (user_id, action_type, details) VALUES (?, 'logout', 'Mahasiswa logout manual');",

                (user_id,)

            )

    conn.close()



def kick_student(nim: str) -> bool:

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute(

            """

            UPDATE users 

            SET session_token = 'KICKED_BY_ADMIN', status = 'offline' 

            WHERE LOWER(nim) = LOWER(?);

            """,

            (nim,)

        )

        cur.execute(

            """

            INSERT INTO exam_logs (action_type, details)

            VALUES ('kick', ?);

            """,

            (f"Pengawas me-reset sesi untuk NIM {nim}",)

        )

    conn.close()

    return True



def stop_all_active_sessions() -> int:

    """Hentikan semua sesi mahasiswa yang sedang berlangsung sekaligus."""

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute(

            """

            UPDATE users 

            SET session_token = 'KICKED_BY_ADMIN', status = 'offline'

            WHERE status = 'online' OR (session_token IS NOT NULL AND session_token != 'KICKED_BY_ADMIN');

            """

        )

        count = cur.rowcount

        cur.execute(

            """

            INSERT INTO exam_logs (action_type, details)

            VALUES ('stop_all_sessions', ?);

            """,

            (f"Pengawas menghentikan semua sesi ujian aktif ({count} sesi dinonaktifkan)",)

        )

    conn.close()

    return count



def clear_exam_logs() -> int:

    """Bersihkan seluruh riwayat log aktivitas sistem."""

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM exam_logs;")

        count = cur.fetchone()[0]

        cur.execute("DELETE FROM exam_logs;")

        cur.execute(

            """

            INSERT INTO exam_logs (action_type, details)

            VALUES ('clear_logs', 'Pengawas membersihkan seluruh riwayat log aktivitas ujian.');

            """

        )

    conn.close()

    return count



def clear_previous_sessions(clear_logs: bool = False) -> Dict[str, int]:

    """Bersihkan seluruh sesi mahasiswa dan jawaban/submisi sebelumnya."""

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users;")

        user_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM submissions;")

        sub_count = cur.fetchone()[0]



        cur.execute("DELETE FROM submissions;")

        cur.execute("DELETE FROM users;")



        if clear_logs:

            cur.execute("DELETE FROM exam_logs;")

            cur.execute(

                """

                INSERT INTO exam_logs (action_type, details)

                VALUES ('reset_all', 'Pengawas membersihkan seluruh sesi mahasiswa, submisi, dan log aktivitas.');

                """

            )

        else:

            cur.execute(

                """

                INSERT INTO exam_logs (action_type, details)

                VALUES ('clear_sessions', ?);

                """,

                (f"Pengawas membersihkan sesi mahasiswa sebelumnya ({user_count} mahasiswa, {sub_count} submisi dihapus).",)

            )

    conn.close()

    return {"users_cleared": user_count, "submissions_cleared": sub_count}



# ------------------------------------------------------------------------------

# Questions CRUD

# ------------------------------------------------------------------------------



def get_all_questions(include_expected_query: bool = False, category: Optional[str] = None) -> List[Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    if category and category.strip():

        cur.execute("SELECT * FROM questions WHERE UPPER(category) = ? ORDER BY question_number ASC;", (category.strip().upper(),))

    else:

        cur.execute("SELECT * FROM questions ORDER BY category ASC, question_number ASC;")

    rows = cur.fetchall()

    conn.close()



    result = []

    for r in rows:

        item = dict(r)

        if not include_expected_query:

            item.pop("expected_query", None)

        result.append(item)

    return result





def get_questions_by_category(category: str, include_expected_query: bool = False) -> List[Dict[str, Any]]:

    """Returns questions filtered by category for student or exam usage."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT * FROM questions WHERE UPPER(category) = ? ORDER BY question_number ASC;", (category.strip().upper(),))

    rows = cur.fetchall()

    conn.close()



    result = []

    for r in rows:

        item = dict(r)

        if not include_expected_query:

            item.pop("expected_query", None)

        result.append(item)

    return result





def get_available_categories() -> List[Dict[str, Any]]:

    """Returns distinct categories of questions present in the database."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("""

        SELECT category, COUNT(*) as count, SUM(score_weight) as total_score

        FROM questions

        GROUP BY category

        ORDER BY category;

    """)

    rows = cur.fetchall()

    conn.close()

    return [{"category": r[0], "count": r[1], "total_score": r[2] or 0} for r in rows]



def get_all_packages(include_inactive: bool = True) -> List[Dict[str, Any]]:

    """Returns all configured exam packages with real question stats."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    query = "SELECT id, code, name, description, is_active, created_at FROM exam_packages"

    if not include_inactive:

        query += " WHERE is_active = 1"

    query += " ORDER BY code ASC;"

    cur.execute(query)

    rows = cur.fetchall()

    

    cur.execute("SELECT category, COUNT(*), SUM(score_weight) FROM questions GROUP BY category;")

    q_stats = {r[0]: {"count": r[1], "total_score": r[2] or 0} for r in cur.fetchall()}

    

    cur.execute("SELECT selected_category, COUNT(*) FROM users WHERE selected_category IS NOT NULL AND selected_category != '' GROUP BY selected_category;")

    u_stats = {r[0]: r[1] for r in cur.fetchall()}

    conn.close()

    

    pkgs = []

    for r in rows:

        code = r[1]

        qs = q_stats.get(code, {"count": 0, "total_score": 0})

        pkgs.append({

            "id": r[0],

            "code": code,

            "name": r[2],

            "description": r[3] or "",

            "is_active": bool(r[4]),

            "created_at": r[5],

            "question_count": qs["count"],

            "total_questions": qs["count"],

            "total_score": qs["total_score"],

            "total_weight": qs["total_score"],

            "student_count": u_stats.get(code, 0),

            "total_students": u_stats.get(code, 0)

        })

    return pkgs



def get_package_by_code(code: str) -> Optional[Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT id, code, name, description, is_active, created_at FROM exam_packages WHERE code = ?;", (code,))

    r = cur.fetchone()

    conn.close()

    if not r:

        return None

    return {

        "id": r[0],

        "code": r[1],

        "name": r[2],

        "description": r[3] or "",

        "is_active": bool(r[4]),

        "created_at": r[5]

    }



def create_package(code: str, name: str, description: str = "", is_active: int = 1) -> Tuple[bool, str, Optional[int]]:

    code = (code or "").strip().upper()

    name = (name or "").strip()

    if not code or not name:

        return False, "Kode dan Nama Paket wajib diisi.", None

    conn = get_sqlite_conn()

    cur = conn.cursor()

    try:

        cur.execute("INSERT INTO exam_packages (code, name, description, is_active) VALUES (?, ?, ?, ?);", (code, name, description, is_active))

        pkg_id = cur.lastrowid

        conn.commit()

        return True, f"Paket {code} berhasil ditambahkan.", pkg_id

    except sqlite3.IntegrityError:

        return False, f"Kode paket '{code}' sudah digunakan.", None

    finally:

        conn.close()



def update_package(code: str, name: Optional[str] = None, description: Optional[str] = None, is_active: Optional[int] = None) -> Tuple[bool, str]:

    code = (code or "").strip().upper()

    conn = get_sqlite_conn()

    cur = conn.cursor()

    fields = []

    vals = []

    if name is not None:

        fields.append("name = ?")

        vals.append(name.strip())

    if description is not None:

        fields.append("description = ?")

        vals.append(description.strip())

    if is_active is not None:

        fields.append("is_active = ?")

        vals.append(1 if is_active else 0)

    if not fields:

        conn.close()

        return False, "Tidak ada data yang diperbarui."

    vals.append(code)

    try:

        cur.execute(f"UPDATE exam_packages SET {', '.join(fields)} WHERE code = ?;", vals)

        conn.commit()

        return True, f"Paket {code} berhasil diperbarui."

    except Exception as e:

        return False, str(e)

    finally:

        conn.close()



def delete_package(code: str, delete_questions: bool = False) -> Tuple[bool, str]:

    code = (code or "").strip().upper()

    conn = get_sqlite_conn()

    cur = conn.cursor()

    try:

        cur.execute("SELECT COUNT(*) FROM users WHERE selected_category = ?;", (code,))

        locked_students = cur.fetchone()[0]

        if locked_students > 0:

            return False, f"Tidak dapat menghapus Paket {code}: Masih ada {locked_students} mahasiswa terkunci pada paket ini."

        cur.execute("DELETE FROM exam_packages WHERE code = ?;", (code,))

        if delete_questions:

            cur.execute("DELETE FROM questions WHERE category = ?;", (code,))

        conn.commit()

        return True, f"Paket {code} berhasil dihapus."

    except Exception as e:

        return False, str(e)

    finally:

        conn.close()



def lock_student_category(nim: str, category: str) -> Tuple[bool, str]:

    clean_nim = (nim or "").strip()

    clean_cat = (category or "").strip().upper()

    if not clean_nim or not clean_cat:

        return False, "NIM dan Paket Soal harus valid."

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT selected_category FROM users WHERE nim = ?;", (clean_nim,))

    row = cur.fetchone()

    if not row:

        conn.close()

        return False, "Mahasiswa tidak ditemukan."

    current_cat = row[0]

    if current_cat and current_cat != clean_cat:

        conn.close()

        return False, f"Paket soal Anda sudah terkunci pada Paket {current_cat}. Hubungi dosen pengawas untuk mereset."

    cur.execute("UPDATE users SET selected_category = ? WHERE nim = ?;", (clean_cat, clean_nim))

    conn.commit()

    conn.close()

    return True, f"Berhasil mengunci Paket {clean_cat}."



def reset_student_category(nim: str) -> Tuple[bool, str]:

    clean_nim = (nim or "").strip()

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("UPDATE users SET selected_category = '' WHERE nim = ?;", (clean_nim,))

    conn.commit()

    conn.close()

    return True, f"Pilihan paket untuk NIM {clean_nim} berhasil di-reset."





def get_student_virtual_database(nim: Optional[str]) -> Optional[str]:
    """Returns the student's currently active virtual database name (created via CREATE DATABASE)."""
    if not nim:
        return None
    clean_nim = str(nim).strip()
    conn = get_sqlite_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT virtual_db FROM users WHERE LOWER(nim) = LOWER(?);", (clean_nim,))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    finally:
        conn.close()

    # Fallback: introspect schema comment in PostgreSQL
    try:
        schema_name = get_clean_student_schema_name(clean_nim)
        conn_pg = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)
        cur_pg = conn_pg.cursor()
        cur_pg.execute("""
            SELECT description FROM pg_description 
            JOIN pg_namespace ON pg_description.objoid = pg_namespace.oid 
            WHERE pg_namespace.nspname = %s;
        """, (schema_name,))
        desc_row = cur_pg.fetchone()
        cur_pg.close()
        conn_pg.close()
        if desc_row and desc_row[0] and desc_row[0].startswith("virtual_db:"):
            return desc_row[0].replace("virtual_db:", "").strip()
    except Exception:
        pass
    return None

def set_student_virtual_database(nim: Optional[str], db_name: str) -> None:
    """Updates the student's virtual database name."""
    if not nim:
        return
    clean_nim = str(nim).strip()
    clean_vdb = db_name.strip().lower()
    conn = get_sqlite_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (nim, name, ip_address, status, virtual_db)
            VALUES (?, ?, '127.0.0.1', 'offline', ?)
            ON CONFLICT(nim) DO UPDATE SET virtual_db = excluded.virtual_db;
        """, (clean_nim, f"Mahasiswa {clean_nim}", clean_vdb))
        conn.commit()
    except Exception as e:
        print(f"Error setting virtual db: {e}")
    finally:
        conn.close()

def clear_student_virtual_database(nim: Optional[str]) -> None:
    """Clears the student's virtual database name upon DROP DATABASE."""
    if not nim:
        return
    clean_nim = str(nim).strip()
    conn = get_sqlite_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET virtual_db = NULL WHERE LOWER(nim) = LOWER(?);", (clean_nim,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()



def get_question_by_id(question_id: int) -> Optional[Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT * FROM questions WHERE id = ?;", (question_id,))

    row = cur.fetchone()

    conn.close()

    return dict(row) if row else None



def save_question(

    question_number: int,

    title: str,

    description: str,

    score_weight: int,

    expected_query: Optional[str] = None,

    question_id: Optional[int] = None,

    category: str = "A",

    target_database: str = DEFAULT_EXAM_DB,

    difficulty_level: str = "Medium",

    expected_output_image: str = ""

) -> int:

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        if question_id:

            cur.execute(

                """

                UPDATE questions

                SET question_number = ?, title = ?, description = ?, score_weight = ?, expected_query = ?,

                    category = ?, target_database = ?, difficulty_level = ?, expected_output_image = ?

                WHERE id = ?;

                """,

                (question_number, title, description, score_weight, expected_query, category, target_database, difficulty_level, expected_output_image, question_id)

            )

            ret_id = question_id

        else:

            cur.execute(

                """

                INSERT INTO questions (question_number, title, description, score_weight, expected_query, category, target_database, difficulty_level, expected_output_image)

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

                """,

                (question_number, title, description, score_weight, expected_query, category, target_database, difficulty_level, expected_output_image)

            )

            ret_id = cur.lastrowid

    conn.close()

    return ret_id



def delete_question(question_id: int):

    conn = get_sqlite_conn()

    with conn:

        conn.execute("DELETE FROM questions WHERE id = ?;", (question_id,))

    conn.close()



def delete_all_questions():

    conn = get_sqlite_conn()

    with conn:

        conn.execute("DELETE FROM questions;")

    conn.close()



# ------------------------------------------------------------------------------

# Submissions Management

# ------------------------------------------------------------------------------





def extract_table_name_from_dml(dml_sql: str) -> Optional[str]:

    """

    Extracts the targeted table name from an INSERT INTO query.

    Handles optional schema qualifiers, quotes, and backticks.

    """

    if not dml_sql:

        return None

    match = re.search(

        r'INSERT\s+INTO\s+(?:[`"]?[a-zA-Z0-9_]+[`"]?\.)?[`"]?([a-zA-Z0-9_]+)[`"]?',

        dml_sql,

        re.IGNORECASE

    )

    return match.group(1).lower() if match else None



def compile_reference_dml(

    expected_dml_sql: str,

    table_name: str,

    student_schema: str,

    dbname: str = DEFAULT_EXAM_DB

) -> Dict[str, Any]:

    """

    Compiles the lecturer's expected DML (INSERT INTO) query inside an isolated temporary schema.

    Clones the table structure from the student's sandbox schema, executes expected DML,

    extracts the reference rows and columns, and cleanly drops the temporary schema.

    Guarantees ZERO schema leaks.

    """

    temp_schema = f"_ref_dml_{uuid.uuid4().hex[:12]}"

    conn = get_pg_admin_connection(dbname=dbname)

    conn.autocommit = True

    cur = conn.cursor()



    try:

        cur.execute(f"CREATE SCHEMA {temp_schema};")

        cur.execute(sql.SQL("CREATE TABLE {}.{} (LIKE {}.{} INCLUDING ALL);").format(

            sql.Identifier(temp_schema),

            sql.Identifier(table_name),

            sql.Identifier(student_schema),

            sql.Identifier(table_name)

        ))

        cur.execute(f"SET search_path TO {temp_schema}, public;")

        cur.execute(expected_dml_sql)

        

        cur.execute(sql.SQL("SELECT * FROM {}.{};").format(

            sql.Identifier(temp_schema),

            sql.Identifier(table_name)

        ))

        columns = [desc[0] for desc in cur.description] if cur.description else []

        rows = cur.fetchall()

        

        return {

            "success": True,

            "columns": columns,

            "rows": rows,

            "row_count": len(rows)

        }

    except Exception as e:

        return {

            "success": False,

            "error": f"Gagal mengeksekusi kunci acuan DML dosen: {str(e)}",

            "columns": [],

            "rows": [],

            "row_count": 0

        }

    finally:

        try:

            cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")

        except Exception:

            pass

        cur.close()

        conn.close()



def compare_table_records(

    ref_columns: List[str],

    ref_rows: List[Tuple],

    stud_columns: List[str],

    stud_rows: List[Tuple],

    table_name: str

) -> Tuple[bool, str, Dict[str, Any]]:

    """

    Compares the reference records with the student's records in a table.

    Validates:

    1. Non-empty table

    2. Row count matching

    3. Record values matching (order-insensitive, normalized)

    Returns (is_correct, feedback_message, diagnostic_details).

    """

    details = {

        "table_name": table_name,

        "expected_rows": len(ref_rows),

        "student_rows": len(stud_rows),

        "status": "ok"

    }



    if not stud_rows:

        details["status"] = "empty"

        return False, f"Tabel '{table_name}' masih kosong. Tidak ada baris data yang tersimpan.", details



    if len(stud_rows) != len(ref_rows):

        details["status"] = "row_count_mismatch"

        msg = f"Jumlah baris data pada tabel '{table_name}' tidak sesuai. Diharapkan {len(ref_rows)} baris data, namun tabel Anda memiliki {len(stud_rows)} baris data."

        return False, msg, details



    ref_cols_lower = [c.lower() for c in ref_columns]

    stud_cols_lower = [c.lower() for c in stud_columns]



    if ref_cols_lower == stud_cols_lower:

        col_mapping = list(range(len(ref_columns)))

    else:

        col_mapping = []

        for rc in ref_cols_lower:

            if rc in stud_cols_lower:

                col_mapping.append(stud_cols_lower.index(rc))

            else:

                col_mapping.append(None)



    norm_stud_rows = []

    for r in stud_rows:

        row_items = []

        for idx in col_mapping:

            val = r[idx] if idx is not None and idx < len(r) else None

            row_items.append(_normalize_cell_value(val))

        norm_stud_rows.append(row_items)



    norm_ref_rows = []

    for r in ref_rows:

        norm_ref_rows.append([_normalize_cell_value(val) for val in r])



    def row_sort_key(row):

        return tuple(str(x) for x in row)



    sorted_stud = sorted(norm_stud_rows, key=row_sort_key)

    sorted_ref = sorted(norm_ref_rows, key=row_sort_key)



    if sorted_stud != sorted_ref:

        details["status"] = "value_mismatch"

        unmatched_stud = [r for r in sorted_stud if r not in sorted_ref]

        unmatched_ref = [r for r in sorted_ref if r not in sorted_stud]

        details["unmatched_student"] = unmatched_stud

        details["unmatched_reference"] = unmatched_ref

        

        msg = f"Data yang tersimpan di tabel '{table_name}' belum sesuai dengan kunci acuan dosen. Periksa kembali keakuratan nilai kolom (angka, teks, atau format tanggal) yang Anda masukkan."

        return False, msg, details



    msg = f"Sempurna! Seluruh {len(stud_rows)} baris data pada tabel '{table_name}' berhasil dimasukkan dan nilainya 100% cocok dengan acuan dosen."

    return True, msg, details





def _normalize_cell_value(val: Any) -> Any:

    """Normalizes cell values for reliable comparisons between PostgreSQL and SQLite."""

    if val is None:

        return None

    if isinstance(val, (int, float)):

        return round(float(val), 4)

    if isinstance(val, (datetime.date, datetime.datetime)):

        return str(val)

    val_str = str(val).strip()

    try:

        num = float(val_str)

        return round(num, 4)

    except ValueError:

        pass

    return val_str.lower()



def evaluate_sql_submission(

    submitted_query: str,

    expected_query: Optional[str],

    score_weight: int = 10,

    target_db: str = DEFAULT_EXAM_DB,

    active_db: str = DEFAULT_EXAM_DB,

    nim: Optional[str] = None

) -> Dict[str, Any]:

    """

    Evaluates a student's SQL submission.

    Supports:

    - Target database connection validation (checks active_db == target_db)

    - Deep DDL evaluation (CREATE TABLE) using PostgreSQL Catalog Inspection & Table Comparison

    - DML evaluation (INSERT INTO) in student sandbox schema

    - DROP TABLE / DROP DATABASE evaluations in student sandbox schema

    - SELECT query comparison against lecturer expected_query (columns, rows, values, ordering)

    - Constructive Indonesian feedback with HackerRank style status

    """

    submitted_query = (submitted_query or "").strip()

    if not submitted_query:

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "empty",

            "feedback": "Query jawaban masih kosong. Silakan tuliskan kueri SQL Anda.",

            "student_result": None

        }



    target_db_clean = (target_db or DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()

    active_db_clean = (active_db or DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()



    # 1. Multi-Database connection guard

    if target_db_clean != active_db_clean:

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "wrong_database",

            "feedback": f"Koneksi database salah! Soal ini memerlukan koneksi ke database '{target_db_clean}', tetapi Anda sedang terhubung ke '{active_db_clean}'. Silakan alihkan database di panel atas.",

            "student_result": None

        }



    # 2. Dangerous SQL check

    is_sandbox = (target_db_clean == "sandbox_pribadi")

    danger_err = check_dangerous_sql(submitted_query, is_sandbox_student=is_sandbox)

    if danger_err:

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "security_violation",

            "feedback": f"Pelanggaran Keamanan: {danger_err}",

            "student_result": None

        }



    clean_q_upper = submitted_query.upper().strip()



    # 3. Handle CREATE DATABASE in sandbox

    match_cdb_exp = re.search(r'CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)', expected_query or "", re.IGNORECASE)

    match_cdb_stud = re.search(r'CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)', submitted_query, re.IGNORECASE)



    if is_sandbox and match_cdb_exp:

        exp_db = match_cdb_exp.group(1).lower()

        if not match_cdb_stud:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "wrong_data",

                "feedback": f"Kueri Anda belum memuat perintah CREATE DATABASE sesuai instruksi soal. Kunci acuan mengharapkan pembuatan database '{exp_db}'.",

                "student_result": None

            }

        stud_db = match_cdb_stud.group(1).lower()

        if stud_db != exp_db:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "wrong_database_name",

                "feedback": f"Nama database belum sesuai. Kunci acuan mengharapkan database '{exp_db}', namun Anda membuat '{stud_db}'.",

                "student_result": None

            }



        exec_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

        if not exec_res.get("success"):

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "syntax_error",

                "feedback": f"Error Eksekusi: {exec_res.get('error')}",

                "student_result": exec_res

            }



        # Check if expected query ALSO expects a table

        match_tbl_exp = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)', expected_query or "", re.IGNORECASE)

        if match_tbl_exp:

            exp_tbl = match_tbl_exp.group(1).lower()

            schema_info = get_database_schema(db_name="sandbox_pribadi", nim=nim)

            if exp_tbl in [t.lower() for t in schema_info.keys()]:

                return {

                    "is_correct": True,

                    "score": int(score_weight),

                    "eval_status": "correct",

                    "feedback": f"Sempurna! Database '{stud_db}' dan tabel '{exp_tbl}' berhasil dibuat di sandbox pribadi Anda (+{score_weight} Poin).",

                    "student_result": exec_res

                }

            else:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "table_not_found",

                    "feedback": f"Database '{stud_db}' valid, namun tabel '{exp_tbl}' belum berhasil dibuat di sandbox pribadi Anda.",

                    "student_result": exec_res

                }

        else:

            return {

                "is_correct": True,

                "score": int(score_weight),

                "eval_status": "correct",

                "feedback": f"Sempurna! Perintah CREATE DATABASE '{stud_db}' berhasil dijalankan di sandbox pribadi Anda (+{score_weight} Poin).",

                "student_result": exec_res

            }



    # Handle DROP DATABASE in sandbox

    match_ddb_exp = re.search(r'DROP\s+DATABASE\s+(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_]+)', expected_query or "", re.IGNORECASE)

    match_ddb_stud = re.search(r'DROP\s+DATABASE\s+(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_]+)', submitted_query, re.IGNORECASE)



    if is_sandbox and (match_ddb_exp or (match_ddb_stud and "CREATE TABLE" not in clean_q_upper and "SELECT" not in clean_q_upper)):

        if match_ddb_exp:

            exp_db = match_ddb_exp.group(1).lower()

            if not match_ddb_stud:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "wrong_data",

                    "feedback": f"Kueri Anda belum memuat perintah DROP DATABASE. Kunci acuan mengharapkan penghapusan database '{exp_db}'.",

                    "student_result": None

                }

            stud_db = match_ddb_stud.group(1).lower()

            if stud_db != exp_db:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "wrong_database_name",

                    "feedback": f"Nama database yang dihapus belum sesuai. Kunci acuan mengharapkan penghapusan '{exp_db}', namun Anda menghapus '{stud_db}'.",

                    "student_result": None

                }



        exec_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

        if not exec_res.get("success"):

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "syntax_error",

                "feedback": f"Error Eksekusi: {exec_res.get('error')}",

                "student_result": exec_res

            }

        dropped_name = match_ddb_stud.group(1) if match_ddb_stud else (match_ddb_exp.group(1) if match_ddb_exp else "database")

        return {

            "is_correct": True,

            "score": int(score_weight),

            "eval_status": "correct",

            "feedback": f"Sempurna! Database '{dropped_name}' dan seluruh tabelnya berhasil dibersihkan dari sandbox pribadi Anda (+{score_weight} Poin).",

            "student_result": exec_res

        }



    # 4. Handle DDL (CREATE TABLE) with Deep Catalog & Structure Inspection (Fase 2)

    ddl_tbl = extract_table_name_from_ddl(submitted_query)

    if ("CREATE TABLE" in clean_q_upper) and (not clean_q_upper.startswith("INSERT INTO")):

        tbl_name = ddl_tbl

        if not tbl_name:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "syntax_error",

                "feedback": "Sintaks CREATE TABLE tidak valid: nama tabel tidak dapat diidentifikasi.",

                "student_result": None

            }



        # Execute in student's sandbox

        stud_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

        

        # If execution failed with syntax error other than 'already exists'

        if not stud_res.get("success"):

            err_msg = stud_res.get("error", "")

            if "already exists" not in err_msg.lower():

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "syntax_error",

                    "feedback": f"Error Sintaks SQL: {err_msg}",

                    "student_result": stud_res

                }



        # Now perform Deep PostgreSQL Catalog Inspection against Lecturer's Expected DDL

        student_schema = get_clean_student_schema_name(nim)

        

        if expected_query and extract_table_name_from_ddl(expected_query):

            # Compile reference DDL to get expected metadata

            ref_meta = compile_reference_ddl(expected_query, dbname=DEFAULT_EXAM_DB)

            if not ref_meta.get("exists"):

                # Fallback if reference DDL has issue

                ref_err = ref_meta.get("error", "Kunci acuan dosen tidak valid.")

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "reference_error",

                    "feedback": f"Peringatan Evaluator: {ref_err}",

                    "student_result": stud_res

                }

            

            # Inspect student's table catalog

            stud_conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

            try:

                stud_meta = inspect_table_catalog(student_schema, tbl_name, conn=stud_conn, dbname=DEFAULT_EXAM_DB)

            finally:

                if stud_conn and not stud_conn.closed:

                    stud_conn.close()



            # Deep structure comparison

            is_valid, comp_msg, details = compare_table_structures(ref_meta, stud_meta)

            if is_valid:

                return {

                    "is_correct": True,

                    "score": int(score_weight),

                    "eval_status": "correct",

                    "feedback": f"Sempurna! Struktur tabel '{tbl_name}' (kolom, tipe data, NOT NULL, dan PRIMARY KEY) 100% valid sesuai spesifikasi acuan dosen (+{score_weight} Poin).",

                    "student_result": stud_res,

                    "diagnostics": details

                }

            else:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "wrong_schema",

                    "feedback": comp_msg,

                    "student_result": stud_res,

                    "diagnostics": details

                }

        else:

            # Fallback if expected_query is not provided: verify table exists in student schema

            stud_conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

            try:

                stud_meta = inspect_table_catalog(student_schema, tbl_name, conn=stud_conn, dbname=DEFAULT_EXAM_DB)

            finally:

                if stud_conn and not stud_conn.closed:

                    stud_conn.close()



            if stud_meta.get("exists"):

                return {

                    "is_correct": True,

                    "score": int(score_weight),

                    "eval_status": "correct",

                    "feedback": f"Tabel '{tbl_name}' berhasil dibuat di skema pribadi Anda (+{score_weight} Poin).",

                    "student_result": stud_res

                }

            else:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "table_not_found",

                    "feedback": f"Tabel '{tbl_name}' belum berhasil dibuat di skema pribadi Anda.",

                    "student_result": stud_res

                }



    # 5. Handle DML (INSERT INTO) with Deep Row Count & Value Inspection (Fase 3)

    dml_tbl = extract_table_name_from_dml(submitted_query) or (extract_table_name_from_dml(expected_query) if expected_query else None)

    if ("INSERT INTO" in clean_q_upper) or (expected_query and "INSERT INTO" in expected_query.upper() and ("SELECT" not in clean_q_upper and "CREATE TABLE" not in clean_q_upper)):

        tbl_name = dml_tbl



        if not tbl_name:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "syntax_error",

                "feedback": "Sintaks INSERT INTO tidak valid: nama tabel target tidak dapat diidentifikasi.",

                "student_result": None

            }



        student_schema = get_clean_student_schema_name(nim)

        

        # Check if target table exists in student schema

        stud_conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

        try:

            stud_meta = inspect_table_catalog(student_schema, tbl_name, conn=stud_conn, dbname=DEFAULT_EXAM_DB)

        finally:

            if stud_conn and not stud_conn.closed:

                stud_conn.close()



        if not stud_meta.get("exists"):

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "table_not_found",

                "feedback": f"Tabel '{tbl_name}' belum dibuat di skema database pribadi Anda. Silakan jalankan perintah CREATE TABLE terlebih dahulu pada soal sebelumnya.",

                "student_result": None

            }



        # Execute student's INSERT INTO query in sandbox

        stud_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

        

        # If execution failed with syntax error other than duplicate key / unique constraint

        if not stud_res.get("success"):

            err_msg = stud_res.get("error", "")

            is_dup_key = ("duplicate key" in err_msg.lower() or "unique constraint" in err_msg.lower())

            if not is_dup_key:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "syntax_error",

                    "feedback": f"Error Eksekusi SQL: {err_msg}",

                    "student_result": stud_res

                }



        # If lecturer provided expected_query containing INSERT INTO

        if expected_query and ("INSERT INTO" in expected_query.upper()):

            # Compile reference DML in isolated temporary schema

            ref_dml_res = compile_reference_dml(expected_query, tbl_name, student_schema, dbname=DEFAULT_EXAM_DB)

            if not ref_dml_res.get("success"):

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "reference_error",

                    "feedback": f"Peringatan Evaluator: {ref_dml_res.get('error')}",

                    "student_result": stud_res

                }



            # Query student's current records in sandbox

            stud_query_res = execute_student_query(f"SELECT * FROM {tbl_name};", active_db=target_db_clean, nim=nim)

            if not stud_query_res.get("success"):

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "syntax_error",

                    "feedback": f"Gagal membaca data dari tabel '{tbl_name}': {stud_query_res.get('error')}",

                    "student_result": stud_query_res

                }



            # Deep record & value comparison

            is_valid, comp_msg, details = compare_table_records(

                ref_columns=ref_dml_res.get("columns", []),

                ref_rows=ref_dml_res.get("rows", []),

                stud_columns=stud_query_res.get("columns", []),

                stud_rows=stud_query_res.get("rows", []),

                table_name=tbl_name

            )



            if is_valid:

                return {

                    "is_correct": True,

                    "score": int(score_weight),

                    "eval_status": "correct",

                    "feedback": f"Sempurna! Seluruh {len(stud_query_res.get('rows', []))} baris data pada tabel '{tbl_name}' berhasil dimasukkan dan nilainya 100% cocok dengan acuan dosen (+{score_weight} Poin).",

                    "student_result": stud_query_res,

                    "diagnostics": details

                }

            else:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "wrong_data",

                    "feedback": comp_msg,

                    "student_result": stud_query_res,

                    "diagnostics": details

                }

        else:

            # Fallback if no expected_query specified: check if table has rows

            stud_query_res = execute_student_query(f"SELECT COUNT(*) FROM {tbl_name};", active_db=target_db_clean, nim=nim)

            cnt = stud_query_res.get("rows", [[0]])[0][0] if stud_query_res.get("rows") else 0

            if cnt > 0:

                return {

                    "is_correct": True,

                    "score": int(score_weight),

                    "eval_status": "correct",

                    "feedback": f"Sempurna! Data berhasil dimasukkan ke tabel '{tbl_name}' ({cnt} baris tersimpan) (+{score_weight} Poin).",

                    "student_result": stud_res

                }

            else:

                return {

                    "is_correct": False,

                    "score": 0,

                    "eval_status": "no_data_affected",

                    "feedback": f"Tabel '{tbl_name}' masih kosong setelah kueri dijalankan.",

                    "student_result": stud_res

                }



    # 6. Handle DROP TABLE in sandbox

    if clean_q_upper.startswith("DROP TABLE") and not ddl_tbl:

        stud_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

        if not stud_res.get("success"):

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "syntax_error",

                "feedback": f"Error Sintaks SQL: {stud_res.get('error')}",

                "student_result": stud_res

            }

        return {

            "is_correct": True,

            "score": int(score_weight),

            "eval_status": "correct",

            "feedback": f"Sempurna! Tabel berhasil dibersihkan dari skema database (+{score_weight} Poin).",

            "student_result": stud_res

        }



    # 7. Handle SELECT query evaluation

    stud_res = execute_student_query(submitted_query, active_db=target_db_clean, nim=nim)

    if not stud_res.get("success"):

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "syntax_error",

            "feedback": f"Error Sintaks SQL: {stud_res.get('error')}",

            "student_result": stud_res

        }



    if not expected_query or not expected_query.strip():

        # No reference query provided by lecturer -> award full points if executed successfully

        return {

            "is_correct": True,

            "score": int(score_weight),

            "eval_status": "correct",

            "feedback": f"Query berhasil dieksekusi dengan {stud_res.get('row_count', 0)} baris data (+{score_weight} Poin).",

            "student_result": stud_res

        }



    # Execute reference query on target database as admin

    exp_res = execute_student_query(expected_query, active_db=target_db_clean, nim="admin_ref")

    if not exp_res.get("success"):

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "reference_error",

            "feedback": f"Error pada Kunci Acuan Dosen: {exp_res.get('error')}. Laporkan ke pengawas ujian.",

            "student_result": stud_res

        }



    # Compare Column Counts

    stud_cols = stud_res.get("columns", [])

    exp_cols = exp_res.get("columns", [])

    if len(stud_cols) != len(exp_cols):

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "column_mismatch",

            "feedback": f"Jumlah kolom tidak sesuai. Diharapkan {len(exp_cols)} kolom ({', '.join(exp_cols)}), tetapi kueri Anda menghasilkan {len(stud_cols)} kolom ({', '.join(stud_cols)}).",

            "student_result": stud_res

        }



    # Compare Column Names

    stud_cols_norm = [c.lower() for c in stud_cols]

    exp_cols_norm = [c.lower() for c in exp_cols]

    if stud_cols_norm != exp_cols_norm:

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "column_mismatch",

            "feedback": f"Nama kolom tidak cocok. Diharapkan: [{', '.join(exp_cols)}], Ditemukan: [{', '.join(stud_cols)}]. Periksa alias atau urutan kolom.",

            "student_result": stud_res

        }



    # Compare Row Counts

    stud_rows = stud_res.get("rows", [])

    exp_rows = exp_res.get("rows", [])

    if len(stud_rows) != len(exp_rows):

        return {

            "is_correct": False,

            "score": 0,

            "eval_status": "row_count_mismatch",

            "feedback": f"Jumlah baris hasil tidak sesuai. Diharapkan {len(exp_rows)} baris, tetapi kueri Anda menghasilkan {len(stud_rows)} baris. Periksa klausa WHERE atau JOIN Anda.",

            "student_result": stud_res

        }



    # Compare Cell Values (Order-Insensitive unless ORDER BY specified)

    norm_stud_rows = [[_normalize_cell_value(cell) for cell in row] for row in stud_rows]

    norm_exp_rows = [[_normalize_cell_value(cell) for cell in row] for row in exp_rows]



    has_order_by = "ORDER BY" in expected_query.upper()



    if has_order_by:

        if norm_stud_rows != norm_exp_rows:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "wrong_order",

                "feedback": "Data hasil belum terurut dengan benar sesuai instruksi soal. Periksa kembali klausa ORDER BY Anda (ASC/DESC).",

                "student_result": stud_res

            }

    else:

        def row_sort_key(r):

            return tuple(str(x) for x in r)

        sorted_stud = sorted(norm_stud_rows, key=row_sort_key)

        sorted_exp = sorted(norm_exp_rows, key=row_sort_key)

        if sorted_stud != sorted_exp:

            return {

                "is_correct": False,

                "score": 0,

                "eval_status": "wrong_data",

                "feedback": "Data yang dihasilkan belum sesuai dengan kunci acuan dosen. Periksa kembali kondisi filter atau kalkulasi kueri Anda.",

                "student_result": stud_res

            }



    return {

        "is_correct": True,

        "score": int(score_weight),

        "eval_status": "correct",

        "feedback": f"Sempurna! Output kueri Anda 100% cocok dengan kunci acuan dosen (+{score_weight} Poin).",

        "student_result": stud_res

    }





def save_submission(

    user_id: int,

    question_id: int,

    submitted_query: str,

    is_correct: int = 0,

    score: int = 0,

    eval_status: str = "pending",

    feedback: str = ""

) -> Dict[str, Any]:

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute(

            """

            INSERT INTO submissions (user_id, question_id, submitted_query, submitted_at, status, is_correct, score, eval_status, feedback)

            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'submitted', ?, ?, ?, ?)

            ON CONFLICT(user_id, question_id) DO UPDATE SET

                submitted_query = excluded.submitted_query,

                submitted_at = CURRENT_TIMESTAMP,

                status = 'submitted',

                is_correct = excluded.is_correct,

                score = excluded.score,

                eval_status = excluded.eval_status,

                feedback = excluded.feedback;

            """,

            (user_id, question_id, submitted_query, is_correct, score, eval_status, feedback)

        )

        cur.execute(

            """

            INSERT INTO exam_logs (user_id, action_type, details)

            VALUES (?, 'submit', ?);

            """,

            (user_id, f"Jawaban untuk Soal ID {question_id} disubmit (Nilai: {score}, Benar: {bool(is_correct)})")

        )

    conn.close()

    return {"status": "success", "message": "Jawaban berhasil disimpan"}



def get_student_submissions(user_id: int) -> Dict[int, Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT * FROM submissions WHERE user_id = ?;", (user_id,))

    rows = cur.fetchall()

    conn.close()

    return {r["question_id"]: dict(r) for r in rows}



def get_all_students_progress() -> List[Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    

    # Calculate online status based on 60-second inactivity window

    query = """

    SELECT 

        u.id,

        u.nim,

        u.name,

        u.ip_address,

        u.status AS raw_status,

        u.last_active,

        u.selected_category,

        COUNT(s.id) AS total_submitted,

        COALESCE(SUM(s.score), 0) AS total_score,

        (

            SELECT COUNT(*) 

            FROM exam_logs l 

            WHERE l.user_id = u.id AND l.action_type = 'blur_tab'

        ) AS tab_switches

    FROM users u

    LEFT JOIN submissions s ON u.id = s.user_id

    GROUP BY u.id

    ORDER BY u.nim ASC;

    """

    cur.execute(query)

    rows = cur.fetchall()

    conn.close()



    result = []

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    for r in rows:

        row_dict = dict(r)

        last_active = r["last_active"]

        is_live = False

        if last_active:

            try:

                # Handle sqlite timestamp

                dt = datetime.datetime.fromisoformat(last_active.replace("Z", ""))

                if (now - dt).total_seconds() < 90 and row_dict["raw_status"] == "online":

                    is_live = True

            except Exception:

                is_live = (row_dict["raw_status"] == "online")



        row_dict["is_active"] = is_live

        result.append(row_dict)

    return result



def log_exam_event(user_id: Optional[int], action_type: str, details: str):

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            """

            INSERT INTO exam_logs (user_id, action_type, details)

            VALUES (?, ?, ?);

            """,

            (user_id, action_type, details)

        )

    conn.close()



def get_recent_exam_logs(limit: int = 40) -> List[Dict[str, Any]]:

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute(

        """

        SELECT l.id, l.user_id, u.nim, u.name, l.action_type, l.details, l.timestamp

        FROM exam_logs l

        LEFT JOIN users u ON l.user_id = u.id

        ORDER BY l.id DESC

        LIMIT ?;

        """,

        (limit,)

    )

    rows = cur.fetchall()

    conn.close()

    return [dict(r) for r in rows]



# ------------------------------------------------------------------------------

# Result Export: CSV and ZIP (.sql files per student)

# ------------------------------------------------------------------------------



def export_all_submissions_csv() -> str:
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            u.nim,
            u.name,
            u.ip_address,
            q.question_number,
            q.title AS question_title,
            q.score_weight,
            s.score,
            s.is_correct,
            s.submitted_query,
            s.submitted_at
        FROM submissions s
        JOIN users u ON s.user_id = u.id
        JOIN questions q ON s.question_id = q.id
        ORDER BY u.nim ASC, q.question_number ASC;
        """
    )
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "NIM", "Nama Mahasiswa", "IP Address",
        "Nomor Soal", "Judul Soal", "Bobot Nilai",
        "Nilai Diperoleh", "Status Evaluasi",
        "Query Jawaban", "Waktu Submit"
    ])
    for r in rows:
        status_text = "BENAR" if r["is_correct"] else "BELUM TEPAT"
        awarded_score = r["score"] if r["score"] is not None else 0
        writer.writerow([
            r["nim"], r["name"], r["ip_address"],
            r["question_number"], r["question_title"], r["score_weight"],
            awarded_score, status_text,
            r["submitted_query"], r["submitted_at"]
        ])
    return output.getvalue()



def export_submissions_zip_bytes() -> bytes:
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nim, name FROM users ORDER BY nim ASC;")
    users = cur.fetchall()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for u in users:
            user_id = u["id"]
            nim = u["nim"]
            name = re.sub(r'[^a-zA-Z0-9_-]', '_', u["name"])

            cur.execute(
                """
                SELECT q.question_number, q.title, q.score_weight, s.submitted_query, s.submitted_at, s.score, s.is_correct
                FROM questions q
                LEFT JOIN submissions s ON q.id = s.question_id AND s.user_id = ?
                ORDER BY q.question_number ASC;
                """,
                (user_id,)
            )
            q_rows = cur.fetchall()

            file_content = [
                f"-- ============================================================",
                f"-- Lembar Jawaban Ujian Praktikum Basis Data",
                f"-- NIM  : {nim}",
                f"-- Nama : {u['name']}",
                f"-- Diekspor pada: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"-- ============================================================\n"
            ]

            for qr in q_rows:
                q_num = qr["question_number"]
                q_title = qr["title"]
                q_weight = qr["score_weight"]
                ans = qr["submitted_query"] or "-- BELUM DIJAWAB"
                submit_time = qr["submitted_at"] or "-"
                score = qr["score"] if qr["score"] is not None else 0
                status_label = "BENAR" if qr["is_correct"] else ("BELUM TEPAT" if qr["submitted_query"] else "BELUM DIJAWAB")

                file_content.append(f"-- ------------------------------------------------------------")
                file_content.append(f"-- SOAL NO. {q_num}: {q_title} (Bobot: {q_weight} | Nilai Diperoleh: {score} | Status: {status_label})")
                file_content.append(f"-- Waktu Submit: {submit_time}")
                file_content.append(f"-- ------------------------------------------------------------")

                clean_ans = ans.strip()
                if not clean_ans.startswith("--") and not clean_ans.endswith(";"):
                    clean_ans += ";"
                file_content.append(f"{clean_ans}\n")

            sql_data = "\n".join(file_content)
            zip_file.writestr(f"{nim}_{name}.sql", sql_data)

    conn.close()
    zip_buffer.seek(0)
    return zip_buffer.getvalue()



def export_all_logs_csv() -> str:

    """Mengekspor seluruh riwayat log aktivitas ujian sistem ke format CSV."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute(

        """

        SELECT 

            l.id,

            l.timestamp,

            COALESCE(u.nim, '-') AS nim,

            COALESCE(u.name, 'Sistem / Pengawas') AS name,

            COALESCE(u.ip_address, '-') AS ip_address,

            l.action_type,

            COALESCE(l.details, '-') AS details

        FROM exam_logs l

        LEFT JOIN users u ON l.user_id = u.id

        ORDER BY l.id ASC;

        """

    )

    rows = cur.fetchall()

    conn.close()



    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([

        "ID Log", 

        "Waktu", 

        "NIM", 

        "Nama Mahasiswa", 

        "IP Address", 

        "Tipe Aksi", 

        "Detail Aktivitas"

    ])

    for r in rows:

        writer.writerow([

            r["id"],

            r["timestamp"],

            r["nim"],

            r["name"],

            r["ip_address"],

            r["action_type"],

            r["details"]

        ])

    return output.getvalue()



def export_tab_switches_csv() -> str:

    """

    Mengekspor rekapitulasi data perpindahan tab & fokus jendela mahasiswa ke format CSV.

    Menampilkan seluruh mahasiswa beserta jumlah peringatan dan riwayat waktu kejadian kronologis.

    """

    conn = get_sqlite_conn()

    cur = conn.cursor()

    

    cur.execute(

        """

        SELECT 

            u.id,

            u.nim,

            u.name,

            u.ip_address,

            u.status,

            u.last_active,

            (

                SELECT COUNT(*) 

                FROM exam_logs l 

                WHERE l.user_id = u.id AND l.action_type = 'blur_tab'

            ) AS tab_switches

        FROM users u

        ORDER BY tab_switches DESC, u.nim ASC;

        """

    )

    users = cur.fetchall()



    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([

        "NIM", 

        "Nama Mahasiswa", 

        "IP Address", 

        "Total Peringatan Tab", 

        "Status Sesi",

        "Waktu Kejadian", 

        "Aksi", 

        "Detail Aktivitas"

    ])



    for u in users:

        user_id = u["id"]

        nim = u["nim"]

        name = u["name"]

        ip = u["ip_address"] or "-"

        switches_count = u["tab_switches"]

        status = u["status"] or "offline"



        cur.execute(

            """

            SELECT action_type, details, timestamp

            FROM exam_logs

            WHERE user_id = ? AND action_type IN ('blur_tab', 'focus_tab')

            ORDER BY id ASC;

            """,

            (user_id,)

        )

        logs = cur.fetchall()



        if logs:

            for l in logs:

                writer.writerow([

                    nim,

                    name,

                    ip,

                    switches_count,

                    status,

                    l["timestamp"],

                    l["action_type"],

                    l["details"]

                ])

        else:

            writer.writerow([

                nim,

                name,

                ip,

                0,

                status,

                "-",

                "NIHIL",

                "Tidak ada catatan perpindahan tab (tertib)"

            ])



    # Cek apakah ada log perpindahan tab tanpa user_id

    cur.execute(

        """

        SELECT action_type, details, timestamp

        FROM exam_logs

        WHERE user_id IS NULL AND action_type IN ('blur_tab', 'focus_tab')

        ORDER BY id ASC;

        """

    )

    anon_logs = cur.fetchall()

    for l in anon_logs:

        writer.writerow([

            "-",

            "Anonim / Sesi Tidak Valid",

            "-",

            "-",

            "-",

            l["timestamp"],

            l["action_type"],

            l["details"]

        ])



    conn.close()

    return output.getvalue()





# ==============================================================================

# PostgreSQL Exam Database (Sandbox & Execution Engine)

# ==============================================================================



def init_postgres_db() -> Tuple[bool, str]:

    """

    Menginisialisasi PostgreSQL secara otomatis pada run pertama kali:

    1. Mengecek koneksi ke server PostgreSQL.

    2. Membuat database 'classicmodels' jika belum ada.

    3. Membuat role 'student_role' dengan izin read-only jika belum ada.

    4. Mengisi dataset awal dari data/classicmodels.sql jika database masih kosong.

    """

    admin_pass = PG_ADMIN_PASS or None

    

    # 1. Coba koneksi ke PostgreSQL

    conn = None

    try:

        conn = psycopg2.connect(

            dbname=PG_DB,

            user=PG_ADMIN_USER,

            password=admin_pass,

            host=PG_HOST,

            port=PG_PORT

        )

    except psycopg2.OperationalError as e:

        err_str = str(e)

        # Jika database belum ada, buat database secara otomatis

        if "does not exist" in err_str or "tidak ada" in err_str:

            fallback_conn = None

            for default_db in ("postgres", "template1"):

                try:

                    fallback_conn = psycopg2.connect(

                        dbname=default_db,

                        user=PG_ADMIN_USER,

                        password=admin_pass,

                        host=PG_HOST,

                        port=PG_PORT

                    )

                    break

                except Exception:

                    continue



            if not fallback_conn:

                return False, f"PostgreSQL berjalan, tetapi database '{PG_DB}' belum ada dan gagal terhubung ke database default (postgres/template1) untuk membuatnya: {err_str}"



            try:

                fallback_conn.autocommit = True

                cur = fallback_conn.cursor()

                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(PG_DB)))

                cur.close()

                fallback_conn.close()



                # Hubungkan ke database yang baru dibuat

                conn = psycopg2.connect(

                    dbname=PG_DB,

                    user=PG_ADMIN_USER,

                    password=admin_pass,

                    host=PG_HOST,

                    port=PG_PORT

                )

            except Exception as create_err:

                return False, f"Gagal membuat database '{PG_DB}': {create_err}"

        else:

            return False, f"PostgreSQL belum dapat diakses ({PG_HOST}:{PG_PORT}): {err_str}"

    except Exception as e:

        return False, f"Gagal koneksi PostgreSQL: {e}"



    # 2. Setup student_role dan muat dataset jika database masih kosong

    try:

        conn.autocommit = True

        cur = conn.cursor()



        # Buat atau sinkronkan student_role

        cur.execute(f"""

        DO $$

        BEGIN

            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{PG_STUDENT_USER}') THEN

                CREATE ROLE {PG_STUDENT_USER} WITH LOGIN PASSWORD '{PG_STUDENT_PASS}';

            ELSE

                ALTER ROLE {PG_STUDENT_USER} WITH LOGIN PASSWORD '{PG_STUDENT_PASS}';

            END IF;

        END

        $$;

        """)



        # Periksa apakah sudah ada tabel di user schemas

        cur.execute("""

            SELECT COUNT(*) 

            FROM information_schema.tables 

            WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')

              AND table_schema NOT LIKE 'pg_%%'

              AND table_type = 'BASE TABLE';

        """)

        table_count = cur.fetchone()[0]

        cur.close()

        conn.close()



        # Jika database masih baru/kosong, isi dataset awal secara otomatis

        if table_count == 0:

            ok, msg = reset_classicmodels_database()

            if not ok:

                return False, f"Database '{PG_DB}' dibuat, namun gagal memuat dataset: {msg}"

            return True, f"Database '{PG_DB}', role '{PG_STUDENT_USER}', dan dataset master berhasil diinisialisasi otomatis."



        return True, f"Database '{PG_DB}' dan role '{PG_STUDENT_USER}' siap digunakan ({table_count} tabel aktif)."

    except Exception as e:

        if conn and not conn.closed:

            conn.close()

        return False, f"Gagal setup PostgreSQL: {e}"



def get_pg_admin_connection(dbname: str = DEFAULT_EXAM_DB):

    """Returns an administrative connection to PostgreSQL."""

    target_db = DEFAULT_EXAM_DB if dbname == "sandbox_pribadi" else dbname

    conn = psycopg2.connect(

        dbname=target_db,

        user=PG_ADMIN_USER,

        password=PG_ADMIN_PASS or None,

        host=PG_HOST,

        port=PG_PORT

    )

    return conn



# Multi-Database pools dictionary: { "pagila": pool, "classicmodels": pool }

_PG_POOL_LOCK = threading.Lock()

_SANDBOX_INIT_LOCK = threading.Lock()

_INITIALIZED_SANDBOX_SCHEMAS: Set[str] = set()



PG_DB_POOLS: Dict[str, pool.ThreadedConnectionPool] = {}

PG_STUDENT_POOL: Optional[pool.ThreadedConnectionPool] = None



def get_pg_student_pool_for_db(dbname: str = DEFAULT_EXAM_DB) -> pool.ThreadedConnectionPool:

    global PG_DB_POOLS

    target_dbname = DEFAULT_EXAM_DB if dbname == "sandbox_pribadi" else dbname

    if target_dbname not in ["pagila", "classicmodels", "praktikum_db"]:

        target_dbname = DEFAULT_EXAM_DB



    if target_dbname not in PG_DB_POOLS or PG_DB_POOLS[target_dbname] is None or PG_DB_POOLS[target_dbname].closed:

        with _PG_POOL_LOCK:

            if target_dbname not in PG_DB_POOLS or PG_DB_POOLS[target_dbname] is None or PG_DB_POOLS[target_dbname].closed:

                PG_DB_POOLS[target_dbname] = pool.ThreadedConnectionPool(

                    minconn=2,

                    maxconn=35,

                    dbname=target_dbname,

                    user=PG_STUDENT_USER,

                    password=PG_STUDENT_PASS or None,

                    host=PG_HOST,

                    port=PG_PORT

                )

    return PG_DB_POOLS[target_dbname]



def get_pg_student_pool() -> pool.ThreadedConnectionPool:

    return get_pg_student_pool_for_db(DEFAULT_EXAM_DB)



def close_pg_pools():

    """Safely closes all pooled PostgreSQL connections across all databases."""

    global PG_DB_POOLS, PG_STUDENT_POOL

    for db_name, pool_inst in list(PG_DB_POOLS.items()):

        if pool_inst and not pool_inst.closed:

            try:

                pool_inst.closeall()

            except Exception:

                pass

    PG_DB_POOLS.clear()

    PG_STUDENT_POOL = None



def get_pg_student_connection(dbname: str = DEFAULT_EXAM_DB):

    """Returns a sandboxed student connection to PostgreSQL for the specified database."""

    target_dbname = DEFAULT_EXAM_DB if dbname == "sandbox_pribadi" else dbname

    try:

        conn = psycopg2.connect(

            dbname=target_dbname,

            user=PG_STUDENT_USER,

            password=PG_STUDENT_PASS or None,

            host=PG_HOST,

            port=PG_PORT

        )

    except Exception:

        conn = get_pg_admin_connection(target_dbname)

        conn.autocommit = False

        cur = conn.cursor()

        cur.execute("SET ROLE student_role;")

        cur.close()

    return conn



def get_clean_student_schema_name(nim: Optional[str]) -> str:

    """Sanitizes student NIM to form a safe schema name (e.g. sandbox_220101001)."""

    if not nim:

        return "sandbox_default"

    clean_nim = re.sub(r'[^a-zA-Z0-9_]', '', str(nim).strip()).lower()

    return f"sandbox_{clean_nim}" if clean_nim else "sandbox_default"



def init_student_sandbox_schema(nim: Optional[str]) -> str:

    """

    Creates a dedicated sandbox schema for a student if not already present.

    Grants USAGE and CREATE privileges to student_role inside this schema only.

    Uses memory cache and thread lock to prevent redundant DDL executions and connection exhaustion.

    """

    schema_name = get_clean_student_schema_name(nim)

    if schema_name in _INITIALIZED_SANDBOX_SCHEMAS:

        return schema_name



    with _SANDBOX_INIT_LOCK:

        if schema_name in _INITIALIZED_SANDBOX_SCHEMAS:

            return schema_name

        try:

            conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

            conn.autocommit = True

            cur = conn.cursor()

            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier(schema_name)))

            cur.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO student_role;").format(sql.Identifier(schema_name)))

            cur.execute(sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA {} TO student_role;").format(sql.Identifier(schema_name)))

            cur.execute(sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA {} TO student_role;").format(sql.Identifier(schema_name)))

            cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT ALL ON TABLES TO student_role;").format(sql.Identifier(schema_name)))

            cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT ALL ON SEQUENCES TO student_role;").format(sql.Identifier(schema_name)))

            cur.close()

            conn.close()

            _INITIALIZED_SANDBOX_SCHEMAS.add(schema_name)

        except Exception as e:

            print(f"Error initializing student sandbox schema {schema_name}: {e}")

    return schema_name



def cleanup_student_sandbox_schema(nim: Optional[str]) -> bool:

    """Drops the student's sandbox schema and all contained dummy tables."""

    schema_name = get_clean_student_schema_name(nim)

    with _SANDBOX_INIT_LOCK:

        _INITIALIZED_SANDBOX_SCHEMAS.discard(schema_name)

    try:

        conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

        conn.autocommit = True

        cur = conn.cursor()

        cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(schema_name)))

        cur.close()

        conn.close()

        return True

    except Exception as e:

        print(f"Error dropping student sandbox schema {schema_name}: {e}")

        return False



def split_sql_statements(sql_text: str) -> List[str]:

    """Splits a multi-statement SQL script into individual statements, ignoring semicolons inside quotes/comments."""

    statements = []

    current = []

    in_single_quote = False

    in_double_quote = False

    in_line_comment = False

    in_block_comment = False

    i = 0

    n = len(sql_text)

    while i < n:

        c = sql_text[i]

        next_c = sql_text[i + 1] if i + 1 < n else ''

        

        # Check comments

        if not in_single_quote and not in_double_quote:

            if not in_block_comment and c == '-' and next_c == '-':

                in_line_comment = True

                i += 2

                continue

            if in_line_comment:

                if c == '\n':

                    in_line_comment = False

                i += 1

                continue

            if not in_line_comment and c == '/' and next_c == '*':

                in_block_comment = True

                i += 2

                continue

            if in_block_comment:

                if c == '*' and next_c == '/':

                    in_block_comment = False

                    i += 2

                    continue

                i += 1

                continue

        

        # Check quotes

        if c == "'" and not in_double_quote and not in_line_comment and not in_block_comment:

            if in_single_quote and next_c == "'":

                current.append("''")

                i += 2

                continue

            in_single_quote = not in_single_quote

            current.append(c)

            i += 1

            continue

        elif c == '"' and not in_single_quote and not in_line_comment and not in_block_comment:

            in_double_quote = not in_double_quote

            current.append(c)

            i += 1

            continue

            

        # Semicolon outside quotes/comments

        if c == ';' and not in_single_quote and not in_double_quote and not in_line_comment and not in_block_comment:

            stmt = "".join(current).strip()

            if stmt:

                statements.append(stmt)

            current = []

            i += 1

            continue

            

        current.append(c)

        i += 1

        

    last_stmt = "".join(current).strip()

    if last_stmt:

        statements.append(last_stmt)

    return statements



def check_dangerous_sql(query_text: str, is_sandbox_student: bool = False) -> Optional[str]:

    """Inspects query text for prohibited operations."""

    cleaned = re.sub(r'--.*?$|/\*.*?\*/', '', query_text, flags=re.MULTILINE)

    

    if is_sandbox_student:

        # In student sandbox mode (Level Easy), student is allowed to CREATE DATABASE (emulated), CREATE TABLE, INSERT, DROP TABLE, DROP DATABASE (emulated)

        forbidden_patterns = [

            r'\bDROP\s+DATABASE\s+(postgres|pagila|classicmodels|praktikum_db|template\d+)\b',

            r'\bDROP\s+(SCHEMA|ROLE|USER)\b',

            r'\bALTER\s+(ROLE|USER|DATABASE|SYSTEM)\b',

            r'\bTRUNCATE\s+(SCHEMA|DATABASE)\b',

            r'\bGRANT\b',

            r'\bREVOKE\b',

            r'\bCREATE\s+(ROLE|USER|EXTENSION|SCHEMA)\b',

            r'\bCOPY\b',

            r'\bVACUUM\b',

            r'\bpg_read_file\b',

            r'\bpg_write_file\b',

            r'\blo_import\b',

            r'\blo_export\b',

            r'\bdblink\b',

            r'\bpg_sleep\b',

            r'\bpg_terminate_backend\b',

            r'\bpg_cancel_backend\b',

            r'\bcurrent_setting\b',

            r'\bSET\s+(SESSION\s+|LOCAL\s+)?statement_timeout\b',

            r'\bpg_authid\b',

            r'\bpg_shadow\b'

        ]

    else:

        # Strictly prohibited commands for standard master databases (pagila, classicmodels)

        forbidden_patterns = [

            r'\bDROP\b',

            r'\bALTER\b',

            r'\bTRUNCATE\b',

            r'\bGRANT\b',

            r'\bREVOKE\b',

            r'\bCREATE\s+(ROLE|USER|DATABASE|EXTENSION)\b',

            r'\bCOPY\b',

            r'\bVACUUM\b',

            r'\bpg_read_file\b',

            r'\bpg_write_file\b',

            r'\blo_import\b',

            r'\blo_export\b',

            r'\bdblink\b',

            r'\bpg_sleep\b',

            r'\bpg_terminate_backend\b',

            r'\bpg_cancel_backend\b',

            r'\bcurrent_setting\b',

            r'\bSET\s+(SESSION\s+|LOCAL\s+)?statement_timeout\b',

            r'\bpg_authid\b',

            r'\bpg_shadow\b'

        ]

        

    for pat in forbidden_patterns:

        if re.search(pat, cleaned, re.IGNORECASE):

            match_word = re.search(pat, cleaned, re.IGNORECASE).group(0)

            return f"Perintah berbahaya terdeteksi ('{match_word}'). Operasi ini dilarang pada sistem ujian!"

    return None



def execute_student_query(

    query_text: str,

    active_db: str = DEFAULT_EXAM_DB,

    nim: Optional[str] = None

) -> Dict[str, Any]:

    """

    Executes a student query within the specified PostgreSQL database sandbox.

    Supports:

    - Multi-Database routing (pagila, classicmodels, sandbox_pribadi)

    - Dedicated schema sandbox per student for Level Easy (CREATE/INSERT/DROP)

    - 3-second statement_timeout

    - Read-only rollback for master databases, autocommit persistence for sandbox schema

    """

    query_text = (query_text or "").strip()

    if not query_text:

        return {"success": False, "error": "Query SQL tidak boleh kosong."}



    active_db = (active_db or DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()

    is_sandbox = (active_db == "sandbox_pribadi")



    # Remove trailing semicolon if single query

    clean_query = query_text

    if clean_query.endswith(";"):

        clean_query = clean_query[:-1].strip()



    danger_error = check_dangerous_sql(clean_query, is_sandbox_student=is_sandbox)

    if danger_error:

        return {"success": False, "error": danger_error}



    start_time = time.time()

    conn = None

    pool_inst = None

    try:

        if is_sandbox:

            schema_name = init_student_sandbox_schema(nim or "default")

            pool_inst = get_pg_student_pool_for_db(DEFAULT_EXAM_DB)

            conn = pool_inst.getconn()

            conn.autocommit = True

            cur = conn.cursor()

            cur.execute("SET statement_timeout = 3000;")

            cur.execute(sql.SQL("SET search_path TO {}, public;").format(sql.Identifier(schema_name)))



            # Split statements to intercept CREATE DATABASE, USE, DROP DATABASE

            stmts = split_sql_statements(clean_query)

            last_desc = None

            total_affected = 0

            executed_any_pg = False

            created_virtual_db = None

            dropped_virtual_db = None



            for st in stmts:

                st_strip = st.strip()

                if not st_strip:

                    continue



                # Intercept CREATE DATABASE

                m_cdb = re.match(r'^\s*CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)', st_strip, re.IGNORECASE)

                if m_cdb:

                    created_virtual_db = m_cdb.group(1).lower()

                    set_student_virtual_database(nim, created_virtual_db)

                    try:

                        cur.execute(sql.SQL("COMMENT ON SCHEMA {} IS %s;").format(sql.Identifier(schema_name)), (f"virtual_db:{created_virtual_db}",))

                    except Exception:

                        pass

                    continue



                # Intercept DROP DATABASE

                m_ddb = re.match(r'^\s*DROP\s+DATABASE\s+(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_]+)', st_strip, re.IGNORECASE)

                if m_ddb:

                    target_drop = m_ddb.group(1).lower()

                    if target_drop in {"postgres", "pagila", "classicmodels", "template0", "template1", "praktikum_db"}:

                        cur.close()

                        pool_inst.putconn(conn)

                        return {"success": False, "error": f"Pelanggaran Keamanan: Dilarang menghapus database sistem '{target_drop}'!"}

                    dropped_virtual_db = target_drop

                    clear_student_virtual_database(nim)

                    try:

                        cur.execute(sql.SQL("""

                            DO $$ DECLARE

                                r RECORD;

                            BEGIN

                                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = {sch}) LOOP

                                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident({sch}) || '.' || quote_ident(r.tablename) || ' CASCADE';

                                END LOOP;

                            END $$;

                        """).format(sch=sql.Literal(schema_name)))

                        cur.execute(sql.SQL("COMMENT ON SCHEMA {} IS NULL;").format(sql.Identifier(schema_name)))

                    except Exception:

                        pass

                    continue



                # Intercept USE <database>

                m_use = re.match(r'^\s*USE\s+([a-zA-Z0-9_]+)', st_strip, re.IGNORECASE)

                if m_use:

                    target_use = m_use.group(1).lower()

                    set_student_virtual_database(nim, target_use)

                    continue



                # Execute statement in PostgreSQL

                cur.execute(st_strip)

                executed_any_pg = True

                last_desc = cur.description

                if cur.rowcount and cur.rowcount > 0:

                    total_affected += cur.rowcount



            columns = []

            rows = []

            row_count = 0

            is_truncated = False



            if executed_any_pg and last_desc:

                columns = [desc[0] for desc in last_desc]

                fetched = cur.fetchmany(501)

                row_count = len(fetched)

                if row_count > 500:

                    is_truncated = True

                    fetched = fetched[:500]

                    row_count = 500



                for r in fetched:

                    row_items = []

                    for val in r:

                        if isinstance(val, (datetime.date, datetime.datetime)):

                            row_items.append(val.isoformat())

                        elif hasattr(val, '__float__'):

                            row_items.append(float(val))

                        elif val is None:

                            row_items.append(None)

                        else:

                            row_items.append(str(val))

                    rows.append(row_items)

            else:

                row_count = total_affected



            execution_time_ms = round((time.time() - start_time) * 1000, 2)

            cur.close()

            pool_inst.putconn(conn)

            conn = None



            current_vdb = get_student_virtual_database(nim) or ""

            if created_virtual_db and not executed_any_pg:

                msg = f"Query OK. Database virtual '{created_virtual_db}' berhasil dibuat di sandbox pribadi Anda ({execution_time_ms} ms)."

            elif dropped_virtual_db and not executed_any_pg:

                msg = f"Query OK. Database '{dropped_virtual_db}' dan seluruh tabelnya berhasil dibersihkan dari sandbox pribadi Anda ({execution_time_ms} ms)."

            elif created_virtual_db and executed_any_pg:

                msg = f"Database virtual '{created_virtual_db}' aktif. Perintah SQL ({row_count} baris terpengaruh) berhasil dijalankan ({execution_time_ms} ms)."

            elif not last_desc:

                msg = f"Perintah SQL berhasil dijalankan ({row_count} baris terpengaruh) dalam {execution_time_ms} ms."

            else:

                msg = f"Query berhasil dieksekusi ({row_count} baris) dalam {execution_time_ms} ms."



            return {

                "success": True,

                "columns": columns,

                "rows": rows,

                "row_count": row_count,

                "is_truncated": is_truncated,

                "execution_time_ms": execution_time_ms,

                "message": msg,

                "virtual_db": current_vdb

            }

        else:

            pool_inst = get_pg_student_pool_for_db(active_db)

            conn = pool_inst.getconn()

            conn.autocommit = False

            cur = conn.cursor()

            cur.execute("SET statement_timeout = 3000;")

            cur.execute("SET search_path TO public;")

            cur.execute(clean_query)



            columns = []

            rows = []

            row_count = 0

            is_truncated = False



            if cur.description:

                columns = [desc[0] for desc in cur.description]

                fetched = cur.fetchmany(501)

                row_count = len(fetched)

                if row_count > 500:

                    is_truncated = True

                    fetched = fetched[:500]

                    row_count = 500



                for r in fetched:

                    row_items = []

                    for val in r:

                        if isinstance(val, (datetime.date, datetime.datetime)):

                            row_items.append(val.isoformat())

                        elif hasattr(val, '__float__'):

                            row_items.append(float(val))

                        elif val is None:

                            row_items.append(None)

                        else:

                            row_items.append(str(val))

                    rows.append(row_items)

            else:

                row_count = cur.rowcount if cur.rowcount != -1 else 0



            execution_time_ms = round((time.time() - start_time) * 1000, 2)



            conn.rollback()

            cur.close()

            pool_inst.putconn(conn)

            conn = None



            msg = f"Query berhasil dieksekusi ({row_count} baris) dalam {execution_time_ms} ms."

            if not cur.description:

                msg = f"Perintah SQL berhasil dijalankan ({row_count} baris terpengaruh) dalam {execution_time_ms} ms."



            return {

                "success": True,

                "columns": columns,

                "rows": rows,

                "row_count": row_count,

                "is_truncated": is_truncated,

                "execution_time_ms": execution_time_ms,

                "message": msg

            }



    except psycopg2.extensions.QueryCanceledError:

        if conn and not conn.closed:

            try:

                conn.rollback()

            except Exception:

                pass

        return {"success": False, "error": "Query timeout: Waktu eksekusi melebihi batas 3000 ms (3 detik)."}

    except Exception as e:

        if conn and not conn.closed and not is_sandbox:

            try:

                conn.rollback()

            except Exception:

                pass

        return {"success": False, "error": f"PostgreSQL Error: {str(e)}"}

    finally:

        if conn and not conn.closed and pool_inst:

            try:

                pool_inst.putconn(conn)

            except Exception:

                pass





# ==============================================================================

# Auto-Grader Deep DDL & DML Inspection Engine (Fase 1 & Fase 2)

# ==============================================================================



def extract_table_name_from_ddl(ddl_sql: str) -> Optional[str]:

    """

    Extracts the targeted table name from a CREATE TABLE query.

    Handles optional IF NOT EXISTS, schema qualifiers, quotes, and backticks.

    """

    if not ddl_sql:

        return None

    match = re.search(

        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[`"]?[a-zA-Z0-9_]+[`"]?\.)?[`"]?([a-zA-Z0-9_]+)[`"]?',

        ddl_sql,

        re.IGNORECASE

    )

    return match.group(1).lower() if match else None



def inspect_table_catalog(

    schema_name: str,

    table_name: str,

    conn=None,

    dbname: str = DEFAULT_EXAM_DB

) -> Dict[str, Any]:

    """

    Introspects the exact PostgreSQL catalog structure of a table:

    - columns: name, data_type, udt_name, is_nullable, character_maximum_length, numeric_precision, numeric_scale, column_default

    - constraints: PRIMARY KEY, FOREIGN KEY, UNIQUE

    """

    should_close = False

    if conn is None:

        conn = get_pg_admin_connection(dbname=dbname)

        should_close = True



    try:

        cur = conn.cursor()

        cur.execute("""

            SELECT column_name, data_type, udt_name, is_nullable,

                   character_maximum_length, numeric_precision, numeric_scale,

                   column_default, ordinal_position

            FROM information_schema.columns

            WHERE table_schema = %s AND table_name = %s

            ORDER BY ordinal_position;

        """, (schema_name.lower(), table_name.lower()))

        col_rows = cur.fetchall()



        if not col_rows:

            return {

                "exists": False,

                "table_name": table_name,

                "schema": schema_name,

                "columns": [],

                "constraints": {"primary_key": [], "foreign_keys": [], "unique": []}

            }



        columns = []

        for r in col_rows:

            columns.append({

                "name": r[0],

                "data_type": r[1],

                "udt_name": r[2],

                "is_nullable": (r[3] == "YES"),

                "character_maximum_length": r[4],

                "numeric_precision": r[5],

                "numeric_scale": r[6],

                "column_default": r[7],

                "ordinal_position": r[8]

            })



        cur.execute("""

            SELECT tc.constraint_type, kcu.column_name, tc.constraint_name

            FROM information_schema.table_constraints tc

            JOIN information_schema.key_column_usage kcu

              ON tc.constraint_name = kcu.constraint_name

              AND tc.table_schema = kcu.table_schema

            WHERE tc.table_schema = %s AND tc.table_name = %s

            ORDER BY tc.constraint_type, kcu.ordinal_position;

        """, (schema_name.lower(), table_name.lower()))

        const_rows = cur.fetchall()



        pks = []

        fks = []

        uniques = []

        for ctype, cname, _ in const_rows:

            ctype_upper = ctype.upper()

            if ctype_upper == 'PRIMARY KEY' and cname not in pks:

                pks.append(cname)

            elif ctype_upper == 'FOREIGN KEY' and cname not in fks:

                fks.append(cname)

            elif ctype_upper == 'UNIQUE' and cname not in uniques:

                uniques.append(cname)



        cur.close()

        return {

            "exists": True,

            "table_name": table_name,

            "schema": schema_name,

            "columns": columns,

            "constraints": {

                "primary_key": pks,

                "foreign_keys": fks,

                "unique": uniques

            }

        }

    finally:

        if should_close and conn and not conn.closed:

            conn.close()



def compile_reference_ddl(

    expected_ddl_sql: str,

    dbname: str = DEFAULT_EXAM_DB

) -> Dict[str, Any]:

    """

    Compiles the lecturer's expected DDL query inside an isolated temporary schema.

    Introspects the generated catalog metadata, and cleanly drops the temporary schema.

    Guarantees ZERO schema leaks.

    """

    tbl_name = extract_table_name_from_ddl(expected_ddl_sql)

    if not tbl_name:

        return {

            "exists": False,

            "error": "Tidak dapat mendeteksi nama tabel dari kunci acuan DDL dosen."

        }



    temp_schema = f"_ref_compile_{uuid.uuid4().hex[:12]}"

    conn = get_pg_admin_connection(dbname=dbname)

    conn.autocommit = True

    cur = conn.cursor()



    try:

        cur.execute(f"CREATE SCHEMA {temp_schema};")

        cur.execute(f"SET search_path TO {temp_schema}, public;")

        cur.execute(expected_ddl_sql)

        meta = inspect_table_catalog(temp_schema, tbl_name, conn=conn, dbname=dbname)

        return meta

    except Exception as e:

        return {

            "exists": False,

            "error": f"Gagal mengeksekusi kunci acuan DDL dosen: {str(e)}"

        }

    finally:

        try:

            cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")

        except Exception:

            pass

        cur.close()

        conn.close()



def normalize_type_label(col_info: Dict[str, Any]) -> str:

    """Returns a readable SQL type representation (e.g. VARCHAR(100), NUMERIC(12,2), INT)."""

    dtype = (col_info.get("data_type") or "").upper()

    udt = (col_info.get("udt_name") or "").lower()

    

    if dtype == "CHARACTER VARYING":

        max_len = col_info.get("character_maximum_length")

        return f"VARCHAR({max_len})" if max_len else "VARCHAR"

    elif dtype == "CHARACTER":

        max_len = col_info.get("character_maximum_length")

        return f"CHAR({max_len})" if max_len else "CHAR"

    elif dtype == "INTEGER" or udt in ("int4", "int"):

        return "INT"

    elif dtype == "SMALLINT" or udt in ("int2",):

        return "SMALLINT"

    elif dtype == "BIGINT" or udt in ("int8",):

        return "BIGINT"

    elif dtype == "NUMERIC":

        prec = col_info.get("numeric_precision")

        scale = col_info.get("numeric_scale")

        if prec is not None and scale is not None:

            return f"NUMERIC({prec},{scale})"

        elif prec is not None:

            return f"NUMERIC({prec})"

        return "NUMERIC"

    elif dtype == "BOOLEAN":

        return "BOOLEAN"

    elif dtype == "TEXT":

        return "TEXT"

    elif "TIMESTAMP" in dtype:

        return "TIMESTAMP"

    elif dtype == "DATE":

        return "DATE"

    return dtype



def compare_table_structures(

    expected_meta: Dict[str, Any],

    student_meta: Dict[str, Any]

) -> Tuple[bool, str, Dict[str, Any]]:

    """

    Compares the reference table structure with the student's table structure.

    Validates:

    1. Table existence

    2. Column presence (all expected columns exist)

    3. Column data types and lengths/precision

    4. PRIMARY KEY constraints (columns participating in PK)

    5. NOT NULL constraints

    Returns (is_correct, feedback_message, diagnostic_details).

    """

    table_name = expected_meta.get("table_name", "tabel")

    details = {

        "table_name": table_name,

        "table_exists": student_meta.get("exists", False),

        "missing_columns": [],

        "extra_columns": [],

        "type_mismatches": [],

        "pk_status": "ok",

        "nullability_mismatches": []

    }



    # 1. Existence check

    if not student_meta.get("exists", False):

        msg = f"Tabel '{table_name}' belum ditemukan di skema database pribadi Anda. Pastikan perintah CREATE TABLE berhasil dijalankan."

        return False, msg, details



    exp_cols = {c["name"].lower(): c for c in expected_meta.get("columns", [])}

    stud_cols = {c["name"].lower(): c for c in student_meta.get("columns", [])}



    # 2. Missing columns check

    missing = [c for c in exp_cols if c not in stud_cols]

    if missing:

        details["missing_columns"] = missing

        missing_names = ", ".join(f"'{exp_cols[m]['name']}'" for m in missing)

        msg = f"Struktur tabel '{table_name}' belum lengkap. Kolom berikut belum ditemukan: {missing_names}."

        return False, msg, details



    # Extra columns detection (for diagnostic info)

    extra = [c for c in stud_cols if c not in exp_cols]

    details["extra_columns"] = extra



    # 3. Data type & length/precision compatibility check

    INT_FAMILY = {"int4", "int2", "integer", "smallint", "serial"}

    BIGINT_FAMILY = {"int8", "bigint", "bigserial"}



    for col_name, exp_c in exp_cols.items():

        stud_c = stud_cols[col_name]

        exp_dtype = (exp_c.get("data_type") or "").lower()

        stud_dtype = (stud_c.get("data_type") or "").lower()

        exp_udt = (exp_c.get("udt_name") or "").lower()

        stud_udt = (stud_c.get("udt_name") or "").lower()



        type_match = False

        if exp_udt and stud_udt and exp_udt == stud_udt:

            type_match = True

        elif exp_dtype == stud_dtype:

            type_match = True

        elif exp_udt in INT_FAMILY and stud_udt in INT_FAMILY:

            type_match = True

        elif exp_udt in BIGINT_FAMILY and stud_udt in BIGINT_FAMILY:

            type_match = True

        elif exp_dtype in ("character varying", "varchar") and stud_dtype in ("character varying", "varchar"):

            type_match = True



        if not type_match:

            exp_label = normalize_type_label(exp_c)

            stud_label = normalize_type_label(stud_c)

            mismatch_desc = f"Kolom '{stud_c['name']}': tipe data tidak sesuai (Diharapkan {exp_label}, tetapi ditemukan {stud_label})."

            details["type_mismatches"].append(mismatch_desc)

            return False, mismatch_desc, details



        # For VARCHAR/CHAR, check maximum length if expected specifies one

        if exp_dtype in ("character varying", "character"):

            exp_len = exp_c.get("character_maximum_length")

            stud_len = stud_c.get("character_maximum_length")

            if exp_len is not None and stud_len is not None and exp_len != stud_len:

                mismatch_desc = f"Ukuran panjang kolom '{stud_c['name']}' tidak sesuai. Diharapkan {normalize_type_label(exp_c)}, namun ditemukan {normalize_type_label(stud_c)}."

                details["type_mismatches"].append(mismatch_desc)

                return False, mismatch_desc, details



        # For NUMERIC/DECIMAL, check precision & scale if expected specifies

        if exp_dtype == "numeric":

            exp_scale = exp_c.get("numeric_scale")

            stud_scale = stud_c.get("numeric_scale")

            if exp_scale is not None and stud_scale is not None and exp_scale != stud_scale:

                mismatch_desc = f"Presisi skala desimal kolom '{stud_c['name']}' tidak sesuai. Diharapkan {normalize_type_label(exp_c)}, namun ditemukan {normalize_type_label(stud_c)}."

                details["type_mismatches"].append(mismatch_desc)

                return False, mismatch_desc, details



    # 4. Primary Key validation

    exp_pk_cols = [c.lower() for c in expected_meta.get("constraints", {}).get("primary_key", [])]

    stud_pk_cols = [c.lower() for c in student_meta.get("constraints", {}).get("primary_key", [])]



    if exp_pk_cols:

        if not stud_pk_cols:

            details["pk_status"] = "missing"

            pk_names = ", ".join(f"'{exp_cols.get(p, {}).get('name', p)}'" for p in exp_pk_cols)

            msg = f"Constraint PRIMARY KEY belum didefinisikan pada tabel '{table_name}'. Diharapkan kolom primary key: {pk_names}."

            return False, msg, details

        elif set(exp_pk_cols) != set(stud_pk_cols):

            details["pk_status"] = "mismatch"

            exp_pk_names = ", ".join(f"'{exp_cols.get(p, {}).get('name', p)}'" for p in exp_pk_cols)

            stud_pk_names = ", ".join(f"'{stud_cols.get(p, {}).get('name', p)}'" for p in stud_pk_cols)

            msg = f"Definisi PRIMARY KEY pada tabel '{table_name}' tidak sesuai. Diharapkan ({exp_pk_names}), namun ditemukan ({stud_pk_names})."

            return False, msg, details



    # 5. NOT NULL constraint validation (for non-PK columns)

    for col_name, exp_c in exp_cols.items():

        if col_name in exp_pk_cols:

            continue

        if not exp_c.get("is_nullable", True):

            stud_c = stud_cols.get(col_name)

            if stud_c and stud_c.get("is_nullable", True):

                details["nullability_mismatches"].append(col_name)

                msg = f"Kolom '{stud_c['name']}' pada tabel '{table_name}' seharusnya memiliki constraint NOT NULL (tidak boleh bernilai NULL)."

                return False, msg, details



    msg = f"Sempurna! Struktur tabel '{table_name}' (kolom, tipe data, NOT NULL, dan PRIMARY KEY) 100% valid sesuai spesifikasi acuan dosen."

    return True, msg, details





def get_database_schema(db_name: str = DEFAULT_EXAM_DB, nim: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:

    """

    Introspects tables and columns dynamically.

    - If db_name == 'sandbox_pribadi', inspects the student's personal schema (sandbox_{nim}).

    - Otherwise, inspects public tables of the selected PostgreSQL database (pagila, classicmodels, etc.).

    Returns: { "table_name": [{"name": col, "type": type, "nullable": bool, "pk": bool}] }

    """

    schema_info = {}

    clean_db = (db_name or DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()

    is_sandbox = (clean_db == "sandbox_pribadi")

    conn = None

    try:

        if is_sandbox:

            schema_name = get_clean_student_schema_name(nim)

            conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

            cur = conn.cursor()

            cur.execute("""

                SELECT 

                    c.table_name,

                    c.column_name,

                    c.data_type,

                    c.is_nullable,

                    CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN 1 ELSE 0 END AS is_pk,

                    c.table_schema

                FROM information_schema.columns c

                JOIN information_schema.tables t 

                    ON c.table_name = t.table_name 

                    AND c.table_schema = t.table_schema

                LEFT JOIN information_schema.key_column_usage kcu

                    ON c.table_name = kcu.table_name 

                    AND c.column_name = kcu.column_name 

                    AND c.table_schema = kcu.table_schema

                LEFT JOIN information_schema.table_constraints tc 

                    ON kcu.constraint_name = tc.constraint_name 

                    AND kcu.table_schema = tc.table_schema 

                    AND tc.constraint_type = 'PRIMARY KEY'

                WHERE c.table_schema = %s

                  AND t.table_type = 'BASE TABLE'

                ORDER BY c.table_name, c.ordinal_position;

            """, (schema_name,))

        else:

            conn = get_pg_admin_connection(dbname=clean_db)

            cur = conn.cursor()

            cur.execute("""

                SELECT 

                    c.table_name,

                    c.column_name,

                    c.data_type,

                    c.is_nullable,

                    CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN 1 ELSE 0 END AS is_pk,

                    c.table_schema

                FROM information_schema.columns c

                JOIN information_schema.tables t 

                    ON c.table_name = t.table_name 

                    AND c.table_schema = t.table_schema

                LEFT JOIN information_schema.key_column_usage kcu

                    ON c.table_name = kcu.table_name 

                    AND c.column_name = kcu.column_name 

                    AND c.table_schema = kcu.table_schema

                LEFT JOIN information_schema.table_constraints tc 

                    ON kcu.constraint_name = tc.constraint_name 

                    AND kcu.table_schema = tc.table_schema 

                    AND tc.constraint_type = 'PRIMARY KEY'

                WHERE c.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')

                  AND c.table_schema NOT LIKE 'pg_%%'

                  AND t.table_type = 'BASE TABLE'

                ORDER BY c.table_schema, c.table_name, c.ordinal_position;

            """)

        

        rows = cur.fetchall()

        for r in rows:

            tbl = r[0]

            col = r[1]

            dtype = r[2]

            nullable = (r[3] == "YES")

            is_pk = bool(r[4])

            

            if tbl not in schema_info:

                schema_info[tbl] = []

            

            if not any(item["name"] == col for item in schema_info[tbl]):

                schema_info[tbl].append({

                    "name": col,

                    "type": dtype,

                    "nullable": nullable,

                    "pk": is_pk

                })

        cur.close()

        conn.close()

    except Exception as e:

        if conn and not conn.closed:

            conn.close()

        print(f"Error inspecting schema for db '{clean_db}': {e}")

    return schema_info



def get_database_fk_relations(db_name: str = DEFAULT_EXAM_DB, nim: Optional[str] = None) -> list:

    """Returns all foreign key relationships in the specified database or student sandbox."""

    relations = []

    clean_db = (db_name or DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()

    is_sandbox = (clean_db == "sandbox_pribadi")

    conn = None

    try:

        if is_sandbox:

            schema_name = get_clean_student_schema_name(nim)

            conn = get_pg_admin_connection(dbname=DEFAULT_EXAM_DB)

            cur = conn.cursor()

            cur.execute("""

                SELECT

                    kcu.table_name        AS from_table,

                    kcu.column_name       AS from_col,

                    ccu.table_name        AS to_table,

                    ccu.column_name       AS to_col,

                    tc.constraint_name

                FROM information_schema.table_constraints AS tc

                JOIN information_schema.key_column_usage AS kcu

                    ON tc.constraint_name = kcu.constraint_name

                    AND tc.table_schema   = kcu.table_schema

                JOIN information_schema.constraint_column_usage AS ccu

                    ON ccu.constraint_name = tc.constraint_name

                    AND ccu.table_schema   = tc.table_schema

                WHERE tc.constraint_type = 'FOREIGN KEY'

                  AND tc.table_schema = %s

                ORDER BY from_table, from_col;

            """, (schema_name,))

        else:

            conn = get_pg_admin_connection(dbname=clean_db)

            cur = conn.cursor()

            cur.execute("""

                SELECT

                    kcu.table_name        AS from_table,

                    kcu.column_name       AS from_col,

                    ccu.table_name        AS to_table,

                    ccu.column_name       AS to_col,

                    tc.constraint_name

                FROM information_schema.table_constraints AS tc

                JOIN information_schema.key_column_usage AS kcu

                    ON tc.constraint_name = kcu.constraint_name

                    AND tc.table_schema   = kcu.table_schema

                JOIN information_schema.constraint_column_usage AS ccu

                    ON ccu.constraint_name = tc.constraint_name

                    AND ccu.table_schema   = tc.table_schema

                WHERE tc.constraint_type = 'FOREIGN KEY'

                  AND tc.table_schema NOT IN ('information_schema', 'pg_catalog')

                  AND tc.table_schema NOT LIKE 'pg_%%'

                ORDER BY from_table, from_col;

            """)

            

        for row in cur.fetchall():

            relations.append({

                "from_table": row[0],

                "from_col":   row[1],

                "to_table":   row[2],

                "to_col":     row[3],

                "constraint":  row[4],

            })

        cur.close()

        conn.close()

    except Exception as e:

        if conn and not conn.closed:

            conn.close()

        print(f"Error fetching FK relations for db '{clean_db}': {e}")

    return relations



def get_classicmodels_schema() -> Dict[str, List[Dict[str, Any]]]:

    """Backward compatibility wrapper."""

    return get_database_schema(db_name="classicmodels")



def get_classicmodels_fk_relations() -> list:

    """Backward compatibility wrapper."""

    return get_database_fk_relations(db_name="classicmodels")



def verify_system_health() -> Dict[str, Any]:

    """Verifies connections to SQLite and PostgreSQL."""

    health = {"sqlite": False, "postgres_admin": False, "postgres_student": False, "details": {}}

    

    # SQLite check

    try:

        conn = get_sqlite_conn()

        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM questions;")

        health["sqlite"] = True

        health["details"]["sqlite_questions"] = cur.fetchone()[0]

        conn.close()

    except Exception as e:

        health["details"]["sqlite_error"] = str(e)



    # Postgres Admin check

    try:

        conn = get_pg_admin_connection()

        cur = conn.cursor()

        cur.execute("SELECT current_database(), current_user;")

        row = cur.fetchone()

        health["postgres_admin"] = True

        health["details"]["pg_admin_db"] = row[0]

        health["details"]["pg_admin_user"] = row[1]

        conn.close()

    except Exception as e:

        health["details"]["pg_admin_error"] = str(e)



    # Postgres Student check

    try:

        conn = get_pg_student_connection()

        cur = conn.cursor()

        cur.execute("SELECT 1;")

        health["postgres_student"] = True

        conn.close()

    except Exception as e:

        health["details"]["pg_student_error"] = str(e)



    return health



# ==============================================================================

# Waiting Room & Exam State Management

# ==============================================================================



def get_exam_state() -> str:

    """Returns 'waiting' or 'active'. Defaults to 'waiting' if not set."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute("SELECT value FROM system_settings WHERE key = 'exam_state';")

    row = cur.fetchone()

    conn.close()

    return row["value"] if row else "waiting"



def set_exam_state(state: str) -> None:

    """Sets exam state to 'waiting' or 'active'."""

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            "INSERT INTO system_settings (key, value) VALUES ('exam_state', ?) "

            "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",

            (state,)

        )

        action = "exam_started" if state == "active" else "exam_stopped"

        label = "Ujian dimulai oleh admin." if state == "active" else "Ujian dihentikan oleh admin."

        conn.execute(

            "INSERT INTO exam_logs (action_type, details) VALUES (?, ?);",

            (action, label)

        )

    conn.close()



def get_waiting_room_participants() -> list:

    """Returns students currently active in the waiting room (heartbeat within 20s)."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    cur.execute(

        """

        SELECT nim, name, ip_address, last_active, status

        FROM users

        WHERE status = 'waiting'

          AND last_active >= datetime('now', '-20 seconds')

        ORDER BY last_active DESC;

        """

    )

    rows = cur.fetchall()

    conn.close()

    return [dict(r) for r in rows]



def mark_student_waiting(nim: str) -> None:

    """Marks a student as 'waiting' with fresh last_active timestamp."""

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            "UPDATE users SET status = 'waiting', last_active = CURRENT_TIMESTAMP WHERE nim = ?;",

            (nim,)

        )

    conn.close()



def heartbeat_student_waiting(nim: str) -> None:

    """Touch last_active for a student in the waiting room without changing status."""

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE nim = ? AND status = 'waiting';",

            (nim,)

        )

    conn.close()



def mark_student_in_exam(nim: str) -> None:

    """Marks a student as 'online' (in exam) when they enter the exam page."""

    conn = get_sqlite_conn()

    with conn:

        conn.execute(

            "UPDATE users SET status = 'online', last_active = CURRENT_TIMESTAMP WHERE nim = ?;",

            (nim,)

        )

    conn.close()



def get_waiting_room_messages(since_id: int = 0, limit: int = 50) -> list:

    """Returns chat messages newer than since_id, or the latest `limit` messages when since_id=0."""

    conn = get_sqlite_conn()

    cur = conn.cursor()

    if since_id > 0:

        cur.execute(

            """

            SELECT id, nim, name, message, sent_at

            FROM waiting_room_messages

            WHERE id > ?

            ORDER BY id ASC

            LIMIT ?;

            """,

            (since_id, limit)

        )

        rows = cur.fetchall()

    else:

        cur.execute(

            """

            SELECT id, nim, name, message, sent_at

            FROM (

                SELECT id, nim, name, message, sent_at

                FROM waiting_room_messages

                ORDER BY id DESC

                LIMIT ?

            )

            ORDER BY id ASC;

            """,

            (limit,)

        )

        rows = cur.fetchall()

    conn.close()

    return [dict(r) for r in rows]



def post_waiting_room_message(nim: str, name: str, message: str) -> dict:

    """Inserts a new chat message and returns it."""

    message = message.strip()[:300]

    if not message:

        return {}

    conn = get_sqlite_conn()

    with conn:

        cur = conn.cursor()

        cur.execute(

            "INSERT INTO waiting_room_messages (nim, name, message) VALUES (?, ?, ?);",

            (nim, name, message)

        )

        msg_id = cur.lastrowid

    cur.execute("SELECT id, nim, name, message, sent_at FROM waiting_room_messages WHERE id = ?;", (msg_id,))

    row = cur.fetchone()

    conn.close()

    return dict(row) if row else {}



def clear_waiting_room_messages() -> None:

    """Clears all waiting room chat messages (called when exam starts)."""

    conn = get_sqlite_conn()

    with conn:

        conn.execute("DELETE FROM waiting_room_messages;")

    conn.close()

