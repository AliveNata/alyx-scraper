import requests
from bs4 import BeautifulSoup
import json
import time
import random
import re
import os
from datetime import datetime
from urllib.parse import quote_plus, quote, urljoin
import xml.etree.ElementTree as ET

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)


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
            # Advertise only what requests can decode; 'br' (Brotli) needs the
            # brotli package or responses come back as undecodable bytes.
            'Accept-Encoding': 'gzip, deflate',
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

    def _ddg_fallback(self, query, platform, site_filter, max_results, keyword=None):
        """DuckDuckGo HTML search — usually bypasses rate-limits that block Google.
        When `keyword` is given, drop results that don't actually mention it
        (search engines rank navigational/homepage pages that aren't relevant)."""
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
                content = self.clean(snip_el.get_text()) if snip_el else title
                if keyword and not self._kw_matches(keyword, title, content):
                    continue
                results.append({
                    'platform': platform,
                    'title':    title,
                    'content':  content,
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

    def _google_fallback(self, query, platform, site_filter, max_results, keyword=None):
        """Google site-search fallback. When `keyword` is given, drop results
        that don't mention it (filters out navigational/homepage hits)."""
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
                    title = self.clean(t.get_text())
                    content = self.clean(sn.get_text()) if sn else title
                    if keyword and not self._kw_matches(keyword, title, content):
                        continue
                    results.append({
                        'platform': platform,
                        'title': title,
                        'content': content,
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
        results = self._ddg_fallback(query, 'Kaskus', 'kaskus.co.id', max_results, keyword=keyword)
        if results:
            self.update_status(f"[Kaskus] DuckDuckGo: {len(results)} hasil")

        # Strategy 2: Google fallback
        if not results:
            self.update_status("[Kaskus] Coba Google fallback...")
            results = self._google_fallback(query, 'Kaskus', 'kaskus.co.id', max_results, keyword=keyword)
            if results:
                self.update_status(f"[Kaskus] Google: {len(results)} hasil")

        for r in results:
            r['keyword'] = keyword
            r['location'] = location

        self.update_status(f"[Kaskus] {len(results)} thread ditemukan")
        return results[:max_results]


# ─────────────────────────────────────────────────────────────
# GDELT — global news index (DOC 2.0 API, free, no key).
#         Research-grade coverage; rate limit is 1 request / 5s.
# ─────────────────────────────────────────────────────────────
_gdelt_last = [0.0]


class GDELTScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[GDELT] Mencari '{keyword}'...")
        results = []
        # Respect GDELT's 1-request-per-5s limit
        gap = time.time() - _gdelt_last[0]
        if gap < 5.5:
            time.sleep(5.5 - gap)
        try:
            params = {
                'query': keyword, 'mode': 'ArtList', 'format': 'json',
                'maxrecords': min(max_results, 75), 'timespan': '3m',
                'sort': 'DateDesc',
            }
            url = 'https://api.gdeltproject.org/api/v2/doc/doc?' + '&'.join(
                f"{k}={quote_plus(str(v))}" for k, v in params.items())
            resp = requests.get(url, headers={'User-Agent': BROWSER_UA}, timeout=20)
            _gdelt_last[0] = time.time()
            if not resp.text.strip().startswith('{'):
                self.update_status("[GDELT] Rate limited / tidak ada data")
                return results
            for a in resp.json().get('articles', [])[:max_results]:
                title = self.clean(a.get('title', ''))
                link = a.get('url', '')
                if not title or not link:
                    continue
                results.append({
                    'platform': 'GDELT',
                    'title': title,
                    'content': f"{a.get('domain', '')} ({a.get('sourcecountry', '')})".strip(),
                    'url': link,
                    'date': self._gdelt_date(a.get('seendate', '')),
                    'source': a.get('domain', 'GDELT'),
                    'keyword': keyword,
                    'location': location,
                })
            self.update_status(f"[GDELT] {len(results)} artikel ditemukan")
        except Exception as e:
            self.update_status(f"[GDELT] Error: {str(e)[:60]}")
        return results

    def _gdelt_date(self, s):
        try:
            return datetime.strptime(s, '%Y%m%dT%H%M%SZ').strftime('%Y-%m-%d %H:%M')
        except Exception:
            return datetime.now().strftime('%Y-%m-%d %H:%M')


# ─────────────────────────────────────────────────────────────
# Wikipedia — MediaWiki search API (id.wikipedia, free, no key).
#             Reference/background + generous limits (scales well).
# ─────────────────────────────────────────────────────────────
class WikipediaScraper(BaseScraper):
    def scrape(self, keyword, location='', max_results=15):
        self.update_status(f"[Wikipedia] Mencari '{keyword}'...")
        results = []
        try:
            params = {
                'action': 'query', 'list': 'search', 'srsearch': keyword,
                'format': 'json', 'srlimit': min(max_results, 20), 'utf8': 1,
                'srprop': 'snippet|timestamp',
            }
            url = 'https://id.wikipedia.org/w/api.php?' + '&'.join(
                f"{k}={quote_plus(str(v))}" for k, v in params.items())
            resp = requests.get(url, headers={
                'User-Agent': 'alyx-scraper/1.0 (research tool; +https://scraper.alyxlabs.tech)'
            }, timeout=15)
            for item in resp.json().get('query', {}).get('search', []):
                title = item.get('title', '')
                snippet = re.sub(r'<[^>]+>', '', item.get('snippet', '') or '')
                if not title:
                    continue
                results.append({
                    'platform': 'Wikipedia',
                    'title': title,
                    'content': self.clean(snippet),
                    'url': 'https://id.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                    'date': self._wiki_date(item.get('timestamp', '')),
                    'source': 'Wikipedia ID',
                    'keyword': keyword,
                    'location': location,
                })
            self.update_status(f"[Wikipedia] {len(results)} artikel ditemukan")
        except Exception as e:
            self.update_status(f"[Wikipedia] Error: {str(e)[:60]}")
        return results

    def _wiki_date(self, s):
        try:
            return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M')
        except Exception:
            return ''


SCRAPERS = {
    'Google News': GoogleNewsScraper,
    'News Sites':  NewsSitesScraper,
    'GDELT':       GDELTScraper,
    'Wikipedia':   WikipediaScraper,
    'Kaskus':      KaskusScraper,
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
