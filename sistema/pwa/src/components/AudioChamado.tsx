// AudioChamado.tsx — Relato por voz → transcrição no servidor → revisão → chamado
import { useEffect, useRef, useState } from 'react'

interface Ativo { ativo_id: string; nome: string; sala: string; rack?: string }
interface Sugestao {
  sintoma: string; ativo_id: string | null; ativo_nome: string | null
  sala: string | null; rack: string | null
  seguranca_pessoas: boolean; prioridade_prevista: string
}
interface Props {
  api: string
  ativoInicial?: Ativo | null       // ativo já lido pelo QR Code, se houver
  onCriado: (prioridade: string) => void
}

const COR: Record<string, string> = { P1: '#dc2626', P2: '#ea580c', P3: '#ca8a04', P4: '#16a34a' }
const LIMITE_S = 120

// Chrome/Android gravam WebM/Opus; o Safari do iPhone só grava MP4/AAC
function formatoGravacao(): string {
  const tipos = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac']
  return tipos.find(t => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) || ''
}
const extensao = (tipo: string) => tipo.includes('mp4') || tipo.includes('aac') ? 'm4a' : 'webm'

export function AudioChamado({ api, ativoInicial, onCriado }: Props) {
  const [gravando, setGravando]   = useState(false)
  const [segundos, setSegundos]   = useState(0)
  const [ocupado, setOcupado]     = useState<'' | 'transcrevendo' | 'analisando' | 'enviando'>('')
  const [erro, setErro]           = useState('')
  const [texto, setTexto]         = useState('')
  const [urlAudio, setUrlAudio]   = useState<string | null>(null)
  const [revisar, setRevisar]     = useState(false)
  const [prioridade, setPrio]     = useState('')
  const [ativos, setAtivos]       = useState<Ativo[]>([])
  const [campos, setCampos] = useState({
    ativo_id: ativoInicial?.ativo_id || '', sala: ativoInicial?.sala || '',
    rack: ativoInicial?.rack || '', seguranca_pessoas: false,
  })
  const recRef    = useRef<MediaRecorder | null>(null)
  const pedacos   = useRef<Blob[]>([])
  const timer     = useRef<number | null>(null)
  const arquivoRef = useRef<HTMLInputElement>(null)

  // Gravar exige HTTPS (ou localhost); sem isso, o técnico envia um arquivo de áudio
  const podeGravar = window.isSecureContext && !!navigator.mediaDevices?.getUserMedia && !!formatoGravacao()

  useEffect(() => {
    fetch(`${api}/v1/ativos/`).then(r => r.json()).then(setAtivos).catch(() => {})
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [api])

  // Relato longo: encerra sozinho no limite de tempo
  useEffect(() => { if (gravando && segundos >= LIMITE_S) parar() }, [gravando, segundos])

  function aplicarSugestao(s: Sugestao) {
    setPrio(s.prioridade_prevista)
    setCampos(c => ({
      // Ativo do QR Code prevalece sobre o citado na fala
      ativo_id: ativoInicial?.ativo_id || s.ativo_id || c.ativo_id,
      sala: ativoInicial?.sala || s.sala || c.sala,
      rack: ativoInicial?.rack || s.rack || c.rack,
      seguranca_pessoas: s.seguranca_pessoas || c.seguranca_pessoas,
    }))
  }

  async function transcrever(audio: Blob, nome: string) {
    setOcupado('transcrevendo'); setErro('')
    try {
      const fd = new FormData(); fd.append('audio', audio, nome)
      const r = await fetch(`${api}/v1/transcricao/voz`, { method: 'POST', body: fd })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Falha na transcrição')
      setTexto(d.texto); setUrlAudio(d.url_audio); setRevisar(d.requer_revisao)
      aplicarSugestao(d.sugestao)
      if (!d.texto) setErro('Não foi possível transcrever. Digite o relato abaixo.')
    } catch (e: any) {
      setErro(e.message)
    } finally { setOcupado('') }
  }

  async function iniciar() {
    setErro('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const tipo = formatoGravacao()
      const rec = new MediaRecorder(stream, { mimeType: tipo })
      pedacos.current = []
      rec.ondataavailable = e => { if (e.data.size > 0) pedacos.current.push(e.data) }
      rec.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(pedacos.current, { type: tipo.split(';')[0] })
        transcrever(blob, `relato.${extensao(tipo)}`)
      }
      rec.start()
      recRef.current = rec
      setGravando(true); setSegundos(0)
      timer.current = window.setInterval(() => setSegundos(s => s + 1), 1000)
    } catch {
      setErro('Microfone não autorizado. Permita o acesso ao microfone ou envie um arquivo de áudio.')
    }
  }

  function parar() {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
    if (recRef.current?.state === 'recording') recRef.current.stop()
    setGravando(false)
  }

  function escolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) transcrever(f, f.name)
    if (arquivoRef.current) arquivoRef.current.value = ''
  }

  async function analisarDeNovo() {
    if (!texto.trim()) return
    setOcupado('analisando')
    try {
      const r = await fetch(`${api}/v1/transcricao/interpretar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto }),
      })
      if (r.ok) aplicarSugestao(await r.json())
    } finally { setOcupado('') }
  }

  async function criarChamado(e: React.FormEvent) {
    e.preventDefault(); setOcupado('enviando'); setErro('')
    try {
      const r = await fetch(`${api}/v1/incidentes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fonte: 'pessoa',
          ativo_id: campos.ativo_id,
          sintoma: texto.trim(),
          local: { sala: campos.sala, rack: campos.rack || null },
          confianca: 1.0,                    // relato revisado pelo técnico
          seguranca_pessoas: campos.seguranca_pessoas,
          evidencias: urlAudio ? [urlAudio] : [],
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Erro ao criar chamado')
      onCriado(d.prioridade)
      setTexto(''); setUrlAudio(null); setPrio(''); setRevisar(false)
      setCampos({ ativo_id: ativoInicial?.ativo_id || '', sala: ativoInicial?.sala || '', rack: ativoInicial?.rack || '', seguranca_pessoas: false })
    } catch (e: any) {
      setErro(e.message)
    } finally { setOcupado('') }
  }

  const inp: React.CSSProperties = { padding: 10, borderRadius: 6, border: '1px solid #d1d5db', fontSize: 15, width: '100%', boxSizing: 'border-box' }
  const btn = (bg = '#1e3a5f', color = '#fff'): React.CSSProperties => ({
    padding: '12px 16px', background: bg, color, border: 'none', borderRadius: 6,
    cursor: 'pointer', fontWeight: 600, fontSize: 16, width: '100%',
  })
  const mmss = `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, '0')}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p style={{ color: '#6b7280', margin: 0 }}>
        Fale o que está acontecendo: o ativo, o local e o sintoma. O áudio é transcrito no servidor do CESUP e vira um chamado depois da sua revisão.
      </p>

      {ativoInicial && (
        <div style={{ padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 14 }}>
          📷 Ativo via QR: <strong>{ativoInicial.nome}</strong> — {ativoInicial.sala}
        </div>
      )}

      {/* 1. Captura */}
      {podeGravar ? (
        <button type="button" onClick={gravando ? parar : iniciar} disabled={!!ocupado}
          style={btn(gravando ? '#dc2626' : '#1e3a5f')}>
          {gravando ? `⏹ Parar e transcrever (${mmss})` : '🎙 Gravar relato'}
        </button>
      ) : (
        <p style={{ margin: 0, padding: 10, background: '#fef9c3', borderRadius: 6, color: '#854d0e', fontSize: 14 }}>
          Para gravar pelo microfone, abra o sistema em <strong>https://</strong>. Você ainda pode enviar um áudio gravado no celular.
        </p>
      )}
      <label style={{ ...btn('#e5e7eb', '#000'), display: 'block', textAlign: 'center', boxSizing: 'border-box' }}>
        📁 Enviar arquivo de áudio
        <input ref={arquivoRef} type="file" accept="audio/*" style={{ display: 'none' }}
          onChange={escolherArquivo} disabled={!!ocupado} />
      </label>

      {ocupado === 'transcrevendo' && (
        <p style={{ margin: 0, color: '#1d4ed8', textAlign: 'center' }}>Transcrevendo o áudio…</p>
      )}
      {erro && (
        <p style={{ margin: 0, padding: 10, background: '#fee2e2', borderRadius: 6, color: '#dc2626' }}>{erro}</p>
      )}

      {/* 2. Revisão e chamado */}
      {(texto || urlAudio || erro) && !ocupado.startsWith('trans') && (
        <form onSubmit={criarChamado} style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
          <label style={{ fontWeight: 600, color: '#374151' }}>
            Relato {revisar && <span style={{ color: '#ca8a04', fontWeight: 500 }}>· revise a transcrição</span>}
          </label>
          <textarea required rows={4} style={{ ...inp, resize: 'vertical' }}
            value={texto} onChange={e => setTexto(e.target.value)} />
          <button type="button" onClick={analisarDeNovo} disabled={!!ocupado || !texto.trim()}
            style={{ ...btn('#e5e7eb', '#000'), fontSize: 14, padding: '8px 12px' }}>
            {ocupado === 'analisando' ? 'Analisando…' : '↻ Analisar o texto de novo'}
          </button>

          <input required list="lista-ativos" placeholder="Ativo (ex.: srv-node-001)" style={inp}
            value={campos.ativo_id} onChange={e => {
              const a = ativos.find(x => x.ativo_id === e.target.value)
              setCampos(c => ({ ...c, ativo_id: e.target.value, ...(a ? { sala: a.sala, rack: a.rack || '' } : {}) }))
            }} />
          <datalist id="lista-ativos">
            {ativos.map(a => <option key={a.ativo_id} value={a.ativo_id}>{a.nome}</option>)}
          </datalist>
          <div style={{ display: 'flex', gap: 8 }}>
            <input required placeholder="Sala" style={inp}
              value={campos.sala} onChange={e => setCampos({ ...campos, sala: e.target.value })} />
            <input placeholder="Rack" style={inp}
              value={campos.rack} onChange={e => setCampos({ ...campos, rack: e.target.value })} />
          </div>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={campos.seguranca_pessoas}
              onChange={e => setCampos({ ...campos, seguranca_pessoas: e.target.checked })} />
            <span style={{ color: '#dc2626', fontWeight: 500 }}>⚠ Risco à segurança de pessoas</span>
          </label>

          {prioridade && (
            <p style={{ margin: 0, fontSize: 14, color: '#374151' }}>
              Prioridade prevista: <strong style={{ color: COR[campos.seguranca_pessoas ? 'P1' : prioridade] }}>
                {campos.seguranca_pessoas ? 'P1' : prioridade}</strong>
              {urlAudio && ' · áudio anexado ao chamado'}
            </p>
          )}

          <button type="submit" disabled={!!ocupado || !texto.trim()} style={btn()}>
            {ocupado === 'enviando' ? 'Criando chamado…' : '✔ Criar chamado'}
          </button>
        </form>
      )}
    </div>
  )
}
