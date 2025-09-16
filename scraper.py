import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import requests
from bs4 import BeautifulSoup
import threading
import json
from datetime import datetime
from urllib.parse import quote_plus
import time
import random
import webbrowser
import os
import xml.etree.ElementTree as ET

class EnhancedPetScraper:
    """Real scraper class for pet logistics and industry data"""
    
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.results = []
    
    def update_gui_status(self, message):
        """Update GUI status if callback provided"""
        if self.gui_callback:
            self.gui_callback(message)
    
    def random_delay(self, min_delay=2, max_delay=5):
        """Random delay to avoid rate limiting"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def clean_text(self, text):
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace and newlines
        text = ' '.join(text.split())
        
        # Remove common HTML entities
        replacements = {
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&quot;': '"',
            '&#39;': "'",
            '&nbsp;': ' '
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    def scrape_google_news(self, keyword, location, max_results=15):
        """Real scraping from Google News RSS"""
        self.update_gui_status(f"🔍 Scraping Google News: '{keyword}' di {location}...")
        
        try:
            # Create search query
            query = f"{keyword} {location}"
            encoded_query = quote_plus(query)
            
            # Google News RSS URL
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
            
            self.update_gui_status(f"📡 Mengakses: {url[:60]}...")
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Parse XML content
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            
            if not items:
                self.update_gui_status("⚠️ Tidak ada hasil dari Google News")
                return 0
            
            count = 0
            for item in items[:max_results]:
                try:
                    title = self.clean_text(item.find('title').text) if item.find('title') else 'N/A'
                    link = item.find('link').text if item.find('link') else 'N/A'
                    description = self.clean_text(item.find('description').text) if item.find('description') else 'N/A'
                    pub_date = item.find('pubDate').text if item.find('pubDate') else datetime.now().strftime('%Y-%m-%d')
                    source_elem = item.find('source')
                    source = source_elem.text if source_elem else 'Google News'
                    
                    # Parse date
                    try:
                        parsed_date = datetime.strptime(pub_date[:25], '%a, %d %b %Y %H:%M:%S')
                        formatted_date = parsed_date.strftime('%Y-%m-%d')
                    except:
                        formatted_date = datetime.now().strftime('%Y-%m-%d')
                    
                    result = {
                        'id': len(self.results) + 1,
                        'platform': 'Google News',
                        'title': title[:100] + '...' if len(title) > 100 else title,
                        'content': description[:200] + '...' if len(description) > 200 else description,
                        'url': link,
                        'date': formatted_date,
                        'source': source,
                        'keyword': keyword,
                        'location': location
                    }
                    
                    self.results.append(result)
                    count += 1
                    
                    if count % 5 == 0:
                        self.update_gui_status(f"📰 Processed {count} news articles...")
                    
                except Exception as e:
                    continue
            
            self.update_gui_status(f"✅ Google News: {count} artikel berhasil di-scrape")
            return count
            
        except requests.RequestException as e:
            self.update_gui_status(f"❌ Network Error Google News: {str(e)[:50]}...")
            return 0
        except Exception as e:
            self.update_gui_status(f"❌ Error Google News: {str(e)[:50]}...")
            return 0
    
    def scrape_bing_news(self, keyword, location, max_results=10):
        """Alternative news source from Bing"""
        self.update_gui_status(f"🔍 Scraping Bing News: '{keyword}' di {location}...")
        
        try:
            query = f"{keyword} {location} site:detik.com OR site:kompas.com OR site:liputan6.com"
            encoded_query = quote_plus(query)
            
            url = f"https://www.bing.com/search?q={encoded_query}&qft=sortbydate%3d%221%22"
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            results = soup.find_all('li', class_='b_algo')
            
            count = 0
            for result in results[:max_results]:
                try:
                    title_elem = result.find('h2')
                    if not title_elem:
                        continue
                    
                    title = self.clean_text(title_elem.get_text())
                    link_elem = title_elem.find('a')
                    link = link_elem.get('href') if link_elem else 'N/A'
                    
                    snippet_elem = result.find('p')
                    snippet = self.clean_text(snippet_elem.get_text()) if snippet_elem else 'N/A'
                    
                    # Determine source
                    source = 'Bing News'
                    if 'detik.com' in link:
                        source = 'Detik'
                    elif 'kompas.com' in link:
                        source = 'Kompas'
                    elif 'liputan6.com' in link:
                        source = 'Liputan6'
                    
                    result_item = {
                        'id': len(self.results) + 1,
                        'platform': 'News Sites',
                        'title': title[:100] + '...' if len(title) > 100 else title,
                        'content': snippet[:200] + '...' if len(snippet) > 200 else snippet,
                        'url': link,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'source': source,
                        'keyword': keyword,
                        'location': location
                    }
                    
                    self.results.append(result_item)
                    count += 1
                    
                except Exception as e:
                    continue
            
            self.update_gui_status(f"✅ Bing News: {count} artikel berhasil di-scrape")
            return count
            
        except Exception as e:
            self.update_gui_status(f"❌ Error Bing News: {str(e)[:50]}...")
            return 0
    
    def scrape_forum_discussions(self, keyword, location, max_results=8):
        """Scrape forum discussions about pet logistics"""
        self.update_gui_status(f"🔍 Scraping Forums: '{keyword}' di {location}...")
        
        try:
            # Search for forum discussions
            queries = [
                f"{keyword} {location} site:kaskus.co.id",
                f"{keyword} {location} forum",
                f"{keyword} {location} diskusi"
            ]
            
            count = 0
            for query in queries:
                if count >= max_results:
                    break
                
                encoded_query = quote_plus(query)
                url = f"https://www.google.com/search?q={encoded_query}&tbm="
                
                try:
                    response = self.session.get(url, timeout=15)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    search_results = soup.find_all('div', class_='g')
                    
                    for result in search_results[:3]:
                        if count >= max_results:
                            break
                        
                        try:
                            title_elem = result.find('h3')
                            if not title_elem:
                                continue
                            
                            title = self.clean_text(title_elem.get_text())
                            
                            link_elem = result.find('a')
                            url_link = link_elem.get('href') if link_elem else 'N/A'
                            
                            snippet_elem = result.find(['span', 'div'], class_=['VwiC3b', 'hgKElc'])
                            snippet = self.clean_text(snippet_elem.get_text()) if snippet_elem else 'N/A'
                            
                            # Determine platform
                            platform = 'Forums'
                            source = 'Forum'
                            if 'kaskus.co.id' in url_link:
                                source = 'Kaskus'
                            elif 'reddit.com' in url_link:
                                source = 'Reddit'
                            
                            result_item = {
                                'id': len(self.results) + 1,
                                'platform': platform,
                                'title': title[:100] + '...' if len(title) > 100 else title,
                                'content': snippet[:200] + '...' if len(snippet) > 200 else snippet,
                                'url': url_link,
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'source': source,
                                'keyword': keyword,
                                'location': location
                            }
                            
                            self.results.append(result_item)
                            count += 1
                            
                        except Exception as e:
                            continue
                
                except Exception as e:
                    continue
                
                self.random_delay(1, 3)
            
            self.update_gui_status(f"✅ Forums: {count} diskusi berhasil di-scrape")
            return count
            
        except Exception as e:
            self.update_gui_status(f"❌ Error Forums: {str(e)[:50]}...")
            return 0
    
    def scrape_social_media_mentions(self, keyword, location, max_results=5):
        """Scrape social media mentions"""
        self.update_gui_status(f"🔍 Scraping Social Media: '{keyword}' di {location}...")
        
        try:
            # Search for social media mentions
            social_queries = [
                f"{keyword} {location} site:facebook.com",
                f"{keyword} {location} site:twitter.com OR site:x.com",
                f"{keyword} {location} site:instagram.com"
            ]
            
            count = 0
            for query in social_queries:
                if count >= max_results:
                    break
                
                encoded_query = quote_plus(query)
                url = f"https://www.google.com/search?q={encoded_query}"
                
                try:
                    response = self.session.get(url, timeout=15)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    search_results = soup.find_all('div', class_='g')
                    
                    for result in search_results[:2]:
                        if count >= max_results:
                            break
                        
                        try:
                            title_elem = result.find('h3')
                            if not title_elem:
                                continue
                            
                            title = self.clean_text(title_elem.get_text())
                            
                            link_elem = result.find('a')
                            url_link = link_elem.get('href') if link_elem else 'N/A'
                            
                            snippet_elem = result.find(['span', 'div'], class_=['VwiC3b', 'hgKElc'])
                            snippet = self.clean_text(snippet_elem.get_text()) if snippet_elem else 'N/A'
                            
                            # Determine platform
                            platform = 'Social Media'
                            source = 'Social Media'
                            if 'facebook.com' in url_link:
                                source = 'Facebook'
                            elif 'twitter.com' in url_link or 'x.com' in url_link:
                                source = 'X (Twitter)'
                            elif 'instagram.com' in url_link:
                                source = 'Instagram'
                            
                            result_item = {
                                'id': len(self.results) + 1,
                                'platform': platform,
                                'title': title[:100] + '...' if len(title) > 100 else title,
                                'content': snippet[:200] + '...' if len(snippet) > 200 else snippet,
                                'url': url_link,
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'source': source,
                                'keyword': keyword,
                                'location': location
                            }
                            
                            self.results.append(result_item)
                            count += 1
                            
                        except Exception as e:
                            continue
                
                except Exception as e:
                    continue
                
                self.random_delay(2, 4)
            
            self.update_gui_status(f"✅ Social Media: {count} mention berhasil di-scrape")
            return count
            
        except Exception as e:
            self.update_gui_status(f"❌ Error Social Media: {str(e)[:50]}...")
            return 0
    
    def scrape_keywords(self, keywords, location, selected_platforms):
        """Main method to scrape multiple keywords across platforms"""
        self.results = []  # Clear previous results
        total_scraped = 0
        
        for i, keyword in enumerate(keywords, 1):
            self.update_gui_status(f"🔄 Memproses keyword {i}/{len(keywords)}: '{keyword}'")
            
            keyword_results = 0
            
            # Scrape based on selected platforms
            if 'Google News' in selected_platforms:
                try:
                    results = self.scrape_google_news(keyword, location)
                    keyword_results += results
                    total_scraped += results
                    self.random_delay(2, 4)
                except Exception as e:
                    self.update_gui_status(f"⚠️ Skip Google News untuk '{keyword}': {str(e)[:30]}...")
            
            if 'News Sites' in selected_platforms:
                try:
                    results = self.scrape_bing_news(keyword, location)
                    keyword_results += results
                    total_scraped += results
                    self.random_delay(2, 4)
                except Exception as e:
                    self.update_gui_status(f"⚠️ Skip News Sites untuk '{keyword}': {str(e)[:30]}...")
            
            if 'Forums' in selected_platforms:
                try:
                    results = self.scrape_forum_discussions(keyword, location)
                    keyword_results += results
                    total_scraped += results
                    self.random_delay(2, 4)
                except Exception as e:
                    self.update_gui_status(f"⚠️ Skip Forums untuk '{keyword}': {str(e)[:30]}...")
            
            if 'Social Media' in selected_platforms:
                try:
                    results = self.scrape_social_media_mentions(keyword, location)
                    keyword_results += results
                    total_scraped += results
                    self.random_delay(2, 4)
                except Exception as e:
                    self.update_gui_status(f"⚠️ Skip Social Media untuk '{keyword}': {str(e)[:30]}...")
            
            self.update_gui_status(f"📊 Keyword '{keyword}': {keyword_results} hasil ditemukan")
        
        self.update_gui_status(f"🎉 Scraping selesai! Total: {total_scraped} data dari {len(keywords)} keywords")
        return self.results


class PetScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🐕 Pet Scraper - Real Dynamic Scraping")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')
        
        # Data storage
        self.scraped_data = []
        self.filtered_data = []
        self.selected_items = set()
        self.is_scraping = False
        
        # Initialize real scraper
        self.scraper = EnhancedPetScraper(gui_callback=self.update_status)
        
        # Create UI
        self.create_header()
        self.create_control_panel()
        self.create_results_area()
        self.create_bottom_panel()
        
        # Load minimal sample
        self.load_sample_data()
        
    def create_header(self):
        """Create header section"""
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="🐕 Pet Scraper - Realtime Scraping", 
            font=("Arial", 20, "bold"), 
            fg='white', 
            bg='#2c3e50'
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=20)
        
        # subtitle_label = tk.Label(
        #     header_frame, 
        #     text="Real-time Scraping Logistik & Industri Pet", 
        #     font=("Arial", 12), 
        #     fg='#ecf0f1', 
        #     bg='#2c3e50'
        # )
        # subtitle_label.pack(side=tk.LEFT, padx=(0, 20), pady=20)
        
    def create_control_panel(self):
        """Create control panel for scraping"""
        control_frame = tk.LabelFrame(self.root, text="🎛️ Panel Kontrol Real Scraping", font=("Arial", 12, "bold"), bg='#ecf0f1')
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Row 1: Keywords and Location
        row1 = tk.Frame(control_frame, bg='#ecf0f1')
        row1.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(row1, text="Keywords (pisah dengan koma):", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        self.keywords_var = tk.StringVar(value="logistik pet, industri pet, pengiriman hewan, transportasi hewan")
        keywords_entry = tk.Entry(row1, textvariable=self.keywords_var, width=50, font=("Arial", 10))
        keywords_entry.pack(side=tk.LEFT, padx=(10, 20))
        
        tk.Label(row1, text="Lokasi:", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        self.location_var = tk.StringVar(value="Jakarta")
        location_entry = tk.Entry(row1, textvariable=self.location_var, width=15, font=("Arial", 10))
        location_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # Row 2: Platform selection
        row2 = tk.Frame(control_frame, bg='#ecf0f1')
        row2.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(row2, text="Platform Target:", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        
        self.platforms = {
            'Google News': tk.BooleanVar(value=True),
            'News Sites': tk.BooleanVar(value=True),
            'Social Media': tk.BooleanVar(value=False),
            'Forums': tk.BooleanVar(value=False)
        }
        
        for platform, var in self.platforms.items():
            cb = tk.Checkbutton(row2, text=platform, variable=var, bg='#ecf0f1', font=("Arial", 9))
            cb.pack(side=tk.LEFT, padx=5)
        
        # Row 3: Action buttons
        row3 = tk.Frame(control_frame, bg='#ecf0f1')
        row3.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_button = tk.Button(
            row3, text="🚀 MULAI REAL SCRAPING", 
            command=self.start_real_scraping,
            bg='#27ae60', fg='white', 
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = tk.Button(
            row3, text="⏹️ Stop", 
            command=self.stop_scraping,
            bg='#e74c3c', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_button = tk.Button(
            row3, text="🗑️ Clear Results", 
            command=self.clear_results,
            bg='#f39c12', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.clear_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Progress bar
        self.progress = ttk.Progressbar(row3, mode='indeterminate')
        self.progress.pack(side=tk.RIGHT, padx=(10, 0), fill=tk.X, expand=True)
        
    def create_results_area(self):
        """Create results display area"""
        results_frame = tk.LabelFrame(self.root, text="📊 Hasil Real Scraping", font=("Arial", 12, "bold"), bg='#ecf0f1')
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Filter and search row
        filter_frame = tk.Frame(results_frame, bg='#ecf0f1')
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(filter_frame, text="🔍 Filter:", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_results)
        search_entry = tk.Entry(filter_frame, textvariable=self.search_var, width=30, font=("Arial", 10))
        search_entry.pack(side=tk.LEFT, padx=(10, 20))
        
        tk.Label(filter_frame, text="Platform:", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        self.platform_filter = ttk.Combobox(filter_frame, values=['Semua', 'Google News', 'Social Media', 'News Sites', 'Forums'], width=15)
        self.platform_filter.set('Semua')
        self.platform_filter.bind('<<ComboboxSelected>>', lambda e: self.filter_results())
        self.platform_filter.pack(side=tk.LEFT, padx=(5, 20))
        
        tk.Label(filter_frame, text="Keyword:", font=("Arial", 10, "bold"), bg='#ecf0f1').pack(side=tk.LEFT)
        self.keyword_filter = ttk.Combobox(filter_frame, values=['Semua'], width=15)
        self.keyword_filter.set('Semua')
        self.keyword_filter.bind('<<ComboboxSelected>>', lambda e: self.filter_results())
        self.keyword_filter.pack(side=tk.LEFT, padx=(5, 0))
        
        # Selection controls
        selection_frame = tk.Frame(results_frame, bg='#ecf0f1')
        selection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.select_all_var = tk.BooleanVar()
        select_all_cb = tk.Checkbutton(
            selection_frame, text="Pilih Semua", 
            variable=self.select_all_var,
            command=self.toggle_select_all,
            bg='#ecf0f1', font=("Arial", 10, "bold")
        )
        select_all_cb.pack(side=tk.LEFT)
        
        self.selected_count_label = tk.Label(
            selection_frame, text="Dipilih: 0", 
            font=("Arial", 10), bg='#ecf0f1'
        )
        self.selected_count_label.pack(side=tk.LEFT, padx=(20, 0))
        
        self.total_count_label = tk.Label(
            selection_frame, text="Total: 0", 
            font=("Arial", 10), bg='#ecf0f1'
        )
        self.total_count_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Treeview for results
        tree_frame = tk.Frame(results_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('Select', 'Platform', 'Title', 'Keyword', 'Date', 'Source', 'URL')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', 
                                yscrollcommand=v_scrollbar.set, 
                                xscrollcommand=h_scrollbar.set)
        
        # Configure scrollbars
        v_scrollbar.config(command=self.tree.yview)
        h_scrollbar.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.heading('Select', text='✓')
        self.tree.heading('Platform', text='Platform')
        self.tree.heading('Title', text='Judul')
        self.tree.heading('Keyword', text='Keyword')
        self.tree.heading('Date', text='Tanggal')
        self.tree.heading('Source', text='Sumber')
        self.tree.heading('URL', text='URL')
        
        self.tree.column('Select', width=50, minwidth=50)
        self.tree.column('Platform', width=120, minwidth=100)
        self.tree.column('Title', width=300, minwidth=200)
        self.tree.column('Keyword', width=120, minwidth=80)
        self.tree.column('Date', width=100, minwidth=80)
        self.tree.column('Source', width=100, minwidth=80)
        self.tree.column('URL', width=150, minwidth=100)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<Double-1>', self.on_tree_double_click)
        
    def create_bottom_panel(self):
        """Create bottom panel with export options"""
        bottom_frame = tk.LabelFrame(self.root, text="💾 Export & Actions", font=("Arial", 12, "bold"), bg='#ecf0f1')
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        button_frame = tk.Frame(bottom_frame, bg='#ecf0f1')
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.export_excel_button = tk.Button(
            button_frame, text="📊 Export ke Excel", 
            command=self.export_to_excel,
            bg='#2ecc71', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.export_excel_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.export_csv_button = tk.Button(
            button_frame, text="📝 Export ke CSV", 
            command=self.export_to_csv,
            bg='#3498db', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.export_csv_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.save_json_button = tk.Button(
            button_frame, text="💾 Save JSON", 
            command=self.save_to_json,
            bg='#9b59b6', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.save_json_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.open_urls_button = tk.Button(
            button_frame, text="🌐 Buka URLs Terpilih", 
            command=self.open_selected_urls,
            bg='#e67e22', fg='white',
            font=("Arial", 11, "bold"),
            padx=20, pady=5
        )
        self.open_urls_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Status label
        self.status_label = tk.Label(
            button_frame, text="Ready - Masukkan keywords dan lokasi, lalu klik 'MULAI REAL SCRAPING'", 
            font=("Arial", 10), bg='#ecf0f1', fg='#27ae60'
        )
        self.status_label.pack(side=tk.RIGHT, padx=(10, 0))
    
    def load_sample_data(self):
        """Load minimal sample data for demonstration"""
        sample_data = [
            {
                'id': 1,
                'platform': 'Demo',
                'title': '🚀 Klik "MULAI REAL SCRAPING" untuk scraping data real dari web',
                'content': 'Masukkan keywords (misal: logistik pet, industri pet) dan lokasi, lalu pilih platform yang ingin di-scrape. Data ini akan diganti dengan hasil scraping real.',
                'url': 'https://example.com/demo',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'Demo',
                'keyword': 'demo',
                'location': 'Demo'
            }
        ]
        
        self.scraped_data = sample_data
        self.filtered_data = sample_data.copy()
        self.refresh_treeview()
        self.update_status("Ready - Siap untuk real scraping dengan keywords dan lokasi dinamis")
    
    def start_real_scraping(self):
        """Start REAL scraping process with dynamic keywords and location"""
        if self.is_scraping:
            messagebox.showwarning("Warning", "Scraping sedang berjalan!")
            return
        
        # Get dynamic input from user
        keywords_text = self.keywords_var.get().strip()
        location = self.location_var.get().strip()
        
        if not keywords_text or not location:
            messagebox.showerror("Error", "Harap isi keywords dan lokasi!")
            return
        
        # Parse keywords dynamically
        keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            messagebox.showerror("Error", "Format keywords tidak valid! Pisahkan dengan koma.")
            return
        
        # Check selected platforms
        selected_platforms = [name for name, var in self.platforms.items() if var.get()]
        if not selected_platforms:
            messagebox.showwarning("Warning", "Pilih minimal satu platform!")
            return
        
        # Confirm real scraping
        confirm_msg = f"""🚀 REAL SCRAPING CONFIRMATION:

