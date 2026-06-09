"""Darknet search module with Tor support"""
import httpx
import socks
import socket
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from typing import Dict, Any, List, Optional
import logging
from stem import Signal
from stem.control import Controller

logger = logging.getLogger(__name__)

class DarknetSearch:
    def __init__(self, tor_proxy: str = "socks5h://127.0.0.1:9050", 
                 control_port: int = 9051):
        self.tor_proxy = tor_proxy
        self.control_port = control_port

    def renew_identity(self) -> bool:
        """Renew Tor circuit to get new IP"""
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
                logger.info("Tor identity renewed successfully")
                return True
        except Exception as e:
            logger.warning(f"Failed to renew Tor identity: {e}")
            return False

    def get_tor_client(self) -> httpx.Client:
        """Get httpx client routed through Tor"""
        return httpx.Client(
            proxy=self.tor_proxy,
            timeout=60.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"}
        )

    def ahmia_search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search Ahmia (.onion search engine)"""
        url = f"http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={quote_plus(query)}"
        try:
            with self.get_tor_client() as client:
                response = client.get(url, timeout=30.0)
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                for item in soup.find_all('li', class_=lambda x: x and 'result' in x.lower()):
                    link = item.find('a')
                    if link and link.get('href'):
                        results.append({
                            "title": link.text.strip() or "Unknown",
                            "url": link['href'] if link['href'].startswith('http') else f"http://{link['href']}",
                            "content": item.get_text(strip=True)[:500],
                            "source": "ahmia"
                        })
                    if len(results) >= max_results:
                        break
                return {"results": results, "total": len(results)}
        except Exception as e:
            logger.error(f"Ahmia search error: {e}")
            return {"results": [], "error": str(e)}

    def onion_search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search via DuckDuckGo onion service"""
        url = f"https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/?q={quote_plus(query)}"
        try:
            with self.get_tor_client() as client:
                response = client.get(url, timeout=60.0)
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                for link in soup.find_all('a', class_='result__a'):
                    results.append({
                        "title": link.text.strip(),
                        "url": link.get('href', ''),
                        "content": "",
                        "source": "ddg_onion"
                    })
                    if len(results) >= max_results:
                        break
                return {"results": results}
        except Exception as e:
            logger.error(f"DDG Onion search error: {e}")
            return {"results": []}

    def fetch_onion_page(self, url: str) -> Optional[str]:
        """Fetch content from a .onion site"""
        if not url.endswith('.onion'):
            return None
        try:
            with self.get_tor_client() as client:
                response = client.get(url, timeout=60.0)
                soup = BeautifulSoup(response.text, 'html.parser')
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                return soup.get_text(strip=True)[:10000]
        except Exception as e:
            logger.error(f"Failed to fetch onion page {url}: {e}")
            return None