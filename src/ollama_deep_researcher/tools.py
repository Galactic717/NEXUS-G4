"""Agent tools for shell execution, Python, file operations, and OSINT"""
import subprocess
import sys
import os
import json
import logging
from io import StringIO
from typing import Optional, List, Dict, Any
from langchain.tools import tool

# Import local specialized modules
from ollama_deep_researcher.shodan_search import ShodanSearch
from ollama_deep_researcher.darknet import DarknetSearch
from ollama_deep_researcher.configuration import Configuration

logger = logging.getLogger(__name__)

# Білий список безпечних команд
SAFE_COMMANDS = {
    "ping", "nmap", "whois", "dig", "nslookup", "curl", "wget",
    "traceroute", "netstat", "ss", "ip", "ifconfig", "iwconfig",
    "airmon-ng", "airodump-ng", "aireplay-ng", "aircrack-ng",
    "host", "dnsrecon", "dnsenum", "theharvester",
    "nikto", "sqlmap", "hydra", "john", "hashcat"
}

@tool
def execute_shell(command: str, timeout: int = 30) -> str:
    """Execute a system command. Use for network tools, scanning, OSINT.
    Allowed commands: ping, nmap, whois, dig, nslookup, curl, traceroute,
    netstat, ip, ifconfig, iwconfig, airmon-ng, airodump-ng, aireplay-ng,
    aircrack-ng, host, dnsrecon, nikto, sqlmap, hydra, john, hashcat.
    Example: 'nmap -sV 192.168.1.1' or 'whois example.com'"""
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "Error: Empty command"
    
    base_cmd = cmd_parts[0]
    if base_cmd not in SAFE_COMMANDS:
        return f"Error: Command '{base_cmd}' is not in allowed list. Available: {', '.join(sorted(SAFE_COMMANDS))}"
    
    try:
        # On Windows, some commands might need .exe or different handling
        # But shell=True usually handles the PATH correctly
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        output = result.stdout + result.stderr
        return output[:10000] if output else "Command executed, no output"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error: {str(e)}"

