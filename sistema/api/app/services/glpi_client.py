"""Cliente REST GLPI para validação de ativos (CMDB)."""
import httpx
from app.core.config import settings
import logging

log = logging.getLogger("glpi_client")

class GLPIClient:
    def __init__(self):
        self.url       = settings.GLPI_URL.rstrip("/") + "/apirest.php"
        self.app_token = settings.GLPI_APP_TOKEN
        self.usr_token = settings.GLPI_USER_TOKEN

    def _headers(self, session: str | None = None) -> dict:
        h = {"Content-Type": "application/json", "App-Token": self.app_token}
        if session:
            h["Session-Token"] = session
        else:
            h["Authorization"] = f"user_token {self.usr_token}"
        return h

    async def _session(self) -> str:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.url}/initSession", headers=self._headers())
            return r.json().get("session_token", "")

    async def buscar_ativo(self, hostname: str) -> dict | None:
        """Busca um ativo no GLPI pelo nome do host."""
        try:
            session = await self._session()
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.url}/Computer",
                    headers=self._headers(session),
                    params={"searchText[name]": hostname, "forcedisplay[0]": 1}
                )
            data = r.json()
            return data[0] if data else None
        except Exception as e:
            log.warning(f"GLPI indisponível: {e} — ativo '{hostname}' não validado")
            return None

glpi = GLPIClient()
