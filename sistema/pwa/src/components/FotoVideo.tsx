// FotoVideo.tsx — Foto ou vídeo do problema, anexado a um incidente aberto
import { useEffect, useRef, useState } from 'react'
import { Evidencias } from './Evidencias'

interface IncidenteResumo { id: string; titulo?: string; prioridade: string; ativo_id: string }
interface Props {
  api: string
  incidenteInicial: string | null      // incidente já selecionado na aba Abertos
  onEnviado: (msg: string) => void
}

const COR: Record<string, string> = { P1: '#dc2626', P2: '#ea580c', P3: '#ca8a04', P4: '#16a34a' }

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
        onEnviado(`✔ ${d.content_type?.startsWith('video/') ? 'Vídeo' : 'Foto'} anexado ao incidente`)
        carregarEvidencias(selecionado)
      } else {
        setErro(d.detail || (xhr.status === 413 ? 'Arquivo grande demais' : `Falha no envio (HTTP ${xhr.status})`))
      }
    }
    xhr.onerror = () => { setProgresso(null); setErro('Sem conexão com o servidor') }
    xhr.send(fd)
  }

  const btn = (bg = '#1e3a5f', color = '#fff'): React.CSSProperties => ({
    padding: '12px 16px', background: bg, color, border: 'none', borderRadius: 6, cursor: 'pointer',
    fontWeight: 600, fontSize: 16, display: 'block', textAlign: 'center', boxSizing: 'border-box',
  })
  const ocupado = progresso !== null
  const desabilitado = ocupado || !selecionado

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label style={{ fontWeight: 600, color: '#374151' }} htmlFor="incidente-foto">Incidente</label>
      <select id="incidente-foto" value={selecionado} onChange={e => setSel(e.target.value)}
        style={{ padding: 10, borderRadius: 6, border: '1px solid #d1d5db', fontSize: 15 }}>
        <option value="">Escolha o incidente…</option>
        {incidentes.map(i => (
          <option key={i.id} value={i.id}>{i.prioridade} · {i.titulo || i.ativo_id}</option>
        ))}
      </select>
      {!incidentes.length && (
        <p style={{ margin: 0, fontSize: 14, color: '#6b7280' }}>Nenhum incidente aberto. Registre um antes de anexar fotos.</p>
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
        <label style={{ ...btn('#e5e7eb', '#000'), gridColumn: '1 / -1' }}>
          🖼 Escolher da galeria
          <input ref={galeriaRef} type="file" accept="image/*,video/*"
            style={{ display: 'none' }} onChange={enviar} disabled={desabilitado} />
        </label>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>Fotos até 20 MB · vídeos até 90 MB (prefira vídeos curtos)</p>

      {ocupado && (
        <div>
          <p style={{ margin: '0 0 4px', color: '#1d4ed8' }}>Enviando… {progresso}%</p>
          <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4 }}>
            <div style={{ height: 8, width: `${progresso}%`, background: '#1d4ed8', borderRadius: 4, transition: 'width .2s' }} />
          </div>
        </div>
      )}
      {erro && <p style={{ margin: 0, padding: 10, background: '#fee2e2', borderRadius: 6, color: '#dc2626' }}>{erro}</p>}

      {selecionado && (
        <div>
          <p style={{ fontWeight: 600, color: '#374151', margin: '4px 0 8px' }}>
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
