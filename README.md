# AlyxLabs Scraper

Alat riset & monitoring media + akademik Indonesia. Kumpulkan data dari berbagai sumber terkurasi, lengkap dengan dokumentasi koleksi dan analisis yang siap untuk skripsi/thesis.

**Live:** https://scraper.alyxlabs.tech

---

## Sumber yang Didukung (12)

| Sumber | Kategori | Metode | API key |
|--------|----------|--------|---------|
| Google News | Berita | RSS feed | - |
| News Sites | Berita | Bing News RSS + 18 feed RSS Indonesia | - |
| GDELT | Berita | DOC 2.0 API (berita global, historis) | - |
| Kompas | Berita | RSS feed | - |
| Liputan6 | Berita | RSS feed | - |
| OpenAlex | Jurnal/Paper | Works API (judul, penulis, abstrak, DOI) | - |
| Semantic Scholar | Jurnal/Paper | Graph API | Gratis (disarankan) |
| arXiv | Jurnal/Paper | Atom API (preprint: fisika, ilmu komputer, matematika) | - |
| Crossref | Jurnal/Paper | REST API (130M+ DOI, metadata lengkap) | - |
| YouTube | Video | Data API v3 | Gratis (wajib) |
| Wikipedia | Referensi | MediaWiki API (id.wikipedia) | - |
| Kaskus | Forum | Indeks pencarian | - |

Semua sumber bisa dinyalakan/dimatikan per-platform via Admin Dashboard. Twitter/X, Instagram, Facebook, Threads, Reddit dihapus karena tidak reliable dari server (blokir IP / API berbayar).

## API Keys

| Key | Fungsi | Wajib |
|-----|--------|-------|
| YouTube Data API v3 | Scraping video YouTube | Ya |
| Google Cloud Vision | Reverse image search (upload) | Tidak (fallback ke nama file) |
| Semantic Scholar | Rate limit lebih tinggi (1 RPS vs shared) | Tidak |
| Groq | Analisis AI otomatis di email notifikasi | Tidak (email tetap terkirim tanpa AI section) |

Set semua key di Admin -> Settings.

---

## Fitur

- **12 sumber terkurasi** - berita, jurnal/paper akademik, video, referensi, forum
- **Sitasi otomatis** APA7 dan format Mendikbud untuk setiap hasil; satu klik salin
- **Teks lengkap artikel** (trafilatura) untuk analisis konten
- **Filter rentang tanggal** berlaku ke semua platform (post-filter backend)
- **Filter relevansi** - artikel tidak relevan dari sumber tier-2 otomatis dibuang
- **Deduplikasi** lintas-sumber otomatis
- **Catatan Koleksi + sitasi** - metadata pengumpulan (keyword, sumber, waktu WIB) siap untuk bab Metodologi
- **Analisis** - frekuensi kata terbanyak & distribusi waktu
- **Export** CSV / JSON / XLSX / Markdown / RIS / BibTeX (dengan metadata)
- **Image Scraper** - pencarian, scrape URL, upload (reverse search via Google Vision)
- **Bilingual** Indonesia / English, **Light/Dark** theme
- **Admin Dashboard** (`/alyx-control-panel`) - toggle platform, kunci API, audit log, chart usage
- **Email notifikasi** dengan preview artikel, ringkasan statistik, dan **Analisis AI** (Insight / Rekomendasi / Kesimpulan via Groq)

---

## Changelog

### v3.1.0 - Okt 2026 (Email & kualitas hasil)

**Email notifikasi:**
- Logo di email sekarang pakai hosted PNG (`/static/brand_email.png`) - fix blank/pecah di Gmail
- Label "Rentang tanggal konten" diganti "Rentang tanggal publikasi artikel"
- Tambah section **Analisis AI** (Insight, Rekomendasi, Kesimpulan) generated via Groq; email tetap terkirim normal jika Groq tidak tersedia

**Kualitas hasil scraping:**
- **Filter relevansi** - artikel dari sumber tier-2 (Kompas, Liputan6, News Sites) wajib mengandung token keyword di judul/konten; sumber terpercaya (Google News, GDELT, YouTube, jurnal) bypass filter
- **Filter tanggal post-processing** - `date_from`/`date_to` sekarang berlaku ke semua platform (sebelumnya hanya GDELT & jurnal); artikel tanpa tanggal tetap dipertahankan

**UI:**
- Toast notifikasi pindah ke kanan atas, slide-in dari kanan, loader bar 5 detik, auto-dismiss
- Hint filter tanggal dipindah ke bawah kedua field tanggal (full-width, tidak terpotong)
- Teks hint diupdate: "Filter diterapkan ke semua hasil. Kosongkan untuk ambil semua tanggal."

**API keys:**
- Tambah field `groq` di `api_keys` config (Admin -> Settings)

### v3.0.0 - Sep 2026 (Fokus riset)

- **Rebrand** ke AlyxLabs (logo + favicon baru)
- **Sumber dirombak** jadi fokus riset: hapus Reddit (termasuk API resmi v2.1.0) + sosial (Twitter/IG/FB/Threads) + Quora; tambah **GDELT, YouTube, Wikipedia, OpenAlex, Semantic Scholar, arXiv, Crossref, Kompas, Liputan6** (total 12)
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

Deploy live: VPS + gunicorn (`gunicorn app:app -b 127.0.0.1:8001`) di belakang nginx, di-manage systemd (`systemctl restart alyx-scraper`). `wsgi.py` disediakan untuk opsi PythonAnywhere tapi bukan yang dipakai sekarang.

---

## Dependensi Utama

| Lib | Fungsi |
|-----|--------|
| Flask | Web framework |
| gunicorn | WSGI server (production) |
| trafilatura | Ekstrak teks lengkap artikel berita |
| lxml | HTML parsing (diperlukan trafilatura) |
| openpyxl | Export XLSX |
| werkzeug | Password hashing admin |
| yagmail | Email notifikasi |
| Groq SDK | Analisis AI di email |
| requests / feedparser | HTTP client + RSS parsing |

---

## Lisensi

MIT - gunakan dengan etika, hormati robots.txt dan hak cipta.
