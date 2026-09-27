# AlyxLabs Scraper

Alat riset & monitoring media + akademik Indonesia. Kumpulkan data dari berbagai sumber terkurasi, lengkap dengan dokumentasi koleksi dan analisis yang siap untuk skripsi/thesis.

**Live:** https://scraper.alyxlabs.tech

---

## Sumber yang Didukung (8)

| Sumber | Metode | API key |
|--------|--------|---------|
| Google News | RSS feed | - |
| News Sites | Bing News RSS + 18 feed RSS Indonesia | - |
| GDELT | DOC 2.0 API (berita global, historis) | - |
| YouTube | Data API v3 (cari video) | Gratis (wajib) |
| Wikipedia | MediaWiki API (id.wikipedia) | - |
| OpenAlex | Works API (jurnal/paper: judul, penulis, abstrak, DOI) | - |
| Semantic Scholar | Graph API (paper akademik) | Gratis (disarankan) |
| Kaskus | Indeks pencarian (forum Indonesia) | - |

Sumber yang butuh API key gratis bisa dinyalakan/dimatikan admin. Twitter/X, Instagram, Facebook, Threads, Reddit dihapus karena tidak reliable dari server (blokir IP / API berbayar).

---

## Fitur

- **8 sumber terkurasi** - berita, video, referensi, jurnal, forum
- **Teks lengkap artikel** (trafilatura) untuk analisis konten
- **Filter rentang tanggal** untuk sumber historis (GDELT, jurnal)
- **Deduplikasi** lintas-sumber otomatis
- **Catatan Koleksi + sitasi** - metadata pengumpulan (keyword, sumber, waktu WIB) siap untuk bab Metodologi
- **Analisis** - frekuensi kata terbanyak & distribusi waktu
- **Export** CSV / JSON / XLSX / Markdown (dengan metadata)
- **Image Scraper** - pencarian, scrape URL, upload (reverse search via Google Vision)
- **Bilingual** Indonesia / English, **Light/Dark** theme
- **Admin Dashboard** (`/alyx-control-panel`) - toggle platform, kunci API, audit log, chart usage

---

## Changelog

### v3.0.0 - Sep 2026 (Fokus riset)

- **Rebrand** ke AlyxLabs (logo + favicon baru)
- **Sumber dirombak** jadi 8 yang reliable: hapus Reddit + sosial (Twitter/IG/FB/Threads) + Quora; tambah **GDELT, YouTube, Wikipedia, OpenAlex, Semantic Scholar**
- **Teks lengkap artikel** (opt-in, trafilatura) untuk berita
- **Filter rentang tanggal** (GDELT + jurnal), **dedup** lintas-sumber
- **Catatan Koleksi + Salin sitasi**; metadata ikut di semua export
- **Export Markdown** (dropdown format + tombol download)
- **Analisis** kata terbanyak & **timeline** (panel collapsible)
- **Admin**: toggle nyala/mati platform, kunci API (Vision, Semantic Scholar, YouTube)
- Bug fix: relevansi hasil forum, filter tanggal audit, statistik platform, dedup

### v2.1.0 - Sep 2026 (Security hardening)

- Auth admin pindah ke **session-only** - tidak ada lagi `ADMIN_KEY` yang lewat di URL (`?key=`) atau disuntik ke HTML
- Password admin sekarang **di-hash** (werkzeug), bukan plaintext. Password plaintext lama otomatis di-upgrade ke hash saat login berikutnya
- **Endpoint `pip install` dari UI dihapus** - jalur RCE, install dependency lewat SSH saja
- Session admin punya **timeout 8 jam** (auto-logout)
- Rate-limit di `/api/forgot-password` (maks 1 request per IP per menit)
- `SECRET_KEY` & password admin wajib di-set lewat environment / config (lihat Setup)

**New:**
- Reverse image search asli untuk fitur upload via **Google Cloud Vision** (Web Detection). Set API key di Admin -> Settings -> Reverse Image Search. Tanpa key, upload jatuh ke pencarian nama file. Gratis s/d 1.000 request/bulan.
- Reddit via **API resmi (OAuth application-only)**. Set client_id + client_secret (script app) di Admin -> Settings -> Reddit API. Tanpa kredensial, jatuh ke metode scraping lama. Lebih stabil karena tidak kena blok IP.

