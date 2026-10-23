"""Inclui o PUBLIC_URL nos redirect URIs / web origins dos clients do realm cesup.

O realm importado só conhece http://localhost; sem isso, o login a partir de
outro computador da rede falha com "Invalid redirect uri". Idempotente.
Usado por rede-local.sh. Só biblioteca padrão.

Variáveis: KC_URL (ex.: http://localhost/auth), KC_ADMIN_USER, KC_ADMIN_PASSWORD, PUBLIC_URL
"""
import json, os, sys, time
import urllib.error, urllib.parse, urllib.request

KC_URL     = os.environ.get("KC_URL", "http://localhost/auth").rstrip("/")
ADMIN      = os.environ.get("KC_ADMIN_USER", "admin")
SENHA      = os.environ.get("KC_ADMIN_PASSWORD", "admin123")
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
REALM      = "cesup"

# client → (redirect URIs, web origins) que precisam existir
CLIENTS = {
    "incidentes-pwa": ([f"{PUBLIC_URL}/*"], [PUBLIC_URL]),
    "grafana":        ([f"{PUBLIC_URL}/grafana/*"], []),
}


def req(method, url, token=None, data=None, form=None):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def token_admin(espera=300):
    """Keycloak recém-recriado demora a responder — tenta até `espera` segundos."""
    fim = time.time() + espera
    ultimo = ""
    while time.time() < fim:
        try:
            r = req("POST", f"{KC_URL}/realms/master/protocol/openid-connect/token",
                    form={"grant_type": "password", "client_id": "admin-cli",
                          "username": ADMIN, "password": SENHA})
            return r["access_token"]
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("Keycloak recusou KC_ADMIN_USER/KC_ADMIN_PASSWORD do .env (HTTP 401)")
            ultimo = f"HTTP {e.code}"
            time.sleep(10)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            ultimo = str(e)
            time.sleep(10)
    sys.exit(f"Keycloak não autenticou em {espera}s ({ultimo})")


def main():
    token = token_admin()
    for client_id, (redirects, origins) in CLIENTS.items():
        base = f"{KC_URL}/admin/realms/{REALM}/clients"
        achados = req("GET", f"{base}?clientId={urllib.parse.quote(client_id)}", token)
        if not achados:
            print(f"client '{client_id}' não existe no realm {REALM} — ignorado")
            continue
        c = achados[0]
        antes = (list(c.get("redirectUris") or []), list(c.get("webOrigins") or []))
        c["redirectUris"] = antes[0] + [u for u in redirects if u not in antes[0]]
        c["webOrigins"]   = antes[1] + [o for o in origins if o not in antes[1]]
        if (c["redirectUris"], c["webOrigins"]) == antes:
            print(f"client '{client_id}': já aceita {PUBLIC_URL}")
            continue
        req("PUT", f"{base}/{c['id']}", token, data=c)
        print(f"client '{client_id}': {PUBLIC_URL} incluído nos redirect URIs")


if __name__ == "__main__":
    main()
