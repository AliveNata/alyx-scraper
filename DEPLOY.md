# Deploy ke PythonAnywhere

## 1. Push ke GitHub (dari lokal)

```bash
cd Alyx_scraper

git init
git add .
git commit -m "Initial release: Alyx Scraper v2.0"
git branch -M main
git remote add origin https://github.com/AliveNata/pet-scraper.git
git push -u origin main
```

---

## 2. Setup di PythonAnywhere

### A. Buka Bash Console

Login ke https://www.pythonanywhere.com → **Consoles** → **Bash**

```bash
# Clone repo
git clone https://github.com/AliveNata/pet-scraper.git
cd pet-scraper

# Buat virtual environment (Python 3.10)
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install optional packages
pip install twikit facebook-scraper instaloader yagmail

# Salin config
cp config.example.json config.json
nano config.json   # edit admin_password, email, dll.
```

### B. Konfigurasi Web App

1. Pergi ke tab **Web** → **Add a new web app**
2. Pilih **Manual configuration** → Python 3.10
3. Di bagian **Virtualenv**, isi:
   ```
   /home/alivenata/pet-scraper/venv
   ```
4. Klik **WSGI configuration file** (link di bagian atas), ganti seluruh isinya dengan:

```python
import sys
import os

path = '/home/alivenata/pet-scraper'
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
```

5. Klik **Save** lalu kembali ke tab Web → **Reload**

### C. Static Files (opsional, jika ada)

Di bagian **Static files**:
| URL | Directory |
|-----|-----------|
| `/static/` | `/home/alivenata/pet-scraper/static/` |

---

## 3. Environment Variables (Opsional)

Di tab **Web** → **Environment variables** atau tambah ke `app.py`:

| Variable | Nilai |
|----------|-------|
| `SECRET_KEY` | string acak panjang |
| `ADMIN_KEY` | key untuk API admin |

---

## 4. Update / Re-deploy

Setiap kali ada update di repo:

```bash
# Di PythonAnywhere Bash Console
cd ~/pet-scraper
git pull origin main
source venv/bin/activate
pip install -r requirements.txt   # jika ada dependency baru
```

Lalu di tab **Web** → **Reload**

---

## 5. Cek Logs

Jika ada error:
- **Error log:** Tab Web → Error log
- **Server log:** Tab Web → Server log
- Atau dari Bash: `tail -f /var/log/alivenata.pythonanywhere.com.error.log`

---

## Catatan Penting

- PythonAnywhere Free tier **tidak bisa akses URL eksternal** kecuali whitelist.
  Domain yang sudah diizinkan otomatis: `google.com`, `reddit.com`, dll.
  Untuk akses penuh → upgrade ke **Hacker plan** ($5/bulan).
- File `config.json` dibuat langsung di server, **jangan di-commit ke GitHub**.
- Database SQLite (`alivyx.db`) tersimpan di server, tidak perlu setup database terpisah.
