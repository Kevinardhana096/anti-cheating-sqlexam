# -*- coding: utf-8 -*-
"""
Official Seeder Script for Draft Konsep Final Basis Data 2026
Populates 6 Exam Packages (SIM-1, SIM-2, FINAL-A, FINAL-B, FINAL-C, FINAL-D)
with 10 questions each (60 questions total).
Generates table preview images for Pagila queries (Q4 to Q10).
"""
import os
import sys
import sqlite3
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import database

STATIC_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads", "questions")
os.makedirs(UPLOADS_DIR, exist_ok=True)

def render_table_screenshot(columns, rows, title="Ekspektasi Output Tabel", output_path="output.png", max_rows=5):
    """Generates a high-contrast, clean dark-themed table reference screenshot."""
    display_rows = rows[:max_rows]
    
    col_widths = []
    for j, col in enumerate(columns):
        max_len = len(str(col))
        for r in display_rows:
            if j < len(r):
                max_len = max(max_len, len(str(r[j])))
        col_widths.append(max(85, min(320, max_len * 9 + 30)))
        
    table_width = sum(col_widths)
    margin = 20
    row_height = 28
    header_height = 34
    title_height = 36
    footer_height = 24 if len(rows) > max_rows else 8
    
    img_width = max(420, table_width + (margin * 2))
    img_height = title_height + header_height + (len(display_rows) * row_height) + footer_height + (margin * 2)
    
    img = Image.new("RGB", (img_width, img_height), color=(15, 23, 42)) # Slate 900
    draw = ImageDraw.Draw(img)
    
    # Title
    draw.text((margin, margin + 4), title, fill=(248, 250, 252))
    
    curr_y = margin + title_height
    curr_x = margin
    
    # Header
    draw.rectangle([margin, curr_y, margin + table_width, curr_y + header_height], fill=(30, 41, 59), outline=(71, 85, 105))
    for j, col in enumerate(columns):
        w = col_widths[j]
        draw.text((curr_x + 10, curr_y + 9), str(col), fill=(129, 140, 248))
        if j < len(columns) - 1:
            draw.line([(curr_x + w, curr_y), (curr_x + w, curr_y + header_height)], fill=(71, 85, 105), width=1)
        curr_x += w
        
    curr_y += header_height
    
    # Rows
    for i, row in enumerate(display_rows):
        row_bg = (15, 23, 42) if i % 2 == 0 else (24, 33, 50)
        draw.rectangle([margin, curr_y, margin + table_width, curr_y + row_height], fill=row_bg, outline=(51, 65, 85))
        curr_x = margin
        for j in range(len(columns)):
            w = col_widths[j]
            val = str(row[j]) if j < len(row) and row[j] is not None else "NULL"
            val_color = (203, 213, 225) if val != "NULL" else (148, 163, 184)
            draw.text((curr_x + 10, curr_y + 7), val, fill=val_color)
            if j < len(columns) - 1:
                draw.line([(curr_x + w, curr_y), (curr_x + w, curr_y + row_height)], fill=(51, 65, 85), width=1)
            curr_x += w
        curr_y += row_height
        
    if len(rows) > max_rows:
        draw.text((margin, curr_y + 5), f"... dan {len(rows) - max_rows} baris lainnya (hanya menampilkan {max_rows} baris pertama)", fill=(148, 163, 184))
        
    img.save(output_path)
    return output_path

