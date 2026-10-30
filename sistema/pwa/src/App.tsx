import { useState, useEffect, useRef } from 'react'
import { RelatoChamado } from './components/RelatoChamado'
import { FotoVideo } from './components/FotoVideo'
import { Evidencias } from './components/Evidencias'

const API = import.meta.env.VITE_API_URL || '/api'

const COR: Record<string, string> = {
  P1: '#dc2626', P2: '#ea580c', P3: '#ca8a04', P4: '#16a34a',
}
const STATUS_COR: Record<string, string> = {
  aberto: '#dc2626', em_atendimento: '#ea580c',
  resolvido: '#16a34a', falso_positivo: '#6b7280',
}

type Aba = 'registrar' | 'audio' | 'listar' | 'qr' | 'foto' | 'metricas' | 'links'

interface Incidente {
  id: string; prioridade: string; status: string
  ativo_id: string; sintoma: string; aberto_em: string
  confianca?: number
}
interface Metrica {
  total_incidentes: number; abertos: number; fonte: string
  por_prioridade: Record<string, number>
  mtta_minutos: number | null; mttr_horas: number | null
}
interface Ativo {
  ativo_id: string; qr_code: string; nome: string; sala: string; rack?: string; tipo: string
}

export default function App() {
  const [aba, setAba]           = useState<Aba>('registrar')
  const [incidentes, setIncs]   = useState<Incidente[]>([])
  const [metricas, setMet]      = useState<Metrica | null>(null)
  const [ativoQr, setAtivoQr]   = useState<Ativo | null>(null)
  const [qrInput, setQrInput]   = useState('')
  const [msg, setMsg]           = useState('')
  const [msgTipo, setMsgTipo]   = useState<'ok'|'err'|'info'>('info')
  const [carregando, setCar]    = useState(false)
  const [incSel, setIncSel]     = useState<string | null>(null)
  const [anexos, setAnexos]     = useState<string[]>([])
  const [form, setForm] = useState({
    ativo_id: '', sintoma: '', sala: '', rack: '',
    seguranca_pessoas: false, confianca: '1.0',
  })

  function aviso(t: string, tipo: 'ok'|'err'|'info' = 'info') {
    setMsg(t); setMsgTipo(tipo)
    setTimeout(() => setMsg(''), 5000)
  }

  // ── Registrar incidente ──────────────────────────────────────
  async function registrar(e: React.FormEvent) {
    e.preventDefault(); setCar(true)
    try {
      const res = await fetch(`${API}/v1/incidentes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fonte: 'pessoa',
          ativo_id: form.ativo_id || ativoQr?.ativo_id,
          sintoma: form.sintoma,
          local: { sala: form.sala || ativoQr?.sala, rack: form.rack || ativoQr?.rack || null },
          confianca: parseFloat(form.confianca) || 1.0,
          seguranca_pessoas: form.seguranca_pessoas,
        }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.detail || 'Erro')
      aviso(`✔ Incidente criado — Prioridade: ${d.prioridade}`, 'ok')
      setForm({ ativo_id:'', sintoma:'', sala:'', rack:'', seguranca_pessoas:false, confianca:'1.0' })
      setAtivoQr(null)
    } catch(err: any) {
      aviso(`✗ ${err.message}`, 'err')
    } finally { setCar(false) }
  }

  // ── Listar incidentes ────────────────────────────────────────
  async function carregar() {
    setCar(true)
    try {
      const r = await fetch(`${API}/v1/incidentes`)
      setIncs(await r.json())
    } catch { aviso('Erro ao carregar incidentes', 'err') }
    finally { setCar(false) }
  }

  async function ack(id: string) {
    await fetch(`${API}/v1/incidentes/${id}/ack?usuario_id=tecnico-pwa`, { method:'PATCH' })
    carregar()
  }

  async function fechar(id: string) {
    const causa = prompt('Causa raiz:')
    if (!causa) return
    await fetch(`${API}/v1/incidentes/${id}/fechar?causa_raiz=${encodeURIComponent(causa)}`, { method:'PATCH' })
    carregar()
  }

  async function falsoPosi(id: string) {
    const motivo = prompt('Motivo:')
    if (!motivo) return
    await fetch(`${API}/v1/incidentes/${id}/falso_positivo?motivo=${encodeURIComponent(motivo)}`, { method:'PATCH' })
    carregar()
  }

  // ── QR Code ──────────────────────────────────────────────────
  async function buscarQr() {
    if (!qrInput.trim()) return
    setCar(true)
    try {
      const r = await fetch(`${API}/v1/ativos/qr/${qrInput.trim().toUpperCase()}`)
      if (!r.ok) { aviso('QR Code não encontrado', 'err'); return }
      const a = await r.json()
      setAtivoQr(a)
      aviso(`✔ Ativo: ${a.nome} — ${a.sala}`, 'ok')
      setForm(f => ({ ...f, ativo_id: a.ativo_id, sala: a.sala, rack: a.rack || '' }))
    } catch { aviso('Erro ao buscar ativo', 'err') }
    finally { setCar(false) }
  }

  // ── Anexos do incidente aberto na lista ──────────────────────
  useEffect(() => {
    setAnexos([])
    if (!incSel || aba !== 'listar') return
    fetch(`${API}/v1/incidentes/${incSel}`)
      .then(r => r.ok ? r.json() : { evidencias: [] })
      .then(d => setAnexos(d.evidencias || [])).catch(() => {})
  }, [incSel, aba])

  // ── Métricas ─────────────────────────────────────────────────
  useEffect(() => {
    if (aba === 'metricas') {
      fetch(`${API}/v1/metricas/resumo`)
        .then(r => r.json()).then(setMet).catch(() => {})
    }
    if (aba === 'listar') carregar()
  }, [aba])

  // ── UI ───────────────────────────────────────────────────────
  const abas: { id: Aba; label: string }[] = [
    { id:'registrar', label:'+ Registrar' },
    { id:'audio',     label:'🎙 Áudio e Vídeo' },
    { id:'listar',    label:'📋 Abertos'   },
    { id:'qr',        label:'📷 QR Code'   },
    { id:'foto',      label:'📷 Foto/vídeo' },
    { id:'metricas',  label:'📊 Métricas'  },
    { id:'links',     label:'🔗 Serviços'  },
  ]

  const inp: React.CSSProperties = {
    padding:10, borderRadius:6, border:'1px solid #d1d5db', fontSize:15, width:'100%', boxSizing:'border-box',
  }
  const btn = (bg='#1e3a5f', color='#fff'): React.CSSProperties => ({
    padding:'10px 16px', background:bg, color, border:'none',
    borderRadius:6, cursor:'pointer', fontWeight:600, fontSize:15,
  })

  return (
    <div style={{ fontFamily:'system-ui', maxWidth:520, margin:'0 auto', padding:16, paddingBottom:32 }}>
      <h1 style={{ fontSize:20, color:'#1e3a5f', margin:'0 0 12px' }}>
        🖥 CESUP — Registro de Incidentes
      </h1>

      {/* Navegação */}
      <div style={{ display:'flex', gap:6, marginBottom:16, flexWrap:'wrap' }}>
        {abas.map(a => (
          <button key={a.id} onClick={() => setAba(a.id)} style={btn(
            aba===a.id ? '#1e3a5f' : '#e5e7eb',
            aba===a.id ? '#fff'    : '#000'
          )}>
            {a.label}
          </button>
        ))}
      </div>

      {/* Mensagem de feedback */}
      {msg && (
        <div style={{ padding:'10px 14px', borderRadius:6, marginBottom:12,
          background: msgTipo==='ok'?'#dcfce7': msgTipo==='err'?'#fee2e2':'#dbeafe',
          color:      msgTipo==='ok'?'#16a34a': msgTipo==='err'?'#dc2626':'#1d4ed8',
          fontWeight:500 }}>
          {msg}
        </div>
      )}

      {/* ── Registrar ─────────────────────────────────────── */}
      {aba === 'registrar' && (
        <form onSubmit={registrar} style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {ativoQr && (
            <div style={{ padding:10, background:'#eff6ff', borderRadius:6, fontSize:14 }}>
              📷 Ativo via QR: <strong>{ativoQr.nome}</strong> — {ativoQr.sala} {ativoQr.rack && `/ ${ativoQr.rack}`}
            </div>
          )}
          <input required placeholder="ID do ativo (ex: srv-node-001)" style={inp}
            value={form.ativo_id} onChange={e => setForm({...form, ativo_id:e.target.value})} />
          <input required placeholder="Sala (ex: sala-A)" style={inp}
            value={form.sala} onChange={e => setForm({...form, sala:e.target.value})} />
          <input placeholder="Rack (opcional)" style={inp}
            value={form.rack} onChange={e => setForm({...form, rack:e.target.value})} />
          <textarea required placeholder="Descreva o sintoma..." rows={3} style={{...inp, resize:'vertical'}}
            value={form.sintoma} onChange={e => setForm({...form, sintoma:e.target.value})} />
          <label style={{ display:'flex', gap:8, alignItems:'center', cursor:'pointer' }}>
            <input type="checkbox" checked={form.seguranca_pessoas}
              onChange={e => setForm({...form, seguranca_pessoas:e.target.checked})} />
            <span style={{ color:'#dc2626', fontWeight:500 }}>⚠ Risco à segurança de pessoas</span>
          </label>
          <button type="submit" disabled={carregando} style={btn()}>
            {carregando ? 'Enviando...' : 'Registrar incidente'}
          </button>
        </form>
      )}

      {/* ── Áudio ou vídeo → chamado ──────────────────────── */}
      {aba === 'audio' && (
        <RelatoChamado api={API} ativoInicial={ativoQr}
          onCriado={p => { aviso(`✔ Chamado criado pelo relato — Prioridade: ${p}`, 'ok'); setAtivoQr(null) }} />
      )}

      {/* ── Listar ────────────────────────────────────────── */}
      {aba === 'listar' && (
        <div>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
            <span style={{ fontWeight:600, color:'#374151' }}>{incidentes.length} incidente(s) aberto(s)</span>
            <button onClick={carregar} style={btn('#e5e7eb','#000')}>↻ Atualizar</button>
          </div>
          {carregando && <p style={{ color:'#6b7280', textAlign:'center' }}>Carregando...</p>}
          {!carregando && incidentes.length === 0 && (
            <p style={{ color:'#6b7280', textAlign:'center', marginTop:32 }}>Nenhum incidente aberto.</p>
          )}
          {incidentes.map(i => (
            <div key={i.id} style={{ border:'1px solid #e5e7eb', borderRadius:8, padding:12,
              marginBottom:8, borderLeft:`4px solid ${COR[i.prioridade]||'#6b7280'}`,
              background: incSel===i.id ? '#eff6ff' : '#fff' }}
              onClick={() => setIncSel(incSel===i.id ? null : i.id)}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                <span style={{ fontWeight:700, color:COR[i.prioridade], fontSize:18 }}>{i.prioridade}</span>
                <span style={{ fontSize:12, padding:'2px 8px', borderRadius:999,
                  background: STATUS_COR[i.status]+'22', color: STATUS_COR[i.status] }}>
                  {i.status}
                </span>
              </div>
              <p style={{ margin:'2px 0', fontWeight:500, fontSize:14 }}>{i.sintoma}</p>
              <p style={{ margin:0, fontSize:12, color:'#6b7280' }}>
                {i.ativo_id} · {new Date(i.aberto_em).toLocaleString('pt-BR')}
              </p>
              {incSel===i.id && i.status==='aberto' && (
                <div style={{ display:'flex', gap:6, marginTop:8, flexWrap:'wrap' }}>
                  <button onClick={e=>{e.stopPropagation();ack(i.id)}}
                    style={btn('#ea580c')}>✔ ACK</button>
                  <button onClick={e=>{e.stopPropagation();fechar(i.id)}}
                    style={btn('#16a34a')}>✓ Fechar</button>
                  <button onClick={e=>{e.stopPropagation();falsoPosi(i.id)}}
                    style={btn('#6b7280')}>✗ Falso positivo</button>
                </div>
              )}
              {incSel===i.id && i.status==='em_atendimento' && (
                <div style={{ display:'flex', gap:6, marginTop:8 }}>
                  <button onClick={e=>{e.stopPropagation();fechar(i.id)}}
                    style={btn('#16a34a')}>✓ Fechar</button>
                </div>
              )}
              {incSel===i.id && (
                <div style={{ marginTop:10 }}>
                  <Evidencias urls={anexos} />
                  <button onClick={e=>{e.stopPropagation();setAba('foto')}}
                    style={{ ...btn('#e5e7eb','#000'), marginTop:8, fontSize:14 }}>📷 Anexar foto ou vídeo</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── QR Code ───────────────────────────────────────── */}
      {aba === 'qr' && (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <p style={{ color:'#6b7280', margin:0 }}>
            Digite o código QR do ativo para preencher o formulário automaticamente.
          </p>
          <div style={{ display:'flex', gap:8 }}>
            <input placeholder="Ex: CESUP-SRV-001" style={{...inp, flex:1}}
              value={qrInput} onChange={e => setQrInput(e.target.value)}
              onKeyDown={e => e.key==='Enter' && buscarQr()} />
            <button onClick={buscarQr} disabled={carregando} style={btn()}>Buscar</button>
          </div>
          {ativoQr && (
            <div style={{ padding:12, background:'#f0fdf4', borderRadius:8, border:'1px solid #bbf7d0' }}>
              <p style={{ margin:0, fontWeight:600 }}>✔ Ativo encontrado</p>
              <p style={{ margin:'4px 0 0', fontSize:14 }}>
                <strong>{ativoQr.nome}</strong><br/>
                Tipo: {ativoQr.tipo} · Sala: {ativoQr.sala}{ativoQr.rack && ` · Rack: ${ativoQr.rack}`}
              </p>
              <button onClick={() => setAba('registrar')} style={{ ...btn('#1e3a5f'), marginTop:10, width:'100%' }}>
                → Registrar incidente para este ativo
              </button>
            </div>
          )}
          <div style={{ marginTop:8 }}>
            <p style={{ fontWeight:600, color:'#374151', marginBottom:8 }}>Ativos cadastrados:</p>
            {['CESUP-SRV-001','CESUP-SRV-002','CESUP-UPS-001','CESUP-SW-001','CESUP-STG-001'].map(qr => (
              <button key={qr} onClick={() => { setQrInput(qr); }}
                style={{ ...btn('#e5e7eb','#000'), marginRight:6, marginBottom:6, fontSize:13 }}>
                {qr}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Foto ──────────────────────────────────────────── */}
      {aba === 'foto' && (
        <FotoVideo api={API} incidenteInicial={incSel} onEnviado={m => aviso(m, 'ok')} />
      )}

      {/* ── Métricas ──────────────────────────────────────── */}
      {aba === 'metricas' && (
        <div>
          {!metricas
            ? <p style={{ color:'#6b7280', textAlign:'center' }}>Carregando métricas...</p>
            : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
                {[
                  { label:'Total', val: metricas.total_incidentes, cor:'#1e3a5f' },
                  { label:'Abertos', val: metricas.abertos, cor:'#dc2626' },
                  { label:'MTTA', val: metricas.mtta_minutos != null ? `${metricas.mtta_minutos.toFixed(0)}min` : '—', cor:'#ea580c' },
                  { label:'MTTR', val: metricas.mttr_horas != null ? `${metricas.mttr_horas.toFixed(1)}h` : '—', cor:'#16a34a' },
                ].map(c => (
                  <div key={c.label} style={{ padding:16, borderRadius:8, background:c.cor+'11',
                    border:`1px solid ${c.cor}33`, textAlign:'center' }}>
                    <p style={{ margin:0, fontSize:12, color:'#6b7280' }}>{c.label}</p>
                    <p style={{ margin:'4px 0 0', fontSize:28, fontWeight:700, color:c.cor }}>{c.val}</p>
                  </div>
                ))}
              </div>
              <div style={{ padding:12, borderRadius:8, border:'1px solid #e5e7eb' }}>
                <p style={{ margin:'0 0 8px', fontWeight:600 }}>Por prioridade</p>
                {Object.entries(metricas.por_prioridade).map(([p,n]) => (
                  <div key={p} style={{ display:'flex', justifyContent:'space-between',
                    padding:'4px 0', borderBottom:'1px solid #f3f4f6' }}>
                    <span style={{ fontWeight:700, color:COR[p] }}>{p}</span>
                    <span>{n as number} incidente(s)</span>
                  </div>
                ))}
              </div>
              <p style={{ margin:0, fontSize:12, color:'#9ca3af', textAlign:'right' }}>
                Fonte: {metricas.fonte}
              </p>
              <button onClick={() => fetch(`${API}/v1/metricas/resumo`).then(r=>r.json()).then(setMet)}
                style={btn('#e5e7eb','#000')}>↻ Atualizar</button>
            </div>
          )}
        </div>
      )}

      {/* ── Links ─────────────────────────────────────────── */}
      {aba === 'links' && (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {[
            { label:'🔧 API — Swagger (documentação)',    url:'/api/docs',     desc:'Testar todos os endpoints' },
            { label:'🔑 Keycloak — Gestão de usuários',  url:'/auth',         desc:'admin / admin123' },
            { label:'📈 Grafana — Dashboards',           url:'/grafana',      desc:'admin / admin123' },
            { label:'🔔 Zabbix — Monitoramento',         url:'/zabbix',       desc:'Admin / zabbix' },
            // GLPI tem porta própria (8081) e só HTTP: usa o mesmo host em que o PWA foi aberto
            { label:'🎫 GLPI — Chamados ITSM',           url:`http://${window.location.hostname}:8081`, desc:'glpi / glpi' },
          ].map(l => (
            <a key={l.url} href={l.url} target="_blank" rel="noreferrer"
              style={{ padding:14, borderRadius:8, border:'1px solid #e5e7eb',
                textDecoration:'none', color:'inherit', display:'block',
                background:'#f9fafb' }}>
              <p style={{ margin:0, fontWeight:600 }}>{l.label}</p>
              <p style={{ margin:'2px 0 0', fontSize:13, color:'#6b7280' }}>{l.desc}</p>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
