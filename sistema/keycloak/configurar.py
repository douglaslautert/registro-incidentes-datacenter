"""Leva o realm cesup ao que as Sprints 2 em diante pedem. Idempotente.

O --import-realm só vale na primeira subida: em instalações existentes, este script cria o
que faltar (perfis, usuários de teste, client de scripts) e, com LDAP_URL definido, federa o
LDAP institucional. Só biblioteca padrão; reaproveita as funções do redirects.py.

Variáveis: KC_URL, KC_ADMIN_USER, KC_ADMIN_PASSWORD, REALM_JSON (padrão: realm-cesup.json
ao lado), e para o LDAP: LDAP_URL, LDAP_BIND_DN, LDAP_BIND_CREDENTIAL, LDAP_USERS_DN,
LDAP_USERNAME_ATTR (uid), LDAP_PAPEL_PADRAO (tecnico-interno).
"""
import json, os, pathlib, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("PUBLIC_URL", "http://localhost")
from redirects import req, token_admin, KC_URL  # noqa: E402

REALM = "cesup"
BASE = f"{KC_URL}/admin/realms/{REALM}"
MODELO = json.loads(pathlib.Path(os.environ.get(
    "REALM_JSON", pathlib.Path(__file__).with_name("realm-cesup.json"))).read_text(encoding="utf-8"))


def garantir_papeis(t):
    existentes = {r["name"] for r in req("GET", f"{BASE}/roles", t)}
    for r in MODELO["roles"]["realm"]:
        if r["name"] not in existentes:
            req("POST", f"{BASE}/roles", t, data=r)
            print(f"perfil criado: {r['name']}")


def garantir_clients(t):
    for c in MODELO["clients"]:
        achado = req("GET", f"{BASE}/clients?clientId={urllib.parse.quote(c['clientId'])}", t)
        if not achado:
            req("POST", f"{BASE}/clients", t, data=c)
            print(f"client criado: {c['clientId']}")
        elif c["clientId"] == "incidentes-pwa":
            atual = achado[0]
            attrs = atual.get("attributes") or {}
            if attrs.get("pkce.code.challenge.method") != "S256" or "post.logout.redirect.uris" not in attrs:
                attrs.update(c["attributes"])
                atual["attributes"] = attrs
                req("PUT", f"{BASE}/clients/{atual['id']}", t, data=atual)
                print("client incidentes-pwa: PKCE e logout ajustados")


def garantir_usuarios(t):
    for u in MODELO["users"]:
        if req("GET", f"{BASE}/users?username={urllib.parse.quote(u['username'])}&exact=true", t):
            continue
        dados = {k: v for k, v in u.items() if k != "realmRoles"}
        req("POST", f"{BASE}/users", t, data=dados)
        uid = req("GET", f"{BASE}/users?username={urllib.parse.quote(u['username'])}&exact=true", t)[0]["id"]
        papeis = [req("GET", f"{BASE}/roles/{p}", t) for p in u["realmRoles"]]
        req("POST", f"{BASE}/users/{uid}/role-mappings/realm", t, data=papeis)
        print(f"usuário de teste criado: {u['username']} ({', '.join(u['realmRoles'])})")


def federar_ldap(t):
    url = os.environ.get("LDAP_URL", "").strip()
    if not url:
        print("LDAP_URL vazio — federação com o LDAP institucional não configurada")
        return
    realm_id = req("GET", BASE, t)["id"]
    nome = "ldap-ufrgs"
    cfg = {
        "enabled": ["true"], "priority": ["0"], "editMode": ["READ_ONLY"], "importEnabled": ["true"],
        "syncRegistrations": ["false"], "vendor": ["other"], "connectionUrl": [url],
        "bindDn": [os.environ.get("LDAP_BIND_DN", "")],
        "bindCredential": [os.environ.get("LDAP_BIND_CREDENTIAL", "")],
        "authType": ["simple" if os.environ.get("LDAP_BIND_DN") else "none"],
        "usersDn": [os.environ.get("LDAP_USERS_DN", "")],
        "usernameLDAPAttribute": [os.environ.get("LDAP_USERNAME_ATTR", "uid")],
        "rdnLDAPAttribute": [os.environ.get("LDAP_USERNAME_ATTR", "uid")],
        "uuidLDAPAttribute": [os.environ.get("LDAP_UUID_ATTR", "entryUUID")],
        "userObjectClasses": [os.environ.get("LDAP_OBJECT_CLASSES", "inetOrgPerson, organizationalPerson")],
        "searchScope": ["2"], "pagination": ["true"], "trustEmail": ["true"],
        "useTruststoreSpi": ["always"], "connectionPooling": ["true"],
    }
    achado = [c for c in req("GET", f"{BASE}/components?type=org.keycloak.storage.UserStorageProvider", t)
              if c["name"] == nome]
    comp = {"name": nome, "providerId": "ldap", "providerType": "org.keycloak.storage.UserStorageProvider",
            "parentId": realm_id, "config": cfg}
    if achado:
        comp["id"] = achado[0]["id"]
        req("PUT", f"{BASE}/components/{comp['id']}", t, data=comp)
        print(f"LDAP {url}: configuração atualizada")
    else:
        req("POST", f"{BASE}/components", t, data=comp)
        comp["id"] = [c for c in req("GET", f"{BASE}/components?type=org.keycloak.storage.UserStorageProvider", t)
                      if c["name"] == nome][0]["id"]
        print(f"LDAP {url}: federação criada")
    # Quem entra pelo LDAP recebe o perfil padrão (o técnico ajusta outros no Keycloak)
    papel = os.environ.get("LDAP_PAPEL_PADRAO", "tecnico-interno")
    mappers = req("GET", f"{BASE}/components?parent={comp['id']}", t)
    if not any(m["name"] == "perfil-padrao" for m in mappers):
        req("POST", f"{BASE}/components", t, data={
            "name": "perfil-padrao", "providerId": "hardcoded-ldap-role-mapper",
            "providerType": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
            "parentId": comp["id"], "config": {"role": [papel]}})
        print(f"LDAP: usuários entram com o perfil '{papel}'")


def main():
    t = token_admin()
    garantir_papeis(t)
    garantir_clients(t)
    garantir_usuarios(t)
    federar_ldap(t)
    print("realm cesup conferido")


if __name__ == "__main__":
    main()