📋 Keywords: {', '.join(keywords)}
📍 Lokasi: {location}
🎯 Platform: {', '.join(selected_platforms)}
⏱️ Estimasi: {len(keywords) * len(selected_platforms) * 2} menit

⚠️ Ini akan melakukan scraping REAL dari web.
Lanjutkan?"""
        
        if not messagebox.askyesno("Konfirmasi Real Scraping", confirm_msg):
            return
        
        # Update keyword filter options
        keyword_options = ['Semua'] + keywords
        self.keyword_filter['values'] = keyword_options
        
        # Clear previous results
        self.scraped_data = []
        self.filtered_data = []
        self.selected_items.clear()
        self.refresh_treeview()
        
        # Start REAL scraping in separate thread
        self.is_scraping = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress.start()
        self.update_status("🚀 Memulai REAL scraping...")
        
        thread = threading.Thread(
            target=self.perform_real_scraping, 
            args=(keywords, location, selected_platforms)
        )
        thread.daemon = True
        thread.start()
    
    def perform_real_scraping(self, keywords, location, selected_platforms):
        """Perform REAL scraping using EnhancedPetScraper"""
        try:
            self.update_status("🔄 Inisialisasi scraper...")
            
            # Use the real scraper
            results = self.scraper.scrape_keywords(keywords, location, selected_platforms)
            
            # Update UI in main thread
            self.root.after(0, self.real_scraping_completed, results, keywords, location)
            
        except Exception as e:
            self.root.after(0, self.scraping_error, f"Real scraping error: {str(e)}")
    
    def real_scraping_completed(self, results, keywords, location):
        """Handle REAL scraping completion"""
        if results:
            # Convert for DF for easysort
            df = pd.DataFrame(results)

            # Sort: platform ASC, keyword ASC, date DESC
            df['date'] = pd.to_datetime(df['date'], errors='coerce')  # pastikan date jadi datetime
            df = df.sort_values(by=['platform', 'keyword', 'date'], ascending=[True, True, False])

            # Pool list of dicts
            results = df.to_dict(orient='records')

            self.scraped_data = results
            self.filtered_data = results.copy()
            self.refresh_treeview()
            
            # Update filter options based on actual results
            platforms_found = list(set([item['platform'] for item in results]))
            sources_found = list(set([item['source'] for item in results]))
            keywords_found = list(set([item['keyword'] for item in results]))
            
            platform_options = ['Semua'] + platforms_found
            keyword_options = ['Semua'] + keywords_found
            
            self.platform_filter['values'] = platform_options
            self.keyword_filter['values'] = keyword_options
            
            success_msg = f"""🎉 REAL SCRAPING BERHASIL!

