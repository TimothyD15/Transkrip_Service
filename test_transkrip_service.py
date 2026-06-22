"""
test_transkrip_service.py — Test end-to-end logika TranskripService
menggunakan SQLite in-memory dan mock RPC (master_service, prs_service),
TANPA membutuhkan RabbitMQ.

Cara jalankan:
    python3 test_transkrip_service.py

Test ini memverifikasi alur:
    1. push_prs_ke_krs()  -> KRS + Nilai kosong terbuat
    2. input_nilai() x4   -> nilai akhir, KHS, DetailTranskrip, IPK terhitung
    3. get_khs_by_mahasiswa(), get_transkrip_mahasiswa(),
       get_ips_per_semester(), get_ipk_mahasiswa(), get_nilai_by_kelas()
"""
import unittest
from unittest.mock import MagicMock
 
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
 
from Transkrip.models import Base
from Transkrip.service import TranskripService
 
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
 
 
def make_service(session):
    """
    Buat instance TranskripService dengan semua dependency di-mock.
    Format mock SAMA dengan response Master Service asli.
    """
    service = TranskripService()
    service.db = session
 
    service.master = MagicMock()
 
    def mock_get_course_by_id(course_id):
        matkul = MATKUL_DB.get(course_id)
        if not matkul:
            return {"status": "error", "message": "Mata Kuliah tidak ditemukan"}
        return {"status": "success", "data": matkul}
 
    def mock_get_student_by_id(student_id):
        mhs = MAHASISWA_DB.get(student_id)
        if not mhs:
            return {"status": "error", "message": "Mahasiswa tidak ditemukan"}
        return {"status": "success", "data": mhs}
 
    def mock_get_semester_by_id(semester_id):
        semester = SEMESTER_DB.get(semester_id)
        if not semester:
            return {"status": "error", "message": "Semester tidak ditemukan"}
        return {"status": "success", "data": semester}
 
    service.master.get_course_by_id.side_effect   = mock_get_course_by_id
    service.master.get_student_by_id.side_effect  = mock_get_student_by_id
    service.master.get_semester_by_id.side_effect = mock_get_semester_by_id
 
    service.prs = MagicMock()
 
    def mock_push_peserta(id_semester):
        peserta = PESERTA_DB.get(id_semester, [])
        if not peserta:
            return {"error": f"Tidak ada peserta untuk semester {id_semester}"}
        return {"peserta": peserta}
 
    service.prs.push_peserta_to_transkrip.side_effect = mock_push_peserta
 
    return service
 
 
