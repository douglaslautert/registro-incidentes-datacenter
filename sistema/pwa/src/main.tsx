import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './estilo.css'
import { iniciarAuth } from './auth'
import { registerSW } from 'virtual:pwa-register'

// Versão nova publicada no servidor: o service worker baixa e a página recarrega
// sozinha. Sem isso o app aberto (ou instalado no celular) seguia mostrando a versão
// antiga guardada em cache até ser fechado e aberto de novo.
registerSW({
  immediate: true,
  onRegisteredSW(_url, reg) {
    if (!reg) return
    const verificar = () => { if (navigator.onLine) reg.update().catch(() => {}) }
    setInterval(verificar, 60_000)
    document.addEventListener('visibilitychange', () => { if (!document.hidden) verificar() })
  },
})

// Endereço único: com o sistema publicado em HTTPS, quem abrir pelo http da rede vai
// para o https. O nginx já redireciona, mas um PWA aberto antes em http fica guardado
// no aparelho e responde sem passar pelo servidor. localhost segue em http.
const publico = import.meta.env.VITE_PUBLIC_URL || ''
if (publico.startsWith('https://') && location.protocol === 'http:'
    && !['localhost', '127.0.0.1'].includes(location.hostname)) {
  location.replace(`https://${location.host}${location.pathname}${location.search}${location.hash}`)
} else {
  // Login no Keycloak antes de abrir (Sprint 2), quando a API exigir
  iniciarAuth().finally(() => {
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )
  })
}
