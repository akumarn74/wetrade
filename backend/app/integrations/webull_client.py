from __future__ import annotations

from app.config import settings


class WebullAPIClient:
    def __init__(self):
        from webullsdkcore.client import ApiClient
        from webullsdktrade.api import API

        api_client = ApiClient(settings.webull_app_key, settings.webull_app_secret, settings.webull_region_id)
        api_client.add_endpoint(settings.webull_region_id, settings.webull_openapi_domain)
        self.api = API(api_client)
