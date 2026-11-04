"""Enfileira tarefas do Celery pelo nome, sem importar o módulo do worker (evita import
circular e deixa os testes trocarem esta função). Fila fora do ar não derruba a API."""
import logging

log = logging.getLogger("tarefas")


def enfileirar(nome: str, *args) -> bool:
    try:
        from app.workers.tasks import celery_app
        celery_app.send_task(f"app.workers.tasks.{nome}", args=list(args))
        return True
    except Exception as e:
        log.warning(f"Tarefa {nome} não enfileirada (fila indisponível?): {e}")
        return False
