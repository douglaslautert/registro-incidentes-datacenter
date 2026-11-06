import { useState, useEffect } from 'react'
import { RelatoChamado } from './components/RelatoChamado'
import { FotoVideo } from './components/FotoVideo'
import { Evidencias } from './components/Evidencias'
import { usuario, entrar, sair, pode, loginDisponivel } from './auth'
import { postarOuGuardar, enviarPendentes } from './filaOffline'

const API = import.meta.env.VITE_API_URL || '/api'

const PRIORIDADE: Record<string, string> = { P1: 'Crítica', P2: 'Alta', P3: 'Média', P4: 'Baixa' }
const STATUS: Record<string, string> = {
  aberto: 'Aberto', em_atendimento: 'Em atendimento', resolvido: 'Resolvido', falso_positivo: 'Falso alarme',
}

type Aba = 'registrar' | 'audio' | 'listar' | 'concluidos' | 'qr' | 'foto' | 'metricas' | 'links'

// Perfis da Sprint 2 que podem cada ação (admin pode tudo; sem login, tudo liberado)
const REGISTRAR = ['tecnico-interno', 'terceirizado', 'plantonista']
const ATENDER   = ['tecnico-interno', 'plantonista']
const METRICAS  = ['gestor', 'tecnico-interno', 'plantonista', 'somente-leitura']
const CONCLUIDOS = ['gestor']           // e o admin, que pode tudo

interface Incidente {
  id: string; titulo: string; prioridade: string; status: string
  ativo_id: string; aberto_em: string; total_eventos: number
  sugestao_correlacao?: string | null
  fechado_em?: string | null; fechado_por?: string | null
  causa_raiz?: string | null; mesclado_em?: string | null
}
interface Passo { quando: string; tipo: string; quem: string | null; texto: string }
interface Detalhe { evidencias: string[]; historico?: Passo[] }
interface Metrica {
  total_incidentes: number; abertos: number; falsos_positivos?: number; periodo_dias?: number
  por_prioridade: Record<string, number>
  mtta_minutos: number | null; mttr_horas: number | null
}
interface Ativo {
  ativo_id: string; qr_code: string; nome: string; sala: string; rack?: string; tipo: string
}

const ABAS: { id: Aba; icone: string; rotulo: string; perfis: string[] | null }[] = [
  { id: 'registrar', icone: '📝', rotulo: 'Novo incidente',              perfis: REGISTRAR },
  { id: 'audio',     icone: '🎙', rotulo: 'Relatar por voz ou vídeo',    perfis: REGISTRAR },
  { id: 'listar',    icone: '📋', rotulo: 'Incidentes abertos',          perfis: null },
  { id: 'concluidos', icone: '✅', rotulo: 'Concluídos',                 perfis: CONCLUIDOS },
  { id: 'qr',        icone: '🔎', rotulo: 'Identificar equipamento',     perfis: REGISTRAR },
  { id: 'foto',      icone: '📎', rotulo: 'Anexar foto, áudio ou vídeo', perfis: REGISTRAR },
  { id: 'metricas',  icone: '📊', rotulo: 'Indicadores',                 perfis: METRICAS },
  { id: 'links',     icone: '🔗', rotulo: 'Outros',                      perfis: null },
]

// O título guardado é "[P1] sintoma — ativo"; a prioridade e o ativo já aparecem ao lado
const tituloLimpo = (t: string) => t.replace(/^(\[[^\]]+\]\s*)+/, '').replace(/\s+—\s+[^—]+$/, '')

const ATUALIZA_S = 15

// Quem fez o passo do histórico, em texto para a pessoa
function quemFez(q: string | null): string {
  if (!q) return ''
  if (q === 'sistema') return 'automático'
  if (q === 'zabbix' || q.startsWith('zabbix-')) return 'Zabbix'
  if (q === 'anonimo') return 'sem login'
  if (q.startsWith('email:')) return `e-mail de ${q.slice(6)}`
  return q
}

const dataHora = (d: string) =>
  new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

const ICONE_PASSO: Record<string, string> = {
  aberto: '🆕', relato: '💬', acionamento: '📣', assumido: '✋', analise: '🔍', recuperado: '💚', encerrado: '✅',
}

