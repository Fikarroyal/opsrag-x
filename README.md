<div align="center">

<img src="docs/assets/banner.png" alt="OpsRAG-X" width="100%">

<br>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/pytest-99%20passed-22c55e?style=flat-square)
![Data](https://img.shields.io/badge/data-sintetis-f59e0b?style=flat-square)

**OpsRAG-X** adalah *investigation agent* (bukan chatbot, bukan agen remediasi otomatis) yang membantu tim IT rumah sakit dalam menyelidiki insiden infrastruktur.
Agen membaca tiket, memilih SOP yang berlaku **pada waktu kejadian**, mencari insiden historis, memeriksa topologi, memanggil tool MCP **read-only**, mengorelasikan log secara temporal, menyusun hipotesis, menghitung *evidence confidence score*, lalu menghasilkan laporan beserta jejak audit.

## <img src="docs/assets/icons/table-of-contents.svg" width="26" align="top"> Daftar isi

| | | |
|---|---|---|
| [Masalah dan tujuan](#masalah-dan-tujuan) | [Arsitektur database](#arsitektur-database) | [Testing dan validasi](#testing-dan-validasi) |
| [Fitur](#fitur) | [Arsitektur RAG](#arsitektur-rag) | [Benchmark dan eksperimen A-D](#benchmark-dan-eksperimen-a-d) |
| [Arsitektur](#arsitektur) | [Arsitektur MCP](#arsitektur-mcp) | [Fine-tuning LoRA](#fine-tuning-lora-opsional) |
| [Tech stack](#tech-stack) | [Alur investigasi](#alur-investigasi) | [Data Privacy and Safety](#data-privacy-and-safety) |
| [Instalasi dan menjalankan](#instalasi-dan-menjalankan) | [Skenario insiden](#skenario-insiden) | [Kebaruan riset](#kebaruan-riset-research-novelty) |
| [Konfigurasi](#konfigurasi) | [API](#api) | [Keterbatasan yang diketahui](#keterbatasan-yang-diketahui) |
| [Akun dan keamanan sesi](#akun-dan-keamanan-sesi) | [Frontend](#frontend) | [Roadmap](#roadmap) |

<br>

## <img src="docs/assets/icons/target.svg" width="26" align="top"> Masalah dan tujuan

Di RS, satu atau dua staf IT menangani jaringan, server, SIMRS, printer, dan perangkat unit. Saat tiket "SIMRS tidak bisa dibuka dari Poli 3" masuk, mereka harus mengingat SOP versi mana yang berlaku, mencari kejadian serupa, memeriksa log beberapa perangkat, dan menentukan urutan sebab-akibat secara manual.

Tujuan OpsRAG-X:

- mempercepat investigasi dengan evidence terstruktur (`FACT` / `INFERENCE` / `UNKNOWN`);
- memakai konteks **waktu** (versi SOP saat kejadian, peluruhan relevansi insiden lama, urutan kejadian di log);
- **menolak menyimpulkan** root cause bila evidence langsung tidak cukup;
- menyimpan seluruh langkah agar dapat diaudit dan di-*replay*.

<br>

## <img src="docs/assets/icons/sparkles.svg" width="26" align="top"> Fitur

| | Fitur | Keterangan |
|:-:|---|---|
| <img src="docs/assets/icons/ticket.svg" width="22"> | **Klasifikasi tiket** | Kategori, severity, scope, entitas, dan petunjuk waktu dengan aturan + LLM opsional yang divalidasi skema. |
| <img src="docs/assets/icons/search.svg" width="22"> | **Retrieval hibrida versi-sadar waktu** | SOP dan insiden historis (pgvector HNSW + fallback TF-IDF). |
| <img src="docs/assets/icons/network.svg" width="22"> | **Analisis topologi** | BFS jalur, scope dampak, dan perangkat bersama. |
| <img src="docs/assets/icons/clipboard-list.svg" width="22"> | **Perencana tool bersyarat** | Kategori × scope, maksimal 14 tool; LLM hanya boleh memangkas rencana. |
| <img src="docs/assets/icons/plug.svg" width="22"> | **10 tool MCP read-only** | Semantik *snapshot as-of* (T + 5 menit) pada data sintetis. |
| <img src="docs/assets/icons/workflow.svg" width="22"> | **Korelasi log temporal** | Deteksi pola sebab-akibat dan 9 hipotesis bersaing. |
| <img src="docs/assets/icons/gauge.svg" width="22"> | **Evidence confidence score** | *Gating* evidence langsung dengan penalti ambiguitas dan cakupan. |
| <img src="docs/assets/icons/file-text.svg" width="22"> | **Rekomendasi dan laporan** | Hanya langkah verifikasi atau mitigasi manual; ekspor JSON/PDF. |
| <img src="docs/assets/icons/history.svg" width="22"> | **Audit trail** | `incident_events`, `tool_executions`, `investigation_evidence`, snapshot konfigurasi dan input, plus *replay* dan *compare*. |
| <img src="docs/assets/icons/flask-conical.svg" width="22"> | **Benchmark 50 item** | Eksperimen A-D yang dihitung dari eksekusi nyata. |
| <img src="docs/assets/icons/layout-dashboard.svg" width="22"> | **Frontend 17 halaman** | React + TypeScript tanpa data palsu: semua dari API. |
| <img src="docs/assets/icons/shield-check.svg" width="22"> | **Mode fallback** | Bila Ollama tidak tersedia, aplikasi tetap berjalan penuh dengan aturan. |
| <img src="docs/assets/icons/lock.svg" width="22"> | **Akun pengguna** | Halaman Masuk dan Daftar, sesi cookie HttpOnly, kata sandi di-hash (PBKDF2-SHA256); semua endpoint API selain health dan auth memerlukan login. |

<br>

## <img src="docs/assets/icons/layers.svg" width="26" align="top"> Arsitektur

```mermaid
flowchart LR
    UI[React Frontend] -->|REST /api| API[FastAPI Backend]
    API --> ORCH[Investigation Orchestrator]
    ORCH --> CLS[Classifier + Severity]
    ORCH --> RAG[Hybrid Retriever + Reranker]
    ORCH --> TOPO[Topology Engine]
    ORCH --> PLAN[Tool Planner]
    PLAN -->|MCP streamable-http| MCP[MCP Server read-only tools]
    ORCH --> COR[Temporal Log Correlation]
    COR --> EVS[Evidence Store]
    EVS --> HYP[Hypothesis Engine]
    HYP --> CONF[Evidence Confidence]
    CONF --> REC[Recommendation + Report]
    RAG --> PG[(PostgreSQL + pgvector)]
    ORCH --> PG
    CLS -. optional .-> LLM[Ollama / fallback rules]
    MCP --> DATA[(Synthetic hospital data)]
```

Prinsip desain:

- **Log dan dokumen adalah data, bukan instruksi** (pertahanan prompt-injection).
- Root cause tidak pernah di-hard-code: orchestrator tidak membaca `scenario_id`.
- Seluruh tool bersifat baca-saja.

<br>

## <img src="docs/assets/icons/blocks.svg" width="26" align="top"> Tech stack

| Lapisan | Teknologi |
|---|---|
| **Backend** | Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, pandas, numpy, scikit-learn, PyMuPDF, ReportLab |
| **Database** | SQLite (mode lokal), atau PostgreSQL 16 + pgvector (HNSW cosine) untuk Docker/produksi |
| **AI / RAG** | Embedding `BAAI/bge-small-en-v1.5` (sentence-transformers, opsional) atau `hashing-lexical-384` (deterministik); Ollama (default `qwen2.5:7b`) opsional |
| **MCP** | MCP Python SDK (FastMCP, streamable-http) + fasad REST |
| **Frontend** | React 18, TypeScript, Vite, Tailwind, Lucide, Recharts, TanStack Query, React Router |
| **Kualitas** | pytest, ruff, black, mypy, eslint, tsc |
| **Deploy** | Docker Compose (postgres, backend, frontend, mcp-server, profil `ollama` opsional) |

<br>

## <img src="docs/assets/icons/rocket.svg" width="26" align="top"> Instalasi dan menjalankan

### <img src="docs/assets/icons/play.svg" width="22" align="top"> Quick start lokal

Cara paling mudah: tanpa Docker, tanpa PostgreSQL. Prasyarat hanya **Python 3.10+** (diuji di 3.10 dan 3.13). Node tidak perlu karena UI hasil build sudah disertakan di `frontend/dist`.

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python scripts/run_local.py          # atau: make local
```

Lalu buka **http://localhost:8000** (dokumentasi API: http://localhost:8000/docs). Perintah itu menyiapkan database SQLite (`data/opsragx.db`), mengisi data dummy rumah sakit sintetis, menjalankan MCP server (read-only) dan backend, lalu membuka UI. Daftar akun di halaman Masuk, kemudian coba: **Incidents → INC-2026-001 → Start Investigation**.

| Opsi | Fungsi |
|---|---|
| `--reset` | hapus database lalu mulai dari nol |
| `--port 8080` | ganti port |
| `--host 0.0.0.0` | akses dari jaringan |
| `--llm` | pakai Ollama bila berjalan; tanpa itu otomatis mode fallback aturan |

<details>
<summary><b>Masalah umum</b></summary>

<br>

| Gejala | Solusi |
|---|---|
| `Python 3.10+ is required` | pasang Python 3.10 atau lebih baru lalu buat ulang `.venv` |
| `Missing Python packages` | aktifkan venv, lalu `pip install -r backend/requirements.txt` |
| `Port 8000 ... already in use` | `python scripts/run_local.py --port 8080` |
| Layar UI kosong atau tidak ada UI | folder `frontend/dist` hilang: pasang Node 20+, jalankan lagi (build otomatis) |
| Ingin mulai ulang bersih | `python scripts/run_local.py --reset` |

</details>

> [!TIP]
> Mode lokal memakai embedder hashing (tanpa unduhan model) dan SQLite. PostgreSQL + pgvector tetap didukung untuk Docker/produksi.

### <img src="docs/assets/icons/container.svg" width="22" align="top"> Opsi A: Docker Compose

```bash
cp .env.example .env
docker compose up --build -d          # postgres + mcp-server + backend + frontend
# opsional LLM lokal (CPU, lebih lambat):
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5:7b
```

Backend otomatis menjalankan migrasi, seed, ingest, dan embedding (`scripts/bootstrap.py --if-empty`).

| Layanan | Alamat |
|---|---|
| Frontend | http://localhost:3000 |
| Swagger | http://localhost:8000/docs |
| MCP | http://localhost:8001 |

> [!NOTE]
> Image default memakai embedder hashing. `INSTALL_SBERT=1 docker compose up --build` menambahkan sentence-transformers (unduhan besar).

### <img src="docs/assets/icons/terminal.svg" width="22" align="top"> Opsi B: Lokal dengan PostgreSQL (pengembangan)

Prasyarat: Python 3.10+, Node 20+, PostgreSQL 16 dengan ekstensi `vector`. Jalankan target `make` dengan `DB_URL=postgresql+psycopg://...` (tanpa itu, `make seed` dan `make dev` memakai SQLite).

```bash
make setup                         # venv, dependensi backend/mcp, npm install
createdb opsragx && psql -d opsragx -c 'CREATE EXTENSION vector'   # hanya untuk PostgreSQL
make seed                          # migrasi + seed data sintetis + ingest SOP + embedding (idempoten)
make dev                           # MCP server :8001, backend :8000, frontend :5173
```

<details>
<summary><b>Perintah Makefile</b></summary>

<br>

| Target | Fungsi |
|---|---|
| `make local` | menjalankan semuanya dengan SQLite (tanpa Docker/PostgreSQL) |
| `make setup` | membuat venv dan memasang dependensi |
| `make data` | membangkitkan ulang data sintetis + SOP PDF (deterministik) |
| `make seed` | migrasi + seed (idempoten) |
| `make ingest` | ingest SOP/dokumen + buat embedding |
| `make dev` | menjalankan seluruh stack lokal |
| `make test` | pytest (SQLite + hashing embedder, tanpa layanan eksternal) |
| `make lint` | ruff, black --check, mypy, eslint, tsc |
| `make format` | ruff --fix + black |
| `make benchmark` | benchmark 50 item (butuh MCP server hidup) |
| `make health` | health check live |
| `make demo` | bootstrap lalu investigasi INC-2026-001 (daftar akun sementara otomatis) |

</details>

<br>

## <img src="docs/assets/icons/settings.svg" width="26" align="top"> Konfigurasi

Semua variabel ada di `.env.example` (database, LLM, embedding, MCP, bobot retrieval, ambang confidence). Bobot retrieval dinormalisasi otomatis. `DEMO_MODE=true` membuat tool MCP mengembalikan snapshot sintetis pada waktu insiden + 5 menit.

<br>

## <img src="docs/assets/icons/key-round.svg" width="26" align="top"> Akun dan keamanan sesi

Saat pertama dibuka, aplikasi menampilkan halaman **Masuk**; pilih **Daftar** untuk membuat akun (nama, email, kata sandi minimal 8 karakter). Akun pertama menjadi `admin`, akun berikutnya `it_support`. Tidak ada akun bawaan.

- Kata sandi disimpan sebagai hash PBKDF2-SHA256 dengan salt acak; sesi berupa cookie `HttpOnly` bertanda tangan HMAC (masa berlaku 7 hari). Skrip dapat memakai `Authorization: Bearer <token>`.
- Percobaan masuk yang gagal dibatasi (8 kali per 5 menit per email dan alamat IP).
- Kunci penanda tangan dibuat acak sekali dan disimpan di `data/.secret_key`. Untuk hosting, atur `SECRET_KEY` dan `COOKIE_SECURE=true` (HTTPS).
- Endpoint: `POST /api/auth/register`, `/login`, `/logout`, dan `GET /api/auth/me`.

<br>

## <img src="docs/assets/icons/database.svg" width="26" align="top"> Arsitektur database

15 tabel (UUID PK + timestamp), ditambah `alembic_version`:

| Kelompok | Tabel |
|---|---|
| Pengguna | `users` |
| Inventori | `devices`, `servers`, `services` |
| Insiden | `incidents`, `incident_events`, `resolutions`, `historical_incidents` |
| Investigasi | `investigations`, `investigation_evidence`, `tool_executions`, `logs` |
| SOP | `sop_documents`, `sop_versions`, `sop_chunks` |

- Kolom `embedding` bertipe `Vector(384)` (JSON pada SQLite untuk test); indeks **HNSW cosine** pada `sop_chunks` dan `historical_incidents` dibuat di migrasi `0001`.
- `investigations` menyimpan `stages`, `config_snapshot`, `input_snapshot`, `report`, skor, dan durasi sehingga hasil dapat diaudit dan di-replay.
- `investigation_evidence` menyimpan jenis (`FACT` / `INFERENCE` / `UNKNOWN`), tag, relasi temporal (before/during/after/unrelated), peran (supporting/contradicting/context), dan prioritas sumber 1-9.

<br>

## <img src="docs/assets/icons/search.svg" width="26" align="top"> Arsitektur RAG

- **Chunking** SOP PDF per bagian (Indikasi, Prasyarat, Langkah, Eskalasi, dst.) dengan header `SOP-xxx | vX | Berlaku: tanggal | Status | Judul`.
- **Versi-sadar waktu**: untuk insiden pada waktu *T*, dipilih versi terbaru dengan `effective_date <= T` (8 SOP, 11 versi).
- **Embedding**: `SentenceTransformerEmbedder` jika terpasang, selain itu `HashingEmbedder` (384 dim). Fallback keyword TF-IDF bila vektor tidak ada.

**Skor hibrida** (bobot dapat dikonfigurasi dan dinormalisasi):

$$
\text{final} = 0.45\,\text{semantic} + 0.25\,\text{temporal} + 0.10\,\text{category} + 0.10\,\text{service} + 0.10\,\text{source}
$$

**Peluruhan temporal** dengan half-life berbeda per sumber: 30 hari (historis), 180 hari (SOP), 10 menit (log).

$$
w(\Delta t) = \exp\left(-\frac{\ln 2}{h}\,\lvert \Delta t \rvert\right)
$$

**Reranker deterministik**:

$$
\text{rerank} = 0.88\,\text{hybrid} + 0.08\,\text{lexical overlap} + 0.04\,\text{unit match}
$$

<p align="center">
  <img src="docs/assets/weights.png" alt="Bobot skor hibrida retrieval dan skor hipotesis" width="49%">
  <img src="docs/assets/temporal-decay.png" alt="Peluruhan temporal per sumber" width="49%">
</p>

<br>

## <img src="docs/assets/icons/plug.svg" width="26" align="top"> Arsitektur MCP

Server FastMCP (`/mcp`, streamable-http, stateless) + fasad REST (`/api/tools/{nama}`, `/health`, `/tools`). Backend hanya boleh memanggil tool pada allow-list `READ_ONLY_TOOLS`:

| | | | | |
|---|---|---|---|---|
| `get_server_status` | `check_http` | `check_dns` | `ping_host` | `query_service_status` |
| `search_logs` | `get_device_info` | `search_previous_incident` | `get_topology_path` | `get_network_interface_status` |

Tidak ada tool `execute_command`, `restart_server`, `delete_file`, `shutdown_server`, atau `change_router_config`. Setiap panggilan memiliki timeout, galat terstruktur, dan dicatat di `tool_executions`.

<br>

## <img src="docs/assets/icons/workflow.svg" width="26" align="top"> Alur investigasi

```mermaid
flowchart TD
    A["1. Klasifikasi<br/>kategori, severity, scope, entitas, waktu"] --> B["2. SOP retrieval<br/>versi-sadar waktu"]
    B --> C["3. Insiden historis<br/>peluruhan temporal"]
    C --> D["4. Inspeksi topologi<br/>jalur, perangkat bersama, scope"]
    D --> E["5. Diagnostik MCP<br/>rencana tool bersyarat, hanya baca"]
    E --> F["6. Korelasi log<br/>onset per domain, pola sebab-akibat"]
    F --> G["7. Analisis root cause<br/>9 hipotesis bersaing"]
    G --> H["8. Rekomendasi + laporan<br/>keterbatasan dan evidence tambahan"]
```

**Korelasi log** (skor pola sebab-akibat):

$$
\text{score} = 0.5\,\text{urutan} + 0.25\,e^{-\text{lag}/600} + 0.25\,\text{volume}
$$

**Analisis root cause**: 9 hipotesis (`H_NET_ACCESS`, `H_ENDPOINT`, `H_APP`, `H_DNS`, `H_DB`, `H_OVERLOAD`, `H_CORE`, `H_AUTH`, `H_CONFIG`) dengan skor:

$$
S_h = 0.35\,\text{evidence} + 0.20\,\text{temporal} + 0.15\,\text{topologi} + 0.10\,\text{historis} + 0.10\,\text{state} + 0.10\,\text{sumber}
$$

**Evidence confidence score**:

$$
\text{confidence} = \min\left(0.99,\; S_h \times \left(0.75 + 0.25\,\frac{\text{tool ok}}{\text{planned}}\right) \times f_{\text{ambiguitas}}\right)
$$

dengan $f_{\text{ambiguitas}} = 0.9$ bila selisih dengan hipotesis kedua kurang dari 0.10, selain itu 1. Skor ini bukan probabilitas statistik.

**Gating**: kesimpulan hanya diberikan bila confidence ≥ 0.40 **dan** ada dukungan evidence langsung ≥ 0.30.

```mermaid
flowchart LR
    S[Skor hipotesis teratas] --> Q{"confidence ≥ 0.40<br/>dan evidence langsung ≥ 0.30?"}
    Q -->|Ya| Y["Root cause disimpulkan<br/>+ langkah verifikasi"]
    Q -->|Tidak| N["Root cause belum dapat ditentukan<br/>+ langkah pengumpulan evidence"]
```

<br>

## <img src="docs/assets/icons/ticket.svg" width="26" align="top"> Skenario insiden

Data dibangkitkan deterministik (`SEED=20260928`). Tersedia delapan tiket contoh dan 50 deskripsi benchmark.

| Tiket | Skenario | Hasil investigasi (dijalankan ulang, mode fallback) |
|---|---|---|
| INC-2026-001 | S1: Poli 3, SW-POLI3 `Gi0/48` CRC/latensi naik, packet loss PC Poli 3 | network, confidence **0.8469** (`H_NET_ACCESS`) |
| INC-2026-002 | S2: DNS internal tidak resolve | dns, **0.9262** |
| INC-2026-003 | S3: timeout database SIMRS | database, **0.8466** |
| INC-2026-004 | S4: server aplikasi overload | server, **0.7981** |
| INC-2026-005 | S5: unit Farmasi tidak bisa akses aplikasi | network, **0.9135** |
| INC-2026-006/007/008 | Kontrol: evidence tidak cukup (login, kasir, printer lab) | root cause **tidak disimpulkan** (confidence 0.12 sampai 0.17) |

<p align="center">
  <img src="docs/assets/confidence.png" alt="Evidence confidence per tiket contoh" width="85%">
</p>

Kontrol 006-008 sengaja memverifikasi bahwa sistem menolak mengklaim root cause tanpa evidence langsung. Halaman *Create Incident* di frontend memungkinkan membuat tiket baru pada waktu kejadian skenario manapun dan menjalankan investigasi secara live.

<br>

## <img src="docs/assets/icons/code.svg" width="26" align="top"> API

41 path (Swagger di `/docs`). Ringkasan:

| Kelompok | Endpoint |
|---|---|
| **Insiden** | `GET/POST /api/incidents`, `GET /api/incidents/{id}`, `POST /api/incidents/{id}/investigate` (202, latar belakang + polling), `POST .../resolve`, `GET .../events` |
| **Investigasi** | `GET /api/investigations`, `/{id}`, `/{id}/timeline`, `/{id}/evidence`, `/{id}/tools`, `POST /{id}/replay`, `GET /{id}/compare/{other}`, `/{id}/export/json`, `/{id}/export/pdf` |
| **Data** | `GET /api/devices`, `/servers`, `/services`, `/topology`, `/logs`, `/logs/correlated`, `/sops`, `/historical-incidents` |
| **Analitik** | `GET /api/dashboard/stats`, `/api/analytics/investigations`, `/api/analytics/benchmark`, `POST /api/analytics/benchmark/run` |
| **AI dan sistem** | `GET /api/ai/config`, `POST /api/ai/test/llm`, `POST /api/ai/test/mcp`, `GET /api/health` |

Galat dikembalikan dalam bentuk `{error, message, request_id}` (header `X-Request-ID`), tanpa membocorkan detail internal.

<br>

## <img src="docs/assets/icons/monitor.svg" width="26" align="top"> Frontend

17 halaman: Dashboard, Incidents, Create Incident, Incident Detail, Investigations, Investigation (progress per tahap + laporan), Timeline, Evidence, Topology Map, Devices, Servers, Services, Logs, SOPs, Historical Incidents, Analytics (benchmark), dan AI Config.

Seluruh data berasal dari backend. Tersedia state loading, skeleton, empty, error, toast, dialog konfirmasi, dan paginasi. Ikon memakai Lucide (tanpa emoji).

<br>

## <img src="docs/assets/icons/test-tube.svg" width="26" align="top"> Testing dan validasi

```bash
make test        # 99 passed
make lint        # ruff, black, mypy (backend/app 58 file, mcp-server 14 file), eslint, tsc: bersih
make build       # frontend production build
make health      # health check live
```

Hasil terakhir (dijalankan pada sesi pembuatan):

| | Pemeriksaan | Hasil |
|:-:|---|---|
| <img src="docs/assets/icons/circle-check.svg" width="18"> | `pytest` | **99 passed** (Python 3.10 dan 3.13) |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | Lint dan typecheck | ruff, black, mypy, eslint, tsc bersih |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | `npm run build` | berhasil |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | `docker compose config` | valid |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | Migrasi Alembic upgrade/downgrade | diuji pada PostgreSQL 16 + pgvector 0.6 nyata |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | `scripts/health_check.py --investigate INC-2026-001` | **18/18** lulus (health, DB, RAG, MCP, penolakan akses anonim, registrasi + sesi, Swagger, proxy frontend, investigasi selesai, evidence 30 item, 12 panggilan tool ter-audit, ekspor JSON dan PDF) |
| <img src="docs/assets/icons/circle-check.svg" width="18"> | Frontend | 17 halaman dimuat di Chromium headless tanpa galat konsol |

<br>

## <img src="docs/assets/icons/chart-column.svg" width="26" align="top"> Benchmark dan eksperimen A-D

`make benchmark` menjalankan 50 item (10 parafrasa × 5 skenario) dan menulis `data/processed/benchmark_results.json`. Angka di bawah dihitung dari eksekusi nyata (embedder hashing, klasifikasi berbasis aturan, MCP live).

| Eksp. | Deskripsi | Klasifikasi | Precision@8 | SOP hit | Tool F1 | Root-cause agreement | Evidence coverage |
|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **A** | Tanpa RAG | 0.98 | | | | 0.78 | 0.00 |
| **B** | RAG tanpa temporal | 0.98 | 0.965 | 0.693 | | 1.00 | 0.00 |
| **C** | RAG + temporal | 0.98 | 0.8275 | 0.693 | | 1.00 | 0.00 |
| **D** | Pipeline penuh (temporal + topologi + MCP) | 0.98 | 0.8175 | 0.703 | 0.871 | 1.00 | 0.941 |

<p align="center">
  <img src="docs/assets/benchmark.png" alt="Hasil benchmark eksperimen A sampai D" width="95%">
</p>

> [!IMPORTANT]
> **Catatan jujur**
> 1. Benchmark sintetis dan label ditulis dari kosakata yang sama dengan data historis, sehingga angka optimistis untuk jenis kegagalan baru.
> 2. Pembobotan temporal pada benchmark ini *menurunkan* precision@8 (B 0.965 vs C 0.8275) karena insiden terbaru sering berasal dari pola lain. Manfaat temporal terlihat pada pemilihan versi SOP dan korelasi log, bukan pada metrik ini.
> 3. Metrik yang tidak relevan untuk suatu eksperimen dilaporkan kosong, bukan nol.
> 4. Tidak ada klaim performa di luar angka ini.

<br>

## <img src="docs/assets/icons/brain.svg" width="26" align="top"> Fine-tuning LoRA (opsional)

Folder `training/` berisi pembangkit dataset (klasifikasi, pemilihan tool, format respons, dll.), persiapan train/val, evaluasi baseline, dan skrip `train_lora.py`. **Tidak diperlukan** untuk menjalankan aplikasi. Lihat `training/README.md`.

<br>

## <img src="docs/assets/icons/shield-check.svg" width="26" align="top"> Data Privacy and Safety

| | Prinsip |
|:-:|---|
| <img src="docs/assets/icons/file-lock.svg" width="22"> | Hanya data sintetis; tidak ada data pasien atau identitas pribadi. **Jangan memasukkan data pasien nyata ke sistem ini.** |
| <img src="docs/assets/icons/eye.svg" width="22"> | Semua tool MCP **read-only**; klien menerapkan allow-list. Tidak ada otomasi destruktif. |
| <img src="docs/assets/icons/shield-alert.svg" width="22"> | Log dan dokumen diperlakukan sebagai **data**, bukan instruksi (mitigasi prompt-injection). LLM hanya memangkas rencana tool dan merangkum, tidak dapat menambah tool di luar allow-list. |
| <img src="docs/assets/icons/users.svg" width="22"> | Sistem menyebut diri *investigation agent*; keluaran adalah rekomendasi yang wajib diverifikasi manusia. |
| <img src="docs/assets/icons/gauge.svg" width="22"> | Skor adalah *evidence confidence score*, bukan kepastian; root cause tidak diklaim bila evidence tidak cukup. |
| <img src="docs/assets/icons/bug.svg" width="22"> | Error dibersihkan sebelum dikirim ke klien; setiap request punya `X-Request-ID`. |

> [!WARNING]
> Untuk penggunaan nyata: tambahkan otorisasi yang lebih rinci (RBAC), TLS, pembatasan jaringan MCP, dan kebijakan retensi log.

<br>

## <img src="docs/assets/icons/lightbulb.svg" width="26" align="top"> Kebaruan riset (research novelty)

1. **Retrieval versi-sadar waktu**: SOP dipilih berdasarkan versi yang berlaku pada saat insiden, bukan versi terbaru.
2. **Peluruhan temporal berbeda per sumber** (historis, SOP, log) dalam skor hibrida yang dapat diaudit.
3. **Evidence terpisah dari inferensi**: `FACT` / `INFERENCE` / `UNKNOWN` dengan relasi temporal dan peran, sehingga kontradiksi tercatat.
4. **Gating evidence langsung**: konteks saja (SOP, riwayat) tidak cukup untuk menyimpulkan root cause; sistem lebih memilih "belum dapat ditentukan".
5. **Audit dan replay** investigasi dengan snapshot konfigurasi/input serta perbandingan antar-run.

<br>

## <img src="docs/assets/icons/triangle-alert.svg" width="26" align="top"> Keterbatasan yang diketahui

- **Skala vektor**: mode lokal SQLite menghitung kemiripan vektor di Python (bukan pgvector); cukup untuk data contoh, bukan untuk skala besar.
- **Data sintetis**: seluruh data dan benchmark sintetis; tidak ada evaluasi pada infrastruktur nyata. Generalisasi belum terbukti.
- **Embedding validasi**: yang dipakai adalah `hashing-lexical-384`, **bukan** `bge-small-en-v1.5`. Jalur sentence-transformers tersedia tetapi tidak dijalankan di lingkungan validasi.
- **Jalur LLM**: Ollama **belum diuji** dengan model sungguhan; seluruh hasil di atas berasal dari mode fallback (aturan).
- **Docker**: `docker-compose.yml` valid secara sintaks (`docker compose config`), tetapi `docker compose up --build` **belum berhasil diverifikasi**. Daemon Docker dapat dijalankan di sandbox pembuatan, namun registry Docker Hub diblokir (HTTP 403) sehingga image dasar (`python`, `node`, `nginx`, `pgvector`) tidak bisa di-pull. Jalankan di mesin dengan akses internet biasa dan laporkan bila ada galat.
- **LoRA**: dataset dan skrip tersedia, tetapi **loop pelatihan belum dieksekusi** (tanpa GPU/`peft`); tidak ada klaim hasil model fine-tuned.
- **Klasifikasi benchmark**: 0.98 (49/50); satu tiket farmasi ambigu diklasifikasikan network, bukan application.
- **Antrean job**: investigasi berjalan via `BackgroundTasks` (satu proses); belum ada antrean terdistribusi.
- **Otorisasi**: autentikasi akun dan sesi sudah ada, tetapi peran (`admin`, `it_support`) belum membedakan hak akses per endpoint (RBAC rinci belum ada).
- **Temporal**: pada benchmark ini pembobotan temporal menurunkan precision@8 (lihat catatan di bagian benchmark).
- **Bundle frontend**: sekitar 730 kB (belum di-*code-split*).

<br>

## <img src="docs/assets/icons/map.svg" width="26" align="top"> Roadmap

- [ ] RBAC per peran pada endpoint API
- [ ] Antrean job (mis. worker terpisah)
- [ ] Code-splitting frontend
- [ ] Evaluasi dengan embedding sentence-transformers dan LLM lokal
- [ ] Integrasi sumber monitoring nyata (SNMP/Zabbix/Prometheus) lewat tool MCP read-only baru
- [ ] Evaluasi LoRA bila GPU tersedia
