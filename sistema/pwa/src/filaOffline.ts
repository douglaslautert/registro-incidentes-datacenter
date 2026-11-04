// filaOffline.ts — Fila offline do PWA (Sprint 3)
//
// Sem conexão com o servidor, o chamado fica guardado no aparelho (IndexedDB) e é enviado
// sozinho quando a rede volta (evento "online") ou na próxima abertura do app.

const BANCO = 'cesup-offline', LOJA = 'chamados'

interface Pendente { id?: number; url: string; corpo: unknown; criado: number }

function abrir(): Promise<IDBDatabase> {
  return new Promise((ok, erro) => {
    const r = indexedDB.open(BANCO, 1)
    r.onupgradeneeded = () => r.result.createObjectStore(LOJA, { keyPath: 'id', autoIncrement: true })
    r.onsuccess = () => ok(r.result)
    r.onerror = () => erro(r.error)
  })
}

async function loja<T>(modo: IDBTransactionMode, f: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await abrir()
  return new Promise((ok, erro) => {
    const req = f(db.transaction(LOJA, modo).objectStore(LOJA))
    req.onsuccess = () => ok(req.result)
    req.onerror = () => erro(req.error)
  })
}

export const pendentes = () => loja<Pendente[]>('readonly', s => s.getAll() as IDBRequest<Pendente[]>)

/** Envia o chamado; sem rede, guarda para depois. Erro do servidor (4xx/5xx) não entra na fila. */
export async function postarOuGuardar(url: string, corpo: unknown):
    Promise<{ enviado: true; dados: any } | { enviado: false }> {
  try {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
    const dados = await r.json().catch(() => ({}))
    if (!r.ok) throw Object.assign(new Error(dados.detail || `Erro ${r.status}`), { doServidor: true })
    return { enviado: true, dados }
  } catch (e: any) {
    if (e?.doServidor) throw e
    await loja('readwrite', s => s.add({ url, corpo, criado: Date.now() }))
    return { enviado: false }
  }
}

let enviando = false
/** Reenvia o que ficou guardado. Devolve quantos foram enviados agora. */
export async function enviarPendentes(): Promise<number> {
  if (enviando || !navigator.onLine) return 0
  enviando = true
  let n = 0
  try {
    for (const p of await pendentes()) {
      try {
        const r = await fetch(p.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p.corpo) })
        if (r.ok || (r.status >= 400 && r.status < 500 && r.status !== 401 && r.status !== 408)) {
          await loja('readwrite', s => s.delete(p.id!))     // enviado, ou recusado de vez
          if (r.ok) n++
        }
      } catch { break }                                      // caiu de novo: tenta depois
    }
  } finally { enviando = false }
  return n
}