PACKAGES_DATA = [
    {
        "code": "SIM-1",
        "name": "Paket Simulasi 1",
        "description": "Gladi resik simulasi ujian: DDL Kamar Sandbox & Analisis Rental Film Pagila.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Produk Elektronik",
                "desc": "Buatlah database 'toko_elektronik' (opsional) dan buat tabel 'produk_elektronik' di kamar Sandbox pribadi Anda dengan kolom: id_produk (INT, PRIMARY KEY), nama_produk (VARCHAR 100), harga (NUMERIC), dan stok (INT).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE produk_elektronik (id_produk INT PRIMARY KEY, nama_produk VARCHAR(100), harga NUMERIC, stok INT);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Produk Elektronik",
                "desc": "Masukkan 3 baris data ke dalam tabel 'produk_elektronik': (1, 'Laptop Gaming', 15000000, 5), (2, 'Mouse Wireless', 250000, 20), dan (3, 'Keyboard Mechanical', 750000, 10).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO produk_elektronik (id_produk, nama_produk, harga, stok) VALUES (1, 'Laptop Gaming', 15000000, 5), (2, 'Mouse Wireless', 250000, 20), (3, 'Keyboard Mechanical', 750000, 10);"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Produk",
                "desc": "Hapus tabel 'produk_elektronik' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS produk_elektronik;"
            },
            {
                "num": 4,
                "title": "Daftar Film Rating PG-13 Durasi Sewa Panjang",
                "desc": "Tampilkan kolom film_id, title, rental_duration, dan rental_rate dari tabel film untuk film dengan rating 'PG-13' yang memiliki durasi sewa (rental_duration) minimal 6 hari. Urutkan berdasarkan rental_rate menurun (DESC), kemudian title menaik (ASC), dan batasi hanya 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT film_id, title, rental_duration, rental_rate FROM film WHERE rating = 'PG-13' AND rental_duration >= 6 ORDER BY rental_rate DESC, title ASC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Film Berbahasa English",
                "desc": "Gabungkan tabel film dan language untuk menampilkan judul film (title), tahun rilis (release_year), dan nama bahasa (name sebagai language_name) yang berbahasa 'English'. Urutkan berdasarkan title ASC dan ambil 5 data teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.title, f.release_year, l.name AS language_name FROM film f JOIN language l ON f.language_id = l.language_id WHERE l.name = 'English' ORDER BY f.title ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Jumlah Film per Kategori",
                "desc": "Tampilkan nama kategori (name sebagai category_name) dan jumlah filmnya (total_film) dengan menggabungkan tabel category dan film_category. Kelompokkan per nama kategori, urutkan dari total_film terbanyak (DESC), lalu category_name ASC, dan batasi 5 baris teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT c.name AS category_name, COUNT(fc.film_id) AS total_film FROM category c JOIN film_category fc ON c.category_id = fc.category_id GROUP BY c.name ORDER BY total_film DESC, category_name ASC LIMIT 5;"
            },
            {
                "num": 7,
                "title": "Pelanggan Aktif di Toko Cabang 1",
                "desc": "Tampilkan customer_id, first_name, last_name, dan alamat lengkap (address) dari pelanggan yang aktif (activebool = true) pada toko cabang store_id = 1. Urutkan berdasarkan customer_id ASC dan batasi 5 baris teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT c.customer_id, c.first_name, c.last_name, a.address FROM customer c JOIN address a ON c.address_id = a.address_id WHERE c.activebool = true AND c.store_id = 1 ORDER BY c.customer_id ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Aktor Produktif dengan Lebih dari 35 Film",
                "desc": "Tampilkan actor_id, first_name, last_name, dan jumlah film yang dibintangi (total_film) untuk aktor yang telah membintangi LEBIH DARI 35 film. Urutkan dari total_film terbanyak, kemudian last_name ASC.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT a.actor_id, a.first_name, a.last_name, COUNT(fa.film_id) AS total_film FROM actor a JOIN film_actor fa ON a.actor_id = fa.actor_id GROUP BY a.actor_id, a.first_name, a.last_name HAVING COUNT(fa.film_id) > 35 ORDER BY total_film DESC, a.last_name ASC;"
            },
            {
                "num": 9,
                "title": "Peringkat Film Termahal Rating R (DENSE_RANK)",
                "desc": "Gunakan CTE dan Window Function DENSE_RANK() untuk memeringkat film berdasarkan tarif sewa (rental_rate) tertinggi dalam setiap rating. Tampilkan film_id, title, rating, rental_rate, dan rank_in_rating untuk film berating 'R' yang memiliki peringkat rank_in_rating = 1. Urutkan berdasarkan title ASC dan ambil 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH RankedFilms AS (SELECT film_id, title, rating, rental_rate, DENSE_RANK() OVER (PARTITION BY rating ORDER BY rental_rate DESC, title ASC) AS rank_in_rating FROM film) SELECT film_id, title, rating, rental_rate, rank_in_rating FROM RankedFilms WHERE rating = 'R' AND rank_in_rating = 1 ORDER BY title ASC LIMIT 5;"
            },
            {
                "num": 10,
                "title": "Segmentasi Aktivitas Pelanggan (CASE WHEN)",
                "desc": "Tampilkan customer_id, first_name, last_name, total_rentals, dan membership_tier dengan kriteria: total_rentals >= 30 menjadi 'VIP', total_rentals >= 20 menjadi 'Loyal', dan selain itu 'Reguler'. Urutkan dari total_rentals terbanyak, lalu customer_id ASC, ambil 5 teratas.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(r.rental_id) AS total_rentals, CASE WHEN COUNT(r.rental_id) >= 30 THEN 'VIP' WHEN COUNT(r.rental_id) >= 20 THEN 'Loyal' ELSE 'Reguler' END AS membership_tier FROM customer c JOIN rental r ON c.customer_id = r.customer_id GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY total_rentals DESC, c.customer_id ASC LIMIT 5;"
            }
        ]
    },
    {
        "code": "SIM-2",
        "name": "Paket Simulasi 2",
        "description": "Gladi resik simulasi ujian: DDL/DML Kamar Sandbox & Analisis Pelanggan dan Kategori Pagila.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Kategori Barang",
                "desc": "Buatlah tabel 'kategori_barang' di kamar Sandbox pribadi Anda dengan kolom: id_kategori (INT, PRIMARY KEY), nama_kategori (VARCHAR 50), dan deskripsi (TEXT).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE kategori_barang (id_kategori INT PRIMARY KEY, nama_kategori VARCHAR(50), deskripsi TEXT);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Kategori Barang",
                "desc": "Masukkan 3 data ke tabel 'kategori_barang': (1, 'Buku', 'Buku dan literatur'), (2, 'Alat Tulis', 'Peralatan kantor'), dan (3, 'Aksesoris', 'Perlengkapan komputer').",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO kategori_barang (id_kategori, nama_kategori, deskripsi) VALUES (1, 'Buku', 'Buku dan literatur'), (2, 'Alat Tulis', 'Peralatan kantor'), (3, 'Aksesoris', 'Perlengkapan komputer');"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Kategori",
                "desc": "Hapus tabel 'kategori_barang' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS kategori_barang;"
            },
            {
                "num": 4,
                "title": "Daftar Pelanggan Aktif Toko Cabang 2",
                "desc": "Tampilkan customer_id, first_name, last_name, dan email dari tabel customer untuk pelanggan aktif (activebool = true) pada toko store_id = 2. Urutkan berdasarkan last_name ASC, first_name ASC, ambil 5 data teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT customer_id, first_name, last_name, email FROM customer WHERE activebool = true AND store_id = 2 ORDER BY last_name ASC, first_name ASC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Kota-Kota di Indonesia, Japan, dan Malaysia",
                "desc": "Gabungkan tabel city dan country untuk menampilkan nama kota (city) dan negara (country) yang berada di negara 'Indonesia', 'Japan', atau 'Malaysia'. Urutkan berdasarkan country ASC, lalu city ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT c.city, co.country FROM city c JOIN country co ON c.country_id = co.country_id WHERE co.country IN ('Indonesia', 'Japan', 'Malaysia') ORDER BY co.country ASC, c.city ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Rata-rata Tarif Sewa per Rating Film",
                "desc": "Tampilkan rating, jumlah film (total_film), dan rata-rata tarif sewa dibulatkan 2 desimal (avg_rental_rate) dari tabel film dikelompokkan per rating. Urutkan dari total_film terbanyak.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT rating, COUNT(film_id) AS total_film, ROUND(AVG(rental_rate), 2) AS avg_rental_rate FROM film GROUP BY rating ORDER BY total_film DESC;"
            },
            {
                "num": 7,
                "title": "Stok Film Toko Cabang 1 Minimal 4 Copy",
                "desc": "Tampilkan film_id, title, dan jumlah unit fisik (stok_tersedia) di toko store_id = 1 untuk film yang memiliki minimal 4 unit di inventory. Urutkan dari stok_tersedia terbanyak, kemudian title ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.film_id, f.title, COUNT(i.inventory_id) AS stok_tersedia FROM film f JOIN inventory i ON f.film_id = i.film_id WHERE i.store_id = 1 GROUP BY f.film_id, f.title HAVING COUNT(i.inventory_id) >= 4 ORDER BY stok_tersedia DESC, f.title ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Pelanggan Pengeluaran Tinggi di Atas $180",
                "desc": "Tampilkan customer_id, first_name, last_name, total_transaksi, dan total_pengeluaran dari tabel customer dan payment untuk pelanggan dengan akumulasi pembayaran LEBIH DARI 180. Urutkan dari total_pengeluaran terbesar, lalu total_transaksi DESC, ambil 5 teratas.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT c.customer_id, c.first_name, c.last_name, COUNT(p.payment_id) AS total_transaksi, SUM(p.amount) AS total_pengeluaran FROM customer c JOIN payment p ON c.customer_id = p.customer_id GROUP BY c.customer_id, c.first_name, c.last_name HAVING SUM(p.amount) > 180 ORDER BY total_pengeluaran DESC, total_transaksi DESC LIMIT 5;"
            },
            {
                "num": 9,
                "title": "Top 5 Pelanggan Paling Loyal (ROW_NUMBER)",
                "desc": "Gunakan CTE dan Window Function ROW_NUMBER() untuk memberi peringkat pelanggan berdasarkan total pembayaran. Tampilkan ranking, customer_id, first_name, last_name, dan total_bayar untuk ranking 1 hingga 5. Urutkan berdasarkan ranking ASC.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH CustomerSpending AS (SELECT customer_id, SUM(amount) AS total_bayar, ROW_NUMBER() OVER (ORDER BY SUM(amount) DESC) AS ranking FROM payment GROUP BY customer_id) SELECT cs.ranking, c.customer_id, c.first_name, c.last_name, cs.total_bayar FROM CustomerSpending cs JOIN customer c ON cs.customer_id = c.customer_id WHERE cs.ranking <= 5 ORDER BY cs.ranking ASC;"
            },
            {
                "num": 10,
                "title": "Klasifikasi Durasi Film Rating G",
                "desc": "Tampilkan title, length, kategori_durasi (length < 60: 'Durasi Pendek', length 60-120: 'Durasi Sedang', else: 'Durasi Panjang'), dan rental_rate untuk film dengan rating 'G'. Urutkan dari length terpanjang, lalu title ASC, batasi 5 baris.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT f.title, f.length, CASE WHEN f.length < 60 THEN 'Durasi Pendek' WHEN f.length BETWEEN 60 AND 120 THEN 'Durasi Sedang' ELSE 'Durasi Panjang' END AS kategori_durasi, f.rental_rate FROM film f WHERE f.rating = 'G' ORDER BY f.length DESC, f.title ASC LIMIT 5;"
            }
        ]
    },
    {
        "code": "FINAL-A",
        "name": "Paket Final A",
        "description": "Paket Final A: DDL Kamar Sandbox, Kueri Multi-Table Film, Aktor, dan Pendapatan Rental.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Master Karyawan",
                "desc": "Buatlah tabel 'master_karyawan' di kamar Sandbox pribadi Anda dengan struktur: id_karyawan (INT, PRIMARY KEY), nama_lengkap (VARCHAR 100), jabatan (VARCHAR 50), dan gaji (NUMERIC).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE master_karyawan (id_karyawan INT PRIMARY KEY, nama_lengkap VARCHAR(100), jabatan VARCHAR(50), gaji NUMERIC);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Karyawan",
                "desc": "Masukkan 3 record data ke tabel 'master_karyawan': (101, 'Ahmad Fauzi', 'Database Administrator', 12000000), (102, 'Rina Wahyuni', 'Backend Engineer', 10500000), dan (103, 'Dimas Pratama', 'Data Analyst', 9000000).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO master_karyawan (id_karyawan, nama_lengkap, jabatan, gaji) VALUES (101, 'Ahmad Fauzi', 'Database Administrator', 12000000), (102, 'Rina Wahyuni', 'Backend Engineer', 10500000), (103, 'Dimas Pratama', 'Data Analyst', 9000000);"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Master Karyawan",
                "desc": "Hapus tabel 'master_karyawan' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS master_karyawan;"
            },
            {
                "num": 4,
                "title": "Film Durasi Panjang dengan Biaya Ganti Ekonomis",
                "desc": "Tampilkan film_id, title, length, dan replacement_cost dari tabel film untuk film berdurasi lebih dari 180 menit dengan biaya penggantian (replacement_cost) kurang dari 15.00. Urutkan berdasarkan length DESC, lalu replacement_cost ASC, ambil 5 teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT film_id, title, length, replacement_cost FROM film WHERE length > 180 AND replacement_cost < 15.00 ORDER BY length DESC, replacement_cost ASC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Pelanggan di Kota Berawalan Huruf A",
                "desc": "Gabungkan tabel customer, address, dan city untuk menampilkan customer_id, first_name, last_name, dan nama kota (city) untuk pelanggan yang tinggal di kota dengan awalan huruf 'A'. Urutkan berdasarkan city ASC, lalu first_name ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT cu.customer_id, cu.first_name, cu.last_name, ci.city FROM customer cu JOIN address a ON cu.address_id = a.address_id JOIN city ci ON a.city_id = ci.city_id WHERE ci.city LIKE 'A%' ORDER BY ci.city ASC, cu.first_name ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Total Omset Pembayaran per Toko Cabang",
                "desc": "Tampilkan store_id, total_transaksi, dan total_pendapatan dari tabel staff dan payment dikelompokkan berdasarkan toko cabang (store_id). Urutkan dari total_pendapatan terbesar.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT s.store_id, COUNT(p.payment_id) AS total_transaksi, SUM(p.amount) AS total_pendapatan FROM staff s JOIN payment p ON s.staff_id = p.staff_id GROUP BY s.store_id ORDER BY total_pendapatan DESC;"
            },
            {
                "num": 7,
                "title": "Film Kategori Comedy Tarif 0.99",
                "desc": "Tampilkan title, category_name (nama kategori), dan rental_rate untuk film dalam kategori 'Comedy' yang memiliki tarif rental 0.99. Urutkan berdasarkan title ASC dan ambil 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.title, c.name AS category_name, f.rental_rate FROM film f JOIN film_category fc ON f.film_id = fc.film_id JOIN category c ON fc.category_id = c.category_id WHERE c.name = 'Comedy' AND f.rental_rate = 0.99 ORDER BY f.title ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Aktor di Film-Film Premium",
                "desc": "Tampilkan actor_id, first_name, last_name, dan total_film untuk aktor yang telah membintangi minimal 15 film yang bertarif sewa mahal (rental_rate > 3.00). Urutkan dari total_film terbesar, lalu last_name ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT a.actor_id, a.first_name, a.last_name, COUNT(fa.film_id) AS total_film FROM actor a JOIN film_actor fa ON a.actor_id = fa.actor_id JOIN film f ON fa.film_id = f.film_id WHERE f.rental_rate > 3.00 GROUP BY a.actor_id, a.first_name, a.last_name HAVING COUNT(fa.film_id) >= 15 ORDER BY total_film DESC, a.last_name ASC LIMIT 5;"
            },
            {
                "num": 9,
                "title": "Peringkat Film Paling Sering Dirental (DENSE_RANK)",
                "desc": "Gunakan CTE dan Window Function DENSE_RANK() untuk memeringkat film berdasarkan frekuensi rental terbanyak. Tampilkan film_id, title, frekuensi_rental, dan rank_populer untuk 5 peringkat teratas. Urutkan berdasarkan rank_populer ASC, title ASC.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH FilmRentalCount AS (SELECT f.film_id, f.title, COUNT(r.rental_id) AS frekuensi_rental, DENSE_RANK() OVER (ORDER BY COUNT(r.rental_id) DESC) AS rank_populer FROM film f JOIN inventory i ON f.film_id = i.film_id JOIN rental r ON i.inventory_id = r.inventory_id GROUP BY f.film_id, f.title) SELECT film_id, title, frekuensi_rental, rank_populer FROM FilmRentalCount WHERE rank_populer <= 5 ORDER BY rank_populer ASC, title ASC LIMIT 5;"
            },
            {
                "num": 10,
                "title": "Klasifikasi Nilai Komersial Film (CASE WHEN)",
                "desc": "Tampilkan film_id, title, rental_rate, rating, dan tier_layanan (rental_rate >= 4.00 dan length > 120: 'Premium Blockbuster', rental_rate >= 4.00: 'Premium Standard', rental_rate <= 1.00: 'Budget Value', else: 'Regular Film') untuk film berating 'PG-13' atau 'R'. Urutkan dari rental_rate DESC, title ASC, ambil 5 teratas.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT f.film_id, f.title, f.rental_rate, f.rating, CASE WHEN f.rental_rate >= 4.00 AND f.length > 120 THEN 'Premium Blockbuster' WHEN f.rental_rate >= 4.00 THEN 'Premium Standard' WHEN f.rental_rate <= 1.00 THEN 'Budget Value' ELSE 'Regular Film' END AS tier_layanan FROM film f WHERE f.rating IN ('PG-13', 'R') ORDER BY f.rental_rate DESC, f.title ASC LIMIT 5;"
            }
        ]
    },
    {
        "code": "FINAL-B",
        "name": "Paket Final B",
        "description": "Paket Final B: DDL Kamar Sandbox, Kueri Relasi Pelanggan, Pembayaran, dan Inventaris Toko.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Inventaris Lab",
                "desc": "Buatlah tabel 'inventaris_lab' di kamar Sandbox pribadi Anda dengan kolom: kode_alat (VARCHAR 10, PRIMARY KEY), nama_alat (VARCHAR 80), kondisi (VARCHAR 30), dan jumlah (INT).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE inventaris_lab (kode_alat VARCHAR(10) PRIMARY KEY, nama_alat VARCHAR(80), kondisi VARCHAR(30), jumlah INT);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Inventaris",
                "desc": "Masukkan 3 baris data ke tabel 'inventaris_lab': ('LAB-01', 'Mikroskop Digital', 'Baik', 10), ('LAB-02', 'Tabung Reaksi', 'Baik', 100), dan ('LAB-03', 'Timbangan Analitik', 'Perlu Kalibrasi', 2).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO inventaris_lab (kode_alat, nama_alat, kondisi, jumlah) VALUES ('LAB-01', 'Mikroskop Digital', 'Baik', 10), ('LAB-02', 'Tabung Reaksi', 'Baik', 100), ('LAB-03', 'Timbangan Analitik', 'Perlu Kalibrasi', 2);"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Inventaris",
                "desc": "Hapus tabel 'inventaris_lab' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS inventaris_lab;"
            },
            {
                "num": 4,
                "title": "Transaksi Pembayaran Bernilai Tinggi",
                "desc": "Tampilkan payment_id, customer_id, amount, dan payment_date dari tabel payment untuk transaksi dengan nominal amount minimal 10.00. Urutkan dari payment_date terbaru (DESC), amount DESC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT payment_id, customer_id, amount, payment_date FROM payment WHERE amount >= 10.00 ORDER BY payment_date DESC, amount DESC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Alamat Lengkap Staf Toko",
                "desc": "Gabungkan tabel staff dan address untuk menampilkan staff_id, first_name, last_name, address, dan district. Urutkan berdasarkan staff_id ASC dan ambil 5 data teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT st.staff_id, st.first_name, st.last_name, a.address, a.district FROM staff st JOIN address a ON st.address_id = a.address_id ORDER BY st.staff_id ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Kategori Film dengan Rata-rata Durasi Terpanjang",
                "desc": "Tampilkan nama kategori (category_name) dan rata-rata durasi film dibulatkan 2 desimal (avg_duration) dari tabel category, film_category, dan film. Kelompokkan per nama kategori, urutkan dari avg_duration tertinggi, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT c.name AS category_name, ROUND(AVG(f.length), 2) AS avg_duration FROM category c JOIN film_category fc ON c.category_id = fc.category_id JOIN film f ON fc.film_id = f.film_id GROUP BY c.name ORDER BY avg_duration DESC LIMIT 5;"
            },
            {
                "num": 7,
                "title": "Film Fitur Khusus Deleted Scenes",
                "desc": "Tampilkan title, release_year, rating, dan rental_rate untuk film dengan rating 'PG' yang memuat fitur 'Deleted Scenes' pada kolom special_features. Urutkan berdasarkan title ASC dan ambil 5 data teratas.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.title, f.release_year, f.rating, f.rental_rate FROM film f WHERE f.special_features::text LIKE '%Deleted Scenes%' AND f.rating = 'PG' ORDER BY f.title ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Pelanggan Paling Rajin Merental (Minimal 40 Rental)",
                "desc": "Tampilkan customer_id, first_name, last_name, dan jumlah_rental dari tabel customer dan rental untuk pelanggan yang telah meminjam film minimal 40 kali. Urutkan dari jumlah_rental terbanyak, lalu last_name ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT cu.customer_id, cu.first_name, cu.last_name, COUNT(r.rental_id) AS jumlah_rental FROM customer cu JOIN rental r ON cu.customer_id = r.customer_id GROUP BY cu.customer_id, cu.first_name, cu.last_name HAVING COUNT(r.rental_id) >= 40 ORDER BY jumlah_rental DESC, cu.last_name ASC LIMIT 5;"
            },
            {
                "num": 9,
                "title": "Peringkat Omset Bulanan per Staf (ROW_NUMBER)",
                "desc": "Gunakan CTE dan Window Function ROW_NUMBER() untuk menghitung omset bulanan staf dan memeringkat staf dengan penjualan tertinggi setiap bulan. Tampilkan staff_id, periode_bulan (DATE), total_omset, dan rank_staf untuk omset di atas 1000. Urutkan dari periode_bulan DESC, rank_staf ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH StaffMonthlyRevenue AS (SELECT staff_id, DATE_TRUNC('month', payment_date) AS bulan, SUM(amount) AS total_omset, ROW_NUMBER() OVER (PARTITION BY DATE_TRUNC('month', payment_date) ORDER BY SUM(amount) DESC) AS rank_staf FROM payment GROUP BY staff_id, DATE_TRUNC('month', payment_date)) SELECT staff_id, bulan::date AS periode_bulan, total_omset, rank_staf FROM StaffMonthlyRevenue WHERE total_omset > 1000 ORDER BY periode_bulan DESC, rank_staf ASC LIMIT 5;"
            },
            {
                "num": 10,
                "title": "Status Keaktifan Pelanggan Aktif (CASE WHEN)",
                "desc": "Tampilkan customer_id, first_name, last_name, total_pinjam, dan status_keaktifan (total_pinjam > 35: 'Peminjam Sangat Aktif', total_pinjam 25-35: 'Peminjam Sedang', else: 'Peminjam Santai') untuk pelanggan aktif (activebool = true). Urutkan dari total_pinjam terbanyak, lalu customer_id ASC, batasi 5 baris.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT cu.customer_id, cu.first_name, cu.last_name, COUNT(r.rental_id) AS total_pinjam, CASE WHEN COUNT(r.rental_id) > 35 THEN 'Peminjam Sangat Aktif' WHEN COUNT(r.rental_id) BETWEEN 25 AND 35 THEN 'Peminjam Sedang' ELSE 'Peminjam Santai' END AS status_keaktifan FROM customer cu JOIN rental r ON cu.customer_id = r.customer_id WHERE cu.activebool = true GROUP BY cu.customer_id, cu.first_name, cu.last_name ORDER BY total_pinjam DESC, cu.customer_id ASC LIMIT 5;"
            }
        ]
    },
    {
        "code": "FINAL-C",
        "name": "Paket Final C",
        "description": "Paket Final C: DDL Kamar Sandbox, Kueri Agregasi Wilayah Toko, Staf Rental, dan Kategori.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Data Mahasiswa",
                "desc": "Buatlah tabel 'data_mahasiswa' di kamar Sandbox pribadi Anda dengan struktur: nim (VARCHAR 15, PRIMARY KEY), nama (VARCHAR 100), jurusan (VARCHAR 50), dan ipk (NUMERIC).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE data_mahasiswa (nim VARCHAR(15) PRIMARY KEY, nama VARCHAR(100), jurusan VARCHAR(50), ipk NUMERIC);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Mahasiswa",
                "desc": "Masukkan 3 baris data ke tabel 'data_mahasiswa': ('220101001', 'Andi Pratama', 'Teknik Informatika', 3.85), ('220101002', 'Bunga Citra', 'Sistem Informasi', 3.70), dan ('220101003', 'Cahyo Utomo', 'Teknologi Informasi', 3.60).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO data_mahasiswa (nim, nama, jurusan, ipk) VALUES ('220101001', 'Andi Pratama', 'Teknik Informatika', 3.85), ('220101002', 'Bunga Citra', 'Sistem Informasi', 3.70), ('220101003', 'Cahyo Utomo', 'Teknologi Informasi', 3.60);"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Mahasiswa",
                "desc": "Hapus tabel 'data_mahasiswa' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS data_mahasiswa;"
            },
            {
                "num": 4,
                "title": "Film Eksklusif Rating NC-17 Tarif Tertinggi",
                "desc": "Tampilkan title, rating, rental_rate, dan length dari tabel film untuk film berating 'NC-17' dengan tarif sewa 4.99. Urutkan berdasarkan length menaik (ASC), kemudian title ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT title, rating, rental_rate, length FROM film WHERE rating = 'NC-17' AND rental_rate = 4.99 ORDER BY length ASC, title ASC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Negara dengan Jumlah Kota Terbanyak",
                "desc": "Tampilkan nama negara (country) dan jumlah kota (total_kota) untuk negara yang memiliki minimal 20 kota terdaftar. Urutkan dari total_kota terbanyak, lalu country ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT co.country, COUNT(ci.city_id) AS total_kota FROM country co JOIN city ci ON co.country_id = ci.country_id GROUP BY co.country HAVING COUNT(ci.city_id) >= 20 ORDER BY total_kota DESC, co.country ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Total Aset Inventaris DVD per Cabang Toko",
                "desc": "Tampilkan store_id dan total_aset_dvd dari tabel store dan inventory dikelompokkan berdasarkan toko cabang. Urutkan dari total_aset_dvd terbesar.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT s.store_id, COUNT(i.inventory_id) AS total_aset_dvd FROM store s JOIN inventory i ON s.store_id = i.store_id GROUP BY s.store_id ORDER BY total_aset_dvd DESC;"
            },
            {
                "num": 7,
                "title": "Film Biaya Penggantian Menengah Rating PG",
                "desc": "Tampilkan film_id, title, rating, dan replacement_cost untuk film dengan rating 'PG' yang memiliki biaya penggantian antara 20.00 dan 25.00. Urutkan dari replacement_cost DESC, lalu title ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.film_id, f.title, f.rating, f.replacement_cost FROM film f WHERE f.replacement_cost BETWEEN 20.00 AND 25.00 AND f.rating = 'PG' ORDER BY f.replacement_cost DESC, f.title ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Kategori Film Paling Populer (Lebih dari 1000 Rental)",
                "desc": "Tampilkan nama kategori (kategori) dan total frekuensi sewa (total_disewa) untuk kategori yang total disewanya LEBIH DARI 1000 kali. Urutkan dari total_disewa terbesar, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT cat.name AS kategori, COUNT(r.rental_id) AS total_disewa FROM category cat JOIN film_category fc ON cat.category_id = fc.category_id JOIN inventory inv ON fc.film_id = inv.film_id JOIN rental r ON inv.inventory_id = r.inventory_id GROUP BY cat.name HAVING COUNT(r.rental_id) > 1000 ORDER BY total_disewa DESC LIMIT 5;"
            },
            {
                "num": 9,
                "title": "Top 5 Aktor Terproduktif Sepanjang Masa (DENSE_RANK)",
                "desc": "Gunakan CTE dan Window Function DENSE_RANK() untuk memeringkat aktor berdasarkan jumlah film yang dibintangi. Tampilkan actor_id, first_name, last_name, total_film, dan rank_aktor untuk peringkat 1 hingga 5. Urutkan dari rank_aktor ASC, last_name ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH TopActorFilms AS (SELECT a.actor_id, a.first_name, a.last_name, COUNT(fa.film_id) AS total_film, DENSE_RANK() OVER (ORDER BY COUNT(fa.film_id) DESC) AS rank_aktor FROM actor a JOIN film_actor fa ON a.actor_id = fa.actor_id GROUP BY a.actor_id, a.first_name, a.last_name) SELECT actor_id, first_name, last_name, total_film, rank_aktor FROM TopActorFilms WHERE rank_aktor <= 5 ORDER BY rank_aktor ASC, last_name ASC LIMIT 5;"
            },
            {
                "num": 10,
                "title": "Klasifikasi Nominal Transaksi Staf 1 (CASE WHEN)",
                "desc": "Tampilkan payment_id, amount, payment_date, dan kategori_transaksi (amount >= 8.00: 'Transaksi Besar', amount >= 4.00: 'Transaksi Standar', else: 'Transaksi Kecil') untuk transaksi yang ditangani oleh staff_id = 1. Urutkan dari amount DESC, payment_id ASC, batasi 5 baris.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT p.payment_id, p.amount, p.payment_date, CASE WHEN p.amount >= 8.00 THEN 'Transaksi Besar' WHEN p.amount >= 4.00 THEN 'Transaksi Standar' ELSE 'Transaksi Kecil' END AS kategori_transaksi FROM payment p WHERE p.staff_id = 1 ORDER BY p.amount DESC, p.payment_id ASC LIMIT 5;"
            }
        ]
    },
    {
        "code": "FINAL-D",
        "name": "Paket Final D",
        "description": "Paket Final D: DDL Kamar Sandbox, Kueri Analisis Durasi Rental, Rating Film, dan Margin Pembayaran.",
        "questions": [
            {
                "num": 1,
                "title": "Membuat Database & Tabel Katalog Buku",
                "desc": "Buatlah tabel 'katalog_buku' di kamar Sandbox pribadi Anda dengan struktur: isbn (VARCHAR 20, PRIMARY KEY), judul (VARCHAR 120), pengarang (VARCHAR 80), dan tahun_terbit (INT).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "CREATE TABLE katalog_buku (isbn VARCHAR(20) PRIMARY KEY, judul VARCHAR(120), pengarang VARCHAR(80), tahun_terbit INT);"
            },
            {
                "num": 2,
                "title": "Pemasukan Data Katalog Buku",
                "desc": "Masukkan 3 data ke tabel 'katalog_buku': ('978-602-01', 'Arsitektur Basis Data Modern', 'Dr. Hendra Gunawan', 2024), ('978-602-02', 'SQL Tingkat Lanjut', 'Prof. Siti Aminah', 2023), dan ('978-602-03', 'Optimasi Indeks PostgreSQL', 'Budi Santoso, M.Kom', 2025).",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "INSERT INTO katalog_buku (isbn, judul, pengarang, tahun_terbit) VALUES ('978-602-01', 'Arsitektur Basis Data Modern', 'Dr. Hendra Gunawan', 2024), ('978-602-02', 'SQL Tingkat Lanjut', 'Prof. Siti Aminah', 2023), ('978-602-03', 'Optimasi Indeks PostgreSQL', 'Budi Santoso, M.Kom', 2025);"
            },
            {
                "num": 3,
                "title": "Pembersihan Tabel Katalog",
                "desc": "Hapus tabel 'katalog_buku' dari kamar Sandbox pribadi Anda menggunakan perintah DROP TABLE.",
                "weight": 5, "target_db": "sandbox_pribadi", "diff": "Easy",
                "query": "DROP TABLE IF EXISTS katalog_buku;"
            },
            {
                "num": 4,
                "title": "Aktor Bernama Depan Berawalan J",
                "desc": "Tampilkan actor_id, first_name, dan last_name dari tabel actor untuk aktor yang memiliki nama depan berawalan huruf 'J'. Urutkan berdasarkan last_name ASC, first_name ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT actor_id, first_name, last_name FROM actor WHERE first_name LIKE 'J%' ORDER BY last_name ASC, first_name ASC LIMIT 5;"
            },
            {
                "num": 5,
                "title": "Pelanggan di Wilayah California",
                "desc": "Gabungkan tabel customer dan address untuk menampilkan customer_id, first_name, last_name, email, dan district untuk pelanggan yang beralamat di wilayah district 'California'. Urutkan berdasarkan last_name ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT cu.customer_id, cu.first_name, cu.last_name, cu.email, a.district FROM customer cu JOIN address a ON cu.address_id = a.address_id WHERE a.district = 'California' ORDER BY cu.last_name ASC LIMIT 5;"
            },
            {
                "num": 6,
                "title": "Statistik Durasi Sewa per Tahun Rilis",
                "desc": "Tampilkan tahun rilis (release_year), jumlah film, dan rata-rata durasi sewa dibulatkan 2 desimal (rata_durasi_sewa) dari tabel film dikelompokkan per tahun rilis. Urutkan dari jumlah film terbanyak, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT release_year, COUNT(film_id) AS jumlah_film, ROUND(AVG(rental_duration), 2) AS rata_durasi_sewa FROM film GROUP BY release_year ORDER BY jumlah_film DESC LIMIT 5;"
            },
            {
                "num": 7,
                "title": "Film Durasi Sewa 3 Hari dengan Panjang Di Atas 170 Menit",
                "desc": "Tampilkan title, rental_duration, dan length dari tabel film untuk film dengan rental_duration = 3 yang durasi tayangnya lebih dari 170 menit. Urutkan dari length terpanjang, lalu title ASC, batasi 5 baris.",
                "weight": 10, "target_db": "pagila", "diff": "Medium",
                "query": "SELECT f.title, f.rental_duration, f.length FROM film f WHERE f.rental_duration = 3 AND f.length > 170 ORDER BY f.length DESC, f.title ASC LIMIT 5;"
            },
            {
                "num": 8,
                "title": "Kategori dengan Koleksi Minimal 60 Judul Film",
                "desc": "Tampilkan nama kategori (nama_kategori) dan jumlah filmnya untuk kategori yang memiliki minimal 60 judul film. Urutkan dari jumlah_film terbanyak, lalu nama_kategori ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "SELECT c.name AS nama_kategori, COUNT(fc.film_id) AS jumlah_film FROM category c JOIN film_category fc ON c.category_id = fc.category_id GROUP BY c.name HAVING COUNT(fc.film_id) >= 60 ORDER BY jumlah_film DESC, nama_kategori ASC LIMIT 5;"
            },
            {
                "num": 9,
                "title": "Peringkat Top 5 Pembelanja Terbesar (DENSE_RANK)",
                "desc": "Gunakan CTE dan Window Function DENSE_RANK() untuk memeringkat pelanggan berdasarkan total nominal belanja (total_belanja). Tampilkan customer_id, first_name, last_name, total_belanja, dan rank_belanja untuk 5 peringkat teratas. Urutkan dari rank_belanja ASC, customer_id ASC, batasi 5 baris.",
                "weight": 20, "target_db": "pagila", "diff": "Hard",
                "query": "WITH CustomerRanking AS (SELECT c.customer_id, c.first_name, c.last_name, SUM(p.amount) AS total_belanja, DENSE_RANK() OVER (ORDER BY SUM(p.amount) DESC) AS rank_belanja FROM customer c JOIN payment p ON c.customer_id = p.customer_id GROUP BY c.customer_id, c.first_name, c.last_name) SELECT customer_id, first_name, last_name, total_belanja, rank_belanja FROM CustomerRanking WHERE rank_belanja <= 5 ORDER BY rank_belanja ASC, customer_id ASC LIMIT 5;"
            },
            {
                "num": 10,
                "title": "Valuasi Aset Penggantian Film Rating PG-13 (CASE WHEN)",
                "desc": "Tampilkan film_id, title, replacement_cost, dan valuasi_aset (replacement_cost >= 25.00: 'Aset Mahal', replacement_cost >= 18.00: 'Aset Menengah', else: 'Aset Ekonomis') untuk film berating 'PG-13'. Urutkan dari replacement_cost termahal, lalu title ASC, batasi 5 baris.",
                "weight": 30, "target_db": "pagila", "diff": "Very Hard",
                "query": "SELECT f.film_id, f.title, f.replacement_cost, CASE WHEN f.replacement_cost >= 25.00 THEN 'Aset Mahal' WHEN f.replacement_cost >= 18.00 THEN 'Aset Menengah' ELSE 'Aset Ekonomis' END AS valuasi_aset FROM film f WHERE f.rating = 'PG-13' ORDER BY f.replacement_cost DESC, f.title ASC LIMIT 5;"
            }
        ]
    }
]

