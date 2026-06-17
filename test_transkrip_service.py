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


# Data mock identik dengan mocks/mock_services.py
PRS_DB = {
    1: {"id_mahasiswa": 1, "semester": "Ganjil", "tahun_ajaran": "2024-2025"},
}
PRS_DETAIL_DB = {
    1: [
        {"id_matkul": 101, "id_kelas": 1},
        {"id_matkul": 102, "id_kelas": 2},
    ],
}
MATKUL_DB = {
    101: {"id_matkul": 101, "nama_matkul": "Algoritma dan Struktur Data", "sks": 4},
    102: {"id_matkul": 102, "nama_matkul": "Basis Data", "sks": 3},
}
MAHASISWA_DB = {
    1: {"id_mahasiswa": 1, "nama": "Budi Santoso", "nrp": "12345678"},
}


def make_service(session):
    """
    Buat instance TranskripService dengan dependency di-mock:
        - db     -> SQLAlchemy session SQLite in-memory
        - master -> mock RpcProxy ke master_service
        - prs    -> mock RpcProxy ke prs_service
    """
    service = TranskripService()
    service.db = session

    service.master = MagicMock()
    service.master.get_matkul_by_id.side_effect = lambda id_matkul: MATKUL_DB.get(id_matkul)
    service.master.get_mahasiswa_by_id.side_effect = lambda id_mhs: MAHASISWA_DB.get(id_mhs)

    service.prs = MagicMock()
    service.prs.get_prs_by_id.side_effect = lambda id_prs: PRS_DB.get(id_prs)
    service.prs.get_prs_detail_by_prs_id.side_effect = lambda id_prs: PRS_DETAIL_DB.get(id_prs, [])

    return service


class TestTranskripService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.service = make_service(self.session)

    def tearDown(self):
        self.session.close()

    def test_full_flow(self):
        # ── 1. Push PRS -> KRS ──────────────────────────────────
        result = self.service.push_prs_ke_krs(1)
        print("push_prs_ke_krs:", result)
        self.assertEqual(result["status"], "ok")
        id_krs = result["id_krs"]
        self.assertEqual(id_krs, 1)

        # Push lagi dengan id_prs sama -> harus error (duplikat)
        dup = self.service.push_prs_ke_krs(1)
        print("push_prs_ke_krs (dup):", dup)
        self.assertEqual(dup["status"], "error")

        # Push id_prs yang tidak ada -> harus error
        not_found = self.service.push_prs_ke_krs(999)
        print("push_prs_ke_krs (not found):", not_found)
        self.assertEqual(not_found["status"], "error")

        # ── 2. Ambil nilai per kelas (sebelum diisi) ─────────────
        nilai_kelas1 = self.service.get_nilai_by_kelas(1)
        print("get_nilai_by_kelas(1):", nilai_kelas1)
        self.assertEqual(len(nilai_kelas1), 1)
        id_nilai_matkul1 = nilai_kelas1[0]["id_nilai"]
        self.assertEqual(nilai_kelas1[0]["status"], "belum_ternilai")

        nilai_kelas2 = self.service.get_nilai_by_kelas(2)
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

        # ── 4. Input nilai bertahap untuk matkul 1 (id_matkul=101, sks=4) ──
        r1 = self.service.input_nilai(id_nilai_matkul1, "uts", 80)
        print("input_nilai uts:", r1)
        self.assertEqual(r1["status"], "ok")
        self.assertIsNone(r1["nilai_huruf"])  # belum lengkap

        r2 = self.service.input_nilai(id_nilai_matkul1, "uas", 90)
        r3 = self.service.input_nilai(id_nilai_matkul1, "tes1", 85)
        r4 = self.service.input_nilai(id_nilai_matkul1, "tes2", 75)
        print("input_nilai tes2 (lengkap):", r4)
        self.assertEqual(r4["status"], "ok")
        self.assertIsNotNone(r4["nilai_huruf"])

        # Verifikasi nilai akhir = 80*0.3 + 90*0.4 + 85*0.15 + 75*0.15
        expected_akhir = round(80 * 0.3 + 90 * 0.4 + 85 * 0.15 + 75 * 0.15, 2)
        print("expected nilai_akhir matkul1:", expected_akhir)

        # ── 5. Input nilai lengkap untuk matkul 2 (id_matkul=102, sks=3) ──
        for komp, val in [("uts", 70), ("uas", 65), ("tes1", 60), ("tes2", 72)]:
            r = self.service.input_nilai(id_nilai_matkul2, komp, val)
        print("input_nilai matkul2 (lengkap):", r)
        self.assertEqual(r["status"], "ok")

        # ── 6. get_khs_by_mahasiswa ───────────────────────────────
        khs = self.service.get_khs_by_mahasiswa(1, "Ganjil", "2024-2025")
        print("get_khs_by_mahasiswa:", khs)
        self.assertEqual(len(khs["matkul"]), 2)
        self.assertGreater(khs["ips"], 0)

        # ── 7. get_transkrip_mahasiswa ───────────────────────────
        transkrip = self.service.get_transkrip_mahasiswa(1)
        print("get_transkrip_mahasiswa:", transkrip)
        self.assertEqual(transkrip["status"], "ok")
        self.assertEqual(transkrip["mahasiswa"]["nama"], "Budi Santoso")
        self.assertEqual(transkrip["total_sks"], 4 + 3)
        self.assertEqual(len(transkrip["riwayat"]), 1)
        self.assertEqual(len(transkrip["riwayat"][0]["matkul"]), 2)

        # transkrip untuk mahasiswa yang belum ada -> error
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
        self.assertEqual(ipk["ipk"], khs["ips"])  # baru 1 semester, IPK == IPS

        # IPK mahasiswa yang belum ada transkrip -> default 0
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
