// VoiceCapture.tsx — Gravação de voz e transcrição automática (Sprint 5)
import React, { useState, useRef } from "react";

interface Props {
  incidenteId: string;
  onTranscricao: (texto: string, confianca: number) => void;
}

export const VoiceCapture: React.FC<Props> = ({ incidenteId, onTranscricao }) => {
  const [gravando, setGravando] = useState(false);
  const [transcrevendo, setTranscrevendo] = useState(false);
  const [texto, setTexto] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const iniciarGravacao = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];
    rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    rec.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setTranscrevendo(true);
      try {
        const fd = new FormData();
        fd.append("audio", blob, "gravacao.webm");
        const res = await fetch(
          `/api/v1/transcricao/voz?incidente_id=${incidenteId}`,
          { method: "POST", body: fd }
        );
        const data = await res.json();
        setTexto(data.texto);
        onTranscricao(data.texto, data.confianca);
      } finally {
        setTranscrevendo(false);
        stream.getTracks().forEach(t => t.stop());
      }
    };
    recorderRef.current = rec;
    rec.start();
    setGravando(true);
  };

  const pararGravacao = () => {
    recorderRef.current?.stop();
    setGravando(false);
  };

  return (
    <div>
      <button onClick={gravando ? pararGravacao : iniciarGravacao} disabled={transcrevendo}>
        {transcrevendo ? "Transcrevendo…" : gravando ? "⏹ Parar" : "🎙 Gravar relato"}
      </button>
      {texto && (
        <textarea
          value={texto}
          onChange={e => setTexto(e.target.value)}
          rows={3}
          style={{ width: "100%", marginTop: 8 }}
          placeholder="Transcrição — edite se necessário"
        />
      )}
    </div>
  );
};
