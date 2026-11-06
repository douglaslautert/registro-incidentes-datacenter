"""Testes de integração das Sprints 1–6, pela API, no PostgreSQL de teste."""
import io, time
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.core.config import settings
from app.services import seguranca
from app.services.escalonamento import verificar_timeouts
from tests.conftest import SERVICO, evento
from tests.test_unidades import emitir, chaves  # noqa: F401 (fixture)

pytestmark = pytest.mark.banco


async def criar(cliente, **kw):
    r = await cliente.post("/api/v1/incidentes", json=evento(**kw))
    assert r.status_code == 201, r.text
    return r.json()


# ── S3 / S4 / S6: registro, deduplicação, correlação ────────────────
async def test_incidente_novo_aciona_o_plantao(cliente, db, canais):
    d = await criar(cliente, sintoma="Fumaça saindo do rack", ativo="pdu-a-01")
    assert d["decisao_correlacao"] == "novo" and d["prioridade"] == "P1"
    ac = (await db.execute(text("SELECT prioridade, nivel, prazo_em - acionado_em AS janela "
                                "FROM acionamentos WHERE incidente_id = :i"), {"i": d["incidente_id"]})).one()
    assert ac.prioridade == "P1" and ac.nivel == 1 and ac.janela == timedelta(minutes=10)
    assert canais["ligacao"] and canais["sms"] and canais["email"]          # P1: tudo
    ev = (await db.execute(text("SELECT embedding_modelo, fingerprint, local FROM eventos WHERE id = :i"),
                           {"i": d["id"]})).one()
    assert ev.embedding_modelo == "local-v2" and ev.fingerprint and ev.local["rack"] == "rack-01"


async def test_mesmo_sintoma_no_mesmo_ativo_deduplica(cliente, db):
    a = await criar(cliente, sintoma="Temperatura 41 C no servidor")
    b = await criar(cliente, sintoma="temperatura 44C no servidor")
    assert b["decisao_correlacao"] == "deduplicado" and b["incidente_id"] == a["incidente_id"]


async def test_vizinho_na_topologia_com_sintoma_parecido_correlaciona(cliente, db):
    a = await criar(cliente, ativo="pdu-a-01", sintoma="PDU do rack 01 sem energia")
    b = await criar(cliente, ativo="rack-01", sintoma="Rack 01 sem energia, nobreak apitando", sala="sala-A")
    assert b["decisao_correlacao"] in ("anexado", "sugerido")
    if b["decisao_correlacao"] == "anexado":
        assert b["incidente_id"] == a["incidente_id"]
    else:
        assert b["sugestao_correlacao"] == a["incidente_id"]


async def test_ativos_sem_relacao_abrem_incidentes_diferentes(cliente, db):
    # UPS e storage estão a 5 saltos na topologia, em salas diferentes e com sintomas distintos
    a = await criar(cliente, ativo="storage-01", sala="sala-B", sintoma="Disco do storage com RAID degradado")
    b = await criar(cliente, ativo="ups-sala-a-1", sala="sala-A", sintoma="UPS com bateria baixa")
    assert b["decisao_correlacao"] == "novo" and b["incidente_id"] != a["incidente_id"]


async def test_evento_mais_grave_recalcula_prioridade(cliente, db, canais):
    a = await criar(cliente, sintoma="Ruído estranho no servidor")
    assert a["prioridade"] == "P4"
    b = await criar(cliente, sintoma="Ruído estranho no servidor", seguranca_pessoas=True)
    assert b["incidente_id"] == a["incidente_id"] and b["prioridade"] == "P1"
    n = (await db.execute(text("SELECT count(*) FROM acionamentos WHERE incidente_id = :i AND prioridade = 'P1'"),
                          {"i": a["incidente_id"]})).scalar()
    assert n == 1 and canais["ligacao"]


async def test_sugestao_pode_ser_mesclada(cliente, db):
    a = await criar(cliente, ativo="srv-node-001", sintoma="Servidor travado, não responde ao ping")
    b = await criar(cliente, ativo="srv-node-002", sintoma="Outro servidor parou de responder")
    if b["incidente_id"] == a["incidente_id"]:
        pytest.skip("o sistema já anexou direto")
    r = await cliente.post(f"/api/v1/incidentes/{b['incidente_id']}/mesclar",
                           params={"destino": a["incidente_id"]})
    assert r.status_code == 200, r.text
    det = (await cliente.get(f"/api/v1/incidentes/{a['incidente_id']}")).json()
    assert len(det["eventos"]) == 2
    orig = (await cliente.get(f"/api/v1/incidentes/{b['incidente_id']}")).json()
    assert orig["status"] == "resolvido" and orig["mesclado_em"] == a["incidente_id"]


