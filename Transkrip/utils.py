"""
utils.py — Fungsi-fungsi murni (pure functions) untuk kalkulasi akademik.

Tidak ada akses database di sini, hanya logika perhitungan.
Ini memudahkan unit testing karena fungsi bisa diuji tanpa database.
"""

# ─────────────────────────────────────────────────────────────
# GRADE_TABLE
# Tabel konversi nilai angka → huruf → bobot mutu (untuk hitung IPS/IPK).
# Diurutkan dari nilai tertinggi ke terendah agar loop bisa berhenti
# di baris pertama yang cocok.
# ─────────────────────────────────────────────────────────────
GRADE_TABLE = [
    (85.5, "A",  4.0),
    (75.5, "B+", 3.5),
    (68.5, "B",  3.0),
    (60.5, "C+", 2.5),
    (55.5, "C",  2.0),
    (40.5, "D",  1.0),
    (0,    "E",  0.0),
]

# Komponen nilai yang valid — dipakai untuk validasi input dari dosen
KOMPONEN_VALID = {"uts", "uas", "tes1", "tes2"}


def hitung_nilai_akhir(uts: float, uas: float, tes1: float, tes2: float) -> float:
    """
    Hitung nilai akhir dari komponen-komponen penilaian.

    Bobot:
        UTS  = 35%
        UAS  = 35%
        Tes1 = 15%
        Tes2 = 15%
    """
    return round((uts * 0.30) + (uas * 0.40) + (tes1 * 0.15) + (tes2 * 0.15), 2)


def nilai_ke_huruf(nilai_angka: float) -> tuple[str, float]:
    """
    Konversi nilai angka ke huruf dan bobot mutu.

    Args:
        nilai_angka: Nilai akhir (0–100). Boleh None (anggap 0).

    Returns:
        Tuple (huruf: str, bobot: float), contoh: ("A", 4.0) atau ("B+", 3.5)
    """
    if nilai_angka is None:
        nilai_angka = 0

    for batas, huruf, bobot in GRADE_TABLE:
        if nilai_angka >= batas:
            return huruf, bobot
    return "E", 0.0


def hitung_ips(detail_nilai_list: list[dict]) -> float:
    """
    Hitung IPS (Indeks Prestasi Semester) atau IPK dari daftar nilai.

    Rumus: IPS = Σ(SKS × Bobot) / Σ(SKS)

    Args:
        detail_nilai_list: List of dict, masing-masing berisi:
            - "sks"   : int   — jumlah SKS matkul
            - "bobot" : float — bobot mutu (dari nilai_ke_huruf)

    Returns:
        IPS/IPK sebagai float, dibulatkan 2 desimal. 0.0 jika list kosong.

    Contoh:
        [{"sks": 3, "bobot": 4.0}, {"sks": 2, "bobot": 3.0}]
        → (3×4.0 + 2×3.0) / (3+2) = 18/5 = 3.60
    """
    if not detail_nilai_list:
        return 0.0
    total_sks  = sum(d["sks"] for d in detail_nilai_list)
    total_mutu = sum(d["sks"] * d["bobot"] for d in detail_nilai_list)
    return round(total_mutu / total_sks, 2) if total_sks > 0 else 0.0


def semua_nilai_lengkap(nilai_uts, nilai_uas, nilai_tes1, nilai_tes2) -> bool:
    """
    Cek apakah semua komponen nilai sudah diisi (tidak ada yang None).

    Returns:
        True jika semua komponen tidak None, False jika ada yang masih None.
    """
    return all(v is not None for v in [nilai_uts, nilai_uas, nilai_tes1, nilai_tes2])


def validasi_komponen(komponen: str) -> bool:
    """
    Validasi bahwa nama komponen yang dikirim dosen adalah valid.
    Mencegah injeksi atribut sembarangan via setattr().

    Returns:
        True jika komponen ada di KOMPONEN_VALID, False jika tidak.
    """
    return isinstance(komponen, str) and komponen in KOMPONEN_VALID
