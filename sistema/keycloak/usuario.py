"""Cria um usuário no realm cesup (o do PWA) com um perfil e senha temporária.

Uso (pelo Makefile):
  make usuario nome=maria perfil=tecnico-interno [email=maria@ufrgs.br] [nome_completo="Maria Silva"]

A senha temporária é gerada aqui e mostrada uma vez no terminal; no primeiro login o
Keycloak pede para a pessoa escolher a dela. O perfil vem do grupo correspondente
("Tecnicos internos", "Gestores"...). Se o usuário já existe, só o põe no grupo.
Perfis: tecnico-interno, terceirizado, plantonista, gestor, somente-leitura, admin.
"""
import json, os, pathlib, secrets, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PUBLIC_URL", "http://localhost")
from redirects import req, token_admin, KC_URL  # noqa: E402

BASE = f"{KC_URL}/admin/realms/cesup"
# Perfil → grupo, a partir dos grupos do realm-cesup.json
_REALM = json.loads(pathlib.Path(__file__).with_name("realm-cesup.json").read_text(encoding="utf-8"))
GRUPO_DO_PERFIL = {g["realmRoles"][0]: g["name"] for g in _REALM.get("groups", [])}
PERFIS = list(GRUPO_DO_PERFIL) or ["tecnico-interno", "terceirizado", "plantonista", "gestor",
                                   "somente-leitura", "admin"]


def main():
    nome = os.environ.get("nome", "").strip()
    perfis = [p.strip() for p in os.environ.get("perfil", "").split(",") if p.strip()]
    if not nome or not perfis:
        sys.exit("Uso: make usuario nome=<login> perfil=<perfil>[,<perfil>] [email=...] [nome_completo=\"...\"]\n"
                 f"Perfis: {', '.join(PERFIS)}")
    invalidos = [p for p in perfis if p not in PERFIS]
    if invalidos:
        sys.exit(f"Perfil desconhecido: {', '.join(invalidos)}. Use: {', '.join(PERFIS)}")

    t = token_admin()
    busca = f"{BASE}/users?username={urllib.parse.quote(nome)}&exact=true"
    existente = req("GET", busca, t)
    senha = None
    if existente:
        uid = existente[0]["id"]
        print(f"Usuário '{nome}' já existe no realm cesup — só os perfis serão acrescentados")
    else:
        completo = os.environ.get("nome_completo", "").strip().split(" ", 1)
        senha = secrets.token_urlsafe(9)
        req("POST", f"{BASE}/users", t, data={
            "username": nome, "enabled": True, "emailVerified": True,
            "email": os.environ.get("email") or None,
            "firstName": completo[0] or nome, "lastName": completo[1] if len(completo) > 1 else "",
            "credentials": [{"type": "password", "value": senha, "temporary": True}],
        })
        uid = req("GET", busca, t)[0]["id"]
    # O perfil vem do grupo (o mesmo que se faz no console em Groups → Join Group);
    # sem o grupo no realm, atribui o perfil direto ao usuário
    grupos = []
    for p in perfis:
        nome_grupo = GRUPO_DO_PERFIL[p]
        g = next((x for x in req("GET", f"{BASE}/groups?search={urllib.parse.quote(nome_grupo)}&exact=true", t)
                  if x["name"] == nome_grupo), None)
        if g:
            req("PUT", f"{BASE}/users/{uid}/groups/{g['id']}", t)
            grupos.append(nome_grupo)
        else:
            req("POST", f"{BASE}/users/{uid}/role-mappings/realm", t, data=[req("GET", f"{BASE}/roles/{p}", t)])
            print(f"  (grupo '{nome_grupo}' não existe — rode make keycloak-config; perfil {p} dado direto)")

    print(f"✔ {nome}: perfil {', '.join(perfis)} no realm cesup"
          + (f" (grupo {', '.join(grupos)})" if grupos else ""))
    if senha:
        print(f"  Senha temporária: {senha}")
        print("  Entregue à pessoa; no primeiro login em https://<servidor> ela escolhe a própria senha.")


if __name__ == "__main__":
    main()
