"""
mocks/mock_services.py — Mock service untuk master_service dan prs_service.

GUNAKAN HANYA UNTUK TESTING LOKAL/MANDIRI, ketika service Master dan PRS
asli dari kelompok lain belum tersedia / belum dijalankan.

Cara pakai:
    nameko run --config config.yml mocks.mock_services

Jalankan BERSAMAAN (proses terpisah, atau gabung di CMD) dengan
Transkrip.service:TranskripService dan gateway.service:GatewayService,
karena transkrip_service melakukan RPC ke "master_service" dan "prs_service".

Data di sini hanya contoh statis (in-memory), cukup untuk
membuktikan alur push_prs_ke_krs -> input_nilai -> KHS/Transkrip
berjalan dengan benar secara end-to-end.
"""
from nameko.rpc import rpc


# ─────────────────────────────────────────────────────────────
# Data contoh
# ─────────────────────────────────────────────────────────────

# id_prs -> data PRS yang sudah disetujui
PRS_DB = {
    1: {"id_mahasiswa": 1, "semester": "Ganjil", "tahun_ajaran": "2024-2025"},
}

# id_prs -> daftar matkul yang diambil (id_matkul, id_kelas)
PRS_DETAIL_DB = {
    1: [
        {"id_matkul": 101, "id_kelas": 1},
        {"id_matkul": 102, "id_kelas": 2},
    ],
}

# id_matkul -> data matkul (nama, sks)
MATKUL_DB = {
    101: {"id_matkul": 101, "nama_matkul": "Algoritma dan Struktur Data", "sks": 4},
    102: {"id_matkul": 102, "nama_matkul": "Basis Data", "sks": 3},
}

# id_mahasiswa -> data mahasiswa
MAHASISWA_DB = {
    1: {"id_mahasiswa": 1, "nama": "Budi Santoso", "nrp": "12345678"},
}


class MockMasterService:
    """Mock untuk master_service (Grup A — data mahasiswa & matkul)."""
    name = "master_service"

    @rpc
    def get_matkul_by_id(self, id_matkul: int):
        return MATKUL_DB.get(
            id_matkul,
            {"id_matkul": id_matkul, "nama_matkul": f"Matkul #{id_matkul}", "sks": 3},
        )

    @rpc
    def get_mahasiswa_by_id(self, id_mahasiswa: int):
        return MAHASISWA_DB.get(
            id_mahasiswa,
            {"id_mahasiswa": id_mahasiswa, "nama": f"Mahasiswa #{id_mahasiswa}", "nrp": "-"},
        )


class MockPrsService:
    """Mock untuk prs_service (Grup E — data PRS tervalidasi)."""
    name = "prs_service"

    @rpc
    def get_prs_by_id(self, id_prs: int):
        return PRS_DB.get(id_prs)

    @rpc
    def get_prs_detail_by_prs_id(self, id_prs: int):
        return PRS_DETAIL_DB.get(id_prs, [])