📊 Total data: {len(results)}
📋 Keywords: {', '.join(keywords)}
📍 Lokasi: {location}
🎯 Platform ditemukan: {', '.join(platforms_found)}
📰 Sumber: {', '.join(sources_found)}

✅ Data real berhasil di-scrape dari web!"""
            
            self.update_status(f"✅ Real scraping selesai! {len(results)} data real berhasil di-scrape")
            messagebox.showinfo("Real Scraping Berhasil!", success_msg)
        else:
            self.update_status("⚠️ Tidak ada data ditemukan dari scraping")
            messagebox.showwarning("Tidak Ada Data", "Tidak ada data ditemukan.\n\nCoba dengan:\n• Keywords yang lebih spesifik\n• Lokasi yang berbeda\n• Platform lain")
        
        self.is_scraping = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress.stop()
    
    def scraping_error(self, error_msg):
        """Handle scraping error"""
        self.is_scraping = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress.stop()
        
        self.update_status("❌ Error dalam real scraping")
        messagebox.showerror("Error", f"Real scraping gagal:\n{error_msg}")
    
    def stop_scraping(self):
        """Stop scraping process"""
        self.is_scraping = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress.stop()
        self.update_status("⏹️ Real scraping dihentikan")
    
    def clear_results(self):
        """Clear all results"""
        if messagebox.askyesno("Konfirmasi", "Hapus semua hasil scraping?"):
            self.scraped_data.clear()
            self.filtered_data.clear()
            self.selected_items.clear()
            self.refresh_treeview()
            self.update_status("🗑️ Hasil scraping dihapus")
    
    def filter_results(self, *args):
        """Filter results based on search and filters"""
        search_term = self.search_var.get().lower()
        platform_filter = self.platform_filter.get()
        keyword_filter = self.keyword_filter.get()
        
        self.filtered_data = []
        
        for item in self.scraped_data:
            # Apply search filter
            if search_term and search_term not in item['title'].lower() and search_term not in item['content'].lower():
                continue
            
            # Apply platform filter
            if platform_filter != 'Semua' and platform_filter not in item['platform']:
                continue
            
            # Apply keyword filter
            if keyword_filter != 'Semua' and keyword_filter != item['keyword']:
                continue
            
            self.filtered_data.append(item)
        
        self.refresh_treeview()
    
    def refresh_treeview(self):
        """Refresh treeview with current data"""
        # Clear treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add filtered data
        for item in self.filtered_data:
            # Check if selected
            selected = "✓" if item['id'] in self.selected_items else "○"
            
            # Truncate long text
            title_display = item['title'][:50] + '...' if len(item['title']) > 50 else item['title']
            url_display = item['url'][:40] + '...' if len(item['url']) > 40 else item['url']
            
            self.tree.insert('', tk.END, values=(
                selected,
                item['platform'],
                title_display,
                item['keyword'],
                item['date'],
                item['source'],
                url_display
            ), tags=(str(item['id']),))
        
        self.update_counts()
    
    def update_counts(self):
        """Update selection and total counts"""
        selected_count = len(self.selected_items)
        total_count = len(self.filtered_data)
        
        self.selected_count_label.config(text=f"Dipilih: {selected_count}")
        self.total_count_label.config(text=f"Total: {total_count}")
        
        # Update select all checkbox
        if selected_count == 0:
            self.select_all_var.set(False)
        elif selected_count == total_count and total_count > 0:
            self.select_all_var.set(True)
        else:
            self.select_all_var.set(False)
    
    def toggle_select_all(self):
        """Toggle select all items"""
        if self.select_all_var.get():
            # Select all filtered items
            for item in self.filtered_data:
                self.selected_items.add(item['id'])
        else:
            # Deselect all filtered items
            for item in self.filtered_data:
                self.selected_items.discard(item['id'])
        
        self.refresh_treeview()
    
    def on_tree_click(self, event):
        """Handle tree click event"""
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify("column", event.x, event.y)
        
        if region == "cell" and column == "#1":  # Select column
            item = self.tree.identify("item", event.x, event.y)
            if item:
                tags = self.tree.item(item, "tags")
                if tags:
                    item_id = int(tags[0])
                    
                    if item_id in self.selected_items:
                        self.selected_items.remove(item_id)
                    else:
                        self.selected_items.add(item_id)
                    
                    self.refresh_treeview()
    
    def on_tree_double_click(self, event):
        """Handle tree double click to open URL"""
        item = self.tree.identify("item", event.x, event.y)
        if item:
            tags = self.tree.item(item, "tags")
            if tags:
                item_id = int(tags[0])
                data_item = next((d for d in self.filtered_data if d['id'] == item_id), None)
                if data_item and data_item['url'] != 'N/A':
                    try:
                        webbrowser.open(data_item['url'])
                        self.update_status(f"🌐 Membuka: {data_item['url'][:50]}...")
                    except Exception as e:
                        messagebox.showerror("Error", f"Gagal membuka URL:\n{str(e)}")
    
    def export_to_excel(self):
        """Export selected items to Excel"""
        if not self.selected_items:
            messagebox.showwarning("Warning", "Pilih minimal satu item untuk diekspor!")
            return
        
        selected_data = [item for item in self.scraped_data if item['id'] in self.selected_items]
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Export Real Scraping ke Excel"
        )
        
        if filename:
            try:
                df = pd.DataFrame(selected_data)
                # Reorder columns for better readability
                column_order = ['id', 'keyword', 'location', 'platform', 'source', 'title', 'content', 'url', 'date']
                df = df.reindex(columns=column_order)
                
                df.to_excel(filename, index=False, sheet_name='Pet Scraping Results')
                self.update_status(f"📊 Data berhasil diekspor ke {os.path.basename(filename)}")
                messagebox.showinfo("Export Berhasil", f"✅ {len(selected_data)} data real berhasil diekspor ke:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal mengekspor data:\n{str(e)}")
    
    def export_to_csv(self):
        """Export selected items to CSV"""
        if not self.selected_items:
            messagebox.showwarning("Warning", "Pilih minimal satu item untuk diekspor!")
            return
        
        selected_data = [item for item in self.scraped_data if item['id'] in self.selected_items]
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Real Scraping ke CSV"
        )
        
        if filename:
            try:
                df = pd.DataFrame(selected_data)
                # Reorder columns
                column_order = ['id', 'keyword', 'location', 'platform', 'source', 'title', 'content', 'url', 'date']
                df = df.reindex(columns=column_order)
                
                df.to_csv(filename, index=False, encoding='utf-8-sig')
                self.update_status(f"📝 Data berhasil diekspor ke {os.path.basename(filename)}")
                messagebox.showinfo("Export Berhasil", f"✅ {len(selected_data)} data real berhasil diekspor ke:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal mengekspor data:\n{str(e)}")
    
    def save_to_json(self):
        """Save selected items to JSON"""
        if not self.selected_items:
            messagebox.showwarning("Warning", "Pilih minimal satu item untuk disimpan!")
            return
        
        selected_data = [item for item in self.scraped_data if item['id'] in self.selected_items]
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Real Scraping ke JSON"
        )
        
        if filename:
            try:
                # Add metadata
                export_data = {
                    'metadata': {
                        'export_date': datetime.now().isoformat(),
                        'total_records': len(selected_data),
                        'scraping_type': 'Real Dynamic Scraping',
                        'keywords_used': list(set([item['keyword'] for item in selected_data])),
                        'locations_used': list(set([item['location'] for item in selected_data])),
                        'platforms_used': list(set([item['platform'] for item in selected_data]))
                    },
                    'data': selected_data
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                    
                self.update_status(f"💾 Data berhasil disimpan ke {os.path.basename(filename)}")
                messagebox.showinfo("Save Berhasil", f"✅ {len(selected_data)} data real berhasil disimpan ke:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal menyimpan data:\n{str(e)}")
    
    def open_selected_urls(self):
        """Open selected URLs in browser"""
        if not self.selected_items:
            messagebox.showwarning("Warning", "Pilih minimal satu item untuk membuka URL!")
            return
        
        selected_data = [item for item in self.scraped_data if item['id'] in self.selected_items]
        valid_urls = [item for item in selected_data if item['url'] != 'N/A' and item['url'].startswith('http')]
        
        if not valid_urls:
            messagebox.showwarning("Warning", "Tidak ada URL valid yang terpilih!")
            return
        
        if len(valid_urls) > 5:
            if not messagebox.askyesno("Konfirmasi", f"Anda akan membuka {len(valid_urls)} URL. Lanjutkan?\n(Rekomendasi: maksimal 5 URL)"):
                return
        
        try:
            opened = 0
            for item in valid_urls[:10]:  # Limit to 10 URLs
                try:
                    webbrowser.open(item['url'])
                    opened += 1
                    time.sleep(0.8)  # Delay between opening URLs
                except:
                    continue
            
            self.update_status(f"🌐 {opened} URL berhasil dibuka dari {len(valid_urls)} URL valid")
            
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membuka URL:\n{str(e)}")
    
    def update_status(self, message):
        """Update status label"""
        self.status_label.config(text=message)
        self.root.update_idletasks()


def main():
    """Main function to run the REAL scraping GUI application"""
    # Check required packages
    required_packages = ['pandas', 'requests', 'beautifulsoup4', 'openpyxl', 'lxml']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'beautifulsoup4':
                import bs4
            elif package == 'openpyxl':
                import openpyxl
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        import subprocess
        import sys
        
        print(f"Installing required packages: {', '.join(missing_packages)}")
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✅ {package} installed successfully!")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install {package}: {e}")
        print("All packages installation completed!")
    
    # Create and run GUI
    root = tk.Tk()
    
    # Set window icon (if available)
    try:
        root.iconbitmap('pet_icon.ico')  # Optional: add pet icon
    except:
        pass
    
    # Center window on screen
    root.update_idletasks()
    width = 1200
    height = 800
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    # Set minimum window size
    root.minsize(1000, 600)
    
    # Create application
    app = PetScraperGUI(root)
    
    print("""
