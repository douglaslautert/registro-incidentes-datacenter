"""Autenticação OIDC (Keycloak) e autorização por perfil (Sprint 2).

O PWA faz login no Keycloak (código + PKCE) e manda o access token em cada chamada. A API
confere a assinatura com as chaves públicas do realm (JWKS), a validade, o realm de origem
e o client que pediu o token; os perfis vêm de realm_access.roles.

Perfis do planejamento: técnico interno, terceirizado, gestor, somente leitura e admin
(mais o plantonista, que dá ACK). Integrações internas (webhook do Zabbix, e-mail, scripts)
usam o TOKEN_SERVICO. Com AUTH_OBRIGATORIA desligada, quem não manda token entra como
"anônimo" com todos os perfis — o comportamento de antes do login.
"""
import hmac, time, logging
from dataclasses import dataclass, field
import httpx
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from app.core.config import settings, lista

log = logging.getLogger("seguranca")

TECNICO, TERCEIRIZADO, GESTOR = "tecnico-interno", "terceirizado", "gestor"
PLANTONISTA, LEITURA, ADMIN, SERVICO = "plantonista", "somente-leitura", "admin", "servico"
TODOS = {TECNICO, TERCEIRIZADO, GESTOR, PLANTONISTA, LEITURA, ADMIN}

# O que cada ação exige (basta um dos perfis). Admin pode tudo.
REGISTRAR = {TECNICO, TERCEIRIZADO, PLANTONISTA, SERVICO}
LER       = TODOS | {SERVICO}
ATENDER   = {TECNICO, PLANTONISTA}                    # ACK, fechar, falso positivo, mesclar
GERIR     = {TECNICO}                                 # inventário e topologia
METRICAS  = {GESTOR, TECNICO, PLANTONISTA, LEITURA}
INTEGRAR  = {SERVICO}                                 # webhook do Zabbix, ingestão de e-mail


@dataclass
class Usuario:
    id: str
    nome: str
    papeis: set[str] = field(default_factory=set)

    def pode(self, exigidos: set[str]) -> bool:
        return ADMIN in self.papeis or bool(self.papeis & exigidos)


ANONIMO = Usuario("anonimo", "Anônimo", TODOS | {SERVICO})
_jwks: dict = {"chaves": None, "quando": 0.0}


async def _chaves() -> dict:
    if _jwks["chaves"] is None or time.time() - _jwks["quando"] > 600:
        url = f"{settings.KEYCLOAK_URL.rstrip('/')}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(url)
            r.raise_for_status()
        _jwks.update(chaves=r.json(), quando=time.time())
    return _jwks["chaves"]


def validar_token(token: str, jwks: dict) -> Usuario:
    """Confere assinatura e claims. Levanta HTTPException(401) se inválido."""
    try:
        cab = jwt.get_unverified_header(token)
        chave = next((k for k in jwks.get("keys", []) if k.get("kid") == cab.get("kid")), None)
        if chave is None:
            raise HTTPException(401, "Token assinado por chave desconhecida")
        claims = jwt.decode(token, chave, algorithms=[cab.get("alg", "RS256")],
                            options={"verify_aud": False})
    except JWTError as e:
        raise HTTPException(401, f"Token inválido: {e}")
    # O emissor varia com o endereço usado no login (IP, localhost); o realm não
    if not str(claims.get("iss", "")).rstrip("/").endswith(f"/realms/{settings.KEYCLOAK_REALM}"):
        raise HTTPException(401, "Token de outro realm")
    if claims.get("azp") not in lista(settings.KEYCLOAK_CLIENTES_ACEITOS):
        raise HTTPException(401, f"Token emitido para client não aceito: {claims.get('azp')}")
    papeis = set((claims.get("realm_access") or {}).get("roles", [])) & (TODOS | {ADMIN})
    return Usuario(claims.get("preferred_username") or claims.get("sub", "?"),
                   claims.get("name") or claims.get("preferred_username") or "?", papeis)


def _token_servico_ok(valor: str | None) -> bool:
    return bool(settings.TOKEN_SERVICO) and valor is not None and hmac.compare_digest(valor, settings.TOKEN_SERVICO)


async def usuario_atual(request: Request) -> Usuario:
    if _token_servico_ok(request.headers.get("x-token-servico")):
        return Usuario("servico", "Integração interna", {SERVICO})
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if _token_servico_ok(token):
            return Usuario("servico", "Integração interna", {SERVICO})
        try:
            jwks = await _chaves()
        except Exception as e:
            log.error(f"Keycloak indisponível para validar o token: {e}")
            raise HTTPException(503, "Serviço de login indisponível")
        return validar_token(token, jwks)
    if settings.AUTH_OBRIGATORIA:
        raise HTTPException(401, "Login necessário", headers={"WWW-Authenticate": "Bearer"})
    return ANONIMO


def exigir(perfis: set[str]):
    """Dependência FastAPI: o usuário precisa de um dos perfis."""
    async def dep(u: Usuario = Depends(usuario_atual)) -> Usuario:
        if not u.pode(perfis):
            raise HTTPException(403, "Seu perfil não permite esta ação")
        return u
    return dep
