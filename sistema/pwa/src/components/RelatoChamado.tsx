// RelatoChamado.tsx — Relato por áudio ou vídeo → transcrição no servidor → revisão → chamado
// O áudio e o vídeo ficam guardados no S3 e anexados ao chamado (do vídeo, também o áudio extraído).
import { useEffect, useRef, useState } from 'react'
import { Evidencias } from './Evidencias'

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
const LIMITE_S = { audio: 120, video: 90 }   // vídeo a ~2,5 Mbit/s: 90 s ≈ 30 MB

// Chrome/Android gravam WebM/Opus; o Safari do iPhone só grava MP4/AAC
function formatoGravacao(): string {
  const tipos = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac']
  return tipos.find(t => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) || ''
}
// iPhone/iPad: Safari e Chrome usam o WebKit, cujo formato nativo é MP4
const ehIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
  (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent))
// Vídeo: WebM no Chrome/Android, MP4 no iPhone. Em ordem de preferência; os que o navegador
// diz aceitar mas falham ao gravar são pulados em iniciar().
function formatosGravacaoVideo(): string[] {
  const tipos = ehIOS ? ['video/mp4', 'video/webm;codecs=vp8,opus', 'video/webm']
                      : ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']
  return typeof MediaRecorder === 'undefined' ? [] : tipos.filter(t => MediaRecorder.isTypeSupported(t))
}
const formatoGravacaoVideo = () => formatosGravacaoVideo()[0] || ''
const extensao = (tipo: string) =>
  tipo.startsWith('video/') ? (tipo.includes('mp4') ? 'mp4' : 'webm')
    : tipo.includes('mp4') || tipo.includes('aac') ? 'm4a' : 'webm'
// Vídeo pelo tipo ou, se o navegador não informou (comum com .mov), pela extensão
const ehVideo = (f: Blob, nome: string) =>
  f.type.startsWith('video/') || (!f.type.startsWith('audio/') && /\.(mov|qt|mp4|m4v|webm)$/i.test(nome))

