"""
OSINT People Search Module.
Шукає інформацію про людину за ПІБ, email, телефоном, ніком.
"""
import re
import json
import logging
import concurrent.futures
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

# Спробуємо імпортувати локальні утиліти для stealth-заголовків
try:
    from ollama_deep_researcher.utils import get_stealth_headers, get_cloudscraper_session
except ImportError:
    try:
        from .utils import get_stealth_headers, get_cloudscraper_session
    except (ImportError, ValueError):
        try:
            from utils import get_stealth_headers, get_cloudscraper_session
        except ImportError:
            def get_stealth_headers():
                return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Agent/1.0"}
            def get_cloudscraper_session():
                import requests
                return requests.Session()

logger = logging.getLogger(__name__)

class PeopleOSINT:
    """
    Агент для пошуку людей. Використовує:
    - Google Dorks (через доступні пошукові системи)
    - Соцмережі (відкриті профілі)
    - Сайти-агрегатори (YouControl, Opendatabot, etc)
    - Telegram
    - Судові реєстри
    """
    
    def __init__(self, tor_proxy: Optional[str] = None):
        self.tor_proxy = tor_proxy
        self.headers = get_stealth_headers()
        self.client = httpx.Client(
            proxy=tor_proxy if tor_proxy else None,
            timeout=30.0,
            headers=self.headers,
            follow_redirects=True
        )
    
    def search_by_full_name(self, full_name: str) -> Dict[str, Any]:
        """
        Головний метод. Приймає ПІБ і повертає ВСЮ знайдену інформацію.
        """
        logger.info(f"OSINT People: Starting search for '{full_name}'")
        
        results = {
            "query": full_name,
            "profiles": [],
            "contacts": [],
            "addresses": [],
            "relatives": [],
            "court_cases": [],
            "found_links": [],
            "raw_sources": []
        }
        
        # 1. Формуємо список завдань для паралельного виконання
        tasks = [
            ("social_media", lambda: self.search_social_media(full_name)),
            ("ukraine_registries", lambda: self.search_ua_registries(full_name)),
            ("general_web", lambda: self._search_web_for_person(full_name))
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_task = {executor.submit(fn): name for name, fn in tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    task_result = future.result()
                    if task_name == "social_media":
                        results["profiles"].extend(task_result)
                    elif task_name == "ukraine_registries":
                        results["found_links"].extend(task_result)
                    elif task_name == "general_web":
                        results["raw_sources"].extend(task_result)
                except Exception as e:
                    logger.error(f"Task {task_name} failed: {e}")
        
        return results

    def search_social_media(self, name: str) -> List[Dict]:
        """Пошук профілів у соцмережах"""
        platforms = {
            "facebook": f"https://www.facebook.com/public/{quote_plus(name)}",
            "instagram": f"https://www.instagram.com/{quote_plus(name.replace(' ', ''))}",
            "linkedin": f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(name)}",
            "twitter": f"https://twitter.com/search?q={quote_plus(name)}",
            "github": f"https://github.com/search?q={quote_plus(name)}&type=users",
            "telegram": f"https://t.me/{quote_plus(name.replace(' ', '_'))}",
        }
        
        profiles = []
        # Використовуємо сесію з Cloudflare bypass якщо можливо
        scraper = get_cloudscraper_session()
        
        for platform, url in platforms.items():
            try:
                # Для деяких сайтів краще використовувати httpx, для інших scraper
                resp = scraper.get(url, timeout=10.0)
                if resp.status_code == 200 and len(resp.text) > 500:
                    profiles.append({
                        "platform": platform,
                        "url": url,
                        "found": True,
                        "snippet": f"Found profile candidate for {name} on {platform}"
                    })
            except Exception as e:
                logger.debug(f"Error searching {platform}: {e}")
        
        return profiles

    def search_ua_registries(self, name: str) -> List[Dict]:
        """Спеціалізовані OSINT сайти (Україна)"""
        sources = [
            {"name": "YouControl", "url": f"https://youcontrol.com.ua/catalog/founder/{quote_plus(name)}"},
            {"name": "Ring", "url": f"https://ring.org.ua/edr/founder/{quote_plus(name)}"},
            {"name": "OpenDataBot", "url": f"https://opendatabot.ua/search?q={quote_plus(name)}"},
            {"name": "Clarity Project", "url": f"https://clarity-project.info/person/{quote_plus(name)}"},
        ]
        
        found = []
        for src in sources:
            try:
                resp = self.client.get(src["url"], timeout=15.0)
                if resp.status_code == 200:
                    found.append({
                        "source": src["name"],
                        "url": src["url"],
                        "status": "Potential data found"
                    })
            except Exception:
                continue
        return found

    def _search_web_for_person(self, name: str) -> List[Dict]:
        """Використовує загальний пошук для пошуку згадок про людину"""
        try:
            from ollama_deep_researcher.utils import parallel_search
            # Шукаємо точну фразу ПІБ
            search_res = parallel_search(f'"{name}"', max_results=10)
            return search_res.get("results", [])
        except Exception:
            return []

    def search_by_email(self, email: str) -> Dict[str, Any]:
        """Пошук за email адресою"""
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return {"error": "Invalid email format"}
            
        return {
            "email": email,
            "breaches": self.check_breaches(email),
            "social_links": [] # Тут може бути логіка пошуку профілів за email
        }

    def check_breaches(self, email: str) -> List[Dict]:
        """Перевірка витоків через публічні джерела"""
        # В реальному OSINT тут був би запит до HIBP API або IntelX
        return []

    def search_by_phone(self, phone: str) -> Dict[str, Any]:
        """Пошук за номером телефону (Україна/Світ)"""
        clean_phone = re.sub(r"\D", "", phone)
        return {
            "phone": clean_phone,
            "service_links": [
                f"https://www.google.com/search?q={quote_plus(phone)}",
                f"https://www.truecaller.com/search/ua/{quote_plus(clean_phone)}"
            ]
        }