🐕 PET SCRAPER - REAL DYNAMIC SCRAPING
=====================================
✅ Aplikasi siap digunakan!
✅ Real scraping from web sources
✅ Dynamic keywords & location
✅ Multiple platform support

📋 CARA PENGGUNAAN:
1. Masukkan keywords (pisah dengan koma)
2. Masukkan lokasi target
3. Pilih platform yang ingin di-scrape
4. Klik "MULAI REAL SCRAPING"
5. Tunggu proses selesai
6. Filter dan export hasil

⚠️ CATATAN:
• Gunakan keywords yang spesifik
• Scraping membutuhkan koneksi internet
• Hasil adalah data real dari web
• Proses bisa memakan waktu 2-10 menit

🚀 Selamat menggunakan Pet Scraper!
    """)
    
    # Run application
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n👋 Aplikasi dihentikan oleh user")
    except Exception as e:
        print(f"❌ Error menjalankan aplikasi: {e}")


if __name__ == "__main__":
    main()


# DOCUMENTATION & USAGE GUIDE
"""
🐕 PET SCRAPER - REAL DYNAMIC SCRAPING GUIDE
============================================

🔥 FITUR UTAMA YANG DIPERBAIKI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ REAL SCRAPING:
   • Scraping benar-benar dari web (bukan simulasi)
   • Data langsung dari Google News, Bing, Forums, Social Media
   • URL, title, content, date semuanya real

