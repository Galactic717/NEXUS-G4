import os
import re
import base64
import random
import logging
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, List, Union, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from langsmith import traceable
from tavily import TavilyClient
from duckduckgo_search import DDGS
from langchain_community.utilities import SearxSearchWrapper

# Налаштування логування
logger = logging.getLogger("AI-Search-Utils")

# Constants
CHARS_PER_TOKEN = 4


_TOKENIZER = None
def count_tokens(text: str) -> int:
    """Реальний підрахунок токенів через tiktoken (з fallback на chars/3.5)."""
    global _TOKENIZER
    if _TOKENIZER is None:
        try:
            import tiktoken
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _TOKENIZER = False
    if _TOKENIZER:
        try:
            return len(_TOKENIZER.encode(text, disallowed_special=()))
        except Exception:
            return max(1, len(text) // 3)
    return max(1, len(text) // 3)

# Список Stealth-заголовків для обходу захисту
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

def get_stealth_headers() -> dict:
    """Generate random stealth headers"""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,ru;q=0.3,uk;q=0.1",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

def get_cloudscraper_session():
    """Get a session that can bypass Cloudflare"""
    try:
        import cloudscraper
        return cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
            delay=10
        )
    except ImportError:
        # Fallback to regular requests
        import requests
        session = requests.Session()
        session.headers.update(get_stealth_headers())
        return session

# Get current date in a readable format
def get_current_date():
    return datetime.now().strftime("%B %d, %Y")


# Get current year as integer string (e.g. "2026")
def get_current_year():
    return str(datetime.now().year)

def get_http_client():
    """Створює клієнт з підтримкою проксі (якщо увімкнено в конфігу)."""
    from config import settings
    
    # Використовуємо базові параметри
    headers = get_stealth_headers()
    timeout = 30.0
    
    client_kwargs = {
        "headers": headers,
        "timeout": timeout,
        "follow_redirects": True
    }
    
    if settings.enable_proxy and settings.proxy_url:
        return httpx.Client(proxy=settings.proxy_url, **client_kwargs)
    
    return httpx.Client(**client_kwargs)


def get_config_value(value: Any) -> str:
    """
    Convert configuration values to string format, handling both string and enum types.

    Args:
        value (Any): The configuration value to process. Can be a string or an Enum.

    Returns:
        str: The string representation of the value.

    Examples:
        >>> get_config_value("tavily")
        'tavily'
        >>> get_config_value(SearchAPI.TAVILY)
        'tavily'
    """
    return value if isinstance(value, str) else value.value


def strip_thinking_tokens(text: str) -> str:
    """
    Remove <think> and </think> tags and their content from the text.

    Iteratively removes all occurrences of content enclosed in thinking tokens.

    Args:
        text (str): The text to process

    Returns:
        str: The text with thinking tokens and their content removed
    """
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


def deduplicate_and_format_sources(
    search_response: Union[Dict[str, Any], List[Dict[str, Any]]],
    max_tokens_per_source: int,
    fetch_full_page: bool = False,
) -> str:
    # Convert input to list of results
    if isinstance(search_response, dict):
        sources_list = search_response["results"]
    elif isinstance(search_response, list):
        sources_list = []
        for response in search_response:
            if isinstance(response, dict) and "results" in response:
                sources_list.extend(response["results"])
            else:
                sources_list.extend(response)
    else:
        raise ValueError(
            "Input must be either a dict with 'results' or a list of search results"
        )

    # Deduplicate by URL
    unique_sources = {}
    for source in sources_list:
        if source["url"] not in unique_sources:
            unique_sources[source["url"]] = source

    sources_to_process = list(unique_sources.values())

    # Асинхронний/паралельний збір контенту для всіх сайтів одночасно (Enterprise Speed)
    if fetch_full_page:
        urls_to_fetch = [s["url"] for s in sources_to_process if s.get("raw_content") in (None, "", s.get("content"))]
        
        if urls_to_fetch:
            logger.info(f"Fetching %d URLs concurrently...", len(urls_to_fetch))
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                # Мапимо URL на результати
                results = list(executor.map(fetch_raw_content, urls_to_fetch))
            
            # Оновлюємо словник
            for url, raw_text in zip(urls_to_fetch, results):
                if raw_text:
                    unique_sources[url]["raw_content"] = raw_text

    # Format output
    formatted_text = "Sources:\n\n"
    for i, source in enumerate(unique_sources.values(), 1):
        source_id = source.get("source_id", f"S{i}")
        fetched_at = source.get("fetched_at", "")
        formatted_text += f"[{source_id}] Source: {source['title']}\n===\n"
        formatted_text += f"URL: {source['url']}\n===\n"
        if fetched_at:
            formatted_text += f"Fetched at: {fetched_at}\n===\n"
        formatted_text += (
            f"Most relevant content from source: {source['content']}\n===\n"
        )
        if fetch_full_page:
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            raw_content = source.get("raw_content", "")
            if raw_content is None:
                raw_content = ""
            if len(raw_content) > char_limit:
                raw_content = raw_content[:char_limit] + "... [truncated]"
            formatted_text += f"Full source content limited to {max_tokens_per_source} tokens: {raw_content}\n\n"

    return formatted_text.strip()


def format_sources(search_results: Dict[str, Any]) -> str:
    """
    Format search results into a bullet-point list of sources with URLs.

    Creates a simple bulleted list of search results with title and URL for each source.

    Args:
        search_results (Dict[str, Any]): Search response containing a 'results' key with
                                        a list of search result objects

    Returns:
        str: Formatted string with sources as bullet points in the format "* title : url"
    """
    lines = []
    for i, source in enumerate(search_results["results"], 1):
        source_id = source.get("source_id", f"S{i}")
        lines.append(f"[{source_id}] {source['title']} : {source['url']}")
    return "\n".join(lines)


def _clean_html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        node.decompose()
    text = markdownify(str(soup), heading_style="ATX")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _decode_response_text(response: httpx.Response) -> str:
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        return response.text


def _jina_reader_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        target = f"{parsed.netloc}{parsed.path}"
        if parsed.params:
            target += f";{parsed.params}"
        if parsed.query:
            target += f"?{parsed.query}"
        if parsed.fragment:
            target += f"#{parsed.fragment}"
    else:
        target = url
    return f"https://r.jina.ai/http://{target}"

def _transform_to_raw_url(url: str) -> str:
    """Перетворює посилання на GitHub/GitLab у прямі посилання на RAW контент."""
    parsed = urlparse(url)
    if "github.com" in parsed.netloc and "/blob/" in parsed.path:
        return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url

def fetch_raw_content(url: str) -> Optional[str]:
    """
    Fetch HTML content from a URL and convert it to markdown format using Stealth Client.
    """
    is_raw = "raw.githubusercontent.com" in url or "raw" in url
    url = _transform_to_raw_url(url)
    try:
        parsed_url = urlparse(url)
        if not parsed_url.netloc or "." not in parsed_url.netloc:
            return None
    except Exception:
        return None

    # Спроба 1: Прямий Stealth-парсинг
    try:
        with get_http_client() as client:
            response = client.get(url)
            response.raise_for_status()
            raw_text = _decode_response_text(response)
            
            # Якщо це RAW-контент (GitHub/Code), повертаємо як є, без очищення HTML
            if is_raw:
                return raw_text
                
            text = _clean_html_to_markdown(raw_text)
            if len(text) >= 500:
                return text
    except Exception as e:
        logger.warning("Direct fetch failed for %s: %s", url, str(e))

    # Спроба 2: Агресивний обхід через Jina Reader (якщо прямий запит заблоковано)
    try:
        with get_http_client() as client:
            response = client.get(_jina_reader_url(url))
            response.raise_for_status()
            text = response.text.strip()
            return text if text else None
    except Exception as e:
        logger.warning("Jina fallback failed for %s: %s", url, str(e))
        return None


def _query_tokens(text: str) -> set[str]:
    """Витягує лексеми з тексту з нормалізацією та урізанням кириличних коренів."""
    tokens = {
        token.lower()
        for token in re.findall(r"[\w\u0400-\u04ff]{2,}", text, flags=re.UNICODE)
    }
    stemmed = set()
    for t in tokens:
        if any('\u0400' <= char <= '\u04FF' for char in t):
            stemmed.add(t[:4])  # Беремо перші 4 символи як корінь для кирилиці
        else:
            stemmed.add(t)  # Англійські слова залишаємо повністю
    return stemmed


def _extract_phrases(text: str, min_len: int = 3) -> list[str]:
    """Витягує біграми та триграми зі строки для пошуку точних фраз."""
    words = re.findall(r"[\w\u0400-\u04ff]{2,}", text.lower(), flags=re.UNICODE)
    phrases = []
    for i in range(len(words) - 1):
        phrases.append(f"{words[i]} {words[i+1]}")
    for i in range(len(words) - 2):
        phrases.append(f"{words[i]} {words[i+1]} {words[i+2]}")
    return phrases


def score_source_relevance(query: str, source: Dict[str, Any]) -> float:
    """Розраховує релевантність джерела до запиту за багатофакторною моделлю.

    Алгоритм:
    - Базовий Jaccard overlap між токенами запиту і джерела
    - БОНУС за "DATA" слова: якщо в тексті є цифри, таблиці, специфікації
    - ШТРАФ за "SERVICE" слова: якщо це просто лендінг сервісу
    """
    query_terms = _query_tokens(query)
    if not query_terms:
        return 0.0

    title = str(source.get("title", ""))
    content = str(source.get("content", ""))
    url = str(source.get("url", ""))
    raw_content = str(source.get("raw_content") or "")

    base_text = f"{title} {content} {url}"
    source_terms = _query_tokens(base_text)
    if not source_terms:
        return 0.0

    overlap = query_terms & source_terms
    base_score = len(overlap) / len(query_terms)

    # --- Бонус за технічну глибину (цифри, метрики) ---
    depth_bonus = 0.0
    text_to_check = (title + " " + content + " " + raw_content[:3000]).lower()
    
    # Регулярка для пошуку цифр та технічних показників (напр. 85%, v1.2, 405B, 100M, 1.5T)
    data_patterns = [
        r"\d+\.?\d*\s*%", r"v\d+\.\d+", r"\d+[BMT]", r"(?:\d+[.,])?\d+\s*(?:million|billion|trillion)",
        r"benchmark", r"dataset", r"parameters", r"accuracy", r"performance",
        r"score", r"metric", r"result", r"comparison", r"state.?of.?the.?art",
        r"SOTA", r"MMLU", r"HumanEval", r"GSM8K", r"BLEU", r"F1",
    ]
    data_hits = sum(1 for p in data_patterns if re.search(p, text_to_check, re.IGNORECASE))
    depth_bonus += (data_hits * 0.05)

    # --- Штраф за слова-маркери "поверхневих" сервісів ---
    service_penalty = 0.0
    service_patterns = ["search engine", "platform for", "find the best", "directory of", "marketplace"]
    if any(p in text_to_check for p in service_patterns):
        service_penalty = 0.3

    # --- Бонус за точне входження ключових слів у заголовку ---
    title_bonus = 0.0
    query_words = re.findall(r"[\w\u0400-\u04ff]{3,}", query.lower(), flags=re.UNICODE)
    title_word_hits = sum(1 for w in query_words if w in title.lower())
    if query_words:
        title_bonus = (title_word_hits / len(query_words)) * 0.3

    final_score = base_score + depth_bonus + title_bonus - service_penalty
    return round(max(0.0, min(final_score, 1.0)), 3)


def annotate_source_relevance(
    search_response: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    for source in search_response.get("results", []):
        source["relevance_score"] = score_source_relevance(query, source)
    return search_response


def filter_search_results(
    search_response: Dict[str, Any],
) -> Dict[str, Any]:
    return search_response


def has_relevant_results(search_response: Dict[str, Any]) -> bool:
    return len(search_response.get("results", [])) > 0


def assign_source_ids(
    search_response: Dict[str, Any],
    *,
    start_index: int = 1,
) -> Dict[str, Any]:
    for offset, source in enumerate(search_response.get("results", [])):
        source["source_id"] = f"S{start_index + offset}"
    return search_response


def _stamp_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for index, result in enumerate(results, 1):
        result.setdefault("source_id", f"S{index}")
        result.setdefault("fetched_at", fetched_at)
        if result.get("raw_content") in (None, ""):
            result["raw_content"] = result.get("content", "")
    return results


def _normalize_duckduckgo_url(url: str) -> str:
    """Resolve DuckDuckGo redirect URLs to the actual target URL."""

    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        redirected_url = parse_qs(parsed.query).get("uddg", [""])[0]
        if redirected_url:
            return unquote(redirected_url)
    return url


def _normalize_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc:
        return url

    encoded_url = parse_qs(parsed.query).get("u", [""])[0]
    if not encoded_url:
        return url

    # Bing prefixes base64url targets with "a1".
    if encoded_url.startswith("a1"):
        encoded_url = encoded_url[2:]

    try:
        padding = "=" * ((4 - len(encoded_url) % 4) % 4)
        return base64.urlsafe_b64decode(encoded_url + padding).decode("utf-8")
    except Exception:
        return url


def bing_reader_search(
    query: str,
    max_results: int = 5,
    fetch_full_page: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fallback search by reading Bing result pages through Jina Reader."""

    try:
        search_url = f"https://r.jina.ai/http://www.bing.com/search?q={quote_plus(query)}"
        with get_http_client() as client:
            response = client.get(search_url)
            response.raise_for_status()


        results = []
        seen_urls = set()
        
        # Покращений пошук посилань (підтримка різних форматів markdown від Jina)
        matches = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", response.text)
        if not matches:
            # Fallback на пошук чистих URL, якщо markdown зламаний
            matches = [(url, url) for url in re.findall(r"https?://[^\s\)]+", response.text)]

        for title, url in matches:
            title = title.strip().replace("**", "").replace("*", "")
            url = _normalize_bing_url(url.strip())

            if not title or url in seen_urls or "bing.com" in url or "microsoft.com" in url:
                continue

            parsed_url = urlparse(url)
            if not parsed_url.netloc or "." not in parsed_url.netloc:
                continue
            
            seen_urls.add(url)
            results.append({
                "title": title,
                "url": url,
                "content": title,
                "source": "bing_reader"
            })
            if len(results) >= max_results:
                break

        return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error("Error in Bing reader search: %s", str(e))
        return {"results": []}


def google_reader_search(
    query: str,
    max_results: int = 5,
    fetch_full_page: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fallback search by reading Google result pages through Jina Reader."""

    try:
        search_url = f"https://r.jina.ai/http://www.google.com/search?q={quote_plus(query)}"
        with get_http_client() as client:
            response = client.get(search_url)
            response.raise_for_status()


        results = []
        seen_urls = set()
        
        matches = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", response.text)
        if not matches:
            matches = [(url, url) for url in re.findall(r"https?://[^\s\)]+", response.text)]

        for title, url in matches:
            title = title.strip().replace("**", "").replace("*", "")
            url = url.strip()

            if not title or url in seen_urls or "google.com" in url:
                continue

            parsed_url = urlparse(url)
            if not parsed_url.netloc or "." not in parsed_url.netloc:
                continue
            
            seen_urls.add(url)
            results.append({
                "title": title,
                "url": url,
                "content": title,
                "source": "google_reader"
            })
            if len(results) >= max_results:
                break

        return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error("Error in Google reader search: %s", str(e))
        return {"results": []}


def _duckduckgo_html_get_search(
    query: str,
    max_results: int,
    fetch_full_page: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Search DuckDuckGo using a clean, synchronous HTTP GET to html.duckduckgo.com."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result in soup.select(".result"):
            link = result.select_one(".result__a")
            if link is None:
                continue

            url_val = _normalize_duckduckgo_url(link.get("href", ""))
            title = link.get_text(" ", strip=True)
            snippet_node = result.select_one(".result__snippet")
            content = snippet_node.get_text(" ", strip=True) if snippet_node else title

            if not all([url_val, title, content]):
                continue

            raw_content = content
            if fetch_full_page:
                raw_content = fetch_raw_content(url_val)

            results.append(
                {
                    "title": title,
                    "url": url_val,
                    "content": content,
                    "raw_content": raw_content,
                }
            )

            if len(results) >= max_results:
                break

        return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error("Error in DuckDuckGo HTML GET search: %s", str(e))
        return {"results": []}


def _duckduckgo_lite_get_search(
    query: str,
    max_results: int,
    fetch_full_page: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Search DuckDuckGo using a clean, synchronous HTTP GET to lite.duckduckgo.com."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        seen_urls = set()

        links = soup.select("a.result-link, td.result-td a, tr.result-td a")
        if not links:
            links = [a for a in soup.select("a") if a.get("href") and not a.get("href").startswith("/") and "duckduckgo.com" not in a.get("href")]

        for link in links:
            href = link.get("href", "")
            url_val = _normalize_duckduckgo_url(href)
            title = link.get_text(" ", strip=True)

            if not url_val or not title or url_val in seen_urls:
                continue
            if url_val.startswith("/") or "duckduckgo.com" in url_val:
                continue

            content = title
            parent_tr = link.find_parent("tr")
            if parent_tr:
                next_tr = parent_tr.find_next_sibling("tr")
                if next_tr:
                    content = next_tr.get_text(" ", strip=True)

            seen_urls.add(url_val)
            raw_content = content
            if fetch_full_page:
                raw_content = fetch_raw_content(url_val)

            results.append(
                {
                    "title": title,
                    "url": url_val,
                    "content": content,
                    "raw_content": raw_content,
                }
            )

            if len(results) >= max_results:
                break

        return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error("Error in DuckDuckGo Lite GET search: %s", str(e))
        return {"results": []}


def _duckduckgo_official_library_search(
    query: str,
    max_results: int,
    fetch_full_page: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Search DuckDuckGo using the standard DDGS library as a fallback."""
    try:
        with DDGS() as ddgs:
            results = []
            search_results = list(
                ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch="off",
                    max_results=max_results,
                )
            )

            for r in search_results:
                url = r.get("href")
                title = r.get("title")
                content = r.get("body")

                if not all([url, title, content]):
                    continue

                raw_content = content
                if fetch_full_page:
                    raw_content = fetch_raw_content(url)

                results.append(
                    {
                        "title": title,
                        "url": url,
                        "content": content,
                        "raw_content": raw_content,
                    }
                )

        return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error("Error in DuckDuckGo official library fallback: %s", str(e))
        return {"results": []}


@traceable
def duckduckgo_search(
    query: str, max_results: int = 3, fetch_full_page: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using DuckDuckGo using a robust, event-loop-safe, multi-layered approach.
    Avoids asyncio loop issues inside FastAPI/Uvicorn.
    """
    # 1. Спробуємо чистий HTTP GET запит до HTML-ендпоінту (найбільш надійний та сумісний)
    res = _duckduckgo_html_get_search(query, max_results, fetch_full_page)
    if res.get("results"):
        return res

    # 2. Якщо не вдалося — пробуємо чистий HTTP GET до Lite-версії
    logger.info("DuckDuckGo HTML GET search returned no results; trying Lite GET...")
    res = _duckduckgo_lite_get_search(query, max_results, fetch_full_page)
    if res.get("results"):
        return res

    # 3. Якщо все інше не спрацювало — використовуємо оригінальну бібліотеку як останній шанс
    logger.info("DuckDuckGo Lite GET search returned no results; trying official library...")
    return _duckduckgo_official_library_search(query, max_results, fetch_full_page)
@traceable
def searxng_search(
    query: str, max_results: int = 3, fetch_full_page: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using SearXNG and return formatted results.

    Uses the SearxSearchWrapper to perform searches through a SearXNG instance.
    The SearXNG host URL is read from the SEARXNG_URL environment variable
    or defaults to http://localhost:8888.

    Args:
        query (str): The search query to execute
        max_results (int, optional): Maximum number of results to return. Defaults to 3.
        fetch_full_page (bool, optional): Whether to fetch full page content from result URLs.
                                         Defaults to False.

    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str or None): Full page content if fetch_full_page is True,
                                           otherwise same as content
    """
    host = os.environ.get("SEARXNG_URL", "http://localhost:8888")
    s = SearxSearchWrapper(searx_host=host)

    results = []
    search_results = s.results(query, num_results=max_results)
    for r in search_results:
        url = r.get("link")
        title = r.get("title")
        content = r.get("snippet")

        if not all([url, title, content]):
            logger.warning("Incomplete result from SearXNG: %s", r)
            continue

        raw_content = content
        if fetch_full_page:
            raw_content = fetch_raw_content(url)

        # Add result to list
        result = {
            "title": title,
            "url": url,
            "content": content,
            "raw_content": raw_content,
        }
        results.append(result)
    return {"results": _stamp_results(results)}


@traceable
def tavily_search(
    query: str, fetch_full_page: bool = True, max_results: int = 3
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using the Tavily API and return formatted results.

    Uses the TavilyClient to perform searches. Tavily API key must be configured
    in the environment.

    Args:
        query (str): The search query to execute
        fetch_full_page (bool, optional): Whether to include raw content from sources.
                                         Defaults to True.
        max_results (int, optional): Maximum number of results to return. Defaults to 3.

    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str or None): Full content of the page if available and
                                            fetch_full_page is True
    """

    tavily_client = TavilyClient()
    response = tavily_client.search(
        query, max_results=max_results, include_raw_content=fetch_full_page
    )
    response["results"] = _stamp_results(response.get("results", []))
    return response


@traceable
def perplexity_search(
    query: str, perplexity_search_loop_count: int = 0
) -> Dict[str, Any]:
    """
    Search the web using the Perplexity API and return formatted results.

    Uses the Perplexity API to perform searches with the 'sonar-pro' model.
    Requires a PERPLEXITY_API_KEY environment variable to be set.

    Args:
        query (str): The search query to execute
        perplexity_search_loop_count (int, optional): The loop step for perplexity search
                                                     (used for source labeling). Defaults to 0.

    Returns:
        Dict[str, Any]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result (includes search counter)
                - url (str): URL of the citation source
                - content (str): Content of the response or reference to main content
                - raw_content (str or None): Full content for the first source, None for additional
                                            citation sources

    Raises:
        requests.exceptions.HTTPError: If the API request fails
    """

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
    }

    payload = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": "Search the web and provide factual information with sources.",
            },
            {"role": "user", "content": query},
        ],
    }

    response = requests.post(
        "https://api.perplexity.ai/chat/completions", headers=headers, json=payload
    )
    response.raise_for_status()  # Raise exception for bad status codes

    # Parse the response
    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Perplexity returns a list of citations for a single search result
    citations = data.get("citations", ["https://perplexity.ai"])

    # Return first citation with full content, others just as references
    results = [
        {
            "title": f"Perplexity Search {perplexity_search_loop_count + 1}, Source 1",
            "url": citations[0],
            "content": content,
            "raw_content": content,
        }
    ]

    # Add additional citations without duplicating content
    for i, citation in enumerate(citations[1:], start=2):
        results.append(
            {
                "title": f"Perplexity Search {perplexity_search_loop_count + 1}, Source {i}",
                "url": citation,
                "content": "See above for full content",
                "raw_content": None,
            }
        )

    return {"results": _stamp_results(results)}


# ═══════════════════════════════════════════
# ГЛОБАЛЬНИЙ ПОШУК: паралельний запуск ВСІХ пошукових систем
# ═══════════════════════════════════════════

def parallel_search(
    query: str,
    max_results: int = 25,
    fetch_full_page: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Запускає ВСІ загальні пошукові провайдери паралельно для максимального покриття інтернету.

    Об'єднує результати від DuckDuckGo, Tavily, Google API, Shodan, Bing/Google Reader та Darknet.
    """
    providers: list[tuple[str, Any]] = [
        ("duckduckgo", lambda: duckduckgo_search(query, max_results=max_results, fetch_full_page=fetch_full_page)),
        ("google_api", lambda: google_api_search(query, max_results=5)),
        ("shodan", lambda: shodan_search(query)),
    ]

    if os.getenv("TAVILY_API_KEY"):
        providers.append(("tavily", lambda: tavily_search(query, max_results=max_results, fetch_full_page=fetch_full_page)))

    providers.extend([
        ("bing", lambda: bing_reader_search(query, max_results=max_results, fetch_full_page=fetch_full_page)),
        ("google", lambda: google_reader_search(query, max_results=max_results, fetch_full_page=fetch_full_page)),
    ])
    
    # Додаємо пошук у Даркнеті, якщо працює Tor
    if check_tor_running():
        try:
            from ollama_deep_researcher.darknet import DarknetSearch
            dn = DarknetSearch()
            providers.append(("ahmia", lambda: dn.ahmia_search(query, max_results=10)))
        except Exception as e:
            logger.warning("Failed to add darknet provider: %s", str(e))

    all_results: Dict[str, Dict[str, Any]] = {}
    seen_urls: set = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {executor.submit(fn): name for name, fn in providers}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                for src in result.get("results", []):
                    url = src.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results[url] = src
            except Exception as e:
                logger.warning("Provider %s failed: %s", name, str(e))

    merged = list(all_results.values())
    logger.info("parallel_search: %d providers → %d unique results (showing top %d)", len(providers), len(merged), max_results)
    return {"results": merged[:max_results]}


def shodan_search(query: str) -> Dict[str, Any]:
    """Shodan search via API (Synchronous)"""
    api_key = os.getenv("SHODAN_API_KEY")
    if not api_key:
        return {"results": []}
    try:
        import shodan
        client = shodan.Shodan(api_key)
        results = client.search(query, limit=10)
        formatted = [{"title": f"IP: {m.get('ip_str', '')} (Port {m.get('port')})", 
                      "url": f"https://www.shodan.io/host/{m.get('ip_str', '')}",
                      "content": f"Organization: {m.get('org', 'N/A')}. Data: {m.get('data', '')[:300]}",
                      "source": "shodan"
                     } for m in results.get('matches', [])]
        return {"results": _stamp_results(formatted)}
    except Exception as e:
        logger.error(f"Shodan error: {e}")
        return {"results": []}


def google_api_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Google Custom Search via API (Synchronous)"""
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return {"results": []}
    url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cse_id}&q={quote_plus(query)}"
    try:
        with get_http_client() as client:
            response = client.get(url, timeout=15.0)
            data = response.json()
            results = [{
                "title": item["title"],
                "url": item["link"],
                "content": item.get("snippet", ""),
                "source": "google_api"
            } for item in data.get("items", [])[:max_results]]
            return {"results": _stamp_results(results)}
    except Exception as e:
        logger.error(f"Google API search error: {e}")
        return {"results": []}


def check_tor_running() -> bool:
    """Check if Tor is running on localhost:9050"""
    import socket
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect(('127.0.0.1', 9050))
        s.close()
        return True
    except:
        return False

