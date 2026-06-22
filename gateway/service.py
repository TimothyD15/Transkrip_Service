"""
gateway/service.py — Gateway HTTP untuk mengakses Transkrip Service.

Service ini TIDAK menyimpan data sendiri. Tugasnya hanya:
    1. Menerima request HTTP (dari Postman/client/service lain)
    2. Memvalidasi body request
    3. Meneruskan (RPC) ke transkrip_service
    4. Mengembalikan response HTTP

PENTING: nama service ini HARUS BERBEDA dari "transkrip_service"
(yang dipakai oleh Transkrip/service.py), karena dua service tidak
boleh memakai nama yang sama dalam satu proses Nameko.
"""
import json
import os
 
import jwt
from nameko.exceptions import BadRequest
from nameko.rpc import RpcProxy
from werkzeug import Response
 
from gateway.entrypoints import http
 
 
class GatewayService:
    name = "gateway_service"
 
    transkrip_rpc = RpcProxy("transkrip_service")
 
    def _check_jwt(self, request):
        """
        Validasi JWT token dari header Authorization.
        Token dibuat oleh Master Service saat login.
 
        Returns:
            (payload, None)     jika token valid
            (None, Response)    jika token tidak valid / tidak ada
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None, Response(
                json.dumps({"status": "error", "message": "Token tidak ditemukan. Silakan login terlebih dahulu."}),
                status=401,
                mimetype="application/json"
            )
 
        token = auth_header.split(" ")[1]
        try:
            SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback_secret")
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return payload, None
        except jwt.ExpiredSignatureError:
            return None, Response(
                json.dumps({"status": "error", "message": "Token sudah kadaluwarsa, silakan login kembali."}),
                status=401,
                mimetype="application/json"
            )
        except jwt.InvalidTokenError:
            return None, Response(
                json.dumps({"status": "error", "message": "Token tidak valid."}),
                status=401,
                mimetype="application/json"
            )
 
    def _check_role(self, payload, allowed_types=None, allowed_roles=None):
        """
        Cek apakah user punya akses berdasarkan type dan role.
 
        Args:
            payload       : hasil decode JWT
            allowed_types : list type yang diizinkan, misal ["dosen"]
            allowed_roles : list role yang diizinkan, misal ["admin", "kaprodi"]
 
        Returns:
            (payload, None)     jika akses diizinkan
            (None, Response)    jika akses ditolak
        """
        user_type  = payload.get("type", "")
        user_roles = payload.get("roles", [])
 
        if allowed_types and user_type not in allowed_types:
            return None, Response(
                json.dumps({"status": "error", "message": f"Akses ditolak. Fitur ini tidak untuk {user_type}."}),
                status=403,
                mimetype="application/json"
            )
 
        if allowed_roles:
            has_access = any(role in allowed_roles for role in user_roles)
            if not has_access:
                return None, Response(
                    json.dumps({"status": "error", "message": f"Akses ditolak. Butuh role: {allowed_roles}."}),
                    status=403,
                    mimetype="application/json"
                )
 
        return payload, None
 
    @http("POST", "/push_semester_ke_krs")
    def push_semester_ke_krs(self, request):
        """
        Push semua peserta PRS tervalidasi ke KRS.
        Hanya bisa diakses oleh dosen dengan role admin/kaprodi/sekprodi.
 
        Body JSON: {"id_semester": 1}
        """
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        _, err = self._check_role(jwt_payload, allowed_types=["dosen"])
        if err:
            return err
 
        try:
            data        = request.get_json(force=True)
            id_semester = data["id_semester"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise BadRequest(f"Invalid request body: {e}")
 
        result = self.transkrip_rpc.push_semester_ke_krs(id_semester)
 
        status_code = 200 if result.get("status") == "ok" else 400
        return Response(json.dumps(result), status=status_code, mimetype="application/json")
 
    @http("POST", "/input_nilai")
    def input_nilai(self, request):
        """
        Dosen mengisi salah satu komponen nilai.
        Hanya bisa diakses oleh dosen.
 
        Body JSON: {"id_nilai": 1, "komponen": "uts", "nilai": 85.5}
        """
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        _, err = self._check_role(jwt_payload, allowed_types=["dosen"])
        if err:
            return err
 
        try:
            data     = request.get_json(force=True)
            id_nilai = data["id_nilai"]
            komponen = data["komponen"]
            nilai    = data["nilai"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise BadRequest(f"Invalid request body: {e}")
 
        result      = self.transkrip_rpc.input_nilai(id_nilai, komponen, nilai)
        status_code = 200 if result.get("status") == "ok" else 400
        return Response(json.dumps(result), status=status_code, mimetype="application/json")
 
    @http("GET", "/nilai/kelas/<int:id_kelas>")
    def get_nilai_by_kelas(self, request, id_kelas):
        """
        Ambil semua nilai mahasiswa dalam satu kelas.
        Bisa diakses dosen maupun mahasiswa.
        """
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        result = self.transkrip_rpc.get_nilai_by_kelas(id_kelas)
        return Response(json.dumps(result), status=200, mimetype="application/json")
 
    @http("GET", "/khs/<int:id_mahasiswa>")
    def get_khs_by_mahasiswa(self, request, id_mahasiswa):
        """
        Ambil KHS mahasiswa untuk semester tertentu.
        Query params: ?tahun_ajaran=2024-2025&semester=Ganjil
 
        Mahasiswa hanya bisa lihat KHS milik sendiri.
        Dosen bisa lihat KHS siapa saja.
        """
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        user_type = jwt_payload.get("type")
        user_id   = jwt_payload.get("user_id")
        if user_type == "mahasiswa" and user_id != id_mahasiswa:
            return Response(
                json.dumps({"status": "error", "message": "Akses ditolak. Anda hanya bisa melihat KHS milik sendiri."}),
                status=403,
                mimetype="application/json"
            )
 
        tahun_ajaran = request.args.get("tahun_ajaran")
        semester     = request.args.get("semester")
        if not tahun_ajaran or not semester:
            raise BadRequest("Query parameter 'tahun_ajaran' dan 'semester' wajib diisi")
 
        result = self.transkrip_rpc.get_khs_by_mahasiswa(id_mahasiswa, semester, tahun_ajaran)
        return Response(json.dumps(result), status=200, mimetype="application/json")
 
    @http("GET", "/krs/<int:id_mahasiswa>")
    def get_krs_by_mahasiswa(self, request, id_mahasiswa):
        """Ambil semua KRS milik seorang mahasiswa."""
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        result = self.transkrip_rpc.get_krs_by_mahasiswa(id_mahasiswa)
        return Response(json.dumps(result), status=200, mimetype="application/json")
 
    @http("GET", "/transkrip/<int:id_mahasiswa>")
    def get_transkrip_mahasiswa(self, request, id_mahasiswa):
        """
        Ambil transkrip lengkap mahasiswa.
        Mahasiswa hanya bisa lihat transkrip milik sendiri.
        """
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        user_type = jwt_payload.get("type")
        user_id   = jwt_payload.get("user_id")
        if user_type == "mahasiswa" and user_id != id_mahasiswa:
            return Response(
                json.dumps({"status": "error", "message": "Akses ditolak. Anda hanya bisa melihat transkrip milik sendiri."}),
                status=403,
                mimetype="application/json"
            )
 
        result      = self.transkrip_rpc.get_transkrip_mahasiswa(id_mahasiswa)
        status_code = 200 if result.get("status") != "error" else 404
        return Response(json.dumps(result), status=status_code, mimetype="application/json")
 
    @http("GET", "/ips/<int:id_mahasiswa>")
    def get_ips_per_semester(self, request, id_mahasiswa):
        """Ambil riwayat IPS mahasiswa per semester."""
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        result = self.transkrip_rpc.get_ips_per_semester(id_mahasiswa)
        return Response(json.dumps(result), status=200, mimetype="application/json")
 
    @http("GET", "/ipk/<int:id_mahasiswa>")
    def get_ipk_mahasiswa(self, request, id_mahasiswa):
        """Ambil IPK terkini mahasiswa."""
        jwt_payload, err = self._check_jwt(request)
        if err:
            return err
 
        result = self.transkrip_rpc.get_ipk_mahasiswa(id_mahasiswa)
        return Response(json.dumps(result), status=200, mimetype="application/json")
 