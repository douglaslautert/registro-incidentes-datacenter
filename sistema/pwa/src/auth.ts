// auth.ts — Login no Keycloak (OIDC, código de autorização + PKCE) — Sprint 2
//
// Sem biblioteca: o Keycloak responde no mesmo endereço do PWA (/auth, pelo Nginx), então
// a troca do código pelo token não esbarra em CORS. Os tokens ficam no localStorage para o
// app instalado no celular não pedir login a cada abertura; o refresh token renova o acesso.
// Toda chamada a /api ganha o cabeçalho Authorization (fetch e XMLHttpRequest).

export interface Usuario { id: string; nome: string; papeis: string[] }
interface Tokens { access: string; refresh: string; idToken: string; expira: number }
interface Config { obrigatoria: boolean; realm: string; client_id: string; caminho: string }

const CHAVE = 'cesup.tokens'
let cfg: Config | null = null
let tokens: Tokens | null = null
let renovando: Promise<boolean> | null = null

const base = () => `${location.origin}${cfg!.caminho}/realms/${cfg!.realm}/protocol/openid-connect`
const retorno = () => `${location.origin}/`

function b64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  return btoa(String.fromCharCode(...arr)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
function aleatorio(n = 32) { return b64url(crypto.getRandomValues(new Uint8Array(n))) }
function claims(jwt: string): any {
  try { return JSON.parse(decodeURIComponent(escape(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))))) }
  catch { return {} }
}

function guardar(t: any) {
  tokens = {
    access: t.access_token, refresh: t.refresh_token, idToken: t.id_token || tokens?.idToken || '',
    expira: Date.now() + (t.expires_in || 300) * 1000,
  }
  try { localStorage.setItem(CHAVE, JSON.stringify(tokens)) } catch { /* modo privado */ }
}
function esquecer() { tokens = null; try { localStorage.removeItem(CHAVE) } catch { /* */ } }

async function pedirToken(form: Record<string, string>): Promise<boolean> {
  const r = await fetch(`${base()}/token`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: cfg!.client_id, ...form }),
  })
  if (!r.ok) return false
  guardar(await r.json())
  return true
}

async function renovar(): Promise<boolean> {
  if (!tokens?.refresh) return false
  renovando ??= pedirToken({ grant_type: 'refresh_token', refresh_token: tokens.refresh })
    .catch(() => false).finally(() => { renovando = null })
  const ok = await renovando
  if (!ok) esquecer()
  return ok
}

export async function entrar() {
  // PKCE: o verificador fica na sessão; o Keycloak só recebe o hash (S256)
  const verificador = aleatorio(48), estado = aleatorio(16)
  const desafio = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verificador)))
  sessionStorage.setItem('cesup.pkce', JSON.stringify({ verificador, estado }))
  location.assign(`${base()}/auth?` + new URLSearchParams({
    client_id: cfg!.client_id, response_type: 'code', scope: 'openid', redirect_uri: retorno(),
    code_challenge: desafio, code_challenge_method: 'S256', state: estado,
  }))
}

export function sair() {
  const id = tokens?.idToken
  esquecer()
  location.assign(`${base()}/logout?` + new URLSearchParams({
    client_id: cfg!.client_id, post_logout_redirect_uri: retorno(), ...(id ? { id_token_hint: id } : {}),
  }))
}

/** Token válido para chamar a API (renova se faltar menos de 30 s). */
export async function token(): Promise<string | null> {
  if (!tokens) return null
  if (tokens.expira - Date.now() < 30_000 && !(await renovar())) return null
  return tokens?.access ?? null
}

export function usuario(): Usuario | null {
  if (!tokens) return null
  const c = claims(tokens.access)
  return { id: c.preferred_username || c.sub, nome: c.name || c.preferred_username || '', papeis: c.realm_access?.roles || [] }
}

/** Perfis efetivos: sem login (modo opcional), todas as ações ficam liberadas. */
export function pode(...perfis: string[]): boolean {
  const u = usuario()
  if (!u) return !cfg?.obrigatoria
  return u.papeis.includes('admin') || perfis.some(p => u.papeis.includes(p))
}

export const loginObrigatorio = () => !!cfg?.obrigatoria
export const loginDisponivel = () => !!cfg && window.isSecureContext && !!crypto?.subtle

function ehApi(url: string) {
  try { return new URL(url, location.href).pathname.startsWith('/api/') } catch { return false }
}

function interceptarChamadas() {
  const fetchOriginal = window.fetch.bind(window)
  window.fetch = async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.href : entrada.url
    if (!ehApi(url)) return fetchOriginal(entrada, init)
    const t = await token()
    const headers = new Headers(init?.headers || (entrada instanceof Request ? entrada.headers : undefined))
    if (t) headers.set('Authorization', `Bearer ${t}`)
    const r = await fetchOriginal(entrada, { ...init, headers })
    if (r.status === 401 && loginObrigatorio() && loginDisponivel()) entrar()
    return r
  }
  // Uploads com barra de progresso usam XMLHttpRequest: o token entra no send()
  const abrir = XMLHttpRequest.prototype.open
  const enviar = XMLHttpRequest.prototype.send
  XMLHttpRequest.prototype.open = function (this: any, metodo: string, url: string | URL, ...resto: any[]) {
    this._cesupApi = ehApi(String(url))
    return (abrir as any).call(this, metodo, url, ...resto)
  }
  XMLHttpRequest.prototype.send = function (this: any, corpo?: any) {
    if (!this._cesupApi) return enviar.call(this, corpo)
    token().then(t => {
      if (t) this.setRequestHeader('Authorization', `Bearer ${t}`)
      enviar.call(this, corpo)
    })
  }
}

/** Antes de abrir o app: lê a configuração, conclui o retorno do login e decide se pede login. */
export async function iniciarAuth(): Promise<void> {
  try {
    cfg = await (await fetch('/api/v1/auth/config')).json()
  } catch {
    cfg = { obrigatoria: false, realm: 'cesup', client_id: 'incidentes-pwa', caminho: '/auth' }
  }
  try { tokens = JSON.parse(localStorage.getItem(CHAVE) || 'null') } catch { tokens = null }
  interceptarChamadas()

  // Voltando do Keycloak com ?code=...&state=...
  const q = new URLSearchParams(location.search)
  const pkce = JSON.parse(sessionStorage.getItem('cesup.pkce') || 'null')
  if (q.get('code') && pkce && q.get('state') === pkce.estado) {
    sessionStorage.removeItem('cesup.pkce')
    await pedirToken({ grant_type: 'authorization_code', code: q.get('code')!, redirect_uri: retorno(),
                       code_verifier: pkce.verificador })
    history.replaceState(null, '', location.pathname)
  }
  if (tokens && tokens.expira < Date.now()) await renovar()
  if (!tokens && cfg!.obrigatoria && loginDisponivel()) await entrar()
}
