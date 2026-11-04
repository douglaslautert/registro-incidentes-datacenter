"""Define a senha de um usuário do realm cesup (o do PWA), digitada sem aparecer na tela.

Uso: make senha nome=douglas
A senha fica definitiva (sem troca no próximo login) e a pendência "atualizar senha" sai.
"""
import getpass, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PUBLIC_URL", "http://localhost")
from redirects import req, token_admin, KC_URL  # noqa: E402

BASE = f"{KC_URL}/admin/realms/cesup"


def main():
    nome = os.environ.get("nome", "").strip()
    if not nome:
        sys.exit("Uso: make senha nome=<login>")
    t = token_admin()
    achados = req("GET", f"{BASE}/users?username={urllib.parse.quote(nome)}&exact=true", t)
    if not achados:
        sys.exit(f"'{nome}' não existe no realm cesup — crie com: make usuario nome={nome} perfil=...")
    senha = getpass.getpass(f"Nova senha para {nome}: ")
    if len(senha) < 6:
        sys.exit("Senha muito curta (mínimo 6 caracteres) — nada foi alterado")
    if getpass.getpass("Repita a senha: ") != senha:
        sys.exit("As senhas não conferem — nada foi alterado")
    u = achados[0]
    req("PUT", f"{BASE}/users/{u['id']}/reset-password", t,
        data={"type": "password", "value": senha, "temporary": False})
    u["requiredActions"] = [a for a in (u.get("requiredActions") or []) if a != "UPDATE_PASSWORD"]
    req("PUT", f"{BASE}/users/{u['id']}", t, data=u)
    print(f"✔ Senha de {nome} definida. Entre no PWA com ela (recarregue a tela de login).")


if __name__ == "__main__":
    main()
