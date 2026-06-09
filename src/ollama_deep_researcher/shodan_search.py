"""Shodan search module"""
import shodan
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ShodanSearch:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = shodan.Shodan(api_key) if api_key else None

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search Shodan for devices/services"""
        if not self.client:
            return {"results": [], "error": "No Shodan API key configured"}
        try:
            results = self.client.search(query, limit=limit)
            formatted = []
            for match in results.get('matches', []):
                formatted.append({
                    "ip": match.get('ip_str'),
                    "port": match.get('port'),
                    "org": match.get('org'),
                    "hostnames": match.get('hostnames', []),
                    "country": match.get('location', {}).get('country_name'),
                    "data": match.get('data', '')[:500]
                })
            return {
                "results": formatted,
                "total": results.get('total', 0)
            }
        except shodan.APIError as e:
            logger.error(f"Shodan API error: {e}")
            return {"results": [], "error": str(e)}

    def host_info(self, ip: str) -> Dict[str, Any]:
        """Get detailed info about a specific IP"""
        if not self.client:
            return {"error": "No Shodan API key configured"}
        try:
            host = self.client.host(ip)
            return {
                "ip": host.get('ip_str'),
                "org": host.get('org'),
                "os": host.get('os'),
                "ports": host.get('ports'),
                "services": [{
                    "port": s.get('port'),
                    "transport": s.get('transport'),
                    "service": s.get('service', ''),
                    "banner": s.get('data', '')[:300]
                } for s in host.get('data', [])]
            }
        except shodan.APIError as e:
            return {"error": str(e)}