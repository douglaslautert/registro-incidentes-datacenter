import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// Endereço único: com o sistema publicado em HTTPS, quem abrir pelo http da rede vai
// para o https. O nginx já redireciona, mas um PWA aberto antes em http fica guardado
// no aparelho e responde sem passar pelo servidor. localhost segue em http.
const publico = import.meta.env.VITE_PUBLIC_URL || ''
if (publico.startsWith('https://') && location.protocol === 'http:'
    && !['localhost', '127.0.0.1'].includes(location.hostname)) {
  location.replace(`https://${location.host}${location.pathname}${location.search}${location.hash}`)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
