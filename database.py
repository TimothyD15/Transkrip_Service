"""
database.py — Script standalone untuk inisialisasi tabel database.

Dijalankan SEKALI oleh service `db-init` di docker-compose, setelah
MySQL siap dan sebelum transkrip-service dinyalakan.

Fungsi utama:
    - Membuat semua tabel yang didefinisikan di Transkrip/models.py
      (KRS, Nilai, KHS, KHSDetail, Transkrip, DetailTranskrip).
    - create_all() bersifat idempotent: aman dijalankan berulang kali,
      hanya membuat tabel yang BELUM ada — tidak akan menghapus data.
    - Retry otomatis (MAX_RETRIES × 3 detik) untuk menunggu MySQL
      benar-benar siap menerima koneksi.

Database: MySQL 8 via PyMySQL.
Connection string dibaca dari environment variable DATABASE_URL,
dengan fallback ke MySQL default yang sesuai docker-compose.yml.
"""
import time
import os
from sqlalchemy import create_engine, text

from Transkrip.models import Base

# Ambil DATABASE_URL dari environment variable.
# Default disesuaikan dengan service `transkrip-db` di docker-compose.yml.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://transkrip_user:transkrip_pass@transkrip-db:3306/transkrip_db?charset=utf8mb4"
)

engine = create_engine(
    DATABASE_URL,
    # pool_pre_ping: setiap kali mengambil koneksi dari pool,
    # lakukan SELECT 1 terlebih dahulu. Ini mencegah error
    # "MySQL server has gone away" saat koneksi idle terlalu lama.
    pool_pre_ping=True,
)

MAX_RETRIES = 15
for i in range(MAX_RETRIES):
    try:
        # Tes koneksi sebelum create_all
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # Buat semua tabel (idempotent)
        Base.metadata.create_all(bind=engine)
        print("Tabel database berhasil dibuat / sudah tersedia.")
        break
    except Exception as e:
        print(f"Database belum siap ({i + 1}/{MAX_RETRIES}): {e}")
        if i < MAX_RETRIES - 1:
            time.sleep(3)
        else:
            print("Gagal konek ke database setelah beberapa percobaan.")
            raise