✅ DYNAMIC INPUT:
   • Keywords bisa diubah sesuai kebutuhan
   • Lokasi bisa diubah dinamis
   • Platform bisa dipilih sesuai target

✅ ENHANCED SCRAPER CLASS:
   • EnhancedPetScraper untuk scraping real
   • Multiple sources: Google News RSS, Bing News, Forums, Social Media
   • Rate limiting dan error handling

🎯 CARA PENGGUNAAN:
━━━━━━━━━━━━━━━━━

1️⃣ INPUT KEYWORDS:
   • Masukkan keywords, pisah dengan koma
   • Contoh: "logistik pet, industri pet, pengiriman hewan"
   • Semakin spesifik, semakin baik hasilnya

2️⃣ PILIH LOKASI:
   • Jakarta, Bandung, Surabaya, dll
   • Bisa kota atau wilayah lain

3️⃣ PILIH PLATFORM:
   • Google News: Berita terbaru
   • News Sites: Portal berita (Detik, Kompas, dll)
   • Social Media: Facebook, Twitter/X, Instagram
   • Forums: Kaskus, Reddit, forum diskusi

4️⃣ MULAI SCRAPING:
   • Klik "MULAI REAL SCRAPING"
   • Konfirmasi scraping
   • Tunggu proses (2-10 menit)

