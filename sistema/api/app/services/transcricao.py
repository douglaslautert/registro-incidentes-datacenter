"""Serviço de transcrição de voz — Whisper local ou fallback por texto."""
import logging, os

log = logging.getLogger("transcricao")

def transcrever_audio(dados: bytes, content_type: str) -> dict:
    """
    Transcreve áudio para texto.
    Usa Whisper se disponível; caso contrário retorna placeholder para Sprint 6.
    """
    resultado = {
        "texto": "",
        "confianca": 0.0,
        "motor": "indisponivel",
        "duracao_segundos": None,
    }
    try:
        import whisper  # type: ignore
        import tempfile, soundfile as sf  # type: ignore
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(dados)
            tmp_path = tmp.name
        model = whisper.load_model("tiny")  # modelo leve para MVP
        res = model.transcribe(tmp_path, language="pt")
        os.unlink(tmp_path)
        resultado.update({
            "texto": res["text"].strip(),
            "confianca": 0.85,  # Whisper tiny ~85% pt-BR
            "motor": "whisper-tiny",
        })
        log.info(f"Transcrição Whisper: '{resultado['texto'][:60]}'")
    except ImportError:
        # Whisper não instalado — modo fallback: texto vazio para o técnico preencher
        resultado.update({
            "texto": "",
            "confianca": 0.0,
            "motor": "fallback-manual",
        })
        log.warning("Whisper não instalado — transcrição manual necessária")
    except Exception as e:
        log.error(f"Erro na transcrição: {e}")
        resultado["motor"] = f"erro: {e}"
    return resultado
