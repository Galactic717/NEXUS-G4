"""
Venator Browser Controller.
Керування браузером Venator через CLI/API.
Venator — це OSINT браузер для автоматизованого збору даних.
"""
import subprocess
import json
import os
import time
import tempfile
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("AI-Search-Venator")

class VenatorController:
    """
    Контролер для Venator Browser.
    Venator — це спеціалізований браузер для OSINT та збору даних,
    побудований на основі Chromium.
    
    Можливості:
    - Відкриття URL
    - Скріншоти сторінок
    - Виконання JavaScript
    - Збір cookie, localStorage
    - Робота з проксі/Tor
    - Масовий збір даних
    """
    
    def __init__(self, 
                 venator_path: str = "venator",
                 headless: bool = True,
                 proxy: Optional[str] = None,
                 data_dir: Optional[str] = None):
        
        self.venator_path = venator_path
        self.headless = headless
        self.proxy = proxy
        
        # Налаштування директорії даних
        if data_dir is None:
            base_dir = Path(__file__).parent.parent.parent
            self.data_dir = base_dir / "data" / "venator_sessions"
        else:
            self.data_dir = Path(data_dir)
            
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_session = None
        self.process = None
    
    def start_session(self, session_name: str = "default") -> bool:
        """Запускає нову сесію Venator"""
        session_dir = self.data_dir / session_name
        session_dir.mkdir(exist_ok=True)
        
        # Базові аргументи
        cmd = [
            self.venator_path,
            "--user-data-dir", str(session_dir),
        ]
        
        if self.headless:
            cmd.append("--headless=new")
        
        if self.proxy:
            cmd.append(f"--proxy-server={self.proxy}")
        
        try:
            # Запускаємо в фоні. Примітка: Venator може мати власні CLI прапорці
            # Це універсальна реалізація для Chromium-based браузерів з OSINT прапорцями
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.active_session = session_name
            time.sleep(2)  # Чекаємо запуск
            logger.info(f"Venator session '{session_name}' initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to start Venator: {e}")
            return False
    
    def navigate(self, url: str) -> Dict[str, Any]:
        """Перейти за URL та отримати дані"""
        if not self.active_session:
            if not self.start_session():
                return {"error": "Failed to start session"}
        
        logger.info(f"Venator: Navigating to {url}")
        
        try:
            # Спроба через CDP (Chrome DevTools Protocol) або REST API, якщо Venator його має
            import httpx
            # За замовчуванням Chrome/Venator може слухати на 9222
            try:
                resp = httpx.get("http://127.0.0.1:9222/json/version", timeout=2.0)
                if resp.status_code == 200:
                    # Тут могла б бути логіка через Playwright або Pyppeteer
                    # Але для MVP використовуємо CLI інтерфейс Venator
                    pass
            except:
                pass

            # Виклик через CLI (якщо Venator підтримує одноразові команди)
            result = subprocess.run(
                [self.venator_path, "--navigate", url, "--user-data-dir", str(self.data_dir / self.active_session)],
                capture_output=True,
                text=True,
                timeout=60
            )
            return {"output": result.stdout, "url": url, "status": "success"}
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return {"error": str(e), "url": url}
    
    def take_screenshot(self, filepath: Optional[str] = None) -> str:
        """Зробити скріншот поточної сторінки"""
        if not self.active_session:
            return "Error: No active session"
            
        if not filepath:
            timestamp = int(time.time())
            # Зберігаємо в папку експортів
            export_dir = self.data_dir.parent / "exports" / "screenshots"
            export_dir.mkdir(parents=True, exist_ok=True)
            filepath = str(export_dir / f"venator_{self.active_session}_{timestamp}.png")
        
        try:
            subprocess.run(
                [self.venator_path, "--screenshot", filepath, 
                 "--user-data-dir", str(self.data_dir / self.active_session)],
                capture_output=True,
                text=True,
                timeout=30
            )
            return filepath if os.path.exists(filepath) else "Screenshot failed"
        except Exception as e:
            return f"Screenshot error: {e}"
    
    def execute_js(self, js_code: str) -> str:
        """Виконати JavaScript на поточній сторінці"""
        if not self.active_session:
            return "Error: No active session"
            
        try:
            result = subprocess.run(
                [self.venator_path, "--eval", js_code,
                 "--user-data-dir", str(self.data_dir / self.active_session)],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            return f"JS execution error: {e}"
    
    def collect_page_data(self, url: str) -> Dict[str, Any]:
        """
        Збирає ВСІ дані зі сторінки:
        """
        self.navigate(url)
        time.sleep(3) # Даємо час на рендеринг JS
        
        # Спроба зібрати структуровані дані через JS
        js_collector = """
        (function() {
            return JSON.stringify({
                title: document.title,
                cookies: document.cookie,
                meta: Array.from(document.querySelectorAll('meta')).map(m => ({name: m.name || m.getAttribute('property'), content: m.content})),
                links: Array.from(document.querySelectorAll('a')).slice(0, 50).map(a => ({href: a.href, text: a.textContent.trim()})).filter(l => l.href.startsWith('http')),
                text: document.body.innerText.substring(0, 10000)
            });
        })()
        """
        
        raw_data = self.execute_js(js_collector)
        try:
            data = json.loads(raw_data)
        except:
            data = {"raw_output": raw_data}
            
        data["url"] = url
        data["screenshot"] = self.take_screenshot()
        
        return data
    
    def mass_collect(self, urls: List[str], max_pages: int = 10) -> List[Dict]:
        """Масовий збір даних зі списку URL"""
        results = []
        for i, url in enumerate(urls):
            if i >= max_pages:
                break
            logger.info(f"Venator: Collecting page {i+1}/{min(len(urls), max_pages)}: {url}")
            try:
                data = self.collect_page_data(url)
                results.append(data)
            except Exception as e:
                logger.error(f"Failed to collect {url}: {e}")
        return results
    
    def close_session(self):
        """Закрити сесію Venator"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                if self.process:
                    self.process.kill()
            self.process = None
            self.active_session = None
            logger.info("Venator session closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_session()
