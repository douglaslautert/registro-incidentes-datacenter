/**
 * Zabbix Media Type: GLPI Webhook
 * Abre ou atualiza chamados no GLPI via API REST.
 *
 * Parâmetros configurados no Media Type do Zabbix:
 *   glpi_url       - URL base da API (ex: https://glpi.intra/apirest.php)
 *   glpi_user      - usuário de serviço (zabbix-api)
 *   glpi_password  - senha do usuário de serviço
 *   app_token      - App-Token criado no GLPI (Setup > General > API)
 *   event_id       - {EVENT.ID}
 *   event_value    - {EVENT.VALUE}  1=PROBLEM 0=OK
 *   host_name      - {HOST.NAME}
 *   trigger_name   - {TRIGGER.NAME}
 *   trigger_sev    - {TRIGGER.NSEVERITY} 0-5
 *   event_date     - {EVENT.DATE}
 *   event_time     - {EVENT.TIME}
 *   glpi_ticket_id - {EVENT.TAGS.__glpi_ticket_id} (preenchido no recovery)
 */

var GLPI = {
  url:      params.glpi_url,
  user:     params.glpi_user,
  password: params.glpi_password,
  appToken: params.app_token,
  session:  null,

  request: function(method, endpoint, body) {
    var req = new HttpRequest();
    req.addHeader('Content-Type: application/json');
    req.addHeader('App-Token: ' + this.appToken);
    if (this.session) {
      req.addHeader('Session-Token: ' + this.session);
    }
    var resp;
    if (method === 'GET')  resp = req.get(this.url + endpoint);
    if (method === 'POST') resp = req.post(this.url + endpoint, JSON.stringify(body));
    if (method === 'PUT')  resp = req.put(this.url + endpoint, JSON.stringify(body));
    var code = req.getStatus();
    if (code < 200 || code > 299) {
      throw 'GLPI API error: HTTP ' + code + ' → ' + resp;
    }
    return JSON.parse(resp);
  },

  initSession: function() {
    var req = new HttpRequest();
    req.addHeader('Content-Type: application/json');
    req.addHeader('App-Token: ' + this.appToken);
    req.addHeader('Authorization: user_token ' +
      btoa(this.user + ':' + this.password));
    var resp = JSON.parse(req.get(this.url + '/initSession'));
    this.session = resp.session_token;
  },

  killSession: function() {
    try { this.request('GET', '/killSession'); } catch(e) {}
  }
};

// Mapeamento severidade Zabbix → prioridade GLPI
// Zabbix: 0=Not class 1=Info 2=Warning 3=Average 4=High 5=Disaster
// GLPI:   1=Very low  2=Low   3=Medium  4=High   5=Very high 6=Major
var SEV_MAP = {'0':1, '1':2, '2':3, '3':3, '4':5, '5':6};

try {
  GLPI.initSession();

  if (params.event_value === '1') {
    // PROBLEM — abrir chamado
    var ticket = GLPI.request('POST', '/Ticket', {
      'input': {
        'name': '[Zabbix] ' + params.trigger_name + ' — ' + params.host_name,
        'content': 'Host: ' + params.host_name +
                   '\nTrigger: ' + params.trigger_name +
                   '\nSeveridade: ' + params.trigger_sev +
                   '\nInício: ' + params.event_date + ' ' + params.event_time +
                   '\nEvento Zabbix ID: ' + params.event_id,
        'priority': SEV_MAP[params.trigger_sev] || 3,
        'type':   1,   // 1=Incident
        'status': 1    // 1=New
      }
    });
    // Retorna o ID para o Zabbix armazenar na tag do evento
    return JSON.stringify({ticket_id: ticket.id});

  } else {
    // RECOVERY — atualizar chamado existente com horário de fim
    var tid = params.glpi_ticket_id;
    if (!tid) { throw 'Recovery sem glpi_ticket_id na tag do evento'; }
    GLPI.request('PUT', '/Ticket/' + tid, {
      'input': {
        'status': 5,  // 5=Solved (pelo Zabbix)
        'solution': 'Recuperação automática detectada pelo Zabbix em ' +
                    params.event_date + ' ' + params.event_time
      }
    });
    return JSON.stringify({status: 'resolved', ticket_id: tid});
  }

} catch(e) {
  throw 'Webhook falhou: ' + e;
} finally {
  GLPI.killSession();
}
