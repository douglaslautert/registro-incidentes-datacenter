// FotoVideo.tsx — Foto, áudio ou vídeo do problema, anexado a um incidente aberto
import { useEffect, useRef, useState } from 'react'
import { Evidencias } from './Evidencias'

interface IncidenteResumo { id: string; titulo?: string; prioridade: string; ativo_id: string }
interface Props {
  api: string
  incidenteInicial: string | null      // incidente já selecionado na aba Abertos
  onEnviado: (msg: string) => void
}

const COR: Record<string, string> = { P1: 'var(--erro)', P2: 'var(--p2)', P3: 'var(--p3)', P4: 'var(--ok)' }

export function FotoVideo({ api, incidenteInicial, onEnviado }: Props) {
  const [incidentes, setIncidentes] = useState<IncidenteResumo[]>([])
  const [selecionado, setSel]       = useState(incidenteInicial || '')
  const [evidencias, setEvidencias] = useState<string[]>([])
  const [progresso, setProgresso]   = useState<number | null>(null)
  const [erro, setErro]             = useState('')
  const fotoRef    = useRef<HTMLInputElement>(null)
  const videoRef   = useRef<HTMLInputElement>(null)
  const galeriaRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch(`${api}/v1/incidentes`).then(r => r.json()).then(setIncidentes).catch(() => {})
  }, [api])

  async function carregarEvidencias(id: string) {
    if (!id) { setEvidencias([]); return }
    try {
      const r = await fetch(`${api}/v1/incidentes/${id}`)
      setEvidencias(r.ok ? (await r.json()).evidencias || [] : [])
    } catch { setEvidencias([]) }
  }
  useEffect(() => { carregarEvidencias(selecionado) }, [selecionado])

  // XMLHttpRequest em vez de fetch: só ele informa o progresso do envio (vídeos são grandes)
  function enviar(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0]
    e.target.value = ''
    if (!arquivo || !selecionado) return
    setErro(''); setProgresso(0)
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${api}/v1/evidencias/upload?incidente_id=${encodeURIComponent(selecionado)}`)
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) setProgresso(Math.round(100 * ev.loaded / ev.total)) }
    xhr.onload = () => {
      setProgresso(null)
      let d: any = {}
      try { d = JSON.parse(xhr.responseText) } catch { /* resposta não-JSON (ex.: 413 do nginx) */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        onEnviado(`✔ ${d.content_type?.startsWith('video/') ? 'Vídeo anexado' : d.content_type?.startsWith('audio/') ? 'Áudio anexado' : 'Foto anexada'} ao incidente`)
        carregarEvidencias(selecionado)
      } else {
        setErro(d.detail || (xhr.status === 413 ? 'Arquivo grande demais' : `Falha no envio (HTTP ${xhr.status})`))
      }
    }
    xhr.onerror = () => { setProgresso(null); setErro('Sem conexão com o servidor') }
    xhr.send(fd)
  }

  const btn = (bg = 'var(--cor-primaria)', color = 'var(--cor-texto-inverso)'): React.CSSProperties => ({
    padding: '12px 16px', background: bg, color, border: 'none', borderRadius: 8, cursor: 'pointer',
    fontWeight: 600, fontSize: 16, display: 'block', textAlign: 'center', boxSizing: 'border-box',
  })
  const ocupado = progresso !== null
  const desabilitado = ocupado || !selecionado

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label style={{ fontWeight: 600, color: 'var(--cor-texto)' }} htmlFor="incidente-foto">A qual incidente anexar?</label>
      <select id="incidente-foto" value={selecionado} onChange={e => setSel(e.target.value)}
        style={{ padding: 10, borderRadius: 8, border: '1px solid #d1d5db', fontSize: 15 }}>
        <option value="">Escolha o incidente…</option>
        {incidentes.map(i => (
          <option key={i.id} value={i.id}>{i.prioridade} · {(i.titulo || i.ativo_id).replace(/^(\[[^\]]+\]\s*)+/, '')}</option>
        ))}
      </select>
      {!incidentes.length && (
        <p style={{ margin: 0, fontSize: 14, color: 'var(--cor-texto-suave)' }}>Nenhum incidente aberto. Registre um antes de anexar arquivos.</p>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, opacity: desabilitado ? 0.5 : 1 }}>
        <label style={btn()}>
          📷 Tirar foto
          <input ref={fotoRef} type="file" accept="image/*" capture="environment"
            style={{ display: 'none' }} onChange={enviar} disabled={desabilitado} />
        </label>
        <label style={btn()}>
          🎥 Gravar vídeo
          <input ref={videoRef} type="file" accept="video/*" capture="environment"
            style={{ display: 'none' }} onChange={enviar} disabled={desabilitado} />
        </label>
        <label style={{ ...btn('var(--cor-superficie-2)', 'var(--cor-texto)'), gridColumn: '1 / -1' }}>
          📁 Escolher arquivo (foto, áudio ou vídeo)
          <input ref={galeriaRef} type="file" accept="image/*,video/*,audio/*,.m4a,.mp3,.weba"
            style={{ display: 'none' }} onChange={enviar} disabled={desabilitado} />
        </label>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--cor-texto-suave)' }}>Fotos e áudios até 20 MB · vídeos até 90 MB (prefira vídeos curtos)</p>

      {ocupado && (
        <div>
          <p style={{ margin: '0 0 4px', color: 'var(--info)' }}>Enviando… {progresso}%</p>
          <div style={{ height: 8, background: 'var(--cor-superficie-2)', borderRadius: 4 }}>
            <div style={{ height: 8, width: `${progresso}%`, background: 'var(--info)', borderRadius: 4, transition: 'width .2s' }} />
          </div>
        </div>
      )}
      {erro && <p style={{ margin: 0, padding: 10, background: 'var(--erro-fundo)', borderRadius: 8, color: 'var(--erro)' }}>{erro}</p>}

      {selecionado && (
        <div>
          <p style={{ fontWeight: 600, color: 'var(--cor-texto)', margin: '4px 0 8px' }}>
            Anexos do incidente{' '}
            <span style={{ color: COR[incidentes.find(i => i.id === selecionado)?.prioridade || ''] }}>
              {incidentes.find(i => i.id === selecionado)?.prioridade}
            </span>
          </p>
          <Evidencias urls={evidencias} />
        </div>
      )}
    </div>
  )
}
