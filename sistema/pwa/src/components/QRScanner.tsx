// QRScanner.tsx — Leitor de QR Code para identificar ativos (Sprint 5)
import React, { useEffect, useRef, useState } from "react";

interface Ativo {
  ativo_id: string;
  nome: string;
  sala: string;
  rack?: string;
  tipo: string;
}

interface Props {
  onAtivo: (ativo: Ativo) => void;
}

export const QRScanner: React.FC<Props> = ({ onAtivo }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ativo, setAtivo] = useState<Ativo | null>(null);
  const [erro, setErro] = useState("");
  const [ativo_manual, setAtivoManual] = useState("");

  useEffect(() => {
    // jsQR via câmera (instalado no package.json)
    let animFrame: number;
    const iniciar = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d")!;
      const scan = () => {
        const v = videoRef.current;
        if (v && v.readyState === v.HAVE_ENOUGH_DATA) {
          canvas.width = v.videoWidth; canvas.height = v.videoHeight;
          ctx.drawImage(v, 0, 0);
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          // @ts-ignore
          const code = window.jsQR?.(img.data, img.width, img.height);
          if (code?.data) buscarAtivo(code.data);
        }
        animFrame = requestAnimationFrame(scan);
      };
      animFrame = requestAnimationFrame(scan);
    };
    iniciar().catch(() => setErro("Câmera indisponível"));
    return () => cancelAnimationFrame(animFrame);
  }, []);

  const buscarAtivo = async (codigo: string) => {
    try {
      const res = await fetch(`/api/v1/ativos/qr/${codigo}`);
      if (res.ok) {
        const a = await res.json();
        setAtivo(a); onAtivo(a);
      } else {
        setErro(`QR não mapeado: ${codigo}`);
      }
    } catch { setErro("Erro ao buscar ativo"); }
  };

  const buscarManual = () => buscarAtivo(ativo_manual.trim());

  return (
    <div>
      <video ref={videoRef} style={{ width: "100%", borderRadius: 8 }} muted playsInline />
      {ativo && (
        <div style={{ marginTop: 8, padding: 12, background: "#e6f4ea", borderRadius: 6 }}>
          <strong>{ativo.nome}</strong><br/>
          Sala: {ativo.sala} · Rack: {ativo.rack || "—"} · Tipo: {ativo.tipo}
        </div>
      )}
      {erro && <p style={{ color: "red" }}>{erro}</p>}
      <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
        <input value={ativo_manual} onChange={e => setAtivoManual(e.target.value)}
               placeholder="Código QR manual" style={{ flex: 1, padding: 8 }} />
        <button onClick={buscarManual}>Buscar</button>
      </div>
    </div>
  );
};
