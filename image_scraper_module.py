import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse
import re
import os
import time
import random
import hashlib
import base64
from io import BytesIO


class ImageScraper:
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def update_status(self, msg):
        if self.gui_callback:
            self.gui_callback(msg)

    def scrape_from_url(self, url, max_images=30):
        self.update_status(f"Scraping images from: {url[:60]}...")
        images = []
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            img_tags = soup.find_all('img')
            seen = set()
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
                if not src or src.startswith('data:image/svg'):
                    continue
                if not src.startswith('http'):
                    src = urljoin(url, src)
                if src in seen:
                    continue
                seen.add(src)
                alt = img.get('alt', '')
                width = img.get('width', '')
                height = img.get('height', '')
                try:
                    w = int(re.sub(r'[^\d]', '', str(width))) if width else 0
                    h = int(re.sub(r'[^\d]', '', str(height))) if height else 0
                    if w and h and (w < 50 or h < 50):
                        continue
                except ValueError:
                    pass
                images.append({
                    'url': src,
                    'alt': alt,
                    'width': width,
                    'height': height,
                    'source_page': url,
                    'domain': urlparse(src).netloc
                })
                if len(images) >= max_images:
                    break
            og_images = soup.find_all('meta', property=re.compile(r'og:image|twitter:image'))
            for og in og_images:
                src = og.get('content', '')
                if src and src not in seen:
                    seen.add(src)
                    images.append({
                        'url': src,
                        'alt': 'Open Graph Image',
                        'width': '',
                        'height': '',
                        'source_page': url,
                        'domain': urlparse(src).netloc
                    })
            self.update_status(f"Found {len(images)} images from URL")
        except Exception as e:
            self.update_status(f"Image scrape error: {str(e)[:60]}")
        return images

    def search_images(self, query, max_images=30):
        self.update_status(f"Searching images: '{query}'...")
        images = []
        try:
            url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first=1"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            img_links = soup.find_all('a', class_='iusc')
            for link in img_links[:max_images]:
                m_attr = link.get('m', '{}')
                try:
                    import json
                    m_data = json.loads(m_attr)
                    img_url = m_data.get('murl', '')
                    title = m_data.get('t', '')
                    page_url = m_data.get('purl', '')
                    if img_url:
                        images.append({
                            'url': img_url,
                            'alt': title,
                            'width': '',
                            'height': '',
                            'source_page': page_url,
                            'domain': urlparse(img_url).netloc
                        })
                except Exception:
                    continue
            if not images:
                for img in soup.find_all('img', src=True):
                    src = img.get('src', '')
                    if src.startswith('http') and 'bing' not in src:
                        images.append({
                            'url': src,
                            'alt': img.get('alt', ''),
                            'width': '',
                            'height': '',
                            'source_page': url,
                            'domain': urlparse(src).netloc
                        })
                        if len(images) >= max_images:
                            break
            self.update_status(f"Found {len(images)} images for '{query}'")
        except Exception as e:
            self.update_status(f"Image search error: {str(e)[:60]}")
        return images

    def find_related_images(self, image_url=None, image_data=None, max_images=20):
        self.update_status("Searching related images...")
        images = []
        try:
            if image_url:
                search_url = f"https://www.bing.com/images/search?q=imgurl:{quote_plus(image_url)}&view=detailv2&iss=sbi"
                resp = self.session.get(search_url, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    for img in soup.find_all('img', src=True)[:max_images]:
                        src = img.get('src', '')
                        if src.startswith('http') and 'bing.com' not in src:
                            images.append({
                                'url': src,
                                'alt': img.get('alt', 'Related Image'),
                                'width': '',
                                'height': '',
                                'source_page': search_url,
                                'domain': urlparse(src).netloc
                            })
            if image_url and not images:
                keywords = self._extract_keywords_from_url(image_url)
                if keywords:
                    images = self.search_images(keywords, max_images)
            self.update_status(f"Found {len(images)} related images")
        except Exception as e:
            self.update_status(f"Related image error: {str(e)[:60]}")
        return images

    def _extract_keywords_from_url(self, url):
        path = urlparse(url).path
        filename = os.path.splitext(os.path.basename(path))[0]
        words = re.split(r'[-_\d]+', filename)
        words = [w for w in words if len(w) > 2]
        return ' '.join(words[:5])

    def download_image(self, image_url):
        try:
            resp = self.session.get(image_url, timeout=15, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', 'image/jpeg')
            data = resp.content
            b64 = base64.b64encode(data).decode('utf-8')
            return {
                'data': b64,
                'content_type': content_type,
                'size': len(data),
                'url': image_url
            }
        except Exception:
            return None
