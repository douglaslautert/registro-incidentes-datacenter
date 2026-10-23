# Etapa 1: pré-compilar com TODAS as variáveis estáticas
# Variáveis dinâmicas (passwords, URLs) ficam apenas no runtime
FROM quay.io/keycloak/keycloak:25.0 AS builder

# Variáveis que afetam a compilação (devem ser idênticas ao runtime)
ENV KC_DB=postgres
ENV KC_HTTP_ENABLED=true
ENV KC_HTTP_PORT=8080
ENV KC_HTTP_RELATIVE_PATH=/auth
ENV KC_HTTPS_ENABLED=false
ENV KC_CACHE=local
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=false
ENV KC_PROXY_HEADERS=xforwarded
ENV KC_HOSTNAME_STRICT=false
ENV KC_LOG_LEVEL=ERROR

ENV JAVA_TOOL_OPTIONS="-Xms256m -Xmx768m -XX:+UseG1GC"
RUN /opt/keycloak/bin/kc.sh build

# Etapa 2: imagem final com resultado do build
FROM quay.io/keycloak/keycloak:25.0
COPY --from=builder /opt/keycloak/lib/quarkus/ /opt/keycloak/lib/quarkus/
USER 1000

# Realm para --import-realm
USER root
COPY --chown=1000:0 realm-cesup.json /opt/keycloak/data/import/realm-cesup.json
USER 1000