@tool
def execute_python(code: str) -> str:
    """Execute Python code and return its output. Use for data processing,
    analysis, visualization, or any Python computation.
    Example: 'print(sum([1,2,3,4,5]))' or 'import hashlib; print(hashlib.md5(b"test").hexdigest())'"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = StringIO()
    
    try:
        sys.stdout = redirected_output
        sys.stderr = redirected_output
        
        # Create a restricted globals dict for safety
        safe_globals = {
            '__builtins__': {
                'abs': abs, 'all': all, 'any': any, 'bin': bin, 'bool': bool,
                'chr': chr, 'complex': complex, 'dict': dict, 'dir': dir,
                'divmod': divmod, 'enumerate': enumerate, 'filter': filter,
                'float': float, 'format': format, 'frozenset': frozenset,
                'hash': hash, 'hex': hex, 'id': id, 'int': int, 'isinstance': isinstance,
                'issubclass': issubclass, 'iter': iter, 'len': len, 'list': list,
                'map': map, 'max': max, 'min': min, 'next': next, 'object': object,
                'oct': oct, 'ord': ord, 'pow': pow, 'print': print, 'range': range,
                'repr': repr, 'reversed': reversed, 'round': round, 'set': set,
                'slice': slice, 'sorted': sorted, 'str': str, 'sum': sum,
                'tuple': tuple, 'type': type, 'zip': zip, 'True': True, 'False': False,
                'None': None, 'Exception': Exception, 'ValueError': ValueError,
                'TypeError': TypeError, 'ImportError': ImportError,
                'ZeroDivisionError': ZeroDivisionError, 'json': json
            },
            '__name__': '__main__',
            '__doc__': None,
            'os': os, # Allow os for path manipulations
            'json': json
        }
        
        exec(code, safe_globals)
        sys.stdout = old_stdout
        return redirected_output.getvalue() or "Code executed successfully, no output"
    except Exception as e:
        sys.stdout = old_stdout
        return f"Error: {type(e).__name__}: {str(e)}"

@tool
def file_read(path: str, max_chars: int = 20000) -> str:
    """Read the contents of a file. Use for reading scripts, configs, results.
    Example: 'logs/scan_result.txt'"""
    try:
        # Security: prevent reading sensitive system files if possible
        abs_path = os.path.abspath(path)
        if any(part in abs_path for part in ['.ssh', 'etc/passwd', 'Windows/System32']):
            return "Error: Access to this path is restricted for security reasons."

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_chars)
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
def file_write(path: str, content: str) -> str:
    """Write content to a file. Use for saving results, scripts, reports.
    Example: 'exports/report.md'"""
    try:
        # Security check
        abs_path = os.path.abspath(path)
        if any(part in abs_path for part in ['.ssh', 'Windows/System32']):
            return "Error: Writing to this path is restricted."

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@tool
def list_directory(path: str = ".") -> str:
    """List contents of a directory. Use for navigating the project or finding files.
    Example: 'server/' or 'data/exports/'"""
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                result.append(f"[DIR] {item}")
            else:
                size = os.path.getsize(full_path)
                result.append(f"{item} ({size} bytes)")
        return "\n".join(result) if result else "Directory is empty"
    except Exception as e:
        return f"Error listing directory: {str(e)}"

@tool
def shodan_query(query: str, limit: int = 5) -> str:
    """Search Shodan for devices, services, and vulnerabilities.
    Requires SHODAN_API_KEY in environment or config.
    Example: 'proftpd 2.3.4' or 'country:UA port:80'"""
    try:
        # Try to get API key from environment or config
        api_key = os.getenv("SHODAN_API_KEY")
        if not api_key:
            return "Error: Shodan API key not found in environment variables."
            
        shodan = ShodanSearch(api_key)
        results = shodan.search(query, limit=limit)
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error during Shodan search: {str(e)}"

@tool
def darknet_search(query: str, engine: str = "ahmia") -> str:
    """Search the Darknet (.onion sites) using Ahmia or DuckDuckGo.
    Requires Tor to be running locally (SOCKS5 on 9050).
    Example: 'ransomware data leaks'"""
    try:
        searcher = DarknetSearch()
        if engine.lower() == "ahmia":
            results = searcher.ahmia_search(query)
        else:
            results = searcher.onion_search(query)
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error during Darknet search: {str(e)}"

@tool
def whois_lookup(domain: str) -> str:
    """Perform a WHOIS lookup for a domain.
    Example: 'google.com'"""
    return execute_shell.invoke(f"whois {domain}")

@tool
def http_get(url: str) -> str:
    """Make an HTTP GET request and return the content (max 10k chars).
    Use for fetching raw data from APIs or websites.
    Example: 'https://api.github.com/repos/owner/repo'"""
    import requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Search-Tool/1.1"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text[:10000]
    except Exception as e:
        return f"Error during HTTP request: {str(e)}"

@tool
def memory_search(query: str) -> str:
    """Search the local knowledge base for information from previous research sessions.
    Use this to recall facts you've already found.
    Example: 'What did we find about Gemma 4 performance?'"""
    try:
        # Import inside tool to avoid circular dependency if any
        try:
            from ollama_deep_researcher.memory_module import search_memory
        except ImportError:
            from memory_module import search_memory
        
        result = search_memory(query)
        return result if result else "No relevant information found in local memory."
    except Exception as e:
        return f"Error searching memory: {str(e)}"

@tool
def memory_save(topic: str, information: str) -> str:
    """Save important information or facts to the local long-term memory for future use.
    Example: ('Gemma 4', 'Released on May 2026, exceeds Llama 3 in coding tasks')"""
    try:
        try:
            from ollama_deep_researcher.memory_module import save_to_memory
        except ImportError:
            from memory_module import save_to_memory
            
        save_to_memory(topic, information)
        return f"Successfully saved information about '{topic}' to memory."
    except Exception as e:
        return f"Error saving to memory: {str(e)}"

@tool
def venator_collect(url: str) -> str:
    """Open URL in Venator browser and collect ALL data: HTML, screenshots, cookies, localStorage, links, images. 
    Use for complex websites, JS-heavy pages, login-required sites.
    Example: 'https://example.com/profile'"""
    import time
    try:
        try:
            from ollama_deep_researcher.venator_controller import VenatorController
        except ImportError:
            from venator_controller import VenatorController
            
        with VenatorController(headless=True, proxy=os.getenv("TOR_PROXY")) as venator:
            data = venator.collect_page_data(url)
            # Повертаємо структуровані дані
            result = json.dumps(data, ensure_ascii=False, indent=2)
            return result[:10000]  # Обрізаємо для контексту
    except Exception as e:
        return f"Venator error: {str(e)}"

@tool
def venator_screenshot(url: str) -> str:
    """Take a screenshot of a webpage using Venator browser.
    Use for visual verification of pages.
    Example: 'https://example.com'"""
    import time
    import base64
    try:
        try:
            from ollama_deep_researcher.venator_controller import VenatorController
        except ImportError:
            from venator_controller import VenatorController
            
        with VenatorController(headless=True) as venator:
            venator.navigate(url)
            time.sleep(3)
            path = venator.take_screenshot()
            
            if os.path.exists(path):
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                return f"Screenshot saved at {path}. Base64 (first 100 chars): {b64[:100]}..."
            return "Screenshot failed: file not created."
    except Exception as e:
        return f"Screenshot error: {str(e)}"

@tool
def people_search(query: str) -> str:
    """Perform a deep OSINT search for a person by full name, email, or phone.
    Returns profiles, registry data, and contact info.
    Example: 'Степанов Гліб Сергійович'"""
    try:
        try:
            from ollama_deep_researcher.osint_people import PeopleOSINT
        except ImportError:
            from osint_people import PeopleOSINT
            
        from config import settings
        searcher = PeopleOSINT(tor_proxy=settings.tor_proxy)
        
        # Визначаємо тип пошуку всередині інструменту
        if '@' in query and '.' in query:
            results = searcher.search_by_email(query)
        elif any(c.isdigit() for c in query) and len([c for c in query if c.isdigit()]) >= 10:
            results = searcher.search_by_phone(query)
        else:
            results = searcher.search_by_full_name(query)
            
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"People search error: {str(e)}"

