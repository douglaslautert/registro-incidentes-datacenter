"""Testes de unidade das Sprints 1–6 (sem banco)."""
import io, json, time
import httpx, pytest
from datetime import timedelta
from app.core.config import settings
from app.services import (fingerprint, embedding, topologia, normalizacao, avaliacao, visao,
                          notificacao, seguranca)
from app.services.registro import score_correlacao
from app.services.correlacao import decisao
from app.services.interpretacao import interpretar
from app.schemas.evento import EventoCreate


# ── S3: fingerprint ────────────────────────────────────────────────
def test_fingerprint_ignora_numeros_e_pontuacao():
    a = fingerprint.calcular("srv-node-001", "Temperatura 41 °C no servidor!")
    b = fingerprint.calcular("SRV-NODE-001", "temperatura 43C no servidor")
    assert a == b


def test_fingerprint_muda_com_ativo_ou_sintoma():
    base = fingerprint.calcular("srv-node-001", "temperatura alta")
    assert base != fingerprint.calcular("srv-node-002", "temperatura alta")
    assert base != fingerprint.calcular("srv-node-001", "disco cheio")


# ── S6: embeddings ─────────────────────────────────────────────────
def test_embedding_local_tem_1024_dimensoes_e_norma_1():
    v = embedding.embedding_local("UPS sem bateria na sala A")
    assert len(v) == 1024
    assert abs(sum(x * x for x in v) - 1) < 1e-6


def test_embedding_aproxima_mesma_categoria_e_separa_outras():
    sim = embedding.similaridade_cosseno
    termica1 = embedding.embedding_local("temperatura alta no rack 1")
    termica2 = embedding.embedding_local("superaquecimento do servidor, CRAC parado")
    rede = embedding.embedding_local("link do switch caiu")
    assert sim(termica1, termica2) > 0.5
    assert sim(termica1, rede) < 0.2
    assert sim(termica1, termica1) == pytest.approx(1.0)


