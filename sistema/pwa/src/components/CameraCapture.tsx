// CameraCapture.tsx — Captura de foto com câmera do celular (Sprint 5)
import React, { useRef, useState } from "react";

interface Props {
  incidenteId: string;
  onUpload: (url: string) => void;
}

export const CameraCapture: React.FC<Props> = ({ incidenteId, onUpload }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("arquivo", file);
      const res = await fetch(
        `/api/v1/evidencias/upload?incidente_id=${incidenteId}`,
        { method: "POST", body: fd }
      );
      const data = await res.json();
      if (res.ok) onUpload(data.url);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"  // câmera traseira do celular
        style={{ display: "none" }}
        onChange={handleCapture}
      />
      <button onClick={() => inputRef.current?.click()} disabled={uploading}>
        {uploading ? "Enviando…" : "📷 Tirar foto"}
      </button>
      {preview && <img src={preview} alt="preview" style={{ width: "100%", marginTop: 8 }} />}
    </div>
  );
};
