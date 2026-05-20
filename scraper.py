import requests
from bs4 import BeautifulSoup
import json
import time
import random
import re
import os
from datetime import datetime
from urllib.parse import quote_plus, urljoin
import xml.etree.ElementTree as ET

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
_DEFAULT_NITTER = [
    'https://nitter.poast.org',
    'https://nitter.privacydev.net',
    'https://nitter.cz',
    'https://nitter.space',
    'https://nitter.mint.lgbt',
    'https://nitter.unixfox.eu',
    'https://nitter.it',
    'https://nitter.foss.wtf',
]

BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)


def load_twitter_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get('twitter', {})
    except Exception:
        return {}


def _parse_rss(content):
    """Parse RSS/Atom feed. Returns (soup, items_list)."""
    if isinstance(content, str):
        content = content.encode('utf-8', errors='replace')

    # Strategy A: stdlib ElementTree (most reliable for well-formed XML)
    try:
        root = ET.fromstring(content)
        # Strip namespace from tag names for comparison
        def _tag(el): return el.tag.split('}')[-1] if '}' in el.tag else el.tag
        items_et = [el for el in root.iter() if _tag(el) in ('item', 'entry')]
        if items_et:
            # Return via BeautifulSoup for uniform access
            pass  # fall through to BS4 below with ET validation done
    except ET.ParseError:
        pass

    # Strategy B: BeautifulSoup with multiple parsers
    for parser in ('xml', 'lxml-xml', 'lxml', 'html.parser'):
        try:
            soup = BeautifulSoup(content, parser)
            items = soup.find_all('item') or soup.find_all('entry')
            if items:
                return soup, items
        except Exception:
            continue

    return BeautifulSoup(content, 'html.parser'), []


def _rss_link(item):
    """Extract URL from an RSS <item> regardless of parser quirks."""
    # 1. Try <link> text / next_sibling (html.parser makes <link> self-closing)
    link_el = item.find('link')
    if link_el:
        txt = (link_el.string or '').strip()
        if txt.startswith('http'):
            return txt
        # html.parser puts the URL as next text sibling
        sib = link_el.next_sibling
        if sib and isinstance(sib, str):
            candidate = sib.strip()
            if candidate.startswith('http'):
                return candidate
        # Try href attribute (Atom feeds)
        href = link_el.get('href', '')
        if href.startswith('http'):
            return href

    # 2. Try <guid> which often IS the URL
    guid = item.find('guid')
    if guid:
        txt = (guid.string or guid.get_text()).strip()
        if txt.startswith('http'):
            return txt

    # 3. Try any element with an href/url attribute
    for el in item.find_all(True):
        for attr in ('href', 'url', 'link'):
            val = el.get(attr, '')
            if val.startswith('http'):
                return val

    return ''


class BaseScraper:
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': BROWSER_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
        })

    def update_status(self, msg):
        if self.gui_callback:
            try:
                self.gui_callback(msg)
            except Exception:
                try:
                    self.gui_callback(msg.encode('ascii', errors='replace').decode('ascii'))
                except Exception:
                    pass

    def delay(self, lo=0.5, hi=1.2):
        time.sleep(random.uniform(lo, hi))

    def clean(self, text):
        if not text:
            return ''
        text = ' '.join(str(text).split())
        for old, new in {
            '&amp;': '&', '&lt;': '<', '&gt;': '>',
            '&quot;': '"', '&#39;': "'", '&nbsp;': ' ',
            '​': '', ' ': ' ',
        }.items():
            text = text.replace(old, new)
        return text.strip()

    def _parse_date(self, pub_el):
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        if not pub_el:
            return date_str
        raw = pub_el.get_text().strip() if hasattr(pub_el, 'get_text') else str(pub_el).strip()
        for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(raw[:len(fmt)+5].strip(), fmt)
                return dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass
        return date_str

    def _kw_matches(self, keyword, *texts):
        """All significant keyword words must appear somewhere in the texts."""
        words = [w for w in keyword.lower().split() if len(w) >= 3]
        if not words:
            return True
        combined = ' '.join(str(t).lower() for t in texts if t)
        return all(w in combined for w in words)

    def _ddg_fallback(self, query, platform, site_filter, max_results):
        """DuckDuckGo HTML search — usually bypasses rate-limits that block Google."""
        results = []
        try:
            from urllib.parse import unquote, parse_qs, urlparse as _up
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query + ' site:' + site_filter)}"
            headers = {
                'User-Agent': BROWSER_UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://duckduckgo.com/',
            }
            resp = requests.get(url, headers=headers, timeout=14)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for item in soup.select('.result')[:max_results * 2]:
                title_el = item.select_one('.result__title a, .result__a')
                snip_el  = item.select_one('.result__snippet')
                if not title_el:
                    continue
                title = self.clean(title_el.get_text())
                href  = title_el.get('href', '')
                # DDG wraps URLs in redirect — extract the real one
                if 'uddg=' in href:
                    try:
                        href = unquote(parse_qs(_up(href).query).get('uddg', [href])[0])
                    except Exception:
                        pass
                if not href or not title:
                    continue
                results.append({
                    'platform': platform,
                    'title':    title,
                    'content':  self.clean(snip_el.get_text()) if snip_el else title,
                    'url':      href,
                    'date':     datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'source':   platform,
                    'keyword':  query,
                    'location': '',
                })
                if len(results) >= max_results:
                    break
        except Exception:
            pass
        return results

    def _google_fallback(self, query, platform, site_filter, max_results):
        """Google site-search fallback."""
        results = []
        try:
            url = f"https://www.google.com/search?q={quote_plus(query)}+site:{site_filter}&num=10"
            resp = self.session.get(url, timeout=12)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for g in soup.select('div.g')[:max_results]:
                t = g.find('h3')
                a = g.find('a', href=True)
                if t and a:
                    sn = g.find(['span', 'div'], class_=lambda c: c and 'VwiC3b' in str(c))
                    results.append({
                        'platform': platform,
                        'title': self.clean(t.get_text()),
                        'content': self.clean(sn.get_text()) if sn else self.clean(t.get_text()),
                        'url': a['href'],
                        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'source': platform,
                        'keyword': query,
                        'location': '',
                    })
        except Exception:
            pass
        return results


