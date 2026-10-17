workspace "Registro de Incidentes do Datacenter" "Opção A: GLPI + Zabbix (MVP)" {

    model {
        tecnico   = person "Técnico de TI"       "Registra incidentes, diagnósticos, peças e fotos"
        gestor    = person "Gestor do datacenter" "Acompanha indicadores e o histórico"
        fornecedor = person "Técnico do fornecedor" "Atende em garantia (ex.: Dell)" "Externo"

        plataforma = softwareSystem "Plataforma de Registro de Incidentes" \
                     "Detecta falhas e guarda o histórico de manutenção" {

            zbxFront  = container "Zabbix Frontend"  "Alertas, gráficos e configuração"          "PHP, Nginx"
            zbxServer = container "Zabbix Server"    "Coleta métricas, avalia triggers, dispara webhook" "C"
            zbxDb     = container "Zabbix DB"        "Métricas, eventos e configuração"           "PostgreSQL" "Database"

            glpi = container "GLPI Web App" "Chamados, ativos, peças, relatórios e API" "PHP 8.2, Apache" {
                api       = component "API REST"           "Recebe chamados do Zabbix"                    "GLPI API v2"
                ui        = component "Interface web"      "Telas de chamado, ativo e relatório"          "PHP, Twig"
                chamados  = component "Chamados"           "Status, prioridade, tarefas, solução"         "Assistência ITIL"
                ativos    = component "Ativos e datacenter" "Equipamento, rack/U, peças, garantia"        "Ativos"
                relat     = component "Relatórios"         "Consultas do histórico"                       "Estatísticas"
                fields    = component "Plugin Fields"      "Executor, chamado fornecedor, origem peça"    "Plugin"
                docs      = component "Documentos"         "Fotos antes/depois por categoria"             "Documentos"
                problemas = component "Problemas e mudanças" "Causa raiz e ação preventiva"              "ITIL"
                regras    = component "Regras e notificações" "Categoriza, atribui e avisa por e-mail"   "Regras, Cron"
            }

            glpiDb   = container "GLPI DB"   "Incidentes, ativos, campos extras e histórico" "MariaDB"       "Database"
            arquivos = container "Arquivos"  "Fotos, laudos e notas fiscais"                 "Volume em disco" "Database"
        }

        equipamentos = softwareSystem "Equipamentos do datacenter" "Servidores, switches, nobreaks e sensores" "Externo"
        ldap         = softwareSystem "Diretório institucional"    "LDAP da universidade"                     "Externo"
        smtp         = softwareSystem "Servidor de e-mail"         "SMTP institucional"                       "Externo"
        netbox       = softwareSystem "NetBox"                     "Racks, IPs, VLANs e cabos (Fase 2)"       "Futuro"
        ia           = softwareSystem "Provedor de IA"             "Resumos e perguntas em linguagem natural (Fase 3)" "Futuro"

        # Relações — pessoas
        fornecedor  -> tecnico    "Informa chamado e peças"
        tecnico     -> zbxFront   "Consulta alertas"           "HTTPS"
        tecnico     -> ui         "Registra e resolve"         "HTTPS"
        gestor      -> ui         "Consulta histórico"         "HTTPS"

        # Relações — Zabbix
        zbxFront    -> zbxDb      "Lê e grava"                 "SQL"
        zbxServer   -> zbxDb      "Grava eventos"              "SQL"
        zbxServer   -> equipamentos "Coleta métricas"          "SNMP, agente, ICMP"
        zbxServer   -> api        "Abre e atualiza chamados"   "Webhook, JSON/HTTPS"

        # Relações — GLPI interno
        api         -> chamados   "Cria e atualiza incidente"
        ui          -> chamados   "Abre, edita e resolve"
        ui          -> ativos     "Cadastra"
        ui          -> relat      "Gera relatórios"
        chamados    -> ativos     "Vincula ativo"
        chamados    -> fields     "Grava campos extras"
        chamados    -> docs       "Anexa fotos"
        chamados    -> problemas  "Vincula causa raiz"
        chamados    -> regras     "Dispara regras"
        chamados    -> glpiDb     "Lê e grava"                 "SQL"
        ativos      -> glpiDb     "Lê e grava"                 "SQL"
        fields      -> glpiDb     "Lê e grava"                 "SQL"
        relat       -> glpiDb     "Consulta"                   "SQL"
        docs        -> arquivos   "Salva arquivos"
        regras      -> smtp       "Envia e-mail"               "SMTP"
        ui          -> ldap       "Autentica"                  "LDAPS"

        # Relações — fases futuras
        glpi        -> netbox     "Importa inventário (Fase 2)" "API REST"
        glpi        -> ia         "Gera resumos (Fase 3)"       "API HTTPS"
    }

    views {
        systemContext plataforma "N1-Contexto" {
            include *
            autolayout tb
        }
        container plataforma "N2-Conteineres" {
            include *
            autolayout lr
        }
        component glpi "N3-Componentes" {
            include *
            autolayout tb
        }
        styles {
            element "Person"          { shape Person background #0B3D6E color #ffffff }
            element "Software System" { background #1561AD color #ffffff }
            element "Container"       { background #2E79C4 color #ffffff }
            element "Component"       { background #D3E4F6 color #0E2944 }
            element "Database"        { shape Cylinder }
            element "Externo"         { background #6A7484 color #ffffff }
            element "Futuro"          { background #ffffff color #3F4A5B border dashed }
        }
    }
}
