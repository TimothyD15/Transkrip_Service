# Transkrip Service — Sistem Akademik Kampus

Microservice **Transkrip Nilai** untuk sistem akademik kampus, dibangun
dengan framework [Nameko](https://www.nameko.io/) dan database MySQL 8.

Service ini bertanggung jawab atas:
- Menerima PRS yang sudah disetujui → membuat KRS + nilai kosong
- Menerima input nilai dari dosen (UTS, UAS, Tes1, Tes2) secara bertahap
- Menghitung nilai akhir, KHS/IPS, dan transkrip/IPK secara otomatis
- Menyediakan data KHS, transkrip, IPS, dan IPK untuk service lain

---

## Daftar Isi

1. [Arsitektur & Struktur Project](#1-arsitektur--struktur-project)
2. [Alur Bisnis](#2-alur-bisnis)
3. [Model Database](#3-model-database)
4. [Endpoint & RPC Methods](#4-endpoint--rpc-methods)
5. [Cara Instalasi & Menjalankan](#5-cara-instalasi--menjalankan)
6. [Cara Menjalankan Test](#6-cara-menjalankan-test)
7. [Panduan Testing Manual dengan Postman / curl](#7-panduan-testing-manual-dengan-postman--curl)
8. [Integrasi dengan Service Kelompok Lain](#8-integrasi-dengan-service-kelompok-lain)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Arsitektur & Struktur Project

```
transkrip-service/
│
├── Dockerfile                      # Image Docker untuk semua service Python
├── docker-compose.yml              # Orkestrasi: RabbitMQ, MySQL, db-init, service
├── docker-compose.override.yml     # (Opsional) Tambah mock master & PRS service
├── config.yml                      # Konfigurasi Nameko (AMQP, DB URI, port HTTP)
├── requirements.txt                # Dependensi Python
├── database.py                     # Script inisialisasi tabel MySQL (dijalankan db-init)
├── test_transkrip_service.py       # Test end-to-end (SQLite in-memory, tanpa Docker)
│
├── Transkrip/                      # Package service RPC utama
│   ├── __init__.py
│   ├── models.py                   # Definisi tabel SQLAlchemy (KRS, Nilai, KHS, dst.)
│   ├── service.py                  # TranskripService — semua @rpc method
│   └── utils.py                    # Fungsi murni: hitung nilai, IPS/IPK, validasi
│
├── gateway/                        # Package Gateway HTTP
│   ├── __init__.py
│   ├── entrypoints/
│   │   └── __init__.py             # Re-export `http` dari nameko.web.handlers
│   └── service.py                  # GatewayService — semua @http endpoint
│
└── mocks/                          # Mock service untuk test mandiri
    ├── __init__.py
    └── mock_services.py            # MockMasterService + MockPrsService
```

### Komponen Utama

```
┌─────────────┐   HTTP :8000    ┌──────────────────┐
│  Client /   │ ──────────────► │  GatewayService  │
│  Postman    │                 │  (gateway_service)│
└─────────────┘                 └────────┬─────────┘
                                         │ RPC via RabbitMQ
                                         ▼
                                ┌──────────────────────┐
                                │  TranskripService    │
                                │  (transkrip_service) │
                                └────────┬─────────────┘
                                         │ SQL via PyMySQL
                                         ▼
                                ┌──────────────────────┐
                                │   MySQL 8 Database   │
                                │   transkrip_db       │
                                └──────────────────────┘

Catatan: TranskripService juga memanggil (via RPC):
  - master_service  → get_matkul_by_id(), get_mahasiswa_by_id()
  - prs_service     → get_prs_by_id(), get_prs_detail_by_prs_id()
```

---

## 2. Alur Bisnis

### Alur 1 — Membuat KRS dari PRS yang Disetujui

```
prs_service
    │
    │  RPC: push_prs_ke_krs(id_prs)          ← dipanggil setelah dosen wali approve
    ▼
transkrip_service
    │
    ├─ Cek duplikasi (1 PRS = 1 KRS)
    ├─ RPC ke prs_service: get_prs_by_id(id_prs)
    │    └─ dapat: id_mahasiswa, semester, tahun_ajaran
    ├─ Buat record KRS
    ├─ RPC ke prs_service: get_prs_detail_by_prs_id(id_prs)
    │    └─ dapat: [{"id_matkul": X, "id_kelas": Y}, ...]
    └─ Buat Nilai kosong untuk setiap matkul
         (nilai_uts/uas/tes1/tes2 = None, status = belum_ternilai)
```

### Alur 2 — Dosen Input Nilai

```
client (atas nama dosen)
    │
    │  HTTP POST /input_nilai
    │  body: {"id_nilai": 1, "komponen": "uts", "nilai": 85}
    ▼
GatewayService
    │
    │  RPC: input_nilai(id_nilai, komponen, nilai)
    ▼
TranskripService
    │
    ├─ Validasi komponen (uts/uas/tes1/tes2) dan rentang nilai (0–100)
    ├─ Simpan komponen ke tabel Nilai
    │
    └─ Jika SEMUA 4 komponen sudah terisi:
         ├─ Hitung nilai_akhir  = UTS×30% + UAS×40% + Tes1×15% + Tes2×15%
         ├─ Konversi ke nilai_huruf (A/B+/B/C+/C/D/E)
         ├─ Status Nilai → sudah_ternilai
         ├─ Buat/update KHS + KHSDetail → hitung ulang IPS semester
         ├─ Isi DetailTranskrip (riwayat lengkap mahasiswa)
         └─ Hitung ulang IPK mahasiswa
```

### Tabel Konversi Nilai

| Rentang Nilai | Huruf | Bobot Mutu |
|:---:|:---:|:---:|
| ≥ 85.5 | A  | 4.0 |
| ≥ 75.5 | B+ | 3.5 |
| ≥ 68.5 | B  | 3.0 |
| ≥ 60.5 | C+ | 2.5 |
| ≥ 55.5 | C  | 2.0 |
| ≥ 40.5 | D  | 1.0 |
| < 40.5 | E  | 0.0 |

### Rumus IPS / IPK

```
IPS = Σ(SKS × Bobot Mutu)  ÷  Σ(SKS)
```

---

## 3. Model Database

MySQL database `transkrip_db` terdiri dari 6 tabel:

```
krs                         nilai
────────────────────        ─────────────────────────────
id_krs      PK INT          id_nilai    PK INT
id_prs      INT UNIQUE      id_krs      FK → krs.id_krs
id_mahasiswa INT            id_matkul   INT
semester    VARCHAR(10)     id_kelas    INT
tahun_ajaran VARCHAR(10)    nilai_uts   FLOAT (nullable)
                            nilai_uas   FLOAT (nullable)
                            nilai_tes1  FLOAT (nullable)
                            nilai_tes2  FLOAT (nullable)
                            nilai_akhir FLOAT (nullable)
                            nilai_huruf VARCHAR(2) (nullable)
                            status      ENUM(belum/sudah_ternilai)

khs                         khs_detail
────────────────────        ─────────────────────────────
id_khs      PK INT          id_khs_detail PK INT
id_krs      FK UNIQUE       id_khs        FK → khs.id_khs
semester    VARCHAR(10)     id_nilai      FK → nilai.id_nilai
tahun_ajaran VARCHAR(10)    sks           INT
ips         FLOAT           nilai_huruf   VARCHAR(2)
                            nilai_akhir   FLOAT

transkrip                   detail_transkrip
────────────────────        ─────────────────────────────
id_transkrip PK INT         id_detail_transkrip PK INT
id_mahasiswa INT UNIQUE     id_transkrip  FK → transkrip.id_transkrip
total_sks   INT             id_nilai      FK UNIQUE → nilai.id_nilai
ipk         FLOAT           id_matkul     INT
                            nama_matkul   VARCHAR(100)  ← di-cache dari master
                            semester      VARCHAR(10)
                            tahun_ajaran  VARCHAR(10)
                            sks           INT
                            nilai_huruf   VARCHAR(2)
                            nilai_akhir   FLOAT
```

---

## 4. Endpoint & RPC Methods

### A. HTTP Endpoints (via GatewayService, port 8000)

| Method | URL | Body / Keterangan |
|---|---|---|
| `POST` | `/push_prs_ke_krs` | `{"id_prs": 1}` — dipanggil setelah PRS disetujui |
| `POST` | `/input_nilai` | `{"id_nilai":1,"komponen":"uts","nilai":85.5}` |
| `GET`  | `/nilai/kelas/<id_kelas>` | Daftar nilai seluruh mahasiswa di 1 kelas |
| `GET`  | `/khs/<id_mahasiswa>/<tahun_ajaran>/<semester>` | KHS + IPS semester |
| `GET`  | `/krs/<id_mahasiswa>` | Daftar KRS mahasiswa (semua semester) |
| `GET`  | `/transkrip/<id_mahasiswa>` | Transkrip lengkap + IPK kumulatif |
| `GET`  | `/ips/<id_mahasiswa>` | Riwayat IPS per semester |
| `GET`  | `/ipk/<id_mahasiswa>` | IPK terkini + total SKS |

### B. RPC Methods (TranskripService, name="transkrip_service")

Method-method ini dipanggil langsung oleh service lain via RabbitMQ:

| Method | Parameter | Return |
|---|---|---|
| `push_prs_ke_krs` | `id_prs: int` | `{"status":"ok","id_krs":int}` |
| `input_nilai` | `id_nilai: int, komponen: str, nilai: float` | `{"status":"ok","nilai_huruf":str\|None}` |
| `get_nilai_by_kelas` | `id_kelas: int` | `[{id_nilai, id_matkul, nilai_*, status, ...}]` |
| `get_khs_by_mahasiswa` | `id_mahasiswa: int, semester: str, tahun_ajaran: str` | `{ips, matkul:[...]}` |
| `get_transkrip_mahasiswa` | `id_mahasiswa: int` | `{mahasiswa, total_sks, ipk, riwayat:[...]}` |
| `get_ips_per_semester` | `id_mahasiswa: int` | `[{semester, tahun_ajaran, ips}]` |
| `get_ipk_mahasiswa` | `id_mahasiswa: int` | `{id_mahasiswa, ipk, total_sks}` |
| `get_krs_by_mahasiswa` | `id_mahasiswa: int` | `[{id_krs, id_prs, semester, ...}]` |

---

## 5. Cara Instalasi & Menjalankan

### Prasyarat

Pastikan sudah terinstal di komputer Anda:
- **Docker Desktop** (sudah termasuk Docker Engine + Docker Compose v2)
  - Windows / Mac: https://www.docker.com/products/docker-desktop
  - Linux: `sudo apt install docker.io docker-compose-plugin`
- **Git** (untuk clone repo)
- **Python 3.10+** (hanya jika ingin menjalankan test tanpa Docker)

Cek versi yang terinstal:
```bash
docker --version        # Docker version 24.x.x
docker compose version  # Docker Compose version v2.x.x
python3 --version       # Python 3.10.x atau lebih baru
```

---

### Langkah 1 — Clone Repository

```bash
git clone <url-repo-anda>
cd transkrip-service
```

---

### Langkah 2 — Pilih Mode Menjalankan

Ada dua mode:

#### Mode A: Testing Mandiri (dengan mock Master & PRS)

Gunakan ini jika service `master_service` dan `prs_service` dari kelompok
lain **belum tersedia**. File `docker-compose.override.yml` yang sudah ada
akan otomatis dipakai, menambahkan container `mock-services`.

```bash
# Jalankan SEMUA container (RabbitMQ + MySQL + db-init + service + mock)
docker compose up --build
```

Docker Compose secara otomatis menggabungkan `docker-compose.yml` dan
`docker-compose.override.yml` bila Anda tidak menyertakan flag `-f`.

#### Mode B: Integrasi dengan Service Asli

Gunakan ini saat service Master dan PRS asli dari kelompok lain sudah
terhubung ke RabbitMQ yang sama.

```bash
# Jalankan TANPA override (tidak ada mock)
docker compose -f docker-compose.yml up --build
```

---

### Langkah 3 — Tunggu Semua Container Siap

Setelah menjalankan `docker compose up`, Anda akan melihat log seperti ini
di terminal. Tunggu hingga muncul pesan dari masing-masing container:

```
transkrip-microservice-rabbitmq-1    | Server startup complete
transkrip-microservice-transkrip-db-1| /usr/sbin/mysqld: ready for connections
transkrip-microservice-db-init-1     | Tabel database berhasil dibuat / sudah tersedia.
transkrip-microservice-transkrip-service-1 | Connected to amqp://guest:**@rabbitmq:5672//
transkrip-microservice-mock-services-1     | Connected to amqp://guest:**@rabbitmq:5672//
```

MySQL biasanya membutuhkan **30–60 detik** untuk pertama kali inisialisasi.
Jangan khawatir jika `db-init` muncul pesan retry beberapa kali — itu normal.

---

### Langkah 4 — Verifikasi Service Berjalan

```bash
# Cek semua container running
docker compose ps

# Harusnya terlihat status Up untuk semua service:
# transkrip-microservice-rabbitmq-1          running
# transkrip-microservice-transkrip-db-1      running (healthy)
# transkrip-microservice-db-init-1           exited (0)   ← normal, sudah selesai
# transkrip-microservice-transkrip-service-1 running
# transkrip-microservice-mock-services-1     running      ← hanya jika mode A
```

```bash
# Test gateway HTTP berjalan
curl http://localhost:8000/ipk/1
# Respon: {"id_mahasiswa": 1, "ipk": 0.0, "total_sks": 0}
```

---

### Langkah 5 — Menghentikan Service

```bash
# Hentikan semua container (data MySQL tetap tersimpan di volume)
docker compose down

# Hentikan DAN hapus semua data MySQL (mulai bersih)
docker compose down -v
```

---

### Melihat Log

```bash
# Log semua container secara real-time
docker compose logs -f

# Log hanya service tertentu
docker compose logs -f transkrip-service
docker compose logs -f transkrip-db
docker compose logs -f rabbitmq
```

---

### Akses Database Langsung (opsional)

```bash
# Masuk ke MySQL via Docker
docker compose exec transkrip-db mysql -u transkrip_user -ptranskrip_pass transkrip_db

# Contoh query untuk verifikasi data
mysql> SELECT * FROM krs;
mysql> SELECT * FROM nilai;
mysql> SELECT * FROM khs;
mysql> SELECT * FROM transkrip;
```

Atau gunakan MySQL client di host Anda (MySQL Workbench, DBeaver, dll):
- Host: `localhost`
- Port: `3307`  ← perhatikan bukan 3306
- User: `transkrip_user`
- Password: `transkrip_pass`
- Database: `transkrip_db`

---

### Akses RabbitMQ Management (opsional)

Buka browser: http://localhost:15672  
Login: `guest` / `guest`

Di sini Anda bisa melihat antrian RPC, jumlah pesan, dan status consumer.
Berguna untuk debug jika RPC call tidak diproses.

---

## 6. Cara Menjalankan Test

Test end-to-end ditulis di `test_transkrip_service.py`. Test ini menggunakan
SQLite in-memory (bukan MySQL) dan mock RPC, sehingga **tidak memerlukan
Docker, RabbitMQ, atau MySQL** untuk dijalankan.

### Langkah 1 — Siapkan Virtual Environment (direkomendasikan)

```bash
# Buat virtual environment
python3 -m venv venv

# Aktifkan virtual environment
# Linux / Mac:
source venv/bin/activate
# Windows (Command Prompt):
venv\Scripts\activate.bat
# Windows (PowerShell):
venv\Scripts\Activate.ps1
```

Setelah diaktifkan, prompt Anda akan berubah menjadi `(venv) $`.

---

### Langkah 2 — Install Dependensi

```bash
pip install -r requirements.txt
```

Output yang diharapkan:
```
Successfully installed nameko-2.14.1 nameko-sqlalchemy-1.5.0 sqlalchemy-1.4.x
PyMySQL-1.1.x cryptography-41.x werkzeug-2.0.x ...
```

---

### Langkah 3 — Jalankan Test

```bash
python3 test_transkrip_service.py
```

Output yang diharapkan (seluruh test lulus):
```
test_full_flow (__main__.TestTranskripService.test_full_flow) ...
push_prs_ke_krs: {'status': 'ok', 'id_krs': 1}
push_prs_ke_krs (dup): {'status': 'error', 'message': 'KRS untuk PRS 1 sudah ada'}
push_prs_ke_krs (not found): {'status': 'error', 'message': 'PRS 999 tidak ditemukan'}
get_nilai_by_kelas(1): [{'id_nilai': 1, ..., 'status': 'belum_ternilai'}]
input_nilai (komponen invalid): {'status': 'error', 'message': "Komponen 'kuis' tidak valid..."}
input_nilai (nilai out of range): {'status': 'error', 'message': 'Nilai harus antara 0 dan 100'}
input_nilai (nilai bukan angka): {'status': 'error', 'message': 'Nilai harus berupa angka'}
input_nilai (id_nilai tidak ada): {'status': 'error', 'message': 'Nilai dengan id 9999 tidak ditemukan'}
input_nilai uts: {'status': 'ok', 'nilai_huruf': None}
input_nilai tes2 (lengkap): {'status': 'ok', 'nilai_huruf': 'B+'}
get_khs_by_mahasiswa: {'ips': 3.07, 'matkul': [{...}, {...}]}
get_transkrip_mahasiswa: {'status': 'ok', 'total_sks': 7, 'ipk': 3.07, ...}
get_ips_per_semester: [{'semester': 'Ganjil', 'ips': 3.07}]
get_ipk_mahasiswa: {'ipk': 3.07, 'total_sks': 7}
ok
----------------------------------------------------------------------
Ran 1 test in 0.07s

OK
```

Jika ada keterangan `OK` di baris paling bawah, semua skenario telah lulus.

---

### Yang Diuji oleh Test

Test mencakup **seluruh alur** secara berurutan:

| # | Skenario | Yang Diverifikasi |
|---|---|---|
| 1 | `push_prs_ke_krs(1)` sukses | Status ok, id_krs kembali |
| 2 | `push_prs_ke_krs(1)` duplikat | Status error, pesan jelas |
| 3 | `push_prs_ke_krs(999)` PRS tidak ada | Status error |
| 4 | `get_nilai_by_kelas(1)` sebelum diisi | 1 record, status belum_ternilai |
| 5 | `input_nilai` komponen tidak valid | Status error, pesan jelas |
| 6 | `input_nilai` nilai > 100 | Status error |
| 7 | `input_nilai` nilai bukan angka | Status error |
| 8 | `input_nilai` id_nilai tidak ada | Status error |
| 9 | Input UTS saja | nilai_huruf masih None (belum lengkap) |
| 10 | Input UAS + Tes1 + Tes2 → lengkap | nilai_huruf = 'B+', KHS otomatis terbuat |
| 11 | Input nilai matkul kedua | KHS + IPS dihitung ulang |
| 12 | `get_khs_by_mahasiswa` | 2 matkul, IPS = 3.07 |
| 13 | `get_transkrip_mahasiswa` | total_sks=7, IPK=3.07, riwayat lengkap |
| 14 | `get_transkrip_mahasiswa` mahasiswa tidak ada | Status error |
| 15 | `get_ips_per_semester` | 1 entri, semester Ganjil |
| 16 | `get_ipk_mahasiswa` | IPK=3.07, total_sks=7 |
| 17 | `get_ipk_mahasiswa` mahasiswa tidak ada | ipk=0.0, total_sks=0 |
| 18 | `get_krs_by_mahasiswa` | 1 KRS ditemukan |

---

## 7. Panduan Testing Manual dengan Postman / curl

Pastikan `docker compose up` sudah berjalan dan service ready (lihat Langkah 5 di atas).

### Skenario Lengkap (ikuti urutan ini)

#### Step 1 — Push PRS ke KRS

Data mock yang tersedia: `id_prs = 1` (Mahasiswa ID 1, Ganjil 2024-2025,
2 matkul: Algoritma & Struktur Data SKS 4, Basis Data SKS 3).

```bash
curl -X POST http://localhost:8000/push_prs_ke_krs \
  -H "Content-Type: application/json" \
  -d '{"id_prs": 1}'
```

Respons sukses:
```json
{"status": "ok", "id_krs": 1}
```

Respons jika PRS sudah ada (duplikat):
```json
{"status": "error", "message": "KRS untuk PRS 1 sudah ada"}
```

---

#### Step 2 — Lihat Nilai yang Baru Dibuat

```bash
# Lihat nilai di kelas id_kelas=1 (Algoritma & Struktur Data)
curl http://localhost:8000/nilai/kelas/1

# Lihat nilai di kelas id_kelas=2 (Basis Data)
curl http://localhost:8000/nilai/kelas/2
```

Catat `id_nilai` dari setiap baris. Biasanya:
- `id_nilai: 1` → Algoritma & Struktur Data (kelas 1)
- `id_nilai: 2` → Basis Data (kelas 2)

---

#### Step 3 — Input Nilai Bertahap (Matkul 1: id_nilai=1)

Nilai bisa diisi bertahap, tidak harus sekaligus.

```bash
# Input UTS
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "uts", "nilai": 80}'

# Input UAS
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "uas", "nilai": 90}'

# Input Tes1
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "tes1", "nilai": 85}'

# Input Tes2 — setelah ini, nilai akhir dihitung otomatis
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "tes2", "nilai": 75}'
```

Respons setelah Tes2 (komponen terakhir):
```json
{"status": "ok", "nilai_huruf": "B+"}
```

Nilai akhir = 80×0.3 + 90×0.4 + 85×0.15 + 75×0.15 = **84.0** → **B+**

---

#### Step 4 — Input Nilai Matkul 2 (id_nilai=2)

```bash
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 2, "komponen": "uts", "nilai": 70}'

curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 2, "komponen": "uas", "nilai": 65}'

curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 2, "komponen": "tes1", "nilai": 60}'

curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 2, "komponen": "tes2", "nilai": 72}'
```

---

#### Step 5 — Lihat KHS Semester

```bash
curl http://localhost:8000/khs/1/2024-2025/Ganjil
```

Respons:
```json
{
  "id_mahasiswa": 1,
  "semester": "Ganjil",
  "tahun_ajaran": "2024-2025",
  "ips": 3.07,
  "matkul": [
    {
      "id_nilai": 1,
      "id_matkul": 101,
      "sks": 4,
      "nilai_uts": 80.0,
      "nilai_uas": 90.0,
      "nilai_tes1": 85.0,
      "nilai_tes2": 75.0,
      "nilai_akhir": 84.0,
      "nilai_huruf": "B+",
      "status": "sudah_ternilai"
    },
    {
      "id_nilai": 2,
      "id_matkul": 102,
      "sks": 3,
      "nilai_akhir": 66.8,
      "nilai_huruf": "C+",
      "status": "sudah_ternilai"
    }
  ]
}
```

IPS = (4×3.5 + 3×2.5) / (4+3) = (14 + 7.5) / 7 = **3.07**

---

#### Step 6 — Lihat Transkrip Lengkap

```bash
curl http://localhost:8000/transkrip/1
```

---

#### Step 7 — Lihat Riwayat IPS & IPK

```bash
# Riwayat IPS per semester
curl http://localhost:8000/ips/1

# IPK terkini
curl http://localhost:8000/ipk/1
```

---

#### Contoh Error Handling

```bash
# Komponen tidak valid
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "kuis", "nilai": 80}'
# → {"status": "error", "message": "Komponen 'kuis' tidak valid. Gunakan: uts, uas, tes1, tes2"}

# Nilai di luar rentang
curl -X POST http://localhost:8000/input_nilai \
  -H "Content-Type: application/json" \
  -d '{"id_nilai": 1, "komponen": "uts", "nilai": 150}'
# → {"status": "error", "message": "Nilai harus antara 0 dan 100"}
```

---

## 8. Integrasi dengan Service Kelompok Lain

Transkrip Service mengharapkan dua service eksternal aktif di RabbitMQ yang sama:

### master_service (Grup A)

Method yang dipanggil oleh transkrip_service:

```python
# Mengembalikan detail mata kuliah
master_service.get_matkul_by_id(id_matkul: int)
# Ekspektasi return:
# {"id_matkul": 101, "nama_matkul": "Algoritma dan Struktur Data", "sks": 4}

# Mengembalikan data mahasiswa
master_service.get_mahasiswa_by_id(id_mahasiswa: int)
# Ekspektasi return:
# {"id_mahasiswa": 1, "nama": "Budi Santoso", "nrp": "12345678"}
```

### prs_service (Grup E)

Method yang dipanggil oleh transkrip_service:

```python
# Mengembalikan data PRS yang sudah disetujui
prs_service.get_prs_by_id(id_prs: int)
# Ekspektasi return:
# {"id_mahasiswa": 1, "semester": "Ganjil", "tahun_ajaran": "2024-2025"}

# Mengembalikan daftar matkul dalam PRS
prs_service.get_prs_detail_by_prs_id(id_prs: int)
# Ekspektasi return:
# [{"id_matkul": 101, "id_kelas": 1}, {"id_matkul": 102, "id_kelas": 2}]
```

### Cara Menghubungkan

Pastikan semua service terhubung ke RabbitMQ yang sama. Jika RabbitMQ
dijalankan oleh satu kelompok sebagai shared broker, sesuaikan
`AMQP_URI` di `config.yml`:

```yaml
# Contoh jika RabbitMQ dijalankan di server shared (IP 192.168.1.100)
AMQP_URI: pyamqp://guest:guest@192.168.1.100:5672/
```

Lalu jalankan tanpa override:
```bash
docker compose -f docker-compose.yml up --build
```

---

## 9. Troubleshooting

### `db-init` terus retry dan gagal

MySQL 8 butuh waktu 30–60 detik untuk inisialisasi pertama kali
(membuat system tables, dll). Ini normal. Tunggu hingga muncul pesan
"Tabel database berhasil dibuat".

Jika masih gagal setelah lama:
```bash
docker compose logs transkrip-db
```

Cari pesan error di log MySQL.

---

### `transkrip-service` error "Can't connect to amqp"

RabbitMQ belum siap saat service mencoba konek. Karena sudah ada
`depends_on` dengan healthcheck, ini seharusnya tidak terjadi. Jika
terjadi, jalankan ulang:

```bash
docker compose restart transkrip-service
```

---

### Port 3307 sudah dipakai

Edit `docker-compose.yml`, ubah baris:
```yaml
ports:
  - "3307:3306"
```
menjadi port lain, misalnya `"3308:3306"`.

---

### Port 8000 sudah dipakai

Edit `docker-compose.yml` dan `config.yml`:
```yaml
# docker-compose.yml
ports:
  - "8080:8000"   # ubah 8000 ke 8080

# config.yml — JANGAN diubah, ini port di dalam container
WEB_SERVER_ADDRESS: "0.0.0.0:8000"
```

Lalu akses gateway di `http://localhost:8080`.

---

### Perubahan kode tidak terlihat

Karena ada `volumes: .:/app` di docker-compose, perubahan kode Python
langsung terlihat tanpa rebuild. Namun Nameko perlu di-restart
untuk memuat ulang kode:

```bash
docker compose restart transkrip-service
```

Jika mengubah `requirements.txt` atau `Dockerfile`, perlu rebuild:
```bash
docker compose up --build
```
