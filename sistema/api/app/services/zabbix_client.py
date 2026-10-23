"""Cliente API Zabbix JSON-RPC para reconciliação de alertas."""
import httpx
from app.core.config import settings
import logging

log = logging.getLogger("zabbix_client")

class ZabbixClient:
    def __init__(self):
        self.url  = f"{settings.ZABBIX_URL}/api_jsonrpc.php"
        self.user = settings.ZABBIX_USER
        self.pwd  = settings.ZABBIX_PASSWORD
        self._token: str | None = None

    async def _token_valido(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self.url, json={
                "jsonrpc": "2.0", "method": "user.login",
                "params": {"username": self.user, "password": self.pwd}, "id": 1
            })
            self._token = r.json()["result"]
        return self._token

    async def alertas_recentes(self, minutos: int = 5) -> list[dict]:
        """Busca alertas PROBLEM dos últimos N minutos."""
        import time
        token = await self._token_valido()
        since = int(time.time()) - minutos * 60
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self.url, json={
                "jsonrpc": "2.0", "method": "problem.get",
                "params": {
                    "time_from": since, "severities": [3, 4, 5],
                    "output": ["eventid","name","severity","clock"],
                    "selectHosts": ["host"],
                },
                "auth": token, "id": 2
            })
        return r.json().get("result", [])

zabbix = ZabbixClient()