async def test_embedding_cai_para_o_local_sem_servico(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDINGS_URL", "http://127.0.0.1:9/v1")
    v, modelo = await embedding.gerar("disco cheio")
    assert modelo == embedding.MODELO_LOCAL and len(v) == 1024


async def test_embedding_usa_o_modelo_remoto(monkeypatch):
    def resposta(req):
        assert req.url.path.endswith("/embeddings")
        assert json.loads(req.content)["model"] == "bge-m3"
        return httpx.Response(200, json={"data": [{"embedding": [0.5] * 1024}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(embedding.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(resposta), **kw))
    monkeypatch.setattr(settings, "EMBEDDINGS_URL", "http://gpu/v1")
    v, modelo = await embedding.gerar("disco cheio")
    assert modelo == "bge-m3" and v[0] == pytest.approx(1 / 32)


# ── S1: topologia ──────────────────────────────────────────────────
ARESTAS = [("ups-sala-a-1", "pdu-a-01"), ("pdu-a-01", "rack-01"), ("rack-01", "srv-node-001"),
           ("rack-01", "srv-node-002"), ("switch-core-01", "srv-node-001"), ("switch-core-01", "storage-01")]


def test_topologia_saltos_e_score():
    g = topologia.montar_grafo(ARESTAS)
    assert topologia.saltos(g, "srv-node-001", "srv-node-001") == 0
    assert topologia.saltos(g, "pdu-a-01", "rack-01") == 1
    assert topologia.saltos(g, "srv-node-001", "srv-node-002") == 2          # pelo rack
    assert topologia.saltos(g, "ups-sala-a-1", "srv-node-001") == 3
    assert topologia.saltos(g, "srv-node-001", "inexistente") is None
    assert topologia.score(g, "rack-01", "srv-node-001") == 0.8
    assert topologia.score(g, "srv-node-001", "x") == topologia.SCORE_SEM_LIGACAO


# ── S6: correlação ─────────────────────────────────────────────────
def test_score_tres_comportamentos():
    agora = timedelta(minutes=1)
    mesmo = score_correlacao(1.0, agora, {"sala": "A", "rack": "r1"}, {"sala": "A", "rack": "r1"}, 0.9)
    vizinho = score_correlacao(0.6, timedelta(minutes=10), {"sala": "A"}, {"sala": "A"}, 0.7)
    longe = score_correlacao(0.1, timedelta(hours=3), {"sala": "A"}, {"sala": "B"}, 0.1)
    assert decisao(mesmo) == "anexa"
    assert decisao(vizinho) == "sugere"
    assert decisao(longe) == "novo"


# ── S6: normalização de todas as fontes ────────────────────────────
def test_normaliza_pessoa_completa_local_pelo_inventario():
    ev = EventoCreate(fonte="pessoa", ativo_id="CESUP-SRV-001", local={"sala": "datacenter"},
                      sintoma="  cheiro de fumaça   no rack  ")
    canon, fp = normalizacao.normalizar(ev)
    assert canon.ativo_id == "srv-node-001"
    assert canon.local.sala == "sala-A" and canon.local.rack == "rack-01"
    assert canon.sintoma == "cheiro de fumaça no rack"
    assert canon.seguranca_pessoas is True                 # "fumaca" no texto
    assert fp == fingerprint.calcular("srv-node-001", canon.sintoma)


def test_normaliza_webhook_zabbix():
    ev, eventid, status = normalizacao.de_zabbix(
        {"eventid": "77", "host": "Switch Core 01", "trigger": "Link down", "severity": "High", "status": "PROBLEM"})
    canon, _ = normalizacao.normalizar(ev)
    assert (eventid, status, canon.fonte, canon.ativo_id) == ("77", "PROBLEM", "zabbix", "switch-core-01")
    assert canon.confianca == 0.85 and canon.local.sala == "sala-DC"
    assert normalizacao.de_zabbix({"eventid": "77", "status": "RESOLVED"})[2] == "RECOVERY"


def test_normaliza_email():
    ev = normalizacao.de_email("op@ufrgs.br", "Storage 01 lento", "O storage da sala B está lento desde as 9h")
    assert ev.fonte == "email" and ev.confianca == 0.6
    assert ev.ativo_id == "storage-01" and ev.local.sala == "sala-B"


def test_interpretacao_reconhece_pdu_nova_no_inventario():
    assert interpretar("A PDU Rack 01 desarmou")["ativo_id"] == "pdu-a-01"


# ── S2: token OIDC ─────────────────────────────────────────────────
@pytest.fixture(scope="module")
def chaves():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from jose import jwk
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = privada.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    pub = privada.public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    publica = jwk.construct(pub, "RS256").to_dict()
    publica.update(kid="teste", use="sig", alg="RS256")
    publica = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in publica.items()}
    return pem, {"keys": [publica]}


def emitir(pem, papeis=("tecnico-interno",), azp="incidentes-pwa", iss="https://10.0.0.1/auth/realms/cesup",
           exp=None, usuario="maria"):
    from jose import jwt
    claims = {"iss": iss, "azp": azp, "sub": "123", "preferred_username": usuario, "name": "Maria",
              "exp": exp or int(time.time()) + 300, "realm_access": {"roles": list(papeis)}}
    return jwt.encode(claims, pem.decode(), algorithm="RS256", headers={"kid": "teste"})


def test_token_valido_traz_usuario_e_perfis(chaves):
    pem, jwks = chaves
    u = seguranca.validar_token(emitir(pem, ("gestor", "offline_access")), jwks)
    assert u.id == "maria" and u.papeis == {"gestor"}
    assert u.pode(seguranca.METRICAS) and not u.pode(seguranca.REGISTRAR)


@pytest.mark.parametrize("problema", ["realm", "client", "expirado", "assinatura"])
def test_token_invalido_e_recusado(chaves, problema):
    from fastapi import HTTPException
    pem, jwks = chaves
    token = {
        "realm": lambda: emitir(pem, iss="https://x/auth/realms/master"),
        "client": lambda: emitir(pem, azp="outro"),
        "expirado": lambda: emitir(pem, exp=int(time.time()) - 10),
        "assinatura": lambda: emitir(pem)[:-6] + "AAAAAA",
    }[problema]()
    with pytest.raises(HTTPException) as e:
        seguranca.validar_token(token, jwks)
    assert e.value.status_code == 401


def test_admin_pode_tudo():
    u = seguranca.Usuario("a", "A", {seguranca.ADMIN})
    assert u.pode(seguranca.ATENDER) and u.pode(seguranca.GERIR) and u.pode(seguranca.INTEGRAR)


# ── S6: avaliação da correlação ────────────────────────────────────
def test_avaliacao_precisao_e_kappa():
    linhas = ([{"mesmo_incidente_sistema": "1", "rotulo_tecnico_1": "1", "rotulo_tecnico_2": "1"}] * 9
              + [{"mesmo_incidente_sistema": "1", "rotulo_tecnico_1": "0", "rotulo_tecnico_2": "0"}]
              + [{"mesmo_incidente_sistema": "0", "rotulo_tecnico_1": "1", "rotulo_tecnico_2": "1"}]
              + [{"mesmo_incidente_sistema": "0", "rotulo_tecnico_1": "0", "rotulo_tecnico_2": "1"}])
    r = avaliacao.avaliar(linhas)
    assert r["pares_avaliados"] == 11 and r["pares_divergentes"] == 1
    assert r["precisao"] == pytest.approx(0.9) and r["meta_atingida"] is True
    assert r["revocacao"] == pytest.approx(0.9)
    assert avaliacao.kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0


def test_avaliacao_le_csv_do_excel_com_ponto_e_virgula():
    csv = "par_id;mesmo_incidente_sistema;rotulo_tecnico_1;rotulo_tecnico_2\n1;1;sim;sim\n2;0;não;não\n"
    assert avaliacao.avaliar(avaliacao.ler_csv(csv))["pares_avaliados"] == 2


# ── S5: visão com degradação graciosa ──────────────────────────────
async def test_visao_sem_gpu_nao_analisa():
    assert await visao.analisar(b"x", "imagem") is None


async def test_visao_le_resposta_do_modelo(monkeypatch):
    def resposta(req):
        corpo = json.loads(req.content)
        assert corpo["messages"][0]["content"][1]["type"] == "image_url"
        texto = 'Segue: {"descricao": "LED âmbar no disco 3", "leds": ["âmbar piscando"], "risco_pessoas": false}'
        return httpx.Response(200, json={"choices": [{"message": {"content": texto}}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(visao.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(resposta), **kw))
    monkeypatch.setattr(settings, "VISION_URL", "http://gpu/v1")
    r = await visao.analisar(b"\xff\xd8jpeg", "imagem")
    assert r["descricao"] == "LED âmbar no disco 3" and r["dados"]["leds"] == ["âmbar piscando"]


async def test_visao_fora_do_ar_segue_sem_analise(monkeypatch):
    monkeypatch.setattr(settings, "VISION_URL", "http://127.0.0.1:9/v1")
    assert await visao.analisar(b"x", "imagem") is None


def test_quadros_chave_do_video():
    import av
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp4") as out:
        s = out.add_stream("mpeg4", rate=10)
        s.width, s.height, s.pix_fmt = 64, 48, "yuv420p"
        for i in range(30):
            quadro = av.VideoFrame.from_ndarray(__import__("numpy").full((48, 64, 3), i * 8, "uint8"), format="rgb24")
            for p in s.encode(quadro):
                out.mux(p)
        for p in s.encode():
            out.mux(p)
    quadros = visao.quadros_chave(buf.getvalue(), quantidade=3)
    assert 1 <= len(quadros) <= 3 and all(q[:2] == b"\xff\xd8" for q in quadros)


# ── S4: política de notificação ────────────────────────────────────
async def test_p1_sms_ligacao_e_email(canais):
    await notificacao.notificar_plantao("i1", "P1", "Fumaça", "rack-01")
    assert [n for n, _ in canais["sms"]] == ["+5551000000001"]
    assert canais["ligacao"] == ["+5551000000001"]
    assert [e for e, _ in canais["email"]] == ["plantao@teste"]


async def test_mensagem_nao_repete_a_prioridade(canais):
    await notificacao.notificar_plantao("i1", "P1", "[REESCALONADO nível 2] [P1] Fumaça", "rack-01")
    assert canais["sms"][0][1].startswith("[CESUP P1] [REESCALONADO nível 2] Fumaça |")


async def test_p3_so_email(canais):
    await notificacao.notificar_plantao("i1", "P3", "Disco lento", "storage-01")
    assert canais["sms"] == [] and canais["ligacao"] == [] and len(canais["email"]) == 1


async def test_reescalonamento_inclui_segundo_nivel_e_liga_em_p2(canais):
    await notificacao.notificar_plantao("i1", "P2", "Link", "switch", nivel=2)
    assert {n for n, _ in canais["sms"]} == {"+5551000000001", "+5551000000002"}
    assert set(canais["ligacao"]) == {"+5551000000001", "+5551000000002"}
    assert {e for e, _ in canais["email"]} == {"plantao@teste", "coordenacao@teste"}