def seed_packages_and_questions():
    print("=" * 75)
    print("STARTING SEEDER: DRAFT KONSEP FINAL BASIS DATA 2026")
    print("=" * 75)

    conn = database.get_sqlite_conn()
    cur = conn.cursor()

    # 1. Clean existing packages and questions
    print("\n[STEP 1] Cleaning old packages and questions...")
    cur.execute("DELETE FROM questions;")
    cur.execute("DELETE FROM exam_packages;")
    conn.commit()
    print("-> Cleared old questions and packages.")

    # 2. Insert Packages and Questions
    total_packages = len(PACKAGES_DATA)
    total_questions = 0

    for pkg_idx, pkg in enumerate(PACKAGES_DATA, 1):
        pkg_code = pkg["code"]
        pkg_name = pkg["name"]
        pkg_desc = pkg["description"]
        print(f"\n[STEP 2.{pkg_idx}] Seeding Package '{pkg_code}' ({pkg_name})...")

        cur.execute("""
            INSERT INTO exam_packages (code, name, description, is_active)
            VALUES (?, ?, ?, 1);
        """, (pkg_code, pkg_name, pkg_desc))

        pkg_questions = pkg["questions"]
        assert len(pkg_questions) == 10, f"Package {pkg_code} must have exactly 10 questions!"

        for q in pkg_questions:
            qnum = q["num"]
            title = q["title"]
            desc = q["desc"]
            weight = q["weight"]
            target_db = q["target_db"]
            diff = q["diff"]
            expected_query = q["query"]
            image_url = ""

            # For Pagila queries (Q4 to Q10), execute and render output table screenshot
            if target_db == "pagila" and expected_query:
                print(f"  -> Generating table preview for Q{qnum}: {title}...")
                res = database.execute_student_query(expected_query, active_db="pagila")
                if res.get("success") and res.get("columns"):
                    img_filename = f"expected_{pkg_code.lower()}_q{qnum}.png"
                    img_disk_path = os.path.join(UPLOADS_DIR, img_filename)
                    render_table_screenshot(
                        columns=res["columns"],
                        rows=res["rows"],
                        title=f"Ekspektasi Output Tabel: {title}",
                        output_path=img_disk_path,
                        max_rows=5
                    )
                    image_url = f"/static/uploads/questions/{img_filename}"
                else:
                    print(f"  [WARN] Query for Q{qnum} failed to execute on Pagila: {res.get('error')}")

            cur.execute("""
                INSERT INTO questions (
                    category, question_number, title, description,
                    score_weight, expected_query, target_database,
                    difficulty_level, expected_output_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pkg_code, qnum, title, desc,
                weight, expected_query, target_db,
                diff, image_url
            ))
            total_questions += 1

        conn.commit()
        print(f"-> Package '{pkg_code}' seeded with 10 questions and screenshots.")

    conn.close()

    print("\n" + "=" * 75)
    print(f"SEEDING COMPLETE! Total Packages: {total_packages}, Total Questions: {total_questions}")
    print("=" * 75)

if __name__ == "__main__":
    seed_packages_and_questions()
