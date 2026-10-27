import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        // O service worker controla o site inteiro ("/") e responderia toda
        // navegação com o index.html do PWA — escondendo os outros serviços
        // publicados no mesmo endereço pelo nginx
        navigateFallbackDenylist: [/^\/(api|ws|auth|grafana|zabbix|glpi)(\/|$|\?)/],
        runtimeCaching: [{
          urlPattern: /^\/api\/v1\/.*/,
          handler: 'NetworkFirst',
          options: { cacheName: 'api-cache', networkTimeoutSeconds: 5 },
        }],
      },
      manifest: {
        name: 'CESUP Incidentes',
        short_name: 'Incidentes',
        description: 'Registro de incidentes do datacenter CESUP/UFRGS',
        theme_color: '#1e3a5f',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
})
