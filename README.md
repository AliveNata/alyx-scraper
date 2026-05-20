# Alyx Scraper

Multi-platform web scraper untuk riset dan analisis data dari berbagai sumber.

**Live:** https://alivenata.pythonanywhere.com

---

## Platform yang Didukung

| Platform | Metode |
|----------|--------|
| Google News | RSS Feed |
| News Sites | Bing News HTML |
| Reddit | JSON API langsung |
| Kaskus | Direct HTML scraping |
| X / Twitter | Nitter / twikit |
| Facebook | facebook-scraper |
| Threads | Google search index |
| Quora | Direct + Google index |
| Instagram | instaloader (session) |

---

## Fitur

- **Direct Scraping** dari 9 platform
- **Image Scraper** - URL, pencarian, upload & cari mirip
- **Export** ke CSV / JSON / XLSX
- **Light / Dark Theme** (light default)
- **Bilingual** Indonesia / English
- **Admin Dashboard** tersembunyi di `/alyx-control-panel`
  - Audit log (IP, keyword, durasi, lokasi)
  - Line chart usage by date
  - Perbandingan WoW, MoM, QoQ, YoY

---

## Changelog

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

# Jalankan
python app.py
```

Buka **http://localhost:5000**

---

## Deploy ke PythonAnywhere

Lihat [DEPLOY.md](DEPLOY.md) untuk panduan lengkap.

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
