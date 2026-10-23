# Etapa 1: build da PWA
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL VITE_WS_URL VITE_KEYCLOAK_URL VITE_KEYCLOAK_REALM VITE_KEYCLOAK_CLIENT_ID
ENV VITE_API_URL=$VITE_API_URL VITE_WS_URL=$VITE_WS_URL \
    VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID
RUN npm run build

# Etapa 2: copiar dist para volume e sair
FROM alpine:3.20
COPY --from=builder /app/dist /dist
# Copia o dist para o volume montado em /app/dist e encerra
CMD ["sh", "-c", "cp -r /dist/. /app/dist/ && echo 'PWA build copiado com sucesso'"]