export function RelatoChamado({ api, ativoInicial, onCriado }: Props) {
  const [video, setVideo]         = useState(false)     // a mídia enviada é vídeo?
  const [gravando, setGravando]   = useState<'' | 'audio' | 'video'>('')
  const [previa, setPrevia]       = useState<MediaStream | null>(null)   // câmera ao vivo
  const [cameraNegada, setCameraNegada] = useState(false)   // mostra a câmera nativa como alternativa
  const [segundos, setSegundos]   = useState(0)
  const [ocupado, setOcupado]     = useState<'' | 'transcrevendo' | 'analisando' | 'enviando'>('')
  const [progresso, setProgresso] = useState<number | null>(null)
  const [erro, setErro]           = useState('')
  const [texto, setTexto]         = useState('')
  const [anexos, setAnexos]       = useState<string[]>([])
  const [revisar, setRevisar]     = useState(false)
  const [prioridade, setPrio]     = useState('')
  const [ativos, setAtivos]       = useState<Ativo[]>([])
  const [campos, setCampos] = useState({
    ativo_id: ativoInicial?.ativo_id || '', sala: ativoInicial?.sala || '',
    rack: ativoInicial?.rack || '', seguranca_pessoas: false,
  })
  const recRef   = useRef<MediaRecorder | null>(null)
  const pedacos  = useRef<Blob[]>([])
  const timer    = useRef<number | null>(null)

  // Gravar pelo microfone e pela câmera exige HTTPS (ou localhost); sem isso, o técnico envia um
  // arquivo, e o vídeo cai na câmera nativa do celular (input capture), que funciona sem essa API.
  const temMidia = window.isSecureContext && !!navigator.mediaDevices?.getUserMedia
  const podeGravarAudio = temMidia && !!formatoGravacao()
  const podeGravarVideo = temMidia && !!formatoGravacaoVideo()

  useEffect(() => {
    fetch(`${api}/v1/ativos/`).then(r => r.json()).then(setAtivos).catch(() => {})
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [api])

  // Relato longo: encerra sozinho no limite de tempo
  useEffect(() => { if (gravando && segundos >= LIMITE_S[gravando]) parar() }, [gravando, segundos])

  // Saiu da aba no meio da gravação: libera a câmera e o microfone
  useEffect(() => () => {
    const rec = recRef.current
    if (rec?.state === 'recording') { rec.onstop = null; rec.stop(); rec.stream.getTracks().forEach(t => t.stop()) }
  }, [])

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

  // XMLHttpRequest: mostra o progresso do envio (vídeos têm dezenas de MB)
  function transcrever(arquivo: Blob, nome: string) {
    const v = ehVideo(arquivo, nome)
    setVideo(v); setAnexos([])
    setOcupado('transcrevendo'); setErro(''); setProgresso(0)
    const fd = new FormData(); fd.append(v ? 'video' : 'audio', arquivo, nome)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${api}/v1/transcricao/${v ? 'video' : 'voz'}`)
    xhr.upload.onprogress = ev => {
      if (ev.lengthComputable) setProgresso(ev.loaded < ev.total ? Math.round(100 * ev.loaded / ev.total) : null)
    }
    xhr.onload = () => {
      setOcupado(''); setProgresso(null)
      let d: any = {}
      try { d = JSON.parse(xhr.responseText) } catch { /* resposta não-JSON (ex.: 413 do nginx) */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        setErro(d.detail || (xhr.status === 413 ? 'Arquivo grande demais' : `Falha no envio (HTTP ${xhr.status})`))
        return
      }
      // Vídeo: anexa o vídeo e o áudio extraído dele; áudio: só o áudio
      setTexto(d.texto); setAnexos([d.url_video, d.url_audio].filter(Boolean)); setRevisar(d.requer_revisao)
      aplicarSugestao(d.sugestao)
      if (d.motor === 'sem-audio') setErro('O vídeo não tem som. Digite o relato abaixo — o vídeo segue anexado.')
      else if (!d.texto) setErro('Não foi possível transcrever. Digite o relato abaixo.')
    }
    xhr.onerror = () => { setOcupado(''); setProgresso(null); setErro('Sem conexão com o servidor') }
    xhr.send(fd)
  }

  // Grava no primeiro formato que o navegador realmente consegue usar; sem nenhum, no padrão dele
  function comecarGravacao(stream: MediaStream, tipos: string[], opcoes: MediaRecorderOptions) {
    for (const tipo of [...tipos, '']) {
      try {
        const rec = new MediaRecorder(stream, tipo ? { ...opcoes, mimeType: tipo } : opcoes)
        rec.start(1000)   // pedaços de 1 s: o que foi gravado não se perde se a gravação cair
        return { rec, tipo: rec.mimeType || tipo }
      } catch { /* formato anunciado mas recusado (já visto no WebKit): tenta o próximo */ }
    }
    throw new Error('gravador')
  }

  // Mesmo fluxo para os dois: grava no app, mostra o tempo e, ao parar, envia para transcrever
  async function iniciar(midia: 'audio' | 'video') {
    setErro(''); setCameraNegada(false)
    const ehVid = midia === 'video'
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia(ehVid
        ? { audio: true, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } } }
        : { audio: true })
    } catch (e: any) {
      const nome = e?.name || ''
      if (ehVid) setCameraNegada(true)   // oferece a câmera nativa do celular, que não depende dessa permissão
      setErro(nome === 'NotAllowedError' || nome === 'SecurityError'
        ? (ehVid
            ? 'O navegador não liberou a câmera para este site. No iPhone: Ajustes › Safari › Câmera (ou Ajustes › Chrome › Câmera) → Permitir, e recarregue a página. Ou filme com a câmera do celular no botão abaixo.'
            : 'O navegador não liberou o microfone para este site. Permita o acesso ao microfone ou envie um arquivo de áudio.')
        : nome === 'NotReadableError' || nome === 'AbortError'
          ? `${ehVid ? 'A câmera' : 'O microfone'} está em uso por outro app. Feche-o e tente de novo.`
          : nome === 'NotFoundError' || nome === 'OverconstrainedError'
            ? `Nenhum${ehVid ? 'a câmera' : ' microfone'} encontrad${ehVid ? 'a' : 'o'} neste aparelho.`
            : `Não foi possível abrir ${ehVid ? 'a câmera' : 'o microfone'} (${nome || e}).`)
      return
    }
    try {
      const { rec, tipo } = ehVid
        ? comecarGravacao(stream, formatosGravacaoVideo(), { videoBitsPerSecond: 2_500_000, audioBitsPerSecond: 128_000 })
        : comecarGravacao(stream, [formatoGravacao()].filter(Boolean), {})
      // Sem tipo informado pelo navegador: o nativo de cada plataforma
      const base = tipo.split(';')[0] || (ehVid ? (ehIOS ? 'video/mp4' : 'video/webm') : (ehIOS ? 'audio/mp4' : 'audio/webm'))
      pedacos.current = []
      rec.ondataavailable = e => { if (e.data.size > 0) pedacos.current.push(e.data) }
      rec.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        setPrevia(null)
        transcrever(new Blob(pedacos.current, { type: base }), `relato.${extensao(base)}`)
      }
      recRef.current = rec
      if (ehVid) setPrevia(stream)
      setGravando(midia); setSegundos(0)
      timer.current = window.setInterval(() => setSegundos(s => s + 1), 1000)
    } catch {
      stream.getTracks().forEach(t => t.stop())
      if (ehVid) setCameraNegada(true)
      setErro(ehVid
        ? 'Este navegador não consegue gravar vídeo dentro do app. Filme com a câmera do celular no botão abaixo.'
        : 'Este navegador não consegue gravar áudio dentro do app. Envie um arquivo de áudio.')
    }
  }

  function parar() {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
    if (recRef.current?.state === 'recording') recRef.current.stop()
    setGravando('')
  }

  function escolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (f) transcrever(f, f.name)
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
          evidencias: anexos,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Erro ao criar chamado')
      onCriado(d.prioridade)
      setTexto(''); setAnexos([]); setPrio(''); setRevisar(false); setVideo(false)
      setCampos({ ativo_id: ativoInicial?.ativo_id || '', sala: ativoInicial?.sala || '', rack: ativoInicial?.rack || '', seguranca_pessoas: false })
    } catch (e: any) {
      setErro(e.message)
    } finally { setOcupado('') }
  }

  const inp: React.CSSProperties = { padding: 10, borderRadius: 6, border: '1px solid #d1d5db', fontSize: 15, width: '100%', boxSizing: 'border-box' }
  const btn = (bg = '#1e3a5f', color = '#fff'): React.CSSProperties => ({
    padding: '12px 16px', background: bg, color, border: 'none', borderRadius: 6,
    cursor: 'pointer', fontWeight: 600, fontSize: 16, width: '100%',
    display: 'block', textAlign: 'center', boxSizing: 'border-box',
  })
  const mmss = `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, '0')}`
  const nomeMidia = video ? 'vídeo' : 'áudio'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p style={{ color: '#6b7280', margin: 0 }}>
        Grave um áudio ou filme o problema falando o que está acontecendo: o ativo, o local e o sintoma.
        A fala é transcrita no servidor do CESUP e vira um chamado depois da sua revisão. O áudio e o vídeo ficam guardados e anexados ao chamado.
      </p>

      {ativoInicial && (
        <div style={{ padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 14 }}>
          📷 Ativo via QR: <strong>{ativoInicial.nome}</strong> — {ativoInicial.sala}
        </div>
      )}

      {/* 1. Captura */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {podeGravarAudio ? (
          <button type="button" onClick={gravando === 'audio' ? parar : () => iniciar('audio')}
            disabled={!!ocupado || gravando === 'video'}
            style={{ ...btn(gravando === 'audio' ? '#dc2626' : '#1e3a5f'), opacity: gravando === 'video' ? 0.5 : 1 }}>
            {gravando === 'audio' ? `⏹ Parar (${mmss})` : '🎙 Gravar áudio'}
          </button>
        ) : (
          <p style={{ margin: 0, padding: 8, background: '#fef9c3', borderRadius: 6, color: '#854d0e', fontSize: 13 }}>
            Gravar áudio exige <strong>https://</strong>
          </p>
        )}
        {podeGravarVideo ? (
          <button type="button" onClick={gravando === 'video' ? parar : () => iniciar('video')}
            disabled={!!ocupado || gravando === 'audio'}
            style={{ ...btn(gravando === 'video' ? '#dc2626' : '#1e3a5f'), opacity: gravando === 'audio' ? 0.5 : 1 }}>
            {gravando === 'video' ? `⏹ Parar (${mmss})` : '🎥 Gravar vídeo'}
          </button>
        ) : (
          /* Sem HTTPS: câmera nativa do celular, que funciona mesmo sem a API de gravação */
          <label style={{ ...btn(), opacity: ocupado || gravando ? 0.5 : 1 }}>
            🎥 Gravar vídeo
            <input type="file" accept="video/*" capture="environment" style={{ display: 'none' }}
              onChange={escolherArquivo} disabled={!!ocupado || !!gravando} />
          </label>
        )}
        {previa && (
          <div style={{ gridColumn: '1 / -1', position: 'relative' }}>
            <video muted playsInline autoPlay
              ref={el => { if (el && el.srcObject !== previa) el.srcObject = previa }}
              style={{ width: '100%', borderRadius: 6, background: '#000', display: 'block' }} />
            <span style={{ position: 'absolute', top: 8, left: 8, padding: '2px 8px', borderRadius: 4,
              background: '#dc2626', color: '#fff', fontSize: 14, fontWeight: 600 }}>
              ● {mmss} / 1:30
            </span>
          </div>
        )}
        <label style={{ ...btn('#e5e7eb', '#000'), gridColumn: '1 / -1', opacity: ocupado || gravando ? 0.5 : 1 }}>
          📁 Enviar áudio ou vídeo do celular
          <input type="file" accept="audio/*,video/*,.mov,.m4a" style={{ display: 'none' }}
            onChange={escolherArquivo} disabled={!!ocupado || !!gravando} />
        </label>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>
        Gravação: áudio até 2 min, vídeo até 1min30 · Envio: áudios até 10 MB, vídeos até 90 MB (MP4, MOV/QuickTime, WebM)
      </p>

      {ocupado === 'transcrevendo' && (
        progresso !== null ? (
          <div>
            <p style={{ margin: '0 0 4px', color: '#1d4ed8' }}>Enviando o {nomeMidia}… {progresso}%</p>
            <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4 }}>
              <div style={{ height: 8, width: `${progresso}%`, background: '#1d4ed8', borderRadius: 4, transition: 'width .2s' }} />
            </div>
          </div>
        ) : (
          <p style={{ margin: 0, color: '#1d4ed8', textAlign: 'center' }}>Transcrevendo o {nomeMidia}…</p>
        )
      )}
      {erro && (
        <p style={{ margin: 0, padding: 10, background: '#fee2e2', borderRadius: 6, color: '#dc2626' }}>{erro}</p>
      )}
      {cameraNegada && !ocupado && (
        /* Câmera nativa do celular: abre o app Câmera e devolve o vídeo, sem a permissão do site */
        <label style={btn('#1e3a5f')}>
          🎥 Filmar com a câmera do celular
          <input type="file" accept="video/*" capture="environment" style={{ display: 'none' }}
            onChange={e => { setCameraNegada(false); escolherArquivo(e) }} />
        </label>
      )}

      {/* 2. Revisão e chamado */}
      {(texto || anexos.length > 0 || erro) && ocupado !== 'transcrevendo' && (
        <form onSubmit={criarChamado} style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
          {anexos.length > 0 && <Evidencias urls={anexos} />}
          <label style={{ fontWeight: 600, color: '#374151' }}>
            Relato {revisar && <span style={{ color: '#ca8a04', fontWeight: 500 }}>· revise a transcrição</span>}
          </label>
          <textarea required rows={4} style={{ ...inp, resize: 'vertical' }}
            value={texto} onChange={e => setTexto(e.target.value)} />
          <button type="button" onClick={analisarDeNovo} disabled={!!ocupado || !texto.trim()}
            style={{ ...btn('#e5e7eb', '#000'), fontSize: 14, padding: '8px 12px' }}>
            {ocupado === 'analisando' ? 'Analisando…' : '↻ Analisar o texto de novo'}
          </button>

          <input required list="lista-ativos-relato" placeholder="Ativo (ex.: srv-node-001)" style={inp}
            value={campos.ativo_id} onChange={e => {
              const a = ativos.find(x => x.ativo_id === e.target.value)
              setCampos(c => ({ ...c, ativo_id: e.target.value, ...(a ? { sala: a.sala, rack: a.rack || '' } : {}) }))
            }} />
          <datalist id="lista-ativos-relato">
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
              {anexos.length > 0 && (video ? ' · vídeo e áudio guardados e anexados ao chamado' : ' · áudio guardado e anexado ao chamado')}
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