5️⃣ FILTER & EXPORT:
   • Filter berdasarkan platform, keyword, atau teks
   • Pilih data yang diinginkan
   • Export ke Excel, CSV, atau JSON

📊 OUTPUT DATA STRUCTURE:
━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "id": unique_identifier,
  "platform": "Google News|News Sites|Social Media|Forums",
  "title": "Real title from web",
  "content": "Real content/snippet",
  "url": "Real URL source",
  "date": "Scraping date",
  "source": "Specific source (Detik, Kompas, etc)",
  "keyword": "Keyword used for scraping",
  "location": "Location used for scraping"
}

⚙️ TECHNICAL IMPROVEMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Real HTTP requests dengan proper headers
• XML/RSS parsing untuk Google News
• HTML parsing untuk web sources
• Error handling dan rate limiting
• Progress tracking dan status updates
• Dynamic filter updates berdasarkan hasil real
• Metadata dalam JSON export

🚨 TROUBLESHOOTING:
━━━━━━━━━━━━━━━━━━━

❌ "Tidak ada data ditemukan":
   → Coba keywords lebih spesifik
   → Ganti lokasi target
   → Pilih platform berbeda

❌ "Network Error":
   → Cek koneksi internet
   → Tunggu sebentar, coba lagi
   → Beberapa situs mungkin memblok bot

❌ "Scraping lambat":
   → Normal untuk scraping real
   → Kurangi jumlah platform
   → Gunakan keywords lebih fokus

🎉 HASIL AKHIR:
━━━━━━━━━━━━━━

• Data REAL dari web sources
• Keywords dan lokasi DINAMIS sesuai input
• Platform bisa dipilih sesuai kebutuhan  
• Export dengan metadata lengkap
• Status real-time selama scraping

Happy Real Scraping! 🚀🐕
"""