class TestTranskripService(unittest.TestCase):
    def setUp(self):
        self.engine  = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session      = sessionmaker(bind=self.engine)
        self.session = Session()
        self.service = make_service(self.session)
 
    def tearDown(self):
        self.session.close()
 
    def test_full_flow(self):
        # ── 1. Push semester -> KRS ──────────────────────────────
        result = self.service.push_semester_ke_krs(1)
        print("push_semester_ke_krs:", result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["berhasil"]), 1)
        id_krs = result["berhasil"][0]["id_krs"]
 
        # Push lagi semester yang sama -> mahasiswa dilewati (duplikat)
        dup = self.service.push_semester_ke_krs(1)
        print("push_semester_ke_krs (dup):", dup)
        self.assertEqual(dup["status"], "ok")
        self.assertEqual(len(dup["dilewati"]), 1)
 
        # Push semester yang tidak ada -> error dari master
        not_found = self.service.push_semester_ke_krs(999)
        print("push_semester_ke_krs (semester not found):", not_found)
        self.assertEqual(not_found["status"], "error")
 
        # ── 2. Ambil nilai per kelas (sebelum diisi) ─────────────
        nilai_kelas1 = self.service.get_nilai_by_kelas(1)
        print("get_nilai_by_kelas(1):", nilai_kelas1)
        self.assertEqual(len(nilai_kelas1), 1)
        id_nilai_matkul1 = nilai_kelas1[0]["id_nilai"]
        self.assertEqual(nilai_kelas1[0]["status"], "belum_ternilai")
 
        nilai_kelas2     = self.service.get_nilai_by_kelas(2)
        id_nilai_matkul2 = nilai_kelas2[0]["id_nilai"]
 
        # ── 3. Validasi input_nilai ──────────────────────────────
        bad_komponen = self.service.input_nilai(id_nilai_matkul1, "kuis", 80)
        print("input_nilai (komponen invalid):", bad_komponen)
        self.assertEqual(bad_komponen["status"], "error")
 
        bad_range = self.service.input_nilai(id_nilai_matkul1, "uts", 150)
        print("input_nilai (nilai out of range):", bad_range)
        self.assertEqual(bad_range["status"], "error")
 
        bad_type = self.service.input_nilai(id_nilai_matkul1, "uts", "abc")
        print("input_nilai (nilai bukan angka):", bad_type)
        self.assertEqual(bad_type["status"], "error")
 
        not_found_nilai = self.service.input_nilai(9999, "uts", 80)
        print("input_nilai (id_nilai tidak ada):", not_found_nilai)
        self.assertEqual(not_found_nilai["status"], "error")
 
        # ── 4. Input nilai bertahap untuk matkul 1 ───────────────
        r1 = self.service.input_nilai(id_nilai_matkul1, "uts", 80)
        print("input_nilai uts:", r1)
        self.assertEqual(r1["status"], "ok")
        self.assertIsNone(r1["nilai_huruf"])
 
        self.service.input_nilai(id_nilai_matkul1, "uas", 90)
        self.service.input_nilai(id_nilai_matkul1, "tes1", 85)
        r4 = self.service.input_nilai(id_nilai_matkul1, "tes2", 75)
        print("input_nilai tes2 (lengkap):", r4)
        self.assertEqual(r4["status"], "ok")
        self.assertIsNotNone(r4["nilai_huruf"])
        # 80*0.3 + 90*0.4 + 85*0.15 + 75*0.15 = 84.0 -> B+
        self.assertEqual(r4["nilai_huruf"], "B+")
 
        # ── 5. Input nilai matkul 2 ───────────────────────────────
        for komp, val in [("uts", 70), ("uas", 65), ("tes1", 60), ("tes2", 72)]:
            r = self.service.input_nilai(id_nilai_matkul2, komp, val)
        print("input_nilai matkul2 (lengkap):", r)
        self.assertEqual(r["status"], "ok")
 
        # ── 6. get_khs_by_mahasiswa ───────────────────────────────
        khs = self.service.get_khs_by_mahasiswa(1, "Ganjil", "2024-2025")
        print("get_khs_by_mahasiswa:", khs)
        self.assertEqual(len(khs["matkul"]), 2)
        self.assertGreater(khs["ips"], 0)
 
        # ── 7. get_transkrip_mahasiswa ────────────────────────────
        transkrip = self.service.get_transkrip_mahasiswa(1)
        print("get_transkrip_mahasiswa:", transkrip)
        self.assertEqual(transkrip["status"], "ok")
        # Master return "name", kita map ke "nama"
        self.assertEqual(transkrip["mahasiswa"]["nama"], "Budi Santoso")
        self.assertEqual(transkrip["total_sks"], 4 + 3)
        self.assertEqual(len(transkrip["riwayat"]), 1)
        self.assertEqual(len(transkrip["riwayat"][0]["matkul"]), 2)
 
        no_transkrip = self.service.get_transkrip_mahasiswa(999)
        print("get_transkrip_mahasiswa (not found):", no_transkrip)
        self.assertEqual(no_transkrip["status"], "error")
 
        # ── 8. get_ips_per_semester ───────────────────────────────
        ips_list = self.service.get_ips_per_semester(1)
        print("get_ips_per_semester:", ips_list)
        self.assertEqual(len(ips_list), 1)
        self.assertEqual(ips_list[0]["semester"], "Ganjil")
 
        # ── 9. get_ipk_mahasiswa ──────────────────────────────────
        ipk = self.service.get_ipk_mahasiswa(1)
        print("get_ipk_mahasiswa:", ipk)
        self.assertEqual(ipk["total_sks"], 7)
        self.assertEqual(ipk["ipk"], khs["ips"])
 
        ipk_none = self.service.get_ipk_mahasiswa(999)
        print("get_ipk_mahasiswa (not found):", ipk_none)
        self.assertEqual(ipk_none["ipk"], 0.0)
        self.assertEqual(ipk_none["total_sks"], 0)
 
        # ── 10. get_krs_by_mahasiswa ──────────────────────────────
        krs_list = self.service.get_krs_by_mahasiswa(1)
        print("get_krs_by_mahasiswa:", krs_list)
        self.assertEqual(len(krs_list), 1)
        self.assertEqual(krs_list[0]["id_krs"], id_krs)
 
 
if __name__ == "__main__":
    unittest.main(verbosity=2)
 