**Bug fixes:**
- Statistik platform di admin dashboard sekarang dihitung per-platform (dulu string gabungan ke-`GROUP BY` utuh)
- Perbandingan QoQ dikelompokkan per kuartal beneran (dulu identik dengan bulanan)
- Filter `date_to` di audit log inklusif sampai akhir hari (dulu kelewat 1 hari)
- Simpan Settings tidak lagi menghapus username Twitter yang tersimpan
- Fitur upload gambar dilabel ulang "Upload & Cari" (mencari via nama file, bukan reverse image)
- Job scraper lama dibersihkan dari memori (cegah kebocoran memori)
- Hapus `analytics.py` (Streamlit lama yang sudah tidak terpakai) & `Procfile.txt`

### v2.0.0 - Mei 2026

**New Features:**
- UI/UX revamp total dengan desain modern berbasis glassmorphism
- Direct scraping dari Reddit (JSON API), Kaskus (HTML), X/Twitter (Nitter/twikit), Facebook (facebook-scraper), Threads, Quora, Instagram (instaloader)
- Image Scraper - cari gambar, scrape dari URL, upload & cari gambar mirip
- Related image search - temukan gambar serupa dari gambar yang dipilih
- Admin dashboard tersembunyi (`/alyx-control-panel`) dengan login & password
- Chart.js line chart usage by date
- Perbandingan WoW, MoM, QoQ, YoY di admin dashboard
- Light/Dark theme toggle (light sebagai default)
- Bilingual Indonesia/English dengan toggle bendera
- News Sites scraping worldwide termasuk Indonesia (Detik, Kompas, CNN, BBC, Reuters)
- Halaman Docs dengan sidebar navigasi, changelog, dan fitur baru
- Footer dengan link docs, repo GitHub, dan Saweria
- SQLite audit logging (IP, keyword, platform, durasi, lokasi) untuk semua aktivitas
- Forgot password via email (yagmail + Gmail App Password)
- Session-based Instagram login via Session ID atau password
- Twitter login via Auth Token (cookie) atau username/password (twikit)
- Multi-lokasi input - bisa isi lebih dari satu kota sekaligus
- Admin panel: platform status checker, test scraper per-platform, pip install dari UI

**Improvements:**
- Arsitektur backend direfactor ke modular (scraper.py, database.py, image_scraper_module.py)
- WSGI entry point (`wsgi.py`) untuk PythonAnywhere
- `.gitignore` yang proper - credentials & session files tidak ikut ke repo

### v1.0.0 - 2024

- Initial release sebagai Pet Scraper
- Google News RSS scraping
- Bing News scraping
- Forum & social media scraping via Google search
- Export ke Excel, CSV, JSON
- Flask web interface

---

## Setup Lokal

```bash
git clone https://github.com/AliveNata/alyx-scraper.git
cd alyx-scraper

# Buat virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Salin config
cp config.example.json config.json
# Edit config.json: ganti admin_password, email, dll.
# admin_password boleh plaintext - otomatis di-hash saat login pertama.

# Jalankan
python app.py
```

Buka **http://localhost:5000**

### Environment variables (produksi)

| Var | Wajib | Fungsi |
|-----|-------|--------|
| `SECRET_KEY` | Ya | Kunci penanda cookie session. Set ke nilai acak kuat, misal `openssl rand -hex 32`. Kalau tidak di-set, session admin bisa dipalsukan. |

Deploy live: VPS + gunicorn (`gunicorn app:app -b 127.0.0.1:8001`) di belakang nginx, di-manage PM2. `wsgi.py` disediakan untuk opsi PythonAnywhere tapi bukan yang dipakai sekarang.

---

## Repos yang Dipakai

| Lib | Repo |
|-----|------|
| twikit | https://github.com/d60/twikit |
| facebook-scraper | https://github.com/kevinzg/facebook-scraper |
| quora-scraper | https://github.com/adrian-dip/quora-scraper |
| Threads-Scraper | https://github.com/Zeeshanahmad4/Threads-Scraper |
| image-scraper | https://github.com/mahdidevlp/image-scraper |

---

## Lisensi

MIT - gunakan dengan etika, hormati robots.txt dan hak cipta.
