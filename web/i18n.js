/* Interface language (English default, Brazilian Portuguese).
   Static text uses data-i18n (text), data-i18n-html (trusted markup from this file) and
   data-i18n-attr="attr:key;attr:key". Dynamic text calls I18N.t(key, {vars}).
   The alert message sent to people has its own language in the draft and does not follow this. */
(() => {
  'use strict';
  const KEY = 'hac-lang';
  const DICT = {
    en: {
      'title': 'Hotspot Alert Console',
      'subtitle': 'Real NASA FIRMS detections from 12 Nov 2026. Alerts are simulated.',
      'lang.group': 'Language',
      'lang.en': 'English', 'lang.pt': 'Português',
      'howto': 'How it works',
      'your-area': 'Your area',
      'q.h': 'Areas with fire',
      'filter': 'Filter', 'filter.all': 'All', 'filter.open': 'To do', 'filter.active': 'Alerts',
      'queue.aria': 'Municipalities with fire detections',
      'map.h': 'Map', 'map.aria': 'Map of fire detections', 'map.zoomout': 'All of Brazil',
      'legend.intensity': 'Fire intensity',
      'lower.aria': 'Phone and activity',
      'tab.phone': 'Phone preview', 'tab.real': 'Real phone', 'tab.log': 'Activity',
      'phone.aria': 'Simulated phone',
      'rp.how': 'How the phone receives', 'rp.ntfy': 'ntfy (works now)', 'rp.page': 'Full-screen page',
      'rp.qr': 'QR code for the phone',
      'rp.n1': 'Scan the code with the phone camera. It opens',
      'rp.n2': 'On that page, tap <strong>Subscribe</strong> and allow notifications. For a stronger alert, install the free ntfy app and subscribe to the channel',
      'rp.n3': 'Press <strong>Send test</strong> here to check it arrives',
      'rp.p1': 'Scan the code with the phone camera',
      'rp.p2': 'Tap <strong>Start receiving alerts</strong> on the phone',
      'rp.basewarn': 'The full-screen page needs an address the phone can open, such as the project\'s GitHub Pages link. <code>localhost</code> only exists on this computer.',
      'rp.test': 'Send test', 'rp.copy': 'Copy link',
      'rp.on': 'Send approved alerts to real phones',
      'rp.settings': 'Settings',
      'rp.base': 'Address where this folder is published (for the full-screen page)',
      'rp.save': 'Save',
      'rp.channel': 'Channel',
      'rp.channel-note': 'on ntfy.sh. Anyone who knows the channel name can read it, so it only carries simulations.',
      'rp.new': 'New channel',
      'cap.summary': 'CAP 1.2 export of the last alert', 'cap.copy': 'Copy CAP XML',
      'foot.1': 'Prototype for NASA Space Apps 2026. Only civil protection can send real alerts.',
      'foot.2': 'Data: NASA FIRMS near-real-time sample (Terra/Aqua MODIS, NOAA-20 VIIRS) and IBGE boundaries. The priority score is provisional; harmonized intensity and how unusual each fire is will come from <code>firms_harmonize</code>.',
    },
    pt: {
      'title': 'Console de Alerta de Focos',
      'subtitle': 'Detecções reais do NASA FIRMS de 12 nov. 2026. Os alertas são simulados.',
      'lang.group': 'Idioma',
      'lang.en': 'English', 'lang.pt': 'Português',
      'howto': 'Como funciona',
      'your-area': 'Sua área',
      'q.h': 'Áreas com fogo',
      'filter': 'Filtro', 'filter.all': 'Todas', 'filter.open': 'A fazer', 'filter.active': 'Alertas',
      'queue.aria': 'Municípios com focos detectados',
      'map.h': 'Mapa', 'map.aria': 'Mapa dos focos detectados', 'map.zoomout': 'Brasil inteiro',
      'legend.intensity': 'Intensidade do fogo',
      'lower.aria': 'Celular e atividade',
      'tab.phone': 'Prévia no celular', 'tab.real': 'Celular de verdade', 'tab.log': 'Atividade',
      'phone.aria': 'Celular simulado',
      'rp.how': 'Como o celular recebe', 'rp.ntfy': 'ntfy (já funciona)', 'rp.page': 'Página em tela cheia',
      'rp.qr': 'QR code para o celular',
      'rp.n1': 'Leia o código com a câmera do celular. Ele abre',
      'rp.n2': 'Nessa página, toque em <strong>Subscribe</strong> e permita as notificações. Para um alerta mais forte, instale o app gratuito ntfy e assine o canal',
      'rp.n3': 'Aperte <strong>Enviar teste</strong> aqui para conferir se chega',
      'rp.p1': 'Leia o código com a câmera do celular',
      'rp.p2': 'No celular, toque em <strong>Start receiving alerts</strong>',
      'rp.basewarn': 'A página em tela cheia precisa de um endereço que o celular consiga abrir, como o link do GitHub Pages do projeto. <code>localhost</code> só existe neste computador.',
      'rp.test': 'Enviar teste', 'rp.copy': 'Copiar link',
      'rp.on': 'Enviar alertas aprovados para celulares de verdade',
      'rp.settings': 'Configurações',
      'rp.base': 'Endereço onde esta pasta está publicada (para a página em tela cheia)',
      'rp.save': 'Salvar',
      'rp.channel': 'Canal',
      'rp.channel-note': 'no ntfy.sh. Quem souber o nome do canal pode lê-lo, por isso ele só transmite simulações.',
      'rp.new': 'Novo canal',
      'cap.summary': 'Exportação CAP 1.2 do último alerta', 'cap.copy': 'Copiar XML CAP',
      'foot.1': 'Protótipo para o NASA Space Apps 2026. Só a Defesa Civil pode enviar alertas reais.',
      'foot.2': 'Dados: amostra quase em tempo real do NASA FIRMS (Terra/Aqua MODIS, NOAA-20 VIIRS) e limites do IBGE. A pontuação de prioridade é provisória; a intensidade harmonizada e o quanto cada fogo foge do normal virão do <code>firms_harmonize</code>.',
    },
  };

  const read = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  const save = v => { try { localStorage.setItem(KEY, v); } catch (e) { /* storage blocked: choice lasts this visit */ } };

  let lang = DICT[read()] ? read() : 'en';
  const subscribers = [];

  function t(key, vars) {
    const s = DICT[lang][key] ?? DICT.en[key];
    if (s === undefined) { console.warn('i18n: missing key', key); return key; }
    return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s;
  }

  function apply(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
    root.querySelectorAll('[data-i18n-html]').forEach(e => { e.innerHTML = t(e.dataset.i18nHtml); });
    root.querySelectorAll('[data-i18n-attr]').forEach(e => {
      e.dataset.i18nAttr.split(';').forEach(pair => { const [attr, key] = pair.split(':'); e.setAttribute(attr, t(key)); });
    });
    document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en';
    document.title = t('title');
    document.querySelectorAll('[data-lang]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));
  }

  function set(next) {
    if (!DICT[next] || next === lang) return;
    lang = next;
    save(next);
    apply();
    subscribers.forEach(fn => fn(next));
  }

  window.I18N = {
    get lang() { return lang; },
    locale: () => (lang === 'pt' ? 'pt-BR' : 'en-US'),
    t, set, apply,
    add: (code, entries) => Object.assign(DICT[code], entries),
    onChange: fn => subscribers.push(fn),
  };

  document.addEventListener('click', e => { const b = e.target.closest('[data-lang]'); if (b) set(b.dataset.lang); });
  apply();
})();
