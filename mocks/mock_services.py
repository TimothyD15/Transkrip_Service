"""
mocks/mock_services.py — Mock service untuk master_service dan prs_service.

Format response DISESUAIKAN dengan Master Service asli:
  - master: {"status": "success", "data": {...}}
  - method names: get_course_by_id, get_student_by_id, get_semester_by_id
  - field names: "name" bukan "nama_matkul", "name" bukan "nama"

GUNAKAN HANYA UNTUK TESTING LOKAL/MANDIRI via docker-compose.override.yml
"""
from nameko.rpc import rpc

SEMESTER_DB = {
    1: {"id": 1, "name": "Ganjil", "year": "2024-2025", "is_active": True, "curriculum_id": 1},
}

PESERTA_DB = {
    1: [
        {"id_mahasiswa": 1, "id_mata_kuliah": 101, "id_kelas": 1},
        {"id_mahasiswa": 1, "id_mata_kuliah": 102, "id_kelas": 2},
    ],
}

MATKUL_DB = {
    101: {"id": 101, "code": "IF001", "name": "Algoritma dan Struktur Data", "sks": 4, "unit_id": 1},
    102: {"id": 102, "code": "IF002", "name": "Basis Data", "sks": 3, "unit_id": 1},
}

MAHASISWA_DB = {
    1: {"id": 1, "nrp": "12345678", "name": "Budi Santoso", "email": "budi@example.com", "status": "aktif", "unit_id": 1},
}


class MockMasterService:
    """
    Mock master_service — format response SAMA PERSIS dengan Master asli.
    Semua method yang dipanggil Transkrip ada di sini.
    """
    name = "master_service"

    @rpc
    def get_course_by_id(self, course_id: int):
        """Dipanggil saat input_nilai() — ambil SKS dan nama matkul."""
        matkul = MATKUL_DB.get(course_id)
        if not matkul:
            return {"status": "error", "message": "Mata Kuliah tidak ditemukan"}
        return {"status": "success", "data": matkul}

    @rpc
    def get_student_by_id(self, student_id: int):
        """Dipanggil saat get_transkrip_mahasiswa() — ambil nama mahasiswa."""
        mhs = MAHASISWA_DB.get(student_id)
        if not mhs:
            return {"status": "error", "message": "Mahasiswa tidak ditemukan"}
        return {"status": "success", "data": mhs}

    @rpc
    def get_semester_by_id(self, semester_id: int):
        """Dipanggil saat push_semester_ke_krs() — ambil nama dan tahun semester."""
        semester = SEMESTER_DB.get(semester_id)
        if not semester:
            return {"status": "error", "message": "Semester tidak ditemukan"}
        return {"status": "success", "data": semester}

    @rpc
    def get_active_semester(self):
        """Opsional — untuk cek semester aktif."""
        for s in SEMESTER_DB.values():
            if s.get("is_active"):
                return {"status": "success", "data": s}
        return {"status": "error", "message": "Tidak ada semester aktif"}


class MockPrsService:
    """
    Mock prs_service — format response SAMA PERSIS dengan PRS asli.
    """
    name = "prs_service"

    @rpc
    def push_peserta_to_transkrip(self, id_semester: int):
        """
        Dipanggil saat push_semester_ke_krs().
        Return semua peserta yang sudah tervalidasi untuk semester ini.
        """
        peserta = PESERTA_DB.get(id_semester, [])
        if not peserta:
            return {"error": f"Tidak ada peserta untuk semester {id_semester}"}
        return {"peserta": peserta}