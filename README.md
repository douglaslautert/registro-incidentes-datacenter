# Registro de Incidentes do Datacenter (CESUP)

Sistema de registro e priorização automática de incidentes para datacenter. Ele recebe eventos de três fontes (pessoas, pelo PWA; alertas do **Zabbix**; e-mail), calcula a prioridade de forma determinística (P1–P4), correlaciona eventos relacionados ao mesmo incidente e integra com o **GLPI** para gestão de chamados e ativos. A stack completa sobe com Docker Compose em um único servidor.

**Artigo relacionado** _(rascunho — ajustar ao texto final do artigo)_

- **Título:** Registro e Priorização Automática de Incidentes em Datacenter com Correlação de Eventos e Integração Zabbix/GLPI
- **Resumo:** Em datacenters acadêmicos, falhas físicas e lógicas são percebidas por canais dispersos — alertas de monitoramento, relatos de técnicos em campo e e-mails —, o que atrasa a triagem e gera chamados duplicados. Este trabalho apresenta um sistema on-premises que unifica alertas de monitoramento e relatos de campo em um evento canônico, atribui prioridade P1–P4 por regras determinísticas e auditáveis (impacto × urgência × confiança, com prioridade máxima para risco a pessoas) e correlaciona eventos relacionados ao mesmo incidente por um escore que combina topologia, proximidade temporal e localização física, com um termo de similaridade semântica por embeddings previsto no modelo. A solução integra-se ao Zabbix, que encaminha alertas por webhook, e ao GLPI, para gestão de chamados e inventário; oferece um aplicativo web progressivo para registro em campo com QR Code, foto e voz; e mantém um vigia externo com notificação por GSM para o caso de indisponibilidade do servidor principal. Toda a stack é distribuída como artefato reprodutível em Docker Compose, com instalação automatizada e experimentos que verificam a priorização, a correlação e a integração com o Zabbix.

---

## Estrutura do readme.md

Este README segue o modelo do Comitê Técnico de Artefatos (CTA) da SBC:

1. [Estrutura do repositório](#estrutura-do-repositório)
2. [Selos Considerados](#selos-considerados)
3. [Informações básicas](#informações-básicas)
4. [Dependências](#dependências)
5. [Preocupações com segurança](#preocupações-com-segurança)
6. [Instalação](#instalação)
7. [Teste mínimo](#teste-mínimo)
8. [Experimentos](#experimentos)
9. [LICENSE](#license)
10. [Apêndice A — Implantação alternativa em VMs (Ansible)](#apêndice-a--implantação-alternativa-em-vms-ansible)
11. [Apêndice B — Problemas comuns](#apêndice-b--problemas-comuns)

### Estrutura do repositório

```
.
├── sistema/                  # Artefato principal: stack Docker Compose
│   ├── docker-compose.yml    # Todos os serviços (15 containers)
│   ├── .env.example          # Modelo de configuração (copiar para .env)
│   ├── setup.sh              # Instalação automatizada (7 passos)
│   ├── garage-setup.sh       # Passo 6 isolado: Garage S3 (idempotente)
│   ├── zabbix-setup.sh       # Passo 7 isolado: Zabbix via API (idempotente)
│   ├── reinstalar.sh         # Apaga tudo (inclusive dados) e reinstala
│   ├── Makefile              # Atalhos: make setup, make health, make logs...
│   ├── api/                  # API FastAPI + workers Celery + migrações Alembic
│   │   └── app/services/     # prioridade.py, correlacao.py, embedding.py...
│   ├── pwa/                  # Aplicativo web (React + Vite) para técnicos
│   ├── init/                 # Schema SQL do PostgreSQL (pgvector)
│   ├── keycloak/             # Imagem e realm de autenticação
│   ├── nginx/                # Proxy reverso (porta 80)
│   ├── grafana/              # Datasources, plugins e dashboards
│   ├── mysql/init/           # Banco do GLPI
│   ├── zabbix/               # Parâmetros do webhook Zabbix → API
│   └── vigia/                # Vigia externo (heartbeat + SMS via GSM), roda em outro dispositivo
├── ansible/                  # Implantação alternativa em VMs (Apêndice A)
├── scripts/                  # Scripts de integração GLPI/Zabbix da implantação em VMs
├── docs/                     # Modelo C4 (workspace.dsl), runbook, apresentação
├── index.html                # Documentação publicada (GitHub Pages)
└── download/                 # Pacote .zip do projeto
```

---

## Selos Considerados

Os selos considerados são:

- **Artefatos Disponíveis (SeloD)**
- **Artefatos Funcionais (SeloF)**
- **Artefatos Sustentáveis (SeloS)**
- **Experimentos Reprodutíveis (SeloR)**

---

## Informações básicas

### Hardware

| Recurso | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 vCPU (x86_64) | 4+ vCPU |
| Memória RAM | 8 GB | 12 GB |
| Disco livre | 20 GB | 40 GB |
| Rede | acesso à internet durante a instalação (download de imagens Docker, do GLPI e do plugin Zabbix do Grafana) | — |

A soma dos limites de memória dos containers (`mem_limit` no `docker-compose.yml`) é de cerca de 5,6 GB. O Keycloak sozinho usa até 1 GB.

### Software

- **Sistema operacional:** Linux x86_64, testado em Ubuntu 22.04/24.04. No Windows, use o WSL2 com o Docker Desktop.
- **Portas livres no host:** `80` (nginx), `8081` (GLPI) e `10051` (Zabbix Server, para agentes).

### Ambiente de execução

Todos os componentes rodam em containers na rede Docker `cesup-net`:

| Serviço | Imagem | Função |
|---|---|---|
| nginx | `nginx:1.27-alpine` | Proxy reverso — PWA, API, Keycloak, Grafana, Zabbix |
| api / worker / beat | build local (`python:3.12-slim`) | API REST, filas de notificação e reconciliação |
| pwa-builder | build local (`node:20-alpine`) | Gera o PWA estático |
| postgres | `pgvector/pgvector:pg16` | Banco de incidentes + banco do Keycloak |
| mysql | `mysql:8.0` | Bancos do Zabbix e do GLPI |
| valkey | `valkey/valkey:7.2-alpine` | Fila Celery |
| garage | `dxflrs/garage:v1.0.1` | Armazenamento S3 de evidências (fotos, áudio) |
| keycloak | build local (`keycloak:25.0`) | Autenticação (realm `cesup`) |
| zabbix-server / web / agent | `zabbix/*:ubuntu-7.0-latest` | Monitoramento |
| glpi | `diouxx/glpi` (GLPI 10.0.18) | Chamados e inventário |
| grafana | `grafana/grafana:11.2.0` | Dashboards |

---

## Dependências

### No host

| Ferramenta | Versão | Uso |
|---|---|---|
| Docker Engine | 24 ou superior | Execução dos containers |
| Docker Compose | v2 (plugin `docker compose`) | Orquestração |
| GNU Make | 4.x | Atalhos (`make setup`, `make health`) |
| Bash | 4.4 ou superior | Scripts de instalação |
| curl | qualquer | Chamadas às APIs no setup e nos testes |
| Python 3 | 3.8 ou superior (só biblioteca padrão) | Parsing de JSON no setup e nos testes |
| Git | qualquer | Download do artefato |

Instalação no Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y git make curl python3
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # depois saia e entre de novo na sessão
```

### Dentro das imagens (instaladas automaticamente no build)

- **API** ([`sistema/api/requirements.txt`](sistema/api/requirements.txt)): FastAPI 0.115.0, Uvicorn 0.30.6, SQLAlchemy 2.0.35, asyncpg 0.29.0, Alembic 1.13.3, pgvector 0.3.5, Celery 5.4.0, redis 5.1.1, boto3 1.35.30, httpx 0.27.2, pydantic 2.9.2, aiosmtplib 3.0.2.
- **PWA** ([`sistema/pwa/package.json`](sistema/pwa/package.json), versões travadas em `package-lock.json`): React 18, Vite 5, vite-plugin-pwa 0.20, keycloak-js 25, @tanstack/react-query 5, zustand 5, jsqr 1.4.

### Recursos de terceiros

Nenhum benchmark ou conjunto de dados externo é necessário. Os dados iniciais (ativos com QR Code) estão em [`sistema/init/02_qrcodes.sql`](sistema/init/02_qrcodes.sql). Na instalação, o host baixa as imagens do Docker Hub e do Quay, o código do GLPI (GitHub) e o plugin Zabbix do Grafana (grafana.com).

---

## Preocupações com segurança

- **Use uma VM ou máquina dedicada.** O container `zabbix-agent` roda com `privileged: true` e monta `/var/run/docker.sock` (somente leitura) para monitorar o host. Isso dá a ele visibilidade sobre todos os containers da máquina.
- **Senhas padrão.** O `.env.example` traz senhas de exemplo (`admin123`, `zabbix`, `glpi/glpi` etc.). Elas servem para avaliação local; troque-as antes de qualquer uso fora de um ambiente isolado.
- **Portas expostas.** O setup publica as portas `80`, `8081` e `10051` em todas as interfaces do host. Em rede compartilhada, restrinja o acesso com firewall (por exemplo, `sudo ufw allow from 127.0.0.1`).
- **Segredo do Garage.** O `rpc_secret` em [`sistema/garage.toml`](sistema/garage.toml) é público neste repositório. A porta RPC (3901) só é acessível dentro da rede Docker; para produção, gere outro com `openssl rand -hex 32`.
- **Remoção.** `make clean` (dentro de `sistema/`) remove todos os containers e volumes criados pelo artefato. Nenhum arquivo fora do diretório do projeto e dos volumes Docker é alterado.

---

## Instalação

**Tempo estimado:** 15 a 30 minutos na primeira vez (download e build das imagens + primeira inicialização do Zabbix, GLPI e Keycloak).

1. Clone o repositório e entre no diretório do artefato:

   ```bash
   git clone https://github.com/douglaslautert/registro-incidentes-datacenter.git
   cd registro-incidentes-datacenter/sistema
   ```

2. Crie o arquivo de configuração a partir do modelo:

   ```bash
   cp .env.example .env
   ```

   Os valores padrão funcionam para avaliação local. `GARAGE_ACCESS_KEY`, `GARAGE_SECRET_KEY` e `GLPI_APP_TOKEN` são preenchidos automaticamente pelo setup.

3. Execute a instalação:

   ```bash
   make setup
   ```

   O script executa 7 passos: build das imagens, bancos de dados, schema do Zabbix, instalação do GLPI, Keycloak, Garage S3 e configuração do Zabbix (webhook, ação de alerta e host).

4. Ao final, a mensagem `Setup concluído com sucesso!` deve aparecer, junto com a lista de serviços:

   | URL | Serviço | Usuário / senha padrão |
   |---|---|---|
   | http://localhost | PWA | `tecnico` / `tecnico123` |
   | http://localhost/api/docs | API (Swagger) | — |
   | http://localhost/auth | Keycloak | `admin` / `admin123` |
   | http://localhost/grafana | Grafana | `admin` / `admin123` |
   | http://localhost/zabbix/ | Zabbix | `Admin` / `zabbix` |
   | http://localhost:8081 | GLPI | `glpi` / `glpi` |

   Se você acessa de outra máquina, troque `localhost` pelo IP do servidor.

Se o passo 6 (Garage) ou o 7 (Zabbix) mostrar um aviso, é possível repeti-los isoladamente, sem reinstalar: `make garage-setup` e `make zabbix-setup`.

---

## Teste mínimo

Execute os comandos dentro de `sistema/`. **Tempo:** cerca de 2 minutos.

1. **Containers saudáveis:**

   ```bash
   make health
   ```

   Resultado esperado: `postgres`, `mysql`, `valkey`, `api`, `keycloak`, `zabbix-web` e `glpi` com status `healthy`, e os demais `running`. O `pwa-builder` termina com `exited (0)` depois de copiar o PWA, e isso é o esperado.

2. **API respondendo pelo nginx:**

   ```bash
   curl -s -H "Authorization: Bearer $(grep ^VIGIA_TOKEN= .env | cut -d= -f2)" \
        http://localhost/api/v1/heartbeat
   ```

   Resultado esperado:

   ```json
   {"alive":true,"service":"cesup-incidentes-api"}
   ```

3. **Registro de um incidente:**

   ```bash
   curl -s -X POST http://localhost/api/v1/incidentes \
        -H "Content-Type: application/json" \
        -d '{"fonte":"pessoa","ativo_id":"srv-node-001","local":{"sala":"sala-A","rack":"rack-01"},"sintoma":"temperatura_alta"}' \
        | python3 -m json.tool
   ```

   Resultado esperado: HTTP 201 com `"prioridade": "P1"`, `"decisao_correlacao": "novo"` e um `incidente_id` preenchido.

4. **Interfaces web:** abra http://localhost/api/docs (Swagger com os endpoints `/api/v1/...`) e http://localhost/zabbix/. No Zabbix, o host **CESUP — Servidor Docker** deve aparecer em *Monitoring → Hosts*.

---

## Experimentos

Os experimentos usam apenas `curl` e `python3` contra a API instalada. Todos rodam em segundos, usam menos de 100 MB de RAM além da stack e não exigem nenhuma alteração de configuração.

A correlação considera os incidentes abertos nas últimas 4 horas. Por isso, cada execução usa um sufixo aleatório (`$RUN`) nos nomes de ativos e salas, e eventos de execuções anteriores não interferem.

Função auxiliar (cole no terminal, dentro de `sistema/`):

```bash
evento() {  # evento <fonte> <ativo> <sala> <rack> <sintoma> <confianca> <seguranca_pessoas>
  curl -s -X POST http://localhost/api/v1/incidentes -H "Content-Type: application/json" \
    -d "{\"fonte\":\"$1\",\"ativo_id\":\"$2\",\"local\":{\"sala\":\"$3\",\"rack\":\"$4\"},\"sintoma\":\"$5\",\"confianca\":$6,\"seguranca_pessoas\":$7}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['prioridade'], r['decisao_correlacao'], r['incidente_id'])"
}
```

### Reivindicações #1 — Priorização determinística P1–P4

A prioridade é calculada por regras fixas, sem IA ([`sistema/api/app/services/prioridade.py`](sistema/api/app/services/prioridade.py)):

- **Fórmula:** `score = impacto × urgência × confiança`.
- **Faixas:** P1 ≥ 18, P2 ≥ 10, P3 ≥ 5, P4 abaixo disso.
- **Risco a pessoas:** qualquer evento com risco a pessoas é sempre P1.

Cada evento usa um ativo e uma sala diferentes, para que nenhum seja correlacionado com o anterior:

```bash
RUN=$RANDOM
evento pessoa srv-a-$RUN sala-1-$RUN r1 temperatura_alta 1.0 false   # 4×5×1.0 = 20   → P1
evento pessoa srv-b-$RUN sala-2-$RUN r2 disco_cheio      1.0 false   # 4×3×1.0 = 12   → P2
evento pessoa srv-c-$RUN sala-3-$RUN r3 cpu_alta         0.6 false   # 3×3×0.6 = 5,4  → P3
evento pessoa srv-d-$RUN sala-4-$RUN r4 ruido_estranho   1.0 false   # 2×2×1.0 = 4    → P4
evento pessoa srv-e-$RUN sala-5-$RUN r5 ruido_estranho   0.1 true    # risco a pessoas → P1
```

Resultado esperado (o terceiro campo, `incidente_id`, varia):

```
P1 novo ...
P2 novo ...
P3 novo ...
P4 novo ...
P1 novo ...
```

### Reivindicações #2 — Correlação de eventos no mesmo incidente

Eventos do mesmo ativo e do mesmo rack, próximos no tempo, são anexados ao incidente aberto em vez de abrir um novo ([`sistema/api/app/services/correlacao.py`](sistema/api/app/services/correlacao.py)).

- **Score:** `S = 0,35·topologia + 0,25·tempo + 0,20·local + 0,20·semântica`.
- **Decisão:** anexa se S ≥ 0,75 e sugere correlação se S ≥ 0,45.
- **Neste experimento:** S ≈ 0,35 + 0,25 + 0,20 = 0,80, portanto o evento é anexado.

Além de anexar, o segundo evento, mais grave, **escala** a prioridade do incidente:

```bash
RUN=$RANDOM
evento pessoa srv-x-$RUN sala-A-$RUN rack-07 cpu_alta  1.0 false   # P3, incidente novo
evento zabbix srv-x-$RUN sala-A-$RUN rack-07 ups_falha 1.0 false   # mesmo incidente_id, anexado
evento pessoa srv-y-$RUN sala-B-$RUN rack-09 cpu_alta  1.0 false   # outro ativo/sala → novo
```

Resultado esperado:

```
P3 novo     <ID-1>
P1 anexado  <ID-1>
P3 novo     <ID-2>
```

A prioridade do incidente `<ID-1>` passa de P3 para P1. Para conferir, use `curl -s http://localhost/api/v1/incidentes/<ID-1> | python3 -m json.tool`.

### Reivindicações #3 — Alerta do Zabbix gera incidente automaticamente

O `zabbix-setup.sh` cria no Zabbix o webhook **CESUP Incidentes**, que envia cada problema (severidade ≥ Warning) para `POST /api/v1/webhook/zabbix`. Recuperações (`RESOLVED`) são ignoradas.

**a) Simulando o payload do webhook** (≈ 5 s):

```bash
curl -s -X POST http://localhost/api/v1/webhook/zabbix -H "Content-Type: application/json" \
     -d '{"eventid":"1001","host":"storage-01","trigger":"disco_cheio","severity":"High","status":"PROBLEM"}'
curl -s -X POST http://localhost/api/v1/webhook/zabbix -H "Content-Type: application/json" \
     -d '{"eventid":"1001","host":"storage-01","trigger":"disco_cheio","severity":"High","status":"RECOVERY"}'
```

Resultado esperado:
- O primeiro comando retorna `{"msg":"ok","incidente_id":"...","prioridade":"P2"}`. A severidade High equivale a confiança 0,85, e 4×3×0,85 = 10,2 dá P2.
- O segundo retorna `{"msg":"Recovery ignorado","eventid":"1001"}`.

**b) Pelo próprio Zabbix** (≈ 2 min):
1. Em http://localhost/zabbix/, abra *Alerts → Media types → CESUP Incidentes → Test*.
2. Preencha `host=teste`, `trigger=temperatura_alta`, `severity=High` e `status=PROBLEM`. Deixe `URL` como está.
3. Clique em *Test*.

O Zabbix deve exibir `Media type test successful` com a resposta `OK`, e o log da API (`docker compose logs api | grep Webhook`) mostra o evento recebido.

### Reivindicações #4 — Métricas operacionais

Depois dos experimentos anteriores, o resumo agrega os incidentes por prioridade:

```bash
curl -s http://localhost/api/v1/metricas/resumo | python3 -m json.tool
```

Resultado esperado: um JSON com o total de incidentes, os abertos e a distribuição por prioridade (P1–P4), coerente com os eventos registrados. MTTA e MTTR só aparecem depois que algum incidente é fechado:

```bash
curl -s -X PATCH http://localhost/api/v1/incidentes/<ID>/fechar
```

O Grafana (http://localhost/grafana) traz os dashboards provisionados a partir de [`sistema/grafana/dashboards/`](sistema/grafana/dashboards/).

---

## LICENSE

Este projeto está licenciado sob a [Licença MIT](LICENSE).

---

## Apêndice A — Implantação alternativa em VMs (Ansible)

Também é possível implantar **GLPI + Zabbix** em duas VMs no Proxmox, sem Docker, com o playbook em [`ansible/`](ansible/):

- **VM-GLPI** (192.168.10.200): PHP 8.2 + Apache + MariaDB + Plugin Fields.
- **VM-ZABBIX** (192.168.10.201): Zabbix Server 7.x + PostgreSQL + Nginx.
- **Integração:** webhook JavaScript (Media Type do Zabbix) → API REST do GLPI.

Pré-requisitos:
- GLPI instalado e acessível por HTTPS;
- Ansible com acesso SSH às VMs;
- Python 3.8+ e `pip install requests`.

Ordem de execução:

1. Snapshot da VM-GLPI no Proxmox.
2. Criar a VM-ZABBIX no Proxmox (ver [`docs/runbook.md`](docs/runbook.md)).
3. Rodar o playbook: `ansible-playbook ansible/site.yml --ask-vault-pass`.
4. Criar o usuário de serviço no GLPI:
   ```bash
   export GLPI_ADMIN_PASS=... GLPI_APP_TOKEN=... GLPI_SVC_PASS=...
   bash scripts/glpi_setup_service_user.sh
   ```
5. Criar o Media Type no Zabbix:
   ```bash
   export ZABBIX_URL=... ZABBIX_USER=... ZABBIX_PASS=... \
          GLPI_API_URL=... GLPI_SVC_USER=... GLPI_SVC_PASS=... GLPI_APP_TOKEN=...
   python3 scripts/setup_zabbix_mediatype.py
   ```
6. Criar as regras de categorização:
   ```bash
   export GLPI_API_URL=... GLPI_APP_TOKEN=... GLPI_SESSION_TOKEN=...
   python3 scripts/glpi_setup_rules.py
   ```
7. Configurar o Plugin Fields na interface do GLPI (*Setup → Plugins → Fields*).
8. Validar o webhook com um chamado de teste.
9. Configurar o monitor da VM-GLPI:
   ```bash
   export ZABBIX_URL=... ZABBIX_API_TOKEN=... GLPI_API_URL=...
   python3 scripts/zabbix_setup_glpi_monitor.py
   ```

Nessa trilha, as senhas ficam no **Ansible Vault**, a autenticação é feita via **LDAP institucional**, o acesso é restrito à rede interna ou VPN e todas as interfaces usam TLS 1.2+.

**Modelo C4:** [`docs/workspace.dsl`](docs/workspace.dsl). Para visualizar:

```bash
docker run -it --rm -p 8080:8080 -v "$(pwd)/docs:/usr/local/structurizr" structurizr/lite
# Acesse http://localhost:8080
```

---

## Apêndice B — Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `⚠ Erro ao criar bucket` no passo 6 | Garage ainda sem layout ou sem quorum | `make garage-setup` |
| `⚠ API do Zabbix não respondeu` no passo 7 | Frontend do Zabbix ainda iniciando, ou nginx com IP antigo de um container | `docker compose exec nginx nginx -s reload` e depois `make zabbix-setup` |
| API retorna 502 pelo nginx | Container recriado ganhou IP novo | `docker compose exec nginx nginx -s reload` |
| Postgres `unhealthy` ou schema ausente | Os scripts `init/` só rodam com volume vazio | `bash limpar_postgres.sh` (apaga os dados do Postgres) ou `make reinstalar` |
| GLPI não instalou automaticamente | O download do GLPI no 1º start demorou | Instalação web em http://localhost:8081 (host `mysql`, usuário `glpi`, senha do `.env`) |
| Keycloak não autentica | 1º start lento (até 3 min) | `bash diagnostico-keycloak.sh` |

Logs: `make logs` (todos os serviços), `make log s=api` (um serviço), `make zabbix-logs` e `make glpi-logs`.
