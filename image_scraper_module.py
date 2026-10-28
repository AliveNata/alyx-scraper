import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse
import re
import os
import base64
import json
import tempfile


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

    # ------------------------------------------------------------------
    # Existing method - unchanged
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Bing image search with pagination support
    # offset maps to Bing's &first= parameter (1-based)
    # ------------------------------------------------------------------

    def search_images(self, query, max_images=30, offset=0):
        self.update_status(f"Searching images: '{query}'...")
        images = []
        try:
            first = offset + 1  # Bing uses 1-based index
            url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first={first}"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            img_links = soup.find_all('a', class_='iusc')
            for link in img_links[:max_images]:
                m_attr = link.get('m', '{}')
                try:
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

    # ------------------------------------------------------------------
    # Google Images search via icrawler (no API key required)
    # Uses a temp dir, reads files back as base64 + metadata.
    # Falls back to Bing if icrawler is not installed.
    # ------------------------------------------------------------------

    def search_images_google(self, query, max_images=30, offset=0):
        self.update_status(f"Searching Google Images: '{query}'...")
        images = []
        try:
            from icrawler.builtin import GoogleImageCrawler
        except ImportError:
            self.update_status("icrawler not installed, falling back to Bing")
            return self.search_images(query, max_images=max_images, offset=offset)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                crawler = GoogleImageCrawler(
                    storage={'root_path': tmp_dir},
                    log_level=40,  # ERROR only - suppress icrawler chatter
                )
                # icrawler offset skips the first N results
                crawler.crawl(
                    keyword=query,
                    max_num=max_images,
                    offset=offset,
                )
                files = sorted(
                    [f for f in os.listdir(tmp_dir) if not f.startswith('.')],
                    key=lambda f: os.path.getmtime(os.path.join(tmp_dir, f))
                )
                for fname in files:
                    fpath = os.path.join(tmp_dir, fname)
                    try:
                        with open(fpath, 'rb') as fh:
                            data = fh.read()
                        ext = os.path.splitext(fname)[1].lower().lstrip('.')
                        content_type = f"image/{ext}" if ext else "image/jpeg"
                        b64 = base64.b64encode(data).decode('utf-8')
                        images.append({
                            'url': f"data:{content_type};base64,{b64[:40]}...",
                            'alt': query,
                            'width': '',
                            'height': '',
                            'source_page': f"https://www.google.com/search?tbm=isch&q={quote_plus(query)}",
                            'domain': 'images.google.com',
                            # full base64 payload for callers that need it
                            '_b64': b64,
                            '_content_type': content_type,
                        })
                    except Exception:
                        continue
            self.update_status(f"Google Images: {len(images)} images for '{query}'")
        except Exception as e:
            self.update_status(f"Google Images error: {str(e)[:80]}")
        return images

    # ------------------------------------------------------------------
    # Resolution/format filter using actual decoded image dimensions
    # formats: list of lowercase extension strings e.g. ['jpg','png','webp']
    # ------------------------------------------------------------------

    def filter_images(self, images, min_width=0, min_height=0, formats=None):
        try:
            from PIL import Image as PILImage
            import io
        except ImportError:
            self.update_status("Pillow not installed; filter_images skipped")
            return images

        allowed_formats = set(f.lower().lstrip('.') for f in formats) if formats else None
        # Normalize 'jpeg' alias so callers can pass 'jpg' and it matches
        if allowed_formats and 'jpg' in allowed_formats:
            allowed_formats.add('jpeg')

        filtered = []
        for item in images:
            img_bytes = None

            # If the item came from search_images_google it already has _b64
            if item.get('_b64'):
                try:
                    img_bytes = base64.b64decode(item['_b64'])
                except Exception:
                    pass
            else:
                downloaded = self.download_image(item.get('url', ''))
                if downloaded:
                    try:
                        img_bytes = base64.b64decode(downloaded['data'])
                    except Exception:
                        pass

            if not img_bytes:
                # Cannot verify; include by default so we don't silently drop things
                filtered.append(item)
                continue

            try:
                with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
                    w, h = pil_img.size
                    fmt = pil_img.format.lower() if pil_img.format else ''
                    # Check size bounds
                    if min_width and w < min_width:
                        continue
                    if min_height and h < min_height:
                        continue
                    # Check format
                    if allowed_formats and fmt not in allowed_formats:
                        continue
                    # Stamp actual dimensions back onto the item
                    item = dict(item)
                    item['width'] = str(w)
                    item['height'] = str(h)
                    filtered.append(item)
            except Exception:
                # Unreadable image; skip
                continue

        self.update_status(f"filter_images: {len(filtered)}/{len(images)} passed")
        return filtered

    # ------------------------------------------------------------------
    # Reverse image search
    # 1. TinEye (always, no key needed) - scrapes match count + URLs
    # 2. Google Vision (premium, only when api_key is provided)
    # ------------------------------------------------------------------

    def reverse_search(self, image_bytes=None, image_url=None, api_key=None, max_images=30):
        self.update_status("Reverse image search...")
        results = []

        # --- Step 1: TinEye (no API key required) ---
        tineye_results = self._tineye_search(
            image_bytes=image_bytes,
            image_url=image_url,
            max_images=max_images,
        )
        results.extend(tineye_results)

        # --- Step 2: Google Vision (premium, only if key is given) ---
        if api_key:
            # Resolve bytes if only url was given
            bytes_for_vision = image_bytes
            if not bytes_for_vision and image_url:
                dl = self.download_image(image_url)
                if dl:
                    try:
                        bytes_for_vision = base64.b64decode(dl['data'])
                    except Exception:
                        pass
            if bytes_for_vision:
                vision_results = self._google_vision_search(
                    bytes_for_vision, api_key, max_images=max_images
                )
                # Merge, avoiding duplicates by URL
                existing_urls = {r['url'] for r in results}
                for r in vision_results:
                    if r['url'] not in existing_urls:
                        results.append(r)
                        existing_urls.add(r['url'])

        self.update_status(f"Reverse search: {len(results)} results total")
        return results

    def _tineye_search(self, image_bytes=None, image_url=None, max_images=30):
        """POST to TinEye and scrape match count + result image URLs.
        No API key required; basic results only."""
        images = []
        try:
            self.update_status("TinEye reverse search...")
            headers = {
                'User-Agent': self.headers['User-Agent'],
                'Origin': 'https://tineye.com',
                'Referer': 'https://tineye.com/',
            }

            if image_bytes:
                # Upload the raw bytes directly
                resp = requests.post(
                    'https://tineye.com/search',
                    files={'image': ('image.jpg', image_bytes, 'image/jpeg')},
                    headers=headers,
                    timeout=30,
                    allow_redirects=True,
                )
            elif image_url:
                resp = requests.post(
                    'https://tineye.com/search',
                    data={'url': image_url},
                    headers=headers,
                    timeout=30,
                    allow_redirects=True,
                )
            else:
                return images

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Extract match count from header text like "X results"
            match_count = ''
            count_tag = soup.find(class_=re.compile(r'matches|result-count|num-results'))
            if count_tag:
                match_count = count_tag.get_text(strip=True)

            # Collect result image links - TinEye uses class "result-image-link"
            seen = set()
            for tag in soup.find_all('a', class_=re.compile(r'result-image-link|result-link')):
                href = tag.get('href', '')
                if href and href.startswith('http') and href not in seen:
                    seen.add(href)
                    # Try to find the nested img src for the thumbnail
                    thumb = tag.find('img')
                    thumb_src = thumb.get('src', '') if thumb else ''
                    images.append({
                        'url': href,
                        'alt': f"TinEye match {match_count}".strip(),
                        'width': '',
                        'height': '',
                        'source_page': resp.url,
                        'domain': urlparse(href).netloc,
                        '_thumb': thumb_src,
                    })
                    if len(images) >= max_images:
                        break

            # Fallback: grab any image tags inside .matches container
            if not images:
                container = soup.find(class_=re.compile(r'matches|results'))
                if container:
                    for img_tag in container.find_all('img', src=True):
                        src = img_tag.get('src', '')
                        if src.startswith('http') and src not in seen:
                            seen.add(src)
                            images.append({
                                'url': src,
                                'alt': f"TinEye match {match_count}".strip(),
                                'width': '',
                                'height': '',
                                'source_page': resp.url,
                                'domain': urlparse(src).netloc,
                            })
                            if len(images) >= max_images:
                                break

            self.update_status(f"TinEye: {len(images)} matches")
        except Exception as e:
            self.update_status(f"TinEye error: {str(e)[:80]}")
        return images

    def _google_vision_search(self, image_bytes, api_key, max_images=30):
        """Google Cloud Vision Web Detection (premium, requires API key)."""
        images = []
        try:
            self.update_status("Google Vision Web Detection...")
            payload = {
                "requests": [{
                    "image": {"content": base64.b64encode(image_bytes).decode("utf-8")},
                    "features": [{"type": "WEB_DETECTION", "maxResults": max_images}],
                }]
            }
            resp = requests.post(
                "https://vision.googleapis.com/v1/images:annotate",
                params={"key": api_key}, json=payload, timeout=20,
            )
            resp.raise_for_status()
            web = (resp.json().get("responses") or [{}])[0].get("webDetection", {})
            entities = web.get("webEntities") or []
            label = entities[0].get("description", "") if entities else ""
            seen = set()
            for sim in web.get("visuallySimilarImages", []):
                url = sim.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                images.append({
                    "url": url, "alt": label or "Similar image",
                    "width": "", "height": "",
                    "source_page": "", "domain": urlparse(url).netloc,
                })
                if len(images) >= max_images:
                    break
            self.update_status(f"Google Vision: {len(images)} similar images")
        except Exception as e:
            self.update_status(f"Vision error: {str(e)[:80]}")
        return images

    # Legacy alias - keeps old call sites working without change
    def google_reverse_search(self, image_bytes, api_key, max_images=30):
        return self.reverse_search(
            image_bytes=image_bytes, api_key=api_key, max_images=max_images
        )

    # ------------------------------------------------------------------
    # Existing method - unchanged
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # JS-rendered page scraping via Playwright (chromium headless)
    # Falls back to scrape_from_url if playwright is not installed.
    # ------------------------------------------------------------------

    def scrape_from_url_js(self, url, max_images=30):
        self.update_status(f"JS scraping: {url[:60]}...")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.update_status("playwright not installed; falling back to requests scrape")
            return self.scrape_from_url(url, max_images=max_images)

        images = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=self.headers['User-Agent']
                )
                page.goto(url, wait_until='networkidle', timeout=30000)

                seen = set()

                # Collect all img[src] and img[data-src]
                for handle in page.query_selector_all('img'):
                    src = (
                        handle.get_attribute('src') or
                        handle.get_attribute('data-src') or
                        ''
                    )
                    alt = handle.get_attribute('alt') or ''
                    width_attr = handle.get_attribute('width') or ''
                    height_attr = handle.get_attribute('height') or ''

                    if not src or src.startswith('data:image/svg'):
                        continue
                    if not src.startswith('http'):
                        src = urljoin(url, src)
                    if src in seen:
                        continue

                    # Skip decorative/tiny images using declared dimensions
                    try:
                        w = int(re.sub(r'[^\d]', '', str(width_attr))) if width_attr else 0
                        h = int(re.sub(r'[^\d]', '', str(height_attr))) if height_attr else 0
                        if w and h and (w < 50 or h < 50):
                            continue
                    except ValueError:
                        pass

                    seen.add(src)
                    images.append({
                        'url': src,
                        'alt': alt,
                        'width': width_attr,
                        'height': height_attr,
                        'source_page': url,
                        'domain': urlparse(src).netloc,
                    })
                    if len(images) >= max_images:
                        break

                # Also grab OG/twitter meta images - same as scrape_from_url does
                if len(images) < max_images:
                    content = page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    for og in soup.find_all('meta', property=re.compile(r'og:image|twitter:image')):
                        src = og.get('content', '')
                        if src and src not in seen:
                            seen.add(src)
                            images.append({
                                'url': src,
                                'alt': 'Open Graph Image',
                                'width': '',
                                'height': '',
                                'source_page': url,
                                'domain': urlparse(src).netloc,
                            })

                browser.close()
            self.update_status(f"JS scrape: {len(images)} images from {url[:40]}")
        except Exception as e:
            self.update_status(f"JS scrape error: {str(e)[:80]}")
        return images