const FORM_VAZIO = { ativo_id: '', sintoma: '', sala: '', rack: '', seguranca_pessoas: false, confianca: '1.0' }

export default function App() {
  const eu = usuario()
  const [aba, setAba]           = useState<Aba>(pode(...REGISTRAR) ? 'registrar' : 'listar')
  const [incidentes, setIncs]   = useState<Incidente[]>([])
  const [concluidos, setConcluidos] = useState<Incidente[]>([])
  const [metricas, setMet]      = useState<Metrica | null>(null)
  const [ativos, setAtivos]     = useState<Ativo[]>([])
  const [ativoQr, setAtivoQr]   = useState<Ativo | null>(null)
  const [qrInput, setQrInput]   = useState('')
  const [msg, setMsg]           = useState('')
  const [msgTipo, setMsgTipo]   = useState<'ok'|'err'|'info'>('info')
  const [carregando, setCar]    = useState(false)
  const [incSel, setIncSel]     = useState<string | null>(null)
  const [detalhe, setDetalhe]   = useState<Detalhe | null>(null)
  const [atualizadoEm, setAtualizadoEm] = useState<Date | null>(null)
  const [form, setForm]         = useState(FORM_VAZIO)

  function aviso(t: string, tipo: 'ok'|'err'|'info' = 'info') {
    setMsg(t); setMsgTipo(tipo)
    setTimeout(() => setMsg(''), 5000)
  }

  // ── Registrar incidente ──────────────────────────────────────
  async function registrar(e: React.FormEvent) {
    e.preventDefault(); setCar(true)
    try {
      const r = await postarOuGuardar(`${API}/v1/incidentes`, {
        fonte: 'pessoa',
        ativo_id: form.ativo_id || ativoQr?.ativo_id,
        sintoma: form.sintoma,
        local: { sala: form.sala || ativoQr?.sala, rack: form.rack || ativoQr?.rack || null },
        confianca: parseFloat(form.confianca) || 1.0,
        seguranca_pessoas: form.seguranca_pessoas,
      })
      if (!r.enviado) aviso('📴 Sem conexão: o incidente ficou guardado no aparelho e será enviado quando a rede voltar', 'info')
      else aviso(r.dados.decisao_correlacao === 'deduplicado' || r.dados.decisao_correlacao === 'anexado'
        ? `✔ Somado a um incidente já aberto — prioridade ${r.dados.prioridade} (${PRIORIDADE[r.dados.prioridade] || ''})`
        : `✔ Incidente registrado — prioridade ${r.dados.prioridade} (${PRIORIDADE[r.dados.prioridade] || ''})`, 'ok')
      setForm(FORM_VAZIO)
      setAtivoQr(null)
    } catch(err: any) {
      aviso(`✗ ${err.message}`, 'err')
    } finally { setCar(false) }
  }

  // ── Listar incidentes ────────────────────────────────────────
  // silencioso: atualização automática, sem "Carregando…" nem aviso de erro a cada tentativa
  async function carregar(silencioso = false) {
    if (!silencioso) setCar(true)
    try {
      const r = await fetch(`${API}/v1/incidentes`)
      if (!r.ok) throw new Error()
      setIncs(await r.json())
      setAtualizadoEm(new Date())
    } catch { if (!silencioso) aviso('Não foi possível carregar os incidentes', 'err') }
    finally { if (!silencioso) setCar(false) }
  }

  // Concluídos: resolvidos e falsos alarmes, do encerramento mais recente para o mais antigo
  async function carregarConcluidos() {
    setCar(true)
    try {
      const r = await fetch(`${API}/v1/incidentes?status=resolvido,falso_positivo`)
      if (!r.ok) throw new Error()
      const lista: Incidente[] = await r.json()
      setConcluidos(lista.sort((a, b) => (b.fechado_em || '').localeCompare(a.fechado_em || '')).slice(0, 200))
    } catch { aviso('Não foi possível carregar os incidentes concluídos', 'err') }
    finally { setCar(false) }
  }

  async function carregarDetalhe(id: string | null) {
    if (!id) { setDetalhe(null); return }
    try {
      const r = await fetch(`${API}/v1/incidentes/${id}`)
      if (r.ok) setDetalhe(await r.json())
    } catch { /* mantém o que já estava na tela */ }
  }

  function atualizarTudo() { carregar(); carregarDetalhe(incSel) }

  async function assumir(id: string) {
    await fetch(`${API}/v1/incidentes/${id}/ack?usuario_id=${encodeURIComponent(eu?.id || 'tecnico-pwa')}`, { method:'PATCH' })
    aviso('✔ Você assumiu o atendimento', 'ok')
    atualizarTudo()
  }

  async function juntar(id: string, destino: string) {
    if (!confirm('Juntar este incidente ao sugerido? Os registros passam para o outro e este é encerrado.')) return
    const r = await fetch(`${API}/v1/incidentes/${id}/mesclar?destino=${encodeURIComponent(destino)}`, { method:'POST' })
    const d = await r.json().catch(() => ({}))
    aviso(r.ok ? `✔ Incidentes juntados — prioridade ${d.prioridade}` : `✗ ${d.detail || 'Não foi possível juntar os incidentes'}`, r.ok ? 'ok' : 'err')
    setIncSel(null); carregar()
  }

  async function encerrar(id: string) {
    const causa = prompt('O que causou o problema e como foi resolvido?')
    if (!causa) return
    await fetch(`${API}/v1/incidentes/${id}/fechar?causa_raiz=${encodeURIComponent(causa)}`, { method:'PATCH' })
    aviso('✔ Incidente encerrado como resolvido', 'ok')
    atualizarTudo()
  }

  async function falsoAlarme(id: string) {
    const motivo = prompt('Por que é um falso alarme?')
    if (!motivo) return
    await fetch(`${API}/v1/incidentes/${id}/falso_positivo?motivo=${encodeURIComponent(motivo)}`, { method:'PATCH' })
    aviso('✔ Marcado como falso alarme', 'ok')
    atualizarTudo()
  }

  // ── Identificar equipamento pelo QR Code ─────────────────────
  async function buscarQr(codigo = qrInput) {
    if (!codigo.trim()) return
    setCar(true)
    try {
      const r = await fetch(`${API}/v1/ativos/qr/${encodeURIComponent(codigo.trim().toUpperCase())}`)
      if (!r.ok) { aviso('Código não encontrado no inventário', 'err'); return }
      const a = await r.json()
      setAtivoQr(a)
      setForm(f => ({ ...f, ativo_id: a.ativo_id, sala: a.sala, rack: a.rack || '' }))
    } catch { aviso('Não foi possível consultar o inventário', 'err') }
    finally { setCar(false) }
  }

  // ── Detalhe (anexos e histórico) do incidente selecionado ────
  useEffect(() => {
    setDetalhe(null)
    if (incSel && (aba === 'listar' || aba === 'concluidos')) carregarDetalhe(incSel)
  }, [incSel, aba])

  // ── A lista se atualiza sozinha enquanto está na tela ────────
  // A cada 15 s, só com o app em primeiro plano (no bolso não gasta bateria nem dados)
  useEffect(() => {
    if (aba !== 'listar') return
    const t = window.setInterval(() => {
      if (document.hidden) return
      carregar(true)
      carregarDetalhe(incSel)
    }, ATUALIZA_S * 1000)
    const voltou = () => { if (!document.hidden) { carregar(true); carregarDetalhe(incSel) } }
    document.addEventListener('visibilitychange', voltou)
    return () => { window.clearInterval(t); document.removeEventListener('visibilitychange', voltou) }
  }, [aba, incSel])

  // ── Fila offline: envia o que ficou guardado ao abrir e quando a rede volta ──
  useEffect(() => {
    const enviar = () => enviarPendentes().then(n => {
      if (n) aviso(`✔ ${n} incidente(s) guardado(s) sem conexão foram enviados`, 'ok')
    })
    enviar()
    window.addEventListener('online', enviar)
    return () => window.removeEventListener('online', enviar)
  }, [])

  // ── Dados de cada aba ────────────────────────────────────────
  useEffect(() => {
    if (aba === 'metricas') fetch(`${API}/v1/metricas/resumo`).then(r => r.json()).then(setMet).catch(() => {})
    if (aba === 'listar') carregar()
    if (aba === 'concluidos') carregarConcluidos()
    if (aba === 'qr' && !ativos.length) fetch(`${API}/v1/ativos/`).then(r => r.json()).then(setAtivos).catch(() => {})
  }, [aba])

  const abas = ABAS.filter(a => !a.perfis || pode(...a.perfis))
  const papeisVisiveis = (eu?.papeis || []).filter(p => !p.startsWith('default-') && p !== 'offline_access' && p !== 'uma_authorization')
  const maxPrio = metricas ? Math.max(1, ...Object.values(metricas.por_prioridade)) : 1

  // Anexos e histórico do incidente selecionado (abertos e concluídos)
  const painelDetalhe = () => (
    <>
      <Evidencias urls={detalhe?.evidencias || []} />
      {!!detalhe?.historico?.length && (
        <section className="historico" aria-label="Histórico do incidente">
          <h3>Histórico</h3>
          <ol>
            {detalhe.historico.map((p, k) => (
              <li key={k} className={`passo passo-${p.tipo}`}>
                <span className="passo-icone" aria-hidden>{ICONE_PASSO[p.tipo] || '•'}</span>
                <div>
                  <p className="passo-texto">{p.texto}</p>
                  <p className="passo-meta">
                    {dataHora(p.quando)}
                    {quemFez(p.quem) && <> · {quemFez(p.quem)}</>}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  )

  return (
    <div className="app">
      <header className="topo">
        <div className="topo-linha">
          <div className="marca">
            <strong>CESUP · Incidentes</strong>
            <span>Datacenter da UFRGS</span>
          </div>
          {eu ? (
            <button className="usuario" onClick={sair} title={`Perfis: ${papeisVisiveis.join(', ')} — toque para sair`}>
              👤 {eu.nome || eu.id} · Sair
            </button>
          ) : loginDisponivel() && (
            <button className="usuario" onClick={entrar}>Entrar</button>
          )}
        </div>
        <nav className="abas" aria-label="Seções">
          {abas.map(a => (
            <button key={a.id} className={`aba${aba === a.id ? ' ativa' : ''}`} onClick={() => setAba(a.id)}
              aria-current={aba === a.id ? 'page' : undefined}>
              <span className="aba-icone" aria-hidden>{a.icone}</span><span className="aba-nome">{a.rotulo}</span>
            </button>
          ))}
        </nav>
      </header>

      <main className="conteudo">
        {msg && <div className={`mensagem ${msgTipo}`} role="status">{msg}</div>}

        {/* ── Novo incidente ────────────────────────────────── */}
        {aba === 'registrar' && (
          <>
            <h1 className="titulo-tela">Novo incidente</h1>
            <p className="subtitulo">Descreva o problema e onde ele está. Leva menos de 30 segundos.</p>
            <form onSubmit={registrar} className="cartao pilha">
              {ativoQr && (
                <div className="mensagem info">🔎 Equipamento identificado: <strong>{ativoQr.nome}</strong> — {ativoQr.sala}{ativoQr.rack && ` / ${ativoQr.rack}`}</div>
              )}
              <label className="campo"><span>Equipamento (código ou nome)</span>
                <input required className="entrada" placeholder="ex.: srv-node-001"
                  value={form.ativo_id} onChange={e => setForm({ ...form, ativo_id: e.target.value })} />
              </label>
              <div className="grade-2">
                <label className="campo"><span>Sala</span>
                  <input required className="entrada" placeholder="ex.: sala-A"
                    value={form.sala} onChange={e => setForm({ ...form, sala: e.target.value })} />
                </label>
                <label className="campo"><span>Rack (opcional)</span>
                  <input className="entrada" placeholder="ex.: rack-01"
                    value={form.rack} onChange={e => setForm({ ...form, rack: e.target.value })} />
                </label>
              </div>
              <label className="campo"><span>O que está acontecendo?</span>
                <textarea required className="entrada" placeholder="ex.: servidor desligou e o LED da fonte está vermelho"
                  value={form.sintoma} onChange={e => setForm({ ...form, sintoma: e.target.value })} />
              </label>
              <label className="marcador">
                <input type="checkbox" checked={form.seguranca_pessoas}
                  onChange={e => setForm({ ...form, seguranca_pessoas: e.target.checked })} />
                <span className="risco">⚠ Há risco para pessoas (fumaça, água, choque…)</span>
              </label>
              <button type="submit" disabled={carregando} className="botao largo">
                {carregando ? 'Enviando…' : 'Registrar incidente'}
              </button>
            </form>
            <div className="grade-2">
              <button className="botao secundario largo" onClick={() => setAba('qr')}>🔎 Identificar pelo QR Code</button>
              <button className="botao secundario largo" onClick={() => setAba('audio')}>🎙 Relatar falando</button>
            </div>
          </>
        )}

        {/* ── Relato por voz ou vídeo ───────────────────────── */}
        {aba === 'audio' && (
          <>
            <h1 className="titulo-tela">Relatar por voz ou vídeo</h1>
            <div className="cartao">
              <RelatoChamado api={API} ativoInicial={ativoQr}
                onCriado={p => {
                  aviso(p.startsWith('P') ? `✔ Incidente registrado pelo relato — prioridade ${p}`
                    : '📴 Sem conexão: o incidente ficou guardado no aparelho e será enviado quando a rede voltar',
                    p.startsWith('P') ? 'ok' : 'info')
                  setAtivoQr(null)
                }} />
            </div>
          </>
        )}

        {/* ── Incidentes abertos ────────────────────────────── */}
        {aba === 'listar' && (
          <>
            <div className="linha entre">
              <h1 className="titulo-tela">Incidentes abertos</h1>
              <button onClick={atualizarTudo} className="botao neutro pequeno">↻ Atualizar</button>
            </div>
            {!carregando && (
              <p className="subtitulo">
                {incidentes.length} incidente(s) em aberto, do mais grave ao menos grave
                {atualizadoEm && <> · atualizado às {atualizadoEm.toLocaleTimeString('pt-BR')} (a cada {ATUALIZA_S} s)</>}
              </p>
            )}
            {carregando && <p className="vazio">Carregando…</p>}
            {!carregando && incidentes.length === 0 && <p className="vazio">Nenhum incidente aberto. 🎉</p>}
            {incidentes.map(i => (
              <article key={i.id} className={`incidente prio-${i.prioridade}${incSel === i.id ? ' selecionado' : ''}`}
                onClick={() => setIncSel(incSel === i.id ? null : i.id)}>
                <div className="linha entre">
                  <span className={`etiqueta prio prio-${i.prioridade}`}>{i.prioridade} · {PRIORIDADE[i.prioridade]}</span>
                  <span className={`etiqueta st-${i.status}`}>{STATUS[i.status] || i.status}</span>
                </div>
                <p className="incidente-titulo">{tituloLimpo(i.titulo)}</p>
                <p className="incidente-meta">
                  {i.ativo_id} · {new Date(i.aberto_em).toLocaleString('pt-BR')}
                  {i.total_eventos > 1 && ` · ${i.total_eventos} relatos`}
                </p>
                {i.sugestao_correlacao && (
                  <div className="sugestao">
                    <span>🔗 Pode ser o mesmo problema de outro incidente (…{i.sugestao_correlacao.slice(-6)})</span>
                    {pode(...ATENDER) && (
                      <button className="botao pequeno" onClick={e => { e.stopPropagation(); juntar(i.id, i.sugestao_correlacao!) }}>
                        Juntar
                      </button>
                    )}
                  </div>
                )}
                {incSel === i.id && pode(...ATENDER) && (
                  <div className="acoes">
                    {i.status === 'aberto' && (
                      <button className="botao alerta" onClick={e => { e.stopPropagation(); assumir(i.id) }}>✋ Assumir atendimento</button>
                    )}
                    <button className="botao sucesso" onClick={e => { e.stopPropagation(); encerrar(i.id) }}>✓ Encerrar como resolvido</button>
                    {i.status === 'aberto' && (
                      <button className="botao neutro" onClick={e => { e.stopPropagation(); falsoAlarme(i.id) }}>Marcar como falso alarme</button>
                    )}
                  </div>
                )}
                {incSel === i.id && (
                  <div className="pilha" style={{ marginTop: 12 }} onClick={e => e.stopPropagation()}>
                    {painelDetalhe()}
                    {pode(...REGISTRAR) && (
                      <button className="botao secundario" onClick={() => setAba('foto')}>📎 Anexar foto, áudio ou vídeo</button>
                    )}
                  </div>
                )}
              </article>
            ))}
          </>
        )}

        {/* ── Concluídos (gestor e admin) ───────────────────── */}
        {aba === 'concluidos' && (
          <>
            <div className="linha entre">
              <h1 className="titulo-tela">Concluídos</h1>
              <button onClick={() => { carregarConcluidos(); carregarDetalhe(incSel) }} className="botao neutro pequeno">↻ Atualizar</button>
            </div>
            {!carregando && (
              <p className="subtitulo">
                {concluidos.length} incidente(s) encerrado(s), do mais recente ao mais antigo · toque para ver o histórico
              </p>
            )}
            {carregando && <p className="vazio">Carregando…</p>}
            {!carregando && concluidos.length === 0 && <p className="vazio">Nenhum incidente encerrado ainda.</p>}
            {concluidos.map(i => (
              <article key={i.id} className={`incidente prio-${i.prioridade}${incSel === i.id ? ' selecionado' : ''}`}
                onClick={() => setIncSel(incSel === i.id ? null : i.id)}>
                <div className="linha entre">
                  <span className={`etiqueta prio prio-${i.prioridade}`}>{i.prioridade} · {PRIORIDADE[i.prioridade]}</span>
                  <span className={`etiqueta st-${i.status}`}>{i.mesclado_em ? 'Juntado a outro' : STATUS[i.status] || i.status}</span>
                </div>
                <p className="incidente-titulo">{tituloLimpo(i.titulo)}</p>
                <p className="incidente-meta">
                  {i.ativo_id} · aberto em {dataHora(i.aberto_em)}
                  {i.fechado_em && <> · encerrado em {dataHora(i.fechado_em)}</>}
                  {i.fechado_por && <> por <strong>{quemFez(i.fechado_por)}</strong></>}
                </p>
                {i.causa_raiz && !i.mesclado_em && (
                  <p className="pequeno" style={{ margin: '6px 0 0' }}>
                    {i.status === 'falso_positivo' ? 'Motivo' : 'Causa e solução'}: {i.causa_raiz}
                  </p>
                )}
                {incSel === i.id && (
                  <div className="pilha" style={{ marginTop: 12 }} onClick={e => e.stopPropagation()}>
                    {painelDetalhe()}
                  </div>
                )}
              </article>
            ))}
          </>
        )}

        {/* ── Identificar equipamento ───────────────────────── */}
        {aba === 'qr' && (
          <>
            <h1 className="titulo-tela">Identificar equipamento</h1>
            <p className="subtitulo">Digite o código da etiqueta QR do equipamento para preencher o incidente.</p>
            <div className="cartao pilha">
              <div className="linha">
                <input className="entrada" placeholder="ex.: CESUP-SRV-001" style={{ flex: 1 }}
                  value={qrInput} onChange={e => setQrInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && buscarQr()} />
                <button onClick={() => buscarQr()} disabled={carregando} className="botao">Buscar</button>
              </div>
              {ativoQr && (
                <div className="cartao destaque">
                  <p style={{ margin: 0, fontWeight: 700 }}>✔ {ativoQr.nome}</p>
                  <p className="pequeno" style={{ margin: '4px 0 12px' }}>
                    {ativoQr.tipo} · {ativoQr.sala}{ativoQr.rack && ` · ${ativoQr.rack}`}
                  </p>
                  <button onClick={() => setAba('registrar')} className="botao largo">Registrar incidente deste equipamento</button>
                </div>
              )}
            </div>
            {ativos.length > 0 && (
              <div className="cartao">
                <h2>Equipamentos cadastrados</h2>
                <div className="chips">
                  {ativos.map(a => (
                    <button key={a.qr_code} className="chip" title={a.nome}
                      onClick={() => { setQrInput(a.qr_code); buscarQr(a.qr_code) }}>
                      {a.nome}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Anexar foto, áudio ou vídeo ───────────────────── */}
        {aba === 'foto' && (
          <>
            <h1 className="titulo-tela">Anexar foto, áudio ou vídeo</h1>
            <p className="subtitulo">Mostre o problema: o arquivo fica guardado junto do incidente.</p>
            <div className="cartao">
              <FotoVideo api={API} incidenteInicial={incSel} onEnviado={m => aviso(m, 'ok')} />
            </div>
          </>
        )}

        {/* ── Indicadores ───────────────────────────────────── */}
        {aba === 'metricas' && (
          <>
            <div className="linha entre">
              <h1 className="titulo-tela">Indicadores</h1>
              <button onClick={() => fetch(`${API}/v1/metricas/resumo`).then(r => r.json()).then(setMet)}
                className="botao neutro pequeno">↻ Atualizar</button>
            </div>
            {!metricas ? <p className="vazio">Carregando…</p> : (
              <>
                <p className="subtitulo">Últimos {metricas.periodo_dias ?? 90} dias</p>
                <div className="grade-2">
                  <div className="cartao indicador"><p className="rotulo">Incidentes no período</p><p className="valor">{metricas.total_incidentes}</p></div>
                  <div className="cartao indicador"><p className="rotulo">Abertos agora</p><p className="valor" style={{ color: 'var(--erro)' }}>{metricas.abertos}</p></div>
                  <div className="cartao indicador">
                    <p className="rotulo">Tempo até alguém assumir (MTTA)</p>
                    <p className="valor">{metricas.mtta_minutos != null ? `${metricas.mtta_minutos.toFixed(0)} min` : '—'}</p>
                  </div>
                  <div className="cartao indicador">
                    <p className="rotulo">Tempo até resolver (MTTR)</p>
                    <p className="valor">{metricas.mttr_horas != null ? `${metricas.mttr_horas.toFixed(1)} h` : '—'}</p>
                  </div>
                </div>
                <div className="cartao pilha">
                  <h2>Por prioridade</h2>
                  {['P1', 'P2', 'P3', 'P4'].map(p => {
                    const n = metricas.por_prioridade[p] || 0
                    return (
                      <div key={p} className={`prio-${p}`}>
                        <div className="linha entre pequeno">
                          <span className={`etiqueta prio prio-${p}`}>{p} · {PRIORIDADE[p]}</span>
                          <span>{n} incidente(s)</span>
                        </div>
                        <div className="barra" style={{ marginTop: 6 }}><div style={{ width: `${(100 * n) / maxPrio}%` }} /></div>
                      </div>
                    )
                  })}
                  {metricas.falsos_positivos != null && (
                    <p className="pequeno suave" style={{ margin: 0 }}>Falsos alarmes no período: {metricas.falsos_positivos}</p>
                  )}
                </div>
              </>
            )}
          </>
        )}

        {/* ── Outros sistemas ───────────────────────────────── */}
        {aba === 'links' && (
          <>
            <h1 className="titulo-tela">Outros sistemas</h1>
            <div className="pilha">
              {[
                { icone: '📈', rotulo: 'Painéis (Grafana)',              url: '/grafana', desc: 'Gráficos e indicadores do datacenter' },
                { icone: '🔔', rotulo: 'Monitoramento (Zabbix)',         url: '/zabbix',  desc: 'Alertas dos equipamentos' },
                // GLPI tem porta própria (8081) e só HTTP: usa o mesmo host em que o PWA foi aberto
                { icone: '🗂', rotulo: 'Inventário e chamados (GLPI)',   url: `http://${window.location.hostname}:8081`, desc: 'Cadastro de equipamentos' },
                { icone: '👥', rotulo: 'Usuários e acessos (Keycloak)',  url: '/auth/admin/', desc: 'Cadastro de pessoas e perfis' },
                { icone: '🧩', rotulo: 'Documentação da API',            url: '/api/docs', desc: 'Para integrações e scripts' },
              ].map(l => (
                <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="cartao link-servico">
                  <span className="icone" aria-hidden>{l.icone}</span>
                  <span><p style={{ fontWeight: 600 }}>{l.rotulo}</p><p className="pequeno suave">{l.desc}</p></span>
                </a>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