# ── S4: ACK e reescalonamento (antes nunca disparava) ───────────────
async def test_sem_ack_no_prazo_reescalona_para_o_segundo_nivel(cliente, db):
    d = await criar(cliente, sintoma="Vazamento de água no piso", ativo="srv-node-002")
    futuro = datetime.now(timezone.utc) + timedelta(minutes=11)
    notificar = await verificar_timeouts(db, agora=futuro)
    await db.commit()
    assert [(n["incidente_id"], n["nivel"]) for n in notificar] == [(d["incidente_id"], 2)]
    niveis = (await db.execute(text("SELECT nivel, escalado FROM acionamentos WHERE incidente_id = :i "
                                    "ORDER BY nivel"), {"i": d["incidente_id"]})).all()
    assert [(n.nivel, n.escalado) for n in niveis] == [(1, True), (2, False)]
    # mesmo instante de novo: nada a fazer
    assert await verificar_timeouts(db, agora=futuro) == []


async def test_ack_interrompe_o_reescalonamento_e_mede_o_mtta(cliente, db):
    d = await criar(cliente, sintoma="UPS em bypass", ativo="ups-sala-a-1")
    r = await cliente.patch(f"/api/v1/incidentes/{d['incidente_id']}/ack", params={"usuario_id": "joana"})
    assert r.status_code == 200 and r.json()["por"] == "joana"
    assert await verificar_timeouts(db, agora=datetime.now(timezone.utc) + timedelta(hours=3)) == []
    m = (await db.execute(text("SELECT mtta_segundos FROM metricas_incidente WHERE incidente_id = :i"),
                          {"i": d["incidente_id"]})).scalar()
    assert m is not None and m >= 0
    resumo = (await cliente.get("/api/v1/metricas/resumo")).json()
    assert resumo["fonte"] == "banco" and resumo["mtta_minutos"] is not None


async def test_incidente_fechado_nao_reescalona(cliente, db):
    d = await criar(cliente, sintoma="Fumaça no corredor", ativo="rack-01")
    await cliente.patch(f"/api/v1/incidentes/{d['incidente_id']}/fechar", params={"causa_raiz": "teste"})
    assert await verificar_timeouts(db, agora=datetime.now(timezone.utc) + timedelta(hours=1)) == []


# ── S1: Zabbix (PROBLEM, reenvio, RECOVERY) ─────────────────────────
def zbx(eventid, status="PROBLEM", host="srv-node-001", trigger="High CPU utilization", sev="Average"):
    return {"eventid": eventid, "host": host, "trigger": trigger, "severity": sev, "status": status}


