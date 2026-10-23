"""
CESUP — Vigia externo (dead man's switch)
Bate coração na API a cada INTERVAL_SECONDS.
2 falhas consecutivas → SMS via modem GSM.
"""
import os, time, logging, requests, schedule

API_URL      = os.environ.get("API_HEARTBEAT_URL", "http://api:8000/api/v1/heartbeat")
API_TOKEN    = os.environ.get("API_TOKEN", "")
INTERVAL     = int(os.environ.get("INTERVAL_SECONDS", 60))
GSM_NUMBER   = os.environ.get("ALERT_GSM_NUMBER", "")
GAMMU_CONFIG = os.environ.get("GAMMU_CONFIG", "/etc/gammu/gammurc")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vigia")
falhas = 0

def enviar_sms(numero, msg):
    try:
        import gammu
        sm = gammu.StateMachine()
        sm.ReadConfig(Filename=GAMMU_CONFIG)
        sm.Init()
        sm.SendSMS({"Text": msg[:160], "SMSC": {"Location": 1}, "Number": numero})
        log.info(f"SMS enviado para {numero}")
    except Exception as e:
        log.error(f"Erro ao enviar SMS: {e}")

def bater_coracao():
    global falhas
    try:
        headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
        r = requests.get(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            falhas = 0
            log.info("heartbeat OK")
        else:
            falhas += 1
            log.warning(f"HTTP {r.status_code} (falhas={falhas})")
    except Exception as e:
        falhas += 1
        log.error(f"heartbeat falhou: {e} (falhas={falhas})")

    if falhas >= 2:
        log.critical("SISTEMA IRRESPONSIVO — disparando alerta!")
        if GSM_NUMBER:
            enviar_sms(GSM_NUMBER, "CESUP ALERTA: sistema irresponsivo! Verificar urgente.")
        falhas = 0

schedule.every(INTERVAL).seconds.do(bater_coracao)
log.info(f"Vigia iniciado — intervalo={INTERVAL}s destino={API_URL}")
bater_coracao()
while True:
    schedule.run_pending()
    time.sleep(1)
