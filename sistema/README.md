# CESUP Incidentes — stack Docker Compose

Este diretório contém o artefato principal: a stack completa do sistema de registro de incidentes, que sobe com Docker Compose.

O roteiro completo está no [README da raiz](../README.md): requisitos, instalação, teste mínimo, experimentos e problemas comuns.

## Resumo rápido

```bash
cp .env.example .env     # ajuste as senhas se necessário
make setup               # instalação completa (15–30 min na 1ª vez)
make health              # estado dos containers
```

| URL | Serviço |
|-----|---------|
| http://localhost | PWA |
| http://localhost/api/docs | API (Swagger) |
| http://localhost/auth | Keycloak |
| http://localhost/grafana | Grafana |
| http://localhost/zabbix/ | Zabbix |
| http://localhost:8081 | GLPI |

## Acesso pela rede local

Por padrão tudo responde em `localhost`. Para acessar de outros computadores e celulares da rede, rode depois do `make setup`:

```bash
make rede-local                     # detecta o IP do servidor
make rede-local ip=192.168.0.10     # ou informe o IP (ou um nome DNS da rede)
```

O script ([`rede-local.sh`](rede-local.sh)):

1. Troca no `.env` o `PUBLIC_URL` para `https://<IP>` e o `KC_HOSTNAME` para o IP.
2. Gera um certificado HTTPS autoassinado (`nginx/certs/cesup.crt`) e ativa a porta 443 no nginx.
3. Reconstrói o PWA e recria Keycloak, Grafana, API e nginx com o novo endereço.
4. Inclui o endereço nos redirect URIs dos clients do Keycloak.

Depois disso, acesse `https://<IP>` (PWA, `/api/docs`, `/auth`, `/grafana`, `/zabbix/`) e `http://<IP>:8081` (GLPI). A porta 80 continua respondendo em HTTP.

**Por que HTTPS:** os navegadores só liberam câmera e microfone em HTTPS ou em `localhost`. Sem HTTPS, a leitura de QR Code, a foto e a gravação de voz do PWA não funcionam nos outros aparelhos. O certificado é autoassinado, então no 1º acesso o navegador mostra um aviso. Aceite-o, ou instale `nginx/certs/cesup.crt` como certificado confiável nos aparelhos. Se não precisar dessas funções, use `make rede-local args=--sem-https`.

**Firewall:** se o servidor tiver firewall, libere as portas 80, 443 e 8081 para a rede local. Por exemplo, com `ufw`: `sudo ufw allow from 192.168.0.0/24 to any port 80,443,8081 proto tcp`.

Se o IP do servidor mudar, rode `make rede-local` de novo. É seguro repetir.

### Servidor no Windows com WSL2

Quando o Docker roda dentro do WSL2, o WSL fica por padrão numa rede virtual própria (modo NAT). O IP que o `make rede-local` detecta lá dentro, algo como `172.26.x.x`, só é alcançado pelo próprio Windows: celulares e outros computadores não chegam a ele. Para liberar o acesso, siga os passos abaixo uma vez.

1. **Modo de rede espelhado.** Crie o arquivo `C:\Users\<seu-usuário>\.wslconfig` com:

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

   O WSL só lê esse arquivo ao iniciar. Reinicie-o no PowerShell com `wsl --shutdown` (isso para os containers) e, de volta ao WSL, rode `docker compose up -d`. Para conferir, `ip -4 addr` dentro do WSL deve mostrar o mesmo IP do Wi-Fi ou da rede cabeada do Windows.

2. **Firewall do Windows e do Hyper-V.** No PowerShell **como Administrador**:

   ```powershell
   Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
   New-NetFirewallRule -DisplayName "CESUP Incidentes" -Direction Inbound -Protocol TCP -LocalPort 80,443,8081 -Action Allow -Profile Private
   New-NetFirewallHyperVRule -Name "CESUP-WSL" -DisplayName "CESUP Incidentes (WSL)" -Direction Inbound -VMCreatorId "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}" -Protocol TCP -LocalPorts 80,443,8081
   ```

   O primeiro comando marca a rede como particular; use-o só em rede doméstica ou de trabalho, e troque `"Wi-Fi"` pelo nome do adaptador se for cabo. O segundo libera as portas no firewall do Windows. O terceiro libera as portas no firewall do Hyper-V, que no modo espelhado fica entre a rede e o WSL e bloqueia conexões de entrada por padrão. Se um comando responder "Não é possível criar um arquivo já existente", a regra já existe e pode seguir.

3. **Antivírus com firewall próprio.** McAfee, Norton, Kaspersky e similares substituem o firewall do Windows, e as regras do passo 2 deixam de valer. No firewall do antivírus, libere as portas TCP **80, 443 e 8081** para a rede doméstica ou de trabalho (no McAfee: Firewall → Portas e serviços do sistema → Adicionar).

4. **Endereço público.** Descubra o IP do Windows com `ipconfig` (linha "Endereço IPv4" do Wi-Fi ou da Ethernet) e, no WSL, rode `make rede-local ip=<esse IP>`. Para o IP não mudar, reserve-o para o computador no DHCP do roteador.

**Teste a partir de outro aparelho.** No modo espelhado, o próprio Windows por padrão não alcança os containers pelo IP da rede, então um teste feito no próprio computador falha mesmo com tudo certo. Abra `https://<IP>` num celular conectado à mesma rede, com os dados móveis desligados.

**Se o celular não abrir,** veja se a requisição chegou ao servidor, logo depois de tentar:

```bash
docker logs --since 5m cesup-nginx 2>&1 | tail -20
```

Se não aparecer nenhuma linha com o IP do celular, a conexão está sendo bloqueada antes do WSL. Revise o firewall do antivírus (passo 3) e verifique se o roteador não tem isolamento entre clientes ("AP isolation" ou rede de convidados).

## Vigia externo

O vigia ([`vigia/`](vigia/)) roda em outro dispositivo, com 4G/GSM, e consulta a cada 60 s:

```
GET http://<IP_DO_SERVIDOR>/api/v1/heartbeat
Authorization: Bearer <VIGIA_TOKEN>
```

Copie o `VIGIA_TOKEN` do `.env` para o dispositivo do vigia.
