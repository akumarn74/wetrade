from __future__ import annotations

from app.config import settings


def _webull_http_host(openapi_domain: str) -> str:
    """SDK signs the Host header from this string; it must be a hostname only (no scheme, no path)."""
    host = (openapi_domain or '').strip()
    for prefix in ('https://', 'http://'):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host.split('/')[0].strip() or 'api.webull.com'


class WebullAPIClient:
    def __init__(self):
        from webullsdkcore.client import ApiClient
        from webullsdktrade.api import API

        api_client = ApiClient(settings.webull_app_key, settings.webull_app_secret, settings.webull_region_id)
        api_client.add_endpoint(settings.webull_region_id, _webull_http_host(settings.webull_openapi_domain))
        self.api = API(api_client)
