// Evidencias.tsx — Miniaturas das fotos, vídeos e áudios anexados a um incidente
interface Props { urls: string[] }

function tipo(url: string): 'imagem' | 'heic' | 'video' | 'audio' | 'outro' {
  const ext = url.split('?')[0].split('.').pop()?.toLowerCase() || ''
  if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) return 'imagem'
  if (['heic', 'heif'].includes(ext)) return 'heic'      // só o Safari exibe
  if (['mp4', 'mov', 'webm'].includes(ext)) return 'video'
  // áudio WebM é salvo como .weba para não confundir com vídeo WebM
  if (['weba', 'm4a', 'ogg', 'wav', 'mp3'].includes(ext)) return 'audio'
  return 'outro'
}

export function Evidencias({ urls }: Props) {
  if (!urls.length) {
    return <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>Nenhuma foto, vídeo ou áudio anexado.</p>
  }
  const caixa: React.CSSProperties = { width: '100%', borderRadius: 6, background: '#000', display: 'block' }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
      {urls.map(u => {
        const t = tipo(u)
        return (
          <div key={u} onClick={e => e.stopPropagation()}>
            {t === 'imagem' && (
              <a href={u} target="_blank" rel="noreferrer">
                <img src={u} alt="Foto anexada" loading="lazy"
                  style={{ ...caixa, aspectRatio: '1', objectFit: 'cover' }} />
              </a>
            )}
            {t === 'video' && (
              <video src={u} controls playsInline preload="metadata" style={{ ...caixa, aspectRatio: '1' }} />
            )}
            {t === 'audio' && <audio src={u} controls preload="none" style={{ width: '100%' }} />}
            {(t === 'heic' || t === 'outro') && (
              <a href={u} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>Abrir anexo</a>
            )}
          </div>
        )
      })}
    </div>
  )
}
