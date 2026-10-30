"""Motor de prioridade P1-P4 — regras determinísticas, nunca IA."""
import re, unicodedata

def calcular_prioridade(
    seguranca_pessoas: bool,
    impacto: int,
    urgencia: int,
    confianca: float
) -> str:
    # Segurança de pessoas sempre é P1
    if seguranca_pessoas:
        return "P1"
    score = impacto * urgencia * confianca
    if score >= 18: return "P1"
    if score >= 10: return "P2"
    if score >= 5:  return "P3"
    return "P4"

def inferir_impacto_urgencia(sintoma: str, fonte: str) -> tuple[int, int]:
    """Valores padrão por tipo de sintoma até calibração manual."""
    # Sem acentos: relatos em texto livre trazem "água", "memória", "fumaça"
    sintoma = unicodedata.normalize("NFKD", sintoma.lower()).encode("ascii", "ignore").decode()
    # "aquec"/"quec": superaquecimento, sobreaquecimento, aquecendo e grafias da transcrição
    # ("sobequecimento"); "esquec" (esquecimento) fica de fora
    if any(k in sintoma for k in ["temperatura", "aquec", "thermal", "quente", "calor"]) \
            or re.search(r"(?<!es)quec(imento|endo|eu)", sintoma):
        return 4, 5
    if any(k in sintoma for k in ["ups", "bateria", "energia", "power"]):
        return 5, 5
    if any(k in sintoma for k in ["disco", "storage", "raid", "disk"]):
        return 4, 3
    if any(k in sintoma for k in ["rede", "switch", "network", "link"]):
        return 3, 4
    if any(k in sintoma for k in ["cpu", "memoria", "memory"]):
        return 3, 3
    if any(k in sintoma for k in ["agua", "water", "curto", "short", "psu", "falha_psu",
                                     "incendio", "fire", "smoke", "fumaca"]):
        return 5, 5  # risco à vida — máximo impacto
    # Zabbix tem impacto maior por ser automático
    if fonte == "zabbix":
        return 3, 3
    return 2, 2
