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
- **Image Scraper** — URL, pencarian, upload & cari mirip
- **Export** ke CSV / JSON / XLSX
- **Light / Dark Theme** (light default)
- **Bilingual** Indonesia / English
- **Admin Dashboard** tersembunyi di `/alyx-control-panel`
  - Audit log (IP, keyword, durasi, lokasi)
  - Line chart usage by date
  - Perbandingan WoW, MoM, QoQ, YoY

---

## Setup Lokal

```bash
git clone https://github.com/AliveNata/pet-scraper.git
cd pet-scraper

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

MIT — gunakan dengan etika, hormati robots.txt dan hak cipta.