# ─────────────────────────────────────────────────────────────
# Google News — RSS (always works)
# ─────────────────────────────────────────────────────────────
class GoogleNewsScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Google News] Mencari '{keyword}'...")
        results = []
        try:
            query = f"{keyword} {location}".strip()
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=id&gl=ID&ceid=ID:id"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            _, items = _parse_rss(resp.content)
            for item in items[:max_results]:
                title_el = item.find('title')
                link_el  = item.find('link')
                desc_el  = item.find('description')
                pub_el   = item.find('pubDate')
                src_el   = item.find('source')
                title = self.clean(title_el.text) if title_el else ''
                link  = link_el.text if link_el else ''
                desc  = self.clean(desc_el.text) if desc_el else ''
                if title:
                    results.append({
                        'platform': 'Google News',
                        'title': title,
                        'content': desc[:300],
                        'url': link,
                        'date': self._parse_date(pub_el),
                        'source': src_el.text if src_el else 'Google News',
                        'keyword': keyword,
                        'location': location,
                    })
            self.update_status(f"[Google News] {len(results)} artikel ditemukan")
        except Exception as e:
            self.update_status(f"[Google News] Error: {str(e)[:60]}")
        return results


# ─────────────────────────────────────────────────────────────
# News Sites — Bing RSS + 16 ID RSS feeds
# ─────────────────────────────────────────────────────────────
class NewsSitesScraper(BaseScraper):
    ID_RSS = [
        ('Detik',         'https://rss.detik.com/index.php/detikcom'),
        ('Detik News',    'https://rss.detik.com/index.php/detiknews'),
        ('Kompas',        'https://rss.kompas.com/rss/breakingnews'),
        ('Kompas Regional','https://rss.kompas.com/rss/regional'),
        ('Antara',        'https://www.antaranews.com/rss/terkini.xml'),
        ('Antara Regional','https://www.antaranews.com/rss/regional.xml'),
        ('Liputan6',      'https://www.liputan6.com/rss'),
        ('Liputan6 Regional','https://www.liputan6.com/regional/rss'),
        ('Tribunnews',    'https://www.tribunnews.com/rss'),
        ('Tribun Jabar',  'https://jabar.tribunnews.com/rss'),
        ('CNN Indonesia', 'https://www.cnnindonesia.com/api/feed/rss'),
        ('Tempo',         'https://rss.tempo.co/'),
        ('SINDOnews',     'https://sindonews.com/rss'),
        ('Republika',     'https://www.republika.co.id/rss/'),
        ('JPNN',          'https://www.jpnn.com/rss'),
        ('Viva',          'https://www.viva.co.id/rss'),
        ('iNews',         'https://www.inews.id/rss'),
        ('Okezone',       'https://economy.okezone.com/rss'),
    ]

    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[News Sites] Mencari '{keyword}'...")
        results = []
        seen_urls = set()
        query = f"{keyword} {location}".strip()

        # ── 1. Bing News RSS
        for bing_url in [
            f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss",
            f"https://www.bing.com/news/search?q={quote_plus(query)}&cc=ID&setlang=id&format=rss",
        ]:
            if len(results) >= max_results:
                break
            try:
                resp = self.session.get(bing_url, timeout=12)
                if resp.status_code != 200:
                    continue
                _, items = _parse_rss(resp.content)
                for item in items[:max_results]:
                    title_el = item.find('title')
                    title = self.clean(title_el.text if title_el else '')
                    if not title:
                        continue
                    link = _rss_link(item)
                    desc_el = item.find('description')
                    desc = self.clean(desc_el.text if desc_el else '')
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)
                    source = 'News'
                    for s in ['detik','kompas','liputan6','cnn','bbc','reuters','tempo',
                              'antara','tribun','sindo','republika','okezone','jpnn','viva']:
                        if s in (link+title).lower():
                            source = s.capitalize()
                            break
                    results.append({
                        'platform': 'News Sites',
                        'title': title,
                        'content': desc[:300],
                        'url': link,
                        'date': self._parse_date(item.find('pubDate')),
                        'source': source,
                        'keyword': keyword,
                        'location': location,
                    })
            except Exception as e:
                self.update_status(f"[News Sites] Bing error: {str(e)[:40]}")

        # ── 2. Indonesian RSS feeds (flexible keyword match)
        if len(results) < max_results:
            for source_name, rss_url in self.ID_RSS:
                if len(results) >= max_results:
                    break
                try:
                    resp = self.session.get(rss_url, timeout=8)
                    if resp.status_code != 200:
                        continue
                    _, items = _parse_rss(resp.content)
                    for item in items[:80]:
                        title_el = item.find('title')
                        if not title_el:
                            continue
                        title = self.clean(title_el.text)
                        desc_el = item.find('description')
                        desc = self.clean(desc_el.text if desc_el else '')
                        if not self._kw_matches(keyword, title, desc):
                            continue
                        link = _rss_link(item)
                        if not link or link in seen_urls:
                            continue
                        seen_urls.add(link)
                        results.append({
                            'platform': 'News Sites',
                            'title': title,
                            'content': desc[:300],
                            'url': link,
                            'date': self._parse_date(item.find('pubDate')),
                            'source': source_name,
                            'keyword': keyword,
                            'location': location,
                        })
                        if len(results) >= max_results:
                            break
                except Exception:
                    continue

        self.update_status(f"[News Sites] {len(results)} artikel ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# Reddit — Public JSON API (no auth, works without API keys)
#          Key: MUST use non-browser User-Agent + fresh session
# ─────────────────────────────────────────────────────────────
class RedditScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Reddit] Mencari '{keyword}'...")
        results = []
        query = f"{keyword} {location}".strip()

        # Reddit blocks browser UAs and requires a bot/script UA
        # Use a completely fresh requests call (no session headers)
        reddit_headers = {
            'User-Agent': 'AlyxScraper/2.0 (research tool; +https://github.com/alyxscraper)',
            'Accept': 'application/json',
        }

        urls_to_try = [
            f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=new&limit={max_results}&type=link",
            f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=relevance&limit={max_results}",
            f"https://old.reddit.com/search.json?q={quote_plus(query)}&sort=new&limit={max_results}",
        ]

        network_blocked = False
        for url in urls_to_try:
            if results:
                break
            try:
                resp = requests.get(url, headers=reddit_headers, timeout=12)
                self.update_status(f"[Reddit] HTTP {resp.status_code}")

                if resp.status_code == 429:
                    self.update_status("[Reddit] Rate limited, menunggu 3s...")
                    time.sleep(3)
                    resp = requests.get(url, headers=reddit_headers, timeout=12)

                if resp.status_code != 200:
                    self.update_status(f"[Reddit] Gagal: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                children = data.get('data', {}).get('children', [])
                self.update_status(f"[Reddit] {len(children)} posts dari API")

                for child in children[:max_results]:
                    post = child.get('data', {})
                    if not post:
                        continue
                    created = datetime.utcfromtimestamp(post.get('created_utc', 0))
                    content = self.clean(post.get('selftext', ''))[:300]
                    if not content:
                        content = self.clean(post.get('title', ''))
                    title = self.clean(post.get('title', ''))
                    if not title:
                        continue
                    results.append({
                        'platform': 'Reddit',
                        'title': title,
                        'content': content,
                        'url': f"https://reddit.com{post.get('permalink', '')}",
                        'date': created.strftime('%Y-%m-%d %H:%M'),
                        'source': f"r/{post.get('subreddit', 'unknown')}",
                        'keyword': keyword,
                        'location': location,
                    })
            except Exception as e:
                err = str(e)
                self.update_status(f"[Reddit] Exception: {err[:60]}")
                # Detect network-level block (Max retries, Connection refused, etc.)
                if any(x in err for x in ('Max retries', 'Connection', 'RemoteDisconnected', 'timeout')):
                    network_blocked = True
                    break
                continue

        # Google fallback — used when network blocks Reddit OR no results
        if not results:
            if network_blocked:
                self.update_status("[Reddit] Koneksi ke Reddit diblokir — coba Google fallback...")
            else:
                self.update_status("[Reddit] Coba Google fallback...")
            results = self._google_fallback(query, 'Reddit', 'reddit.com', max_results)
            for r in results:
                r['keyword'] = keyword
                r['location'] = location

        self.update_status(f"[Reddit] {len(results)} posts ditemukan")
        return results


# ─────────────────────────────────────────────────────────────
# Kaskus — DuckDuckGo / Google search engine first
# NOTE: Modern Kaskus is a React SPA. requests.get() returns an empty
#       HTML shell with no thread content, so HTML parsing never works.
#       We skip straight to search-engine indexing which DOES have the
#       content cached/indexed.
# ─────────────────────────────────────────────────────────────
class KaskusScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Kaskus] Mencari '{keyword}'...")
        query = f"{keyword} {location}".strip()
        results = []

        # Strategy 1: DuckDuckGo (usually works without rate-limiting)
        self.update_status("[Kaskus] Coba DuckDuckGo (Kaskus React SPA)...")
        results = self._ddg_fallback(query, 'Kaskus', 'kaskus.co.id', max_results)
        if results:
            self.update_status(f"[Kaskus] DuckDuckGo: {len(results)} hasil")

        # Strategy 2: Google fallback
        if not results:
            self.update_status("[Kaskus] Coba Google fallback...")
            results = self._google_fallback(query, 'Kaskus', 'kaskus.co.id', max_results)
            if results:
                self.update_status(f"[Kaskus] Google: {len(results)} hasil")

        for r in results:
            r['keyword'] = keyword
            r['location'] = location

        self.update_status(f"[Kaskus] {len(results)} thread ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# X/Twitter — Nitter → twikit (if enabled) → Google fallback
# ─────────────────────────────────────────────────────────────
class TwitterScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[X/Twitter] Mencari '{keyword}'...")
        results = []
        try:
            cfg = load_twitter_config()
            use_twikit = cfg.get('use_twikit', False)
            nitter_instances = cfg.get('nitter_instances', _DEFAULT_NITTER) or _DEFAULT_NITTER

            if use_twikit:
                try:
                    results = self._scrape_twikit(keyword, location, max_results)
                    if results:
                        self.update_status(f"[X/Twitter] twikit: {len(results)} tweets")
                except Exception as e:
                    self.update_status(f"[X/Twitter] twikit error: {str(e)[:50]}")

            if not results:
                results = self._scrape_nitter(keyword, location, max_results, nitter_instances)

            if not results:
                self.update_status("[X/Twitter] Coba DuckDuckGo fallback...")
                results = self._ddg_fallback(
                    f"{keyword} {location}".strip(), 'X/Twitter', 'x.com', max_results
                )
                for r in results:
                    r['keyword'] = keyword
                    r['location'] = location

            if not results:
                self.update_status("[X/Twitter] Coba Google fallback...")
                results = self._google_fallback(
                    f"{keyword} {location}".strip(), 'X/Twitter', 'x.com', max_results
                )
                for r in results:
                    r['keyword'] = keyword
                    r['location'] = location

        except Exception as e:
            self.update_status(f"[X/Twitter] Error: {str(e)[:60]}")

        self.update_status(f"[X/Twitter] {len(results)} tweets ditemukan")
        return results

    def _scrape_nitter(self, keyword, location, max_results, nitter_instances=None):
        results = []
        instances = list(nitter_instances or _DEFAULT_NITTER)
        query = f"{keyword} {location}".strip()

        for instance in instances:
            try:
                url = f"{instance}/search?f=tweets&q={quote_plus(query)}"
                resp = self.session.get(url, timeout=12)
                self.update_status(f"[X/Twitter] Nitter {instance}: HTTP {resp.status_code}")
                if resp.status_code != 200:
                    continue

                html = resp.text
                # Quick sanity check: a working Nitter page contains at least one of these
                if not any(marker in html for marker in
                           ('timeline-item', 'tweet-content', 'tweet-body',
                            'nitter', 'tweet-date', 'tweet-link')):
                    self.update_status(f"[X/Twitter] Nitter {instance}: bukan halaman tweet")
                    continue

                soup = BeautifulSoup(resp.content, 'html.parser')

                # Multiple selector strategies for different Nitter versions
                tweet_containers = (
                    soup.select('.timeline-item') or
                    soup.select('div.tweet-body') or
                    soup.select('article') or
                    soup.select('[class*="tweet"]')
                )
                if not tweet_containers:
                    continue

                for tweet in tweet_containers[:max_results]:
                    # Content
                    content_el = (
                        tweet.select_one('.tweet-content') or
                        tweet.select_one('.tweet-body') or
                        tweet.select_one('p') or
                        tweet.select_one('[class*="content"]')
                    )
                    content = self.clean(content_el.get_text()) if content_el else ''

                    # Username
                    username_el = (
                        tweet.select_one('.username') or
                        tweet.select_one('[class*="username"]') or
                        tweet.select_one('a[href^="/"]')
                    )
                    username = ''
                    if username_el:
                        username = self.clean(username_el.get_text()).lstrip('@')

                    # Link to original tweet
                    link = ''
                    date_el = tweet.select_one('.tweet-date a') or tweet.select_one('a.tweet-link')
                    if date_el and date_el.get('href'):
                        href = date_el['href']
                        # Convert Nitter-relative path to x.com URL
                        if href.startswith('/'):
                            link = f"https://x.com{href}"
                        elif 'twitter.com' in href or 'x.com' in href:
                            link = href.replace('twitter.com', 'x.com')

                    # Date
                    date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                    if date_el:
                        title_attr = date_el.get('title', '')
                        if title_attr:
                            try:
                                dt = datetime.strptime(title_attr[:19], '%Y-%m-%d %H:%M:%S')
                                date_str = dt.strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                pass

                    if content and len(content) > 5:
                        results.append({
                            'platform': 'X/Twitter',
                            'title': f"@{username}: {content[:80]}" if username else content[:80],
                            'content': content[:300],
                            'url': link,
                            'date': date_str,
                            'source': f"@{username}" if username else 'Nitter',
                            'keyword': keyword,
                            'location': location,
                        })

                if results:
                    self.update_status(f"[X/Twitter] Nitter OK ({instance}): {len(results)} tweets")
                    break
            except Exception as ex:
                self.update_status(f"[X/Twitter] Nitter {instance} error: {str(ex)[:40]}")
                continue

        return results

    def _scrape_twikit(self, keyword, location, max_results):
        """Direct X/Twitter internal API — no twikit, no KEY_BYTE.
        Uses the adaptive search endpoint the browser itself uses."""
        cookies_path = os.path.join(os.path.dirname(CONFIG_PATH), 'twitter_cookies.json')
        if not os.path.exists(cookies_path):
            raise FileNotFoundError("twitter_cookies.json not found")

        with open(cookies_path) as f:
            raw = json.load(f)

        # Support simple dict {"auth_token": "..."} or httpx list [{name,value,...}]
        if isinstance(raw, list):
            cookies = {c['name']: c['value'] for c in raw if 'name' in c and 'value' in c}
        else:
            cookies = raw

        auth_token = cookies.get('auth_token', '')
        ct0        = cookies.get('ct0', '')
        if not auth_token or not ct0:
            raise ValueError("auth_token atau ct0 tidak ditemukan di twitter_cookies.json")

        # Public bearer token (embedded in Twitter/X web app JS — stable for years)
        BEARER = (
            'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs'
            '%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
        )

        query_str = f"{keyword} {location}".strip()

        # Set cookies on ALL relevant domains (twitter.com AND x.com both needed)
        session = requests.Session()
        for domain in ('.twitter.com', 'twitter.com', '.x.com', 'x.com'):
            for name, value in cookies.items():
                session.cookies.set(name, value, domain=domain)

        base_headers = {
            'Authorization':           f'Bearer {BEARER}',
            'x-csrf-token':            ct0,
            'User-Agent':              BROWSER_UA,
            'Accept':                  '*/*',
            'Accept-Language':         'en-US,en;q=0.9',
            'x-twitter-active-user':   'yes',
            'x-twitter-client-language': 'en',
            'x-twitter-auth-type':     'OAuth2Session',
        }

        params = {
            'q':                query_str,
            'count':            str(min(max_results, 20)),
            'tweet_mode':       'extended',
            'result_type':      'recent',
            'include_entities': '1',
        }

        # Try x.com first (rebranded), then twitter.com as backup
        endpoints = [
            ('https://x.com/i/api/2/search/adaptive.json',
             {**base_headers, 'Referer': 'https://x.com/search'}),
            ('https://twitter.com/i/api/2/search/adaptive.json',
             {**base_headers, 'Referer': 'https://twitter.com/search'}),
        ]

        data = None
        last_err = ''
        for url, hdrs in endpoints:
            try:
                resp = session.get(url, headers=hdrs, params=params,
                                   timeout=15, allow_redirects=True)
                body = resp.text.strip() if resp.text else ''
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    continue
                if not body or body[0] not in ('{', '['):
                    # Got HTML redirect / login page — not JSON
                    last_err = f"Non-JSON response ({body[:60]!r})"
                    continue
                data = resp.json()
                break
            except Exception as ex:
                last_err = str(ex)
                continue

        if data is None:
            # Empty body + backoff header = cookies expired
            if 'backoff' in last_err.lower() or 'Non-JSON' in last_err:
                raise Exception(
                    "Cookie expired - buka x.com, F12 -> Application -> Cookies, "
                    "salin auth_token & ct0 baru ke Admin -> X/Twitter Settings"
                )
            raise Exception(last_err or "Semua endpoint Twitter gagal")

        tweets_obj = data.get('globalObjects', {}).get('tweets', {})
        users_obj  = data.get('globalObjects', {}).get('users',  {})

        # Collect tweet IDs in timeline order
        ordered_ids = []
        for instr in data.get('timeline', {}).get('instructions', []):
            for entry in instr.get('addEntries', {}).get('entries', []):
                tid = (entry.get('content', {})
                           .get('item', {})
                           .get('content', {})
                           .get('tweet', {})
                           .get('id'))
                if tid:
                    ordered_ids.append(str(tid))
        if not ordered_ids:
            ordered_ids = list(tweets_obj.keys())

        results = []
        for tid in ordered_ids[:max_results]:
            tw = tweets_obj.get(str(tid))
            if not tw:
                continue
            uid         = str(tw.get('user_id_str', ''))
            user        = users_obj.get(uid, {})
            screen_name = user.get('screen_name', 'unknown')
            text        = tw.get('full_text', '') or tw.get('text', '')
            created_at  = tw.get('created_at', '')
            try:
                dt       = datetime.strptime(created_at, '%a %b %d %H:%M:%S +0000 %Y')
                date_str = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            if text:
                results.append({
                    'platform': 'X/Twitter',
                    'title':    f"@{screen_name}: {text[:80]}",
                    'content':  text[:300],
                    'url':      f"https://x.com/{screen_name}/status/{tid}",
                    'date':     date_str,
                    'source':   f"@{screen_name}",
                    'keyword':  keyword,
                    'location': location,
                })
        return results


# ─────────────────────────────────────────────────────────────
# Facebook — mbasic search → known pages via get_posts → Google fallback
# NOTE: facebook-scraper's get_posts() scrapes by PAGE NAME, not keyword.
#       We use mbasic.facebook.com (simpler HTML) for keyword search first,
#       then scrape known relevant public pages, then fall back to Google.
# ─────────────────────────────────────────────────────────────

# Popular Indonesian & international news/topic pages on Facebook
# Used when searching for keyword-matching posts
_FB_NEWS_PAGES = [
    'detikcom', 'kompascom', 'tribunnews', 'liputan6', 'CNNIndonesia',
    'metrotvnews', 'tempoco', 'BBCIndonesia', 'voaindonesia', 'antaranews',
    'okezone', 'sindonews', 'jawapos', 'suaracom', 'katadataid',
    'BBCNews', 'CNN', 'AlJazeeraEnglish', 'reuters',
]

class FacebookScraper(BaseScraper):

    def _try_mbasic_search(self, keyword, max_results):
        """Scrape Facebook posts via mbasic.facebook.com — simpler HTML, no JS required."""
        results = []
        try:
            url = (
                f"https://mbasic.facebook.com/search/posts/"
                f"?q={quote_plus(keyword)}&source=filter&isTrending=0"
            )
            headers = {
                'user-agent': (
                    'Mozilla/5.0 (Linux; Android 10; K) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/114.0.0.0 Mobile Safari/537.36'
                ),
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'id-ID,id;q=0.9,en;q=0.8',
                'referer': 'https://mbasic.facebook.com/',
            }
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            self.update_status(f"[Facebook] mbasic HTTP {resp.status_code}")

            # If redirected to login, bail
            if 'login' in resp.url or resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.content, 'html.parser')

            # mbasic post structure: each post is in a <div> with data-ft attribute
            # or inside <article> tags
            post_containers = (
                soup.find_all('div', attrs={'data-ft': True}) or
                soup.find_all('article') or
                soup.find_all('div', class_=re.compile(r'story|post|feed', re.I))
            )

            for container in post_containers[:max_results * 2]:
                # Extract text
                text_el = container.find(['p', 'div', 'span'],
                                         class_=re.compile(r'story_body|_5rgt|message', re.I))
                if not text_el:
                    text_el = container
                text = self.clean(text_el.get_text(separator=' '))
                if len(text) < 15:
                    continue

                # Extract link
                link = ''
                for a in container.find_all('a', href=True):
                    href = a['href']
                    if '/story.php' in href or '/permalink/' in href or '/posts/' in href:
                        # Convert mbasic URL to regular Facebook URL
                        link = ('https://www.facebook.com' + href.split('?')[0]
                                if href.startswith('/') else href)
                        break

                # Extract date
                date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                abbr = container.find('abbr')
                if abbr:
                    date_str = abbr.get_text(strip=True) or date_str

                # Extract author
                author = 'Facebook'
                author_el = container.find('h3') or container.find('strong')
                if author_el:
                    author = author_el.get_text(strip=True)

                results.append({
                    'platform': 'Facebook',
                    'title': text[:120],
                    'content': text[:400],
                    'url': link,
                    'date': date_str,
                    'source': author,
                    'keyword': keyword,
                    'location': '',
                })
                if len(results) >= max_results:
                    break

        except Exception as e:
            self.update_status(f"[Facebook] mbasic error: {str(e)[:60]}")
        return results

    def _try_page_scraping(self, keyword, max_results):
        """Use facebook-scraper's get_posts() correctly: scrape known news pages,
        then filter posts containing the keyword."""
        results = []
        try:
            from facebook_scraper import get_posts
        except ImportError:
            self.update_status("[Facebook] facebook-scraper tidak terinstall — jalankan pip install facebook-scraper")
            return results

        kw_lower = keyword.lower()
        # Shuffle so we don't always hit the same pages
        pages_to_try = _FB_NEWS_PAGES[:]
        random.shuffle(pages_to_try)

        for page_name in pages_to_try:
            if len(results) >= max_results:
                break
            try:
                self.update_status(f"[Facebook] Scraping page @{page_name}...")
                for post in get_posts(
                    page_name, pages=1,
                    options={
                        'allow_extra_requests': False,
                        'posts_per_page': 10,
                        'comments': False,
                        'reactions': False,
                    }
                ):
                    text = (post.get('post_text') or post.get('text') or '').strip()
                    if not text or len(text) < 10:
                        continue
                    # Filter: keyword must appear in post text
                    if not any(w in text.lower() for w in kw_lower.split()):
                        continue

                    post_time = post.get('time')
                    date_str = (post_time.strftime('%Y-%m-%d %H:%M')
                                if post_time else datetime.now().strftime('%Y-%m-%d %H:%M'))
                    results.append({
                        'platform': 'Facebook',
                        'title': text[:120],
                        'content': text[:400],
                        'url': post.get('post_url', ''),
                        'date': date_str,
                        'source': post.get('username') or page_name,
                        'keyword': keyword,
                        'location': '',
                    })
                    if len(results) >= max_results:
                        break
            except Exception:
                # Page may be private/restricted — silently skip
                continue

        return results

    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Facebook] Mencari '{keyword}'...")
        query = f"{keyword} {location}".strip()
        results = []

        # Attempt 1: mbasic.facebook.com search (no login, simple HTML)
        results = self._try_mbasic_search(query, max_results)
        if results:
            self.update_status(f"[Facebook] mbasic: {len(results)} posts")

        # Attempt 2: Scrape known news pages, filter by keyword
        if not results:
            results = self._try_page_scraping(keyword, max_results)
            if results:
                self.update_status(f"[Facebook] Page scraping: {len(results)} posts")

        # Attempt 3: Google fallback (site:facebook.com)
        if not results:
            self.update_status("[Facebook] Coba Google fallback...")
            results = self._google_fallback(query, 'Facebook', 'facebook.com', max_results)
            for r in results:
                r['keyword'] = keyword
                r['location'] = location

        self.update_status(f"[Facebook] {len(results)} posts ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# Threads — Internal GraphQL API → embedded JSON → Google fallback
# NOTE: Threads is JS-rendered. We try their internal API first.
# ─────────────────────────────────────────────────────────────
class ThreadsScraper(BaseScraper):

    _THREADS_APP_ID = '238260118697367'

    def _threads_headers(self, referer='https://www.threads.net/'):
        return {
            'user-agent': BROWSER_UA,
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://www.threads.net',
            'referer': referer,
            'x-ig-app-id': self._THREADS_APP_ID,
            'x-requested-with': 'XMLHttpRequest',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
        }

    def _extract_lsd(self, html):
        """Extract lsd token from Threads page (needed for GraphQL requests)."""
        m = re.search(r'"LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'lsd["\s:]+([A-Za-z0-9_-]{10,})', html)
        return m.group(1) if m else None

    def _try_graphql_search(self, keyword, max_results):
        """Hit Threads GraphQL search endpoint — requires lsd token from page."""
        results = []
        try:
            # Step 1: get lsd token from search page
            page_url = f"https://www.threads.net/search?q={quote_plus(keyword)}&serp_type=default"
            hdrs = {
                'user-agent': BROWSER_UA,
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'referer': 'https://www.threads.net/',
            }
            page_resp = requests.get(page_url, headers=hdrs, timeout=15)
            if page_resp.status_code != 200:
                self.update_status(f"[Threads] Page HTTP {page_resp.status_code}")
                return results

            html = page_resp.text
            lsd = self._extract_lsd(html)

            # Step 2: try extracting embedded JSON from SSR data
            # Threads embeds search results as JSON in <script> tags
            json_results = self._extract_ssr_posts(html, keyword, max_results)
            if json_results:
                self.update_status(f"[Threads] SSR JSON: {len(json_results)} posts")
                return json_results

            # Step 3: GraphQL API call
            if lsd:
                gql_headers = self._threads_headers(referer=page_url)
                gql_headers['x-fb-lsd'] = lsd
                gql_headers['content-type'] = 'application/x-www-form-urlencoded'

                # Known working doc_id for Threads search (may change over time)
                for doc_id in ['6232751443445612', '7189807164445839', '6354798414579755']:
                    try:
                        payload = (
                            f"variables={quote_plus(json.dumps({'q': keyword, 'count': max_results, 'serp_type': 'DEFAULT'}))}"
                            f"&doc_id={doc_id}"
                        )
                        gql_resp = requests.post(
                            'https://www.threads.net/api/graphql',
                            headers=gql_headers, data=payload, timeout=15
                        )
                        if gql_resp.status_code == 200:
                            gql_data = gql_resp.json()
                            posts = self._parse_graphql_response(gql_data, keyword)
                            if posts:
                                self.update_status(f"[Threads] GraphQL: {len(posts)} posts")
                                return posts[:max_results]
                    except Exception:
                        continue
        except Exception as e:
            self.update_status(f"[Threads] API error: {str(e)[:60]}")
        return results

    def _extract_ssr_posts(self, html, keyword, max_results):
        """Extract posts from Threads' server-side rendered JSON blobs in <script> tags."""
        results = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup.find_all('script', type=re.compile(r'application/json|__SSR')):
                raw = script.string or ''
                if not raw or len(raw) < 50:
                    continue
                try:
                    data = json.loads(raw)
                    posts = self._walk_for_posts(data)
                    for post in posts[:max_results]:
                        text = post.get('text', '') or post.get('caption', '')
                        username = post.get('username', '') or post.get('user', {}).get('username', '')
                        pk = post.get('pk') or post.get('id', '')
                        url = f"https://www.threads.net/@{username}/post/{pk}" if username and pk else ''
                        created = post.get('taken_at') or post.get('created_at', '')
                        if created and str(created).isdigit():
                            try:
                                created = datetime.fromtimestamp(int(created)).strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                created = str(created)
                        if text and len(text) > 5:
                            results.append({
                                'platform': 'Threads',
                                'title': text[:120],
                                'content': text[:400],
                                'url': url,
                                'date': created or datetime.now().strftime('%Y-%m-%d %H:%M'),
                                'source': f'@{username}' if username else 'Threads',
                                'keyword': keyword,
                                'location': '',
                            })
                    if results:
                        return results
                except (json.JSONDecodeError, TypeError):
                    continue
        except Exception:
            pass
        return results

    def _walk_for_posts(self, obj, depth=0):
        """Recursively find post-like objects in a nested JSON structure."""
        if depth > 12:
            return []
        posts = []
        if isinstance(obj, dict):
            # Looks like a Threads post
            if ('text' in obj or 'caption' in obj) and ('pk' in obj or 'id' in obj) and 'username' in obj:
                posts.append(obj)
            else:
                for v in obj.values():
                    posts.extend(self._walk_for_posts(v, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                posts.extend(self._walk_for_posts(item, depth + 1))
        return posts

    def _parse_graphql_response(self, data, keyword):
        """Parse Threads GraphQL API response into our standard format."""
        results = []
        try:
            edges = (data.get('data') or {})
            # Walk down typical Threads GraphQL structure
            posts = self._walk_for_posts(edges)
            for post in posts:
                text = post.get('text', '') or ''
                username = post.get('username', '') or ''
                pk = post.get('pk') or post.get('id', '')
                url = f"https://www.threads.net/@{username}/post/{pk}" if username and pk else ''
                created = post.get('taken_at') or post.get('created_at', '')
                if created and str(created).isdigit():
                    try:
                        created = datetime.fromtimestamp(int(created)).strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        created = str(created)
                if text:
                    results.append({
                        'platform': 'Threads',
                        'title': text[:120],
                        'content': text[:400],
                        'url': url,
                        'date': created or datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'source': f'@{username}' if username else 'Threads',
                        'keyword': keyword,
                        'location': '',
                    })
        except Exception:
            pass
        return results

    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Threads] Mencari '{keyword}'...")
        query = f"{keyword} {location}".strip()
        results = []

        # Attempt 1: Internal Threads API (GraphQL + SSR extraction)
        results = self._try_graphql_search(query, max_results)

        # Attempt 2: Google fallback (site:threads.net)
        if not results:
            self.update_status("[Threads] Coba Google fallback (site:threads.net)...")
            results = self._google_fallback(query, 'Threads', 'threads.net', max_results)
            for r in results:
                r['keyword'] = keyword
                r['location'] = location

        self.update_status(f"[Threads] {len(results)} posts ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# Quora — Mobile site → embedded JSON → Quora GraphQL → Google fallback
# NOTE: Quora is JS-rendered. m.quora.com (mobile) has simpler HTML.
#       adrian-dip/quora-scraper uses Selenium + scrapes by topic (not keyword)
#       so it's not suitable for real-time keyword search here.
# ─────────────────────────────────────────────────────────────
class QuoraScraper(BaseScraper):

    _QUORA_HEADERS = {
        'user-agent': (
            'Mozilla/5.0 (Linux; Android 11; Pixel 5) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/114.0.0.0 Mobile Safari/537.36'
        ),
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'referer': 'https://www.quora.com/',
    }

    def _parse_quora_html(self, html, keyword, location, max_results):
        """Extract questions/answers from Quora page HTML or embedded JSON."""
        results = []
        seen = set()
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy A: Extract from embedded JSON blobs in <script> tags
        for script in soup.find_all('script'):
            src = script.string or ''
            if not src or len(src) < 100:
                continue
            # Look for question text + URL patterns in JSON
            questions_found = re.findall(
                r'"question":\s*\{"url"\s*:\s*"([^"]+)"[^}]*"title"\s*:\s*"([^"]+)"', src
            )
            for url_part, title in questions_found:
                if not title or len(title) < 8:
                    continue
                title = title.replace('\\u2019', "'").replace('\\n', ' ').strip()
                full_url = f"https://www.quora.com{url_part}" if url_part.startswith('/') else url_part
                if full_url in seen:
                    continue
                seen.add(full_url)
                results.append({
                    'platform': 'Quora',
                    'title': title[:150],
                    'content': title[:300],
                    'url': full_url,
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'source': 'Quora',
                    'keyword': keyword,
                    'location': location,
                })
                if len(results) >= max_results:
                    return results

        if results:
            return results

        # Strategy B: Parse anchor tags (works on mobile/simplified pages)
        skip_patterns = ['/profile/', '/topic/', '/search', '/login', '/sitemap',
                         'javascript:', '#', '/about', '/careers', '/press']
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            txt = self.clean(a.get_text(separator=' '))
            if not txt or len(txt) < 12:
                continue
            if any(p in href for p in skip_patterns):
                continue
            # Quora questions typically have format /What-is-... or /How-does-...
            if not re.search(r'/[A-Z][^/?#]{8,}', href):
                continue
            full_url = f"https://www.quora.com{href}" if href.startswith('/') else href
            if 'quora.com' not in full_url or full_url in seen:
                continue
            seen.add(full_url)
            results.append({
                'platform': 'Quora',
                'title': txt[:150],
                'content': txt[:300],
                'url': full_url,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'source': 'Quora',
                'keyword': keyword,
                'location': location,
            })
            if len(results) >= max_results:
                break

        return results

    def _try_mobile(self, query, keyword, location, max_results):
        """Try m.quora.com — mobile version has simpler HTML structure."""
        try:
            url = f"https://www.quora.com/search?q={quote_plus(query)}&type=question"
            resp = requests.get(url, headers=self._QUORA_HEADERS, timeout=15)
            self.update_status(f"[Quora] Mobile HTTP {resp.status_code}")
            if resp.status_code == 200 and 'quora' in resp.url:
                results = self._parse_quora_html(resp.text, keyword, location, max_results)
                if results:
                    return results

            # Try the profile-less search endpoint
            url2 = f"https://www.quora.com/search?q={quote_plus(query)}"
            resp2 = requests.get(url2, headers=self._QUORA_HEADERS, timeout=15)
            if resp2.status_code == 200:
                return self._parse_quora_html(resp2.text, keyword, location, max_results)
        except Exception as e:
            self.update_status(f"[Quora] Mobile error: {str(e)[:50]}")
        return []

    def _try_quora_graphql(self, keyword, max_results):
        """Try Quora's internal GraphQL API for search."""
        results = []
        try:
            # Quora uses GraphQL — this endpoint sometimes works without auth
            headers = {
                **self._QUORA_HEADERS,
                'content-type': 'application/json',
                'quora-formkey': '',
            }
            # Try fetching the search page first to get formkey
            page_resp = requests.get(
                f'https://www.quora.com/search?q={quote_plus(keyword)}',
                headers=self._QUORA_HEADERS, timeout=12
            )
            if page_resp.status_code != 200:
                return results

            # Extract formkey from page
            formkey_m = re.search(r'"formkey"\s*:\s*"([^"]+)"', page_resp.text)
            if not formkey_m:
                return results
            formkey = formkey_m.group(1)

            gql_headers = {**headers, 'quora-formkey': formkey}
            payload = {
                "queryName": "SearchPagedListQuery",
                "variables": {
                    "query": keyword,
                    "resultType": "question",
                    "first": max_results,
                },
                "extensions": {"hash": ""},
            }
            gql_resp = requests.post(
                'https://www.quora.com/graphql/gql_para_public',
                json=payload, headers=gql_headers, timeout=12
            )
            if gql_resp.status_code == 200:
                data = gql_resp.json()
                edges = (
                    data.get('data', {})
                    .get('searchConnection', {})
                    .get('edges', [])
                )
                for edge in edges[:max_results]:
                    node = edge.get('node', {})
                    q = node.get('question', node)
                    title = q.get('title', '') or q.get('text', '')
                    url = q.get('url', '')
                    if title and len(title) > 5:
                        results.append({
                            'platform': 'Quora',
                            'title': title[:150],
                            'content': title[:300],
                            'url': f"https://www.quora.com{url}" if url.startswith('/') else url,
                            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'source': 'Quora',
                            'keyword': keyword,
                            'location': '',
                        })
        except Exception as e:
            self.update_status(f"[Quora] GraphQL error: {str(e)[:50]}")
        return results

    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Quora] Mencari '{keyword}'...")
        query = f"{keyword} {location}".strip()
        results = []

        # Attempt 1: Mobile/simplified Quora page
        results = self._try_mobile(query, keyword, location, max_results)
        if results:
            self.update_status(f"[Quora] Mobile: {len(results)} results")

        # Attempt 2: Quora internal GraphQL
        if not results:
            results = self._try_quora_graphql(keyword, max_results)
            if results:
                self.update_status(f"[Quora] GraphQL: {len(results)} results")

        # Attempt 3: DuckDuckGo (site:quora.com) — avoids Google rate-limits
        if not results:
            self.update_status("[Quora] Coba DuckDuckGo fallback...")
            results = self._ddg_fallback(query, 'Quora', 'quora.com', max_results)
            if results:
                self.update_status(f"[Quora] DuckDuckGo: {len(results)} results")

        # Attempt 4: Google fallback (site:quora.com)
        if not results:
            self.update_status("[Quora] Coba Google fallback...")
            results = self._google_fallback(query, 'Quora', 'quora.com', max_results)

        for r in results:
            r['keyword'] = keyword
            r['location'] = location

        self.update_status(f"[Quora] {len(results)} pertanyaan ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# Instagram — Private API → instaloader → HTML → Google fallback
# NOTE: Instagram requires login for most content since 2023.
# ─────────────────────────────────────────────────────────────
class InstagramScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Instagram] Mencari '{keyword}'...")
        results = []
        query = f"{keyword} {location}".strip()
        tag = re.sub(r'[^a-zA-Z0-9]', '', keyword.lower())

        # Attempt 1: Instagram hashtag sections API
        try:
            headers = {
                'User-Agent': BROWSER_UA,
                'X-IG-App-ID': '936619743392459',
                'Accept': '*/*',
                'Referer': f'https://www.instagram.com/explore/tags/{tag}/',
            }
            url = f"https://i.instagram.com/api/v1/tags/{tag}/sections/?count=25&tab=recent"
            resp = self.session.get(url, headers=headers, timeout=12)
            self.update_status(f"[Instagram] Hashtag API HTTP {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                for section in data.get('sections', []):
                    for m in section.get('layout_content', {}).get('medias', []):
                        media = m.get('media', {})
                        caption_obj = media.get('caption') or {}
                        caption = caption_obj.get('text', '') if isinstance(caption_obj, dict) else ''
                        user = (media.get('user') or {}).get('username', 'unknown')
                        code = media.get('code', '')
                        if not code:
                            continue
                        results.append({
                            'platform': 'Instagram',
                            'title': f"@{user}: {caption[:80]}" if caption else f"@{user} #{tag}",
                            'content': caption[:300] or f"#{tag}",
                            'url': f"https://www.instagram.com/p/{code}/",
                            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'source': f"@{user}",
                            'keyword': keyword,
                            'location': location,
                        })
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

        # Attempt 2: instaloader (with saved session if available)
        if not results:
            try:
                import instaloader
                L = instaloader.Instaloader()

                # Load saved session from config if available
                session_loaded = False
                try:
                    with open(CONFIG_PATH) as f:
                        cfg = json.load(f)
                    ig_cfg = cfg.get('instagram', {})
                    ig_user = ig_cfg.get('username', '')
                    ig_session = ig_cfg.get('session_file', '')
                    if ig_user and ig_session and os.path.exists(ig_session):
                        L.load_session_from_file(ig_user, filename=ig_session)
                        session_loaded = True
                        self.update_status(f"[Instagram] Session loaded: @{ig_user}")
                except Exception:
                    pass

                ht = instaloader.Hashtag.from_name(L.context, tag)
                count_before = len(results)

                # Wrap each iteration step so a KeyError('more_available') or any
                # other Instagram API-format change only stops iteration, doesn't crash.
                post_gen = ht.get_posts()
                while len(results) < max_results:
                    try:
                        post = next(post_gen)
                    except StopIteration:
                        break
                    except KeyError as ke:
                        # Instagram changed API response format — partial results OK
                        self.update_status(
                            f"[Instagram] API berubah (KeyError: {ke}), hasil parsial"
                        )
                        break
                    except Exception as iter_e:
                        self.update_status(
                            f"[Instagram] Iterator error: {str(iter_e)[:60]}"
                        )
                        break
                    try:
                        caption = post.caption or ''
                        shortcode = post.shortcode
                        owner = post.owner_username
                        date_str = post.date_utc.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        continue
                    results.append({
                        'platform': 'Instagram',
                        'title': f"@{owner}: {caption[:80]}" if caption else f"@{owner} #{tag}",
                        'content': caption[:300] or f"#{tag}",
                        'url': f"https://www.instagram.com/p/{shortcode}/",
                        'date': date_str,
                        'source': f"@{owner}",
                        'keyword': keyword,
                        'location': location,
                    })

                new_count = len(results) - count_before
                mode = "with login" if session_loaded else "anonymous"
                self.update_status(f"[Instagram] instaloader ({mode}): {new_count} posts")
            except ImportError:
                self.update_status("[Instagram] instaloader tidak terinstall")
            except Exception as e:
                self.update_status(f"[Instagram] instaloader error: {str(e)[:80]}")

        # Attempt 3: Instagram hashtag sections API with session cookie (if saved)
        if not results:
            try:
                ig_session_id = ''
                with open(CONFIG_PATH) as f:
                    ig_session_id = json.load(f).get('instagram', {}).get('session_id', '')
                if ig_session_id:
                    headers_ig = {
                        'User-Agent': BROWSER_UA,
                        'X-IG-App-ID': '936619743392459',
                        'Accept': '*/*',
                        'Referer': f'https://www.instagram.com/explore/tags/{tag}/',
                        'Cookie': f'sessionid={ig_session_id}',
                    }
                    url2 = (
                        f"https://i.instagram.com/api/v1/tags/{tag}/sections/"
                        f"?count=25&tab=recent&include_persistent=0"
                    )
                    r2 = self.session.get(url2, headers=headers_ig, timeout=12)
                    if r2.status_code == 200:
                        data2 = r2.json()
                        for section in data2.get('sections', []):
                            for m in section.get('layout_content', {}).get('medias', []):
                                media = m.get('media', {})
                                cap_obj = media.get('caption') or {}
                                caption = cap_obj.get('text', '') if isinstance(cap_obj, dict) else ''
                                user = (media.get('user') or {}).get('username', 'unknown')
                                code = media.get('code', '')
                                if not code:
                                    continue
                                results.append({
                                    'platform': 'Instagram',
                                    'title': f"@{user}: {caption[:80]}" if caption else f"@{user} #{tag}",
                                    'content': caption[:300] or f"#{tag}",
                                    'url': f"https://www.instagram.com/p/{code}/",
                                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                    'source': f"@{user}",
                                    'keyword': keyword,
                                    'location': location,
                                })
                                if len(results) >= max_results:
                                    break
                            if len(results) >= max_results:
                                break
                        if results:
                            self.update_status(f"[Instagram] Session API: {len(results)} posts")
            except Exception:
                pass

        # Attempt 4: DuckDuckGo then Google fallback
        if not results:
            self.update_status("[Instagram] Coba DuckDuckGo fallback...")
            results = self._ddg_fallback(query, 'Instagram', 'instagram.com', max_results)
        if not results:
            self.update_status("[Instagram] Coba Google fallback...")
            results = self._google_fallback(query, 'Instagram', 'instagram.com', max_results)
        for r in results:
            r['keyword'] = keyword
            r['location'] = location

        self.update_status(f"[Instagram] {len(results)} posts ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# Scraper registry
# ─────────────────────────────────────────────────────────────
SCRAPERS = {
    'Google News': GoogleNewsScraper,
    'News Sites':  NewsSitesScraper,
    'Reddit':      RedditScraper,
    'Kaskus':      KaskusScraper,
    'X/Twitter':   TwitterScraper,
    'Facebook':    FacebookScraper,
    'Threads':     ThreadsScraper,
    'Quora':       QuoraScraper,
    'Instagram':   InstagramScraper,
}


class UnifiedScraper:
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.results = []

    def scrape_keywords(self, keywords, locations, selected_platforms):
        self.results = []
        total_kw = len(keywords)
        total_loc = len(locations)
        platform_counts = {}

        for ki, keyword in enumerate(keywords, 1):
            for li, location in enumerate(locations, 1):
                loc_label = f" [{location}]" if location else ""
                if self.gui_callback:
                    self.gui_callback(
                        f"Keyword {ki}/{total_kw}: '{keyword}'{loc_label} — "
                        f"memproses {len(selected_platforms)} platform..."
                    )
                for platform_name in selected_platforms:
                    scraper_cls = SCRAPERS.get(platform_name)
                    if not scraper_cls:
                        continue
                    try:
                        scraper = scraper_cls(gui_callback=self.gui_callback)
                        platform_results = scraper.scrape(keyword, location)
                        count = len(platform_results)
                        platform_counts[platform_name] = platform_counts.get(platform_name, 0) + count
                        for r in platform_results:
                            r['id'] = len(self.results) + 1
                            self.results.append(r)
                        if self.gui_callback:
                            self.gui_callback(
                                f"✓ {platform_name}: {count} hasil | Total: {len(self.results)}"
                            )
                        scraper.delay(0.4, 1.0)
                    except Exception as e:
                        platform_counts[platform_name] = platform_counts.get(platform_name, 0)
                        if self.gui_callback:
                            self.gui_callback(
                                f"✗ {platform_name}: {str(e)[:60]}"
                            )

        # Final summary with per-platform breakdown
        summary = " | ".join(f"{p}: {c}" for p, c in platform_counts.items())
        if self.gui_callback:
            self.gui_callback(
                f"Selesai! {len(self.results)} hasil — {summary}"
            )
        return self.results