async def test_zabbix_problem_reenvio_e_recovery_fecha(cliente, db):
    r = (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9001"), headers=SERVICO)).json()
    assert r["decisao_correlacao"] == "novo"
    again = (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9001"), headers=SERVICO)).json()
    assert again["decisao_correlacao"] == "duplicado" and again["incidente_id"] == r["incidente_id"]
    rec = (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9001", "RESOLVED"), headers=SERVICO)).json()
    assert rec["fechado"] is True
    det = (await cliente.get(f"/api/v1/incidentes/{r['incidente_id']}")).json()
    assert det["status"] == "resolvido" and det["causa_raiz"].startswith("Recuperação automática")
    assert [e["status_origem"] for e in det["eventos"]] == ["PROBLEM", "RECOVERY"]
    # recuperado não fica na fila de ACK nem reescalona
    pend = (await cliente.get("/api/v1/notificacoes/pendentes")).json()
    assert r["incidente_id"] not in [p["incidente_id"] for p in pend]


async def test_relato_de_pessoa_mantem_aberto_apos_recovery(cliente, db):
    r = (await cliente.post("/api/v1/webhook/zabbix", headers=SERVICO,
                            json=zbx("9002", trigger="Temperatura alta", host="srv-node-001"))).json()
    p = await criar(cliente, sintoma="Temperatura alta", ativo="srv-node-001")
    assert p["incidente_id"] == r["incidente_id"]
    rec = (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9002", "RECOVERY"), headers=SERVICO)).json()
    assert rec["fechado"] is False


async def test_webhook_exige_token_com_login_obrigatorio(cliente, db, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_OBRIGATORIA", True)
    assert (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9003"))).status_code == 401
    errado = {"X-Token-Servico": "outro"}
    assert (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9003"), headers=errado)).status_code == 401
    assert (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9003"), headers=SERVICO)).status_code == 200


# ── S2: perfis com login obrigatório ────────────────────────────────
async def test_perfis_com_login_obrigatorio(cliente, db, monkeypatch, chaves):
    pem, jwks = chaves
    monkeypatch.setattr(settings, "AUTH_OBRIGATORIA", True)
    seguranca._jwks.update(chaves=jwks, quando=time.time())
    def h(*papeis):
        return {"Authorization": f"Bearer {emitir(pem, papeis)}"}

    assert (await cliente.get("/api/v1/incidentes")).status_code == 401
    assert (await cliente.get("/api/v1/incidentes", headers=h("somente-leitura"))).status_code == 200
    assert (await cliente.post("/api/v1/incidentes", json=evento(), headers=h("somente-leitura"))).status_code == 403
    assert (await cliente.post("/api/v1/incidentes", json=evento(), headers=h("gestor"))).status_code == 403
    criado = await cliente.post("/api/v1/incidentes", json=evento(), headers=h("terceirizado"))
    assert criado.status_code == 201
    iid = criado.json()["incidente_id"]
    assert (await cliente.patch(f"/api/v1/incidentes/{iid}/ack", headers=h("terceirizado"))).status_code == 403
    ack = await cliente.patch(f"/api/v1/incidentes/{iid}/ack", headers=h("plantonista"))
    assert ack.status_code == 200 and ack.json()["por"] == "maria"       # quem dá ACK vem do token
    assert (await cliente.get("/api/v1/metricas/resumo", headers=h("terceirizado"))).status_code == 403
    assert (await cliente.get("/api/v1/metricas/resumo", headers=h("gestor"))).status_code == 200
    assert (await cliente.post("/api/v1/topologia/arestas", headers=h("admin"),
                               json={"origem": "a", "destino": "b"})).status_code == 201
    eu = (await cliente.get("/api/v1/auth/eu", headers=h("gestor"))).json()
    assert eu == {"id": "maria", "nome": "Maria", "papeis": ["gestor"]}
    assert (await cliente.get("/api/v1/auth/config")).json()["obrigatoria"] is True


# ── Histórico: quem fez cada passo ──────────────────────────────────
async def test_historico_registra_quem_fez_cada_passo(cliente, db, monkeypatch, chaves):
    pem, jwks = chaves
    monkeypatch.setattr(settings, "AUTH_OBRIGATORIA", True)
    seguranca._jwks.update(chaves=jwks, quando=time.time())
    def h(usuario, papel):
        return {"Authorization": f"Bearer {emitir(pem, (papel,), usuario=usuario)}"}

    iid = (await cliente.post("/api/v1/incidentes", headers=h("ana", "terceirizado"),
                              json=evento(sintoma="Rack sem energia", ativo="rack-01"))).json()["incidente_id"]
    extra = await cliente.post("/api/v1/incidentes", headers=h("bruno", "tecnico-interno"),
                               json=evento(sintoma="rack sem energia!", ativo="rack-01"))
    assert extra.json()["incidente_id"] == iid                       # mesmo problema, mesmo incidente
    await cliente.patch(f"/api/v1/incidentes/{iid}/ack", headers=h("carla", "plantonista"))
    await cliente.patch(f"/api/v1/incidentes/{iid}/fechar", params={"causa_raiz": "Disjuntor religado"},
                        headers=h("bruno", "tecnico-interno"))

    det = (await cliente.get(f"/api/v1/incidentes/{iid}", headers=h("davi", "gestor"))).json()
    assert det["criado_por"] == "ana" and det["fechado_por"] == "bruno"
    passos = [(p["tipo"], p["quem"]) for p in det["historico"]]
    assert passos[0] == ("aberto", "ana")
    assert ("relato", "bruno") in passos
    assert ("assumido", "carla") in passos
    assert passos[-1] == ("encerrado", "bruno")
    assert det["historico"][-1]["texto"] == "Encerrado como resolvido: Disjuntor religado"
    quandos = [p["quando"] for p in det["historico"]]
    assert quandos == sorted(quandos)
    # Aba Concluídos: a lista de encerrados traz quem, quando e por quê
    fechados = (await cliente.get("/api/v1/incidentes", params={"status": "resolvido,falso_positivo"},
                                  headers=h("davi", "gestor"))).json()
    item = next(i for i in fechados if i["id"] == iid)
    assert item["fechado_por"] == "bruno" and item["causa_raiz"] == "Disjuntor religado" and item["fechado_em"]


async def test_falso_alarme_e_recuperacao_registram_quem_encerrou(cliente, db):
    d = await criar(cliente, sintoma="Alarme de porta aberta", ativo="rack-01")
    await cliente.patch(f"/api/v1/incidentes/{d['incidente_id']}/falso_positivo", params={"motivo": "Sensor com defeito"})
    det = (await cliente.get(f"/api/v1/incidentes/{d['incidente_id']}")).json()
    assert det["fechado_por"] == "anonimo"
    assert det["historico"][-1]["texto"] == "Marcado como falso alarme: Sensor com defeito"

    r = (await cliente.post("/api/v1/webhook/zabbix", json=zbx("9100"), headers=SERVICO)).json()
    await cliente.post("/api/v1/webhook/zabbix", json=zbx("9100", "RESOLVED"), headers=SERVICO)
    det = (await cliente.get(f"/api/v1/incidentes/{r['incidente_id']}")).json()
    assert det["fechado_por"] == "zabbix"
    assert [p["tipo"] for p in det["historico"]] == ["aberto", "acionamento", "recuperado", "encerrado"]


# ── S6: e-mail, inventário, topologia e avaliação ───────────────────
async def test_relato_por_email(cliente, db):
    r = await cliente.post("/api/v1/ingestao/email", headers=SERVICO, json={
        "remetente": "operador@ufrgs.br", "assunto": "Storage 01 com disco falhando",
        "corpo": "O storage da sala B acendeu LED âmbar"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["fonte"] == "email" and d["ativo_id"] == "storage-01" and d["confianca"] == 0.6


async def test_inventario_persistido(cliente, db):
    await db.execute(text("DELETE FROM qr_codes WHERE qr_code = 'CESUP-TST-001'"))
    await db.commit()
    r = await cliente.post("/api/v1/ativos/", json={"qr_code": "cesup-tst-001", "ativo_id": "srv-teste",
                                                    "nome": "Servidor Teste", "sala": "sala-A", "rack": "rack-01"})
    assert r.status_code == 201
    assert (await cliente.get("/api/v1/ativos/qr/CESUP-TST-001")).json()["ativo_id"] == "srv-teste"
    n = (await db.execute(text("SELECT count(*) FROM qr_codes WHERE qr_code = 'CESUP-TST-001'"))).scalar()
    assert n == 1
    await db.execute(text("DELETE FROM qr_codes WHERE qr_code = 'CESUP-TST-001'"))
    await db.commit()


async def test_topologia_no_banco(cliente, db):
    d = (await cliente.get("/api/v1/topologia/distancia", params={"a": "ups-sala-a-1", "b": "srv-node-001"})).json()
    assert d["saltos"] == 3 and d["score"] == 0.45


async def test_avaliacao_exporta_e_calcula(cliente, db):
    await criar(cliente, sintoma="Temperatura alta")
    await criar(cliente, ativo="storage-01", sala="sala-B", sintoma="Disco cheio")
    r = await cliente.get("/api/v1/avaliacao/pares.csv")
    assert r.status_code == 200 and r.text.startswith("par_id;evento_a")
    linhas = r.text.strip().splitlines()
    assert len(linhas) == 2
    rotulado = linhas[0] + "\n" + linhas[1].rstrip(";") + ";0;0\n"
    res = (await cliente.post("/api/v1/avaliacao/resultado",
                              files={"arquivo": ("rotulado.csv", rotulado.encode(), "text/csv")})).json()
    assert res["pares_avaliados"] == 1


# ── S5: análise de mídia ────────────────────────────────────────────
async def test_foto_anexada_vai_para_analise_e_aparece_no_incidente(cliente, db, fila, monkeypatch):
    from app.workers import tasks
    from app.services import visao
    d = await criar(cliente, sintoma="LED vermelho no storage", ativo="storage-01", sala="sala-B",
                    evidencias=["/api/v1/evidencias/arquivo/evidencias/abc.jpg"])
    assert ("analisar_midia", (d["incidente_id"], "/api/v1/evidencias/arquivo/evidencias/abc.jpg")) in fila

    class Corpo:
        def read(self): return b"\xff\xd8jpeg"
    monkeypatch.setattr("app.services.s3_client.baixar_evidencia", lambda key: {"Body": Corpo(), "ContentType": "image/jpeg"})
    monkeypatch.setattr(settings, "VISION_URL", "http://gpu/v1")

    async def analisar(dados, tipo, mime):
        return {"modelo": "teste-vl", "descricao": "LED vermelho no controlador A", "dados": {"leds": ["vermelho"]}}
    monkeypatch.setattr(visao, "analisar", analisar)
    await tasks._analisar_midia(d["incidente_id"], "/api/v1/evidencias/arquivo/evidencias/abc.jpg")
    det = (await cliente.get(f"/api/v1/incidentes/{d['incidente_id']}")).json()
    assert det["analises"][0]["descricao"] == "LED vermelho no controlador A"


async def test_status_da_ia_sem_gpu(cliente):
    s = (await cliente.get("/api/v1/ia/status")).json()
    assert s["visao"]["ativa"] is False and s["embeddings"]["modelo"] == "local-v2"
    assert s["transcricao"]["dispositivo"] == "cpu"
