/**
 * Сборка отчёта Traffic Quality Lab в Google Sheets.
 *
 * Работает без ключей сервисного аккаунта: скрипт привязан к таблице и пишет в неё
 * от имени владельца.
 *   - «Обновить отчёт» забирает CSV, которые пайплайн кладёт в exports/sheets/,
 *     из репозитория на GitHub и раскладывает их по листам с оформлением.
 *   - «Выгрузить Метрику» берёт живые визиты из Reporting API за последние N дней
 *     и оформляет их так же.
 *   - «Обновлять каждый день» ставит триггер на обе выгрузки.
 *
 * Настройка: Расширения → Apps Script → вставить файл → Настройки проекта →
 * Свойства скрипта. Для листа Метрики нужны METRIKA_TOKEN и METRIKA_COUNTER_ID,
 * по желанию METRIKA_GOAL_ADD_TO_CART, METRIKA_GOAL_FORM_SUBMIT, METRIKA_DAYS (по умолчанию 30).
 * Колонки CSV задаёт src/report/sheet_tables.py: LAYOUT ниже меняется вместе с ним.
 */

const REPO_RAW = 'https://raw.githubusercontent.com/yzinchenko-data/traffic-quality-lab/main/exports/sheets/';
const METRIKA_SHEET = 'Метрика live';

const COLORS = {
  header: '#0F766E',
  headerText: '#FFFFFF',
  flag: '#FDE3E0',
  low: '#F8696B',
  mid: '#FFEB84',
  high: '#63BE7B',
  total: '#F1F5F4',
};

// Подписи колонок на листах. Чего нет в словаре, остаётся как в CSV.
const LABELS = {
  date: 'Дата', ssp: 'SSP', placement: 'Площадка', kind: 'Тип', slice: 'Срез',
  start: 'Начало', end: 'Конец', days: 'Дней', source: 'Источник', issue: 'Проблема',
  rows: 'Строк', detail: 'Детали',
  dsp_clicks: 'Клики DSP', dsp_clicks_matched: 'Клики DSP (дни с Верификатором)',
  verifier_total: 'Кликов всего с учётом IVT', givt: 'GIVT', sivt: 'SIVT', clean_clicks: 'Чистые клики',
  visits: 'Визиты', visits_matched: 'Визиты (дни с Верификатором)', users: 'Посетители', robots: 'Роботы',
  add_to_cart: 'Корзина', form_submit: 'Заявки',
  reach_dsp: 'Доходимость от DSP', reach_verifier: 'Доходимость от Верификатора',
  dsp_vs_verifier_pct: 'Расхождение DSP / Верификатор, %', givt_share: 'Доля GIVT', sivt_share: 'Доля SIVT',
  robot_share: 'Роботность', bounce_rate: 'Отказы', cr_cart: 'CR корзина', cr_form: 'CR заявка',
  avg_daily_reach: 'Средняя доходимость по дням', avg_daily_gap_pct: 'Среднее расхождение по дням, %',
  z: 'robust z', flag: 'Аномалия',
  utm_source: 'utm_source', utm_medium: 'utm_medium', utm_campaign: 'utm_campaign', utm_content: 'utm_content',
};

// Оформление листов: доли в %, колонка-флаг для подсветки строки, градиент.
// gradient.goodHigh = true: большие значения зелёные (доходимость), false: красные (GIVT, роботность).
const LAYOUT = {
  summary: {
    title: 'Сводка', freezeCols: 1, totalRow: true,
    percent: ['reach_dsp', 'reach_verifier', 'givt_share', 'sivt_share', 'robot_share', 'cr_cart', 'cr_form', 'avg_daily_reach'],
    gradient: { col: 'reach_verifier', goodHigh: true },
  },
  daily_ssp: {
    title: 'По дням SSP', freezeCols: 2,
    percent: ['reach_verifier'], flag: 'flag',
    gradient: { col: 'reach_verifier', goodHigh: true },
  },
  givt: {
    title: 'Площадки GIVT', freezeCols: 2,
    percent: ['givt_share'], flag: 'flag',
    gradient: { col: 'givt_share', goodHigh: false },
  },
  anomalies: { title: 'Аномалии' },
  cleaning: { title: 'Чистка' },
};

const METRIKA_LAYOUT = {
  title: METRIKA_SHEET, freezeCols: 1,
  percent: ['bounce_rate', 'robot_share', 'cr_cart', 'cr_form'], flag: 'flag',
  gradient: { col: 'robot_share', goodHigh: false },
};

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Traffic Quality Lab')
    .addItem('Обновить отчёт', 'buildReport')
    .addItem('Выгрузить Метрику', 'exportMetrika')
    .addSeparator()
    .addItem('Обновлять каждый день', 'enableDailyTrigger')
    .addItem('Отключить обновление', 'disableTriggers')
    .addToUi();
}

/** Все листы отчёта из CSV в репозитории. */
function buildReport() {
  const ss = SpreadsheetApp.getActive();
  Object.keys(LAYOUT).forEach((name, i) => {
    const resp = UrlFetchApp.fetch(REPO_RAW + name + '.csv', { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) throw new Error(name + '.csv: HTTP ' + resp.getResponseCode());
    const csv = Utilities.parseCsv(resp.getContentText('UTF-8'));
    const header = csv[0];
    const rows = csv.slice(1).map(r => r.map(parseCell_));
    writeSheet_(ss, LAYOUT[name], header, rows, i);
  });
  ss.toast('Отчёт обновлён ' + now_(), 'Traffic Quality Lab');
}

/** Визиты из Метрики за последние N дней по датам и UTM, с той же подсветкой. */
function exportMetrika() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('METRIKA_TOKEN');
  const counter = props.getProperty('METRIKA_COUNTER_ID');
  if (!token || !counter) throw new Error('Нужны свойства скрипта METRIKA_TOKEN и METRIKA_COUNTER_ID');
  const days = Number(props.getProperty('METRIKA_DAYS') || 30);
  const goals = [props.getProperty('METRIKA_GOAL_ADD_TO_CART'), props.getProperty('METRIKA_GOAL_FORM_SUBMIT')];

  const dims = ['ym:s:date', 'ym:s:UTMSource', 'ym:s:UTMMedium', 'ym:s:UTMCampaign', 'ym:s:UTMContent'];
  const metrics = ['ym:s:visits', 'ym:s:users', 'ym:s:bounceRate', 'ym:s:robotPercentage'];
  goals.forEach(g => { if (g) metrics.push('ym:s:goal' + g + 'reaches'); });

  const end = new Date();
  const start = new Date(end.getTime() - (days - 1) * 86400000);
  const params = {
    ids: counter, date1: ymd_(start), date2: ymd_(end),
    dimensions: dims.join(','), metrics: metrics.join(','),
    accuracy: 'full', limit: 10000, sort: 'ym:s:date',
  };
  const url = 'https://api-metrika.yandex.net/stat/v1/data?' +
    Object.keys(params).map(k => k + '=' + encodeURIComponent(params[k])).join('&');
  const resp = fetchWithRetry_(url, token);
  const data = JSON.parse(resp.getContentText()).data;

  const header = ['date', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
    'visits', 'users', 'bounce_rate', 'robot_share'];
  if (goals[0]) header.push('add_to_cart');
  if (goals[1]) header.push('form_submit');
  if (goals[0]) header.push('cr_cart');
  if (goals[1]) header.push('cr_form');
  header.push('flag');

  const rows = data.map(item => {
    const d = item.dimensions.map(x => x.name || '(не задано)');
    const m = item.metrics;
    const visits = m[0];
    const row = d.concat([visits, m[1], m[2] / 100, m[3] / 100]);
    const goalVals = m.slice(4);
    goalVals.forEach(v => row.push(v));
    goalVals.forEach(v => row.push(visits ? v / visits : ''));
    // Флаг: больше половины визитов среза Метрика считает роботами
    row.push(m[3] >= 50);
    return row;
  });
  writeSheet_(SpreadsheetApp.getActive(), METRIKA_LAYOUT, header, rows, Object.keys(LAYOUT).length);
  SpreadsheetApp.getActive().toast('Метрика: ' + rows.length + ' строк, ' + now_(), 'Traffic Quality Lab');
}

function dailyUpdate() {
  buildReport();
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('METRIKA_TOKEN')) exportMetrika();
}

function enableDailyTrigger() {
  disableTriggers();
  ScriptApp.newTrigger('dailyUpdate').timeBased().everyDays(1).atHour(8).create();
  SpreadsheetApp.getActive().toast('Обновление каждый день в 8:00', 'Traffic Quality Lab');
}

function disableTriggers() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'dailyUpdate')
    .forEach(t => ScriptApp.deleteTrigger(t));
}

// ---------- оформление ----------

function writeSheet_(ss, layout, header, rows, index) {
  let sh = ss.getSheetByName(layout.title);
  if (!sh) sh = ss.insertSheet(layout.title, Math.min(index, ss.getSheets().length));
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.setFrozenColumns(0);

  const nCols = header.length;
  const nRows = rows.length;
  sh.getRange(1, 1, 1, nCols)
    .setValues([header.map(h => LABELS[h] || h)])
    .setFontWeight('bold').setFontColor(COLORS.headerText).setBackground(COLORS.header)
    .setWrap(true).setVerticalAlignment('middle');
  sh.setRowHeight(1, 42);
  if (nRows) sh.getRange(2, 1, nRows, nCols).setValues(rows);
  sh.setFrozenRows(1);
  if (layout.freezeCols) sh.setFrozenColumns(layout.freezeCols);

  const col = name => header.indexOf(name) + 1;
  if (nRows) {
    (layout.percent || []).forEach(p => {
      if (col(p)) sh.getRange(2, col(p), nRows, 1).setNumberFormat('0.0%');
    });
    if (col('dsp_vs_verifier_pct')) sh.getRange(2, col('dsp_vs_verifier_pct'), nRows, 1).setNumberFormat('0.00');
    if (col('avg_daily_gap_pct')) sh.getRange(2, col('avg_daily_gap_pct'), nRows, 1).setNumberFormat('0.00');
    if (col('z')) sh.getRange(2, col('z'), nRows, 1).setNumberFormat('0.00');
    if (layout.totalRow) {
      sh.getRange(nRows + 1, 1, 1, nCols).setFontWeight('bold').setBackground(COLORS.total);
    }
    sh.getRange(1, 1, nRows + 1, nCols).setBorder(true, true, true, true, true, true, '#D9E2DF', SpreadsheetApp.BorderStyle.SOLID);
  }

  const rules = [];
  if (nRows && layout.flag && col(layout.flag)) {
    const letter = columnLetter_(col(layout.flag));
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=$' + letter + '2=TRUE')
      .setBackground(COLORS.flag).setBold(true)
      .setRanges([sh.getRange(2, 1, nRows, nCols)])
      .build());
  }
  if (nRows && layout.gradient && col(layout.gradient.col)) {
    // В сводке градиент без строки «Итого»
    const n = layout.totalRow ? nRows - 1 : nRows;
    const [lo, hi] = layout.gradient.goodHigh ? [COLORS.low, COLORS.high] : [COLORS.high, COLORS.low];
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .setGradientMinpoint(lo)
      .setGradientMidpointWithValue(COLORS.mid, SpreadsheetApp.InterpolationType.PERCENTILE, '50')
      .setGradientMaxpoint(hi)
      .setRanges([sh.getRange(2, col(layout.gradient.col), n, 1)])
      .build());
  }
  sh.setConditionalFormatRules(rules);

  sh.autoResizeColumns(1, nCols);
  for (let c = 1; c <= nCols; c++) {
    sh.setColumnWidth(c, Math.min(Math.max(sh.getColumnWidth(c), 90), 220));
  }
  sh.setTabColor(layout.flag ? '#B42318' : COLORS.header);
}

// ---------- утилиты ----------

function parseCell_(v) {
  if (v === '') return '';
  if (v === 'True' || v === 'TRUE') return true;
  if (v === 'False' || v === 'FALSE') return false;
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
  return v;
}

function columnLetter_(n) {
  let s = '';
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

function fetchWithRetry_(url, token) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const resp = UrlFetchApp.fetch(url, { headers: { Authorization: 'OAuth ' + token }, muteHttpExceptions: true });
    const code = resp.getResponseCode();
    if (code === 200) return resp;
    if (code !== 429 && code < 500) throw new Error('HTTP ' + code + ': ' + resp.getContentText().slice(0, 200));
    Utilities.sleep(2000 * (attempt + 1));
  }
  throw new Error('API Метрики не ответил после 4 попыток');
}

function ymd_(d) { return Utilities.formatDate(d, 'Europe/Moscow', 'yyyy-MM-dd'); }
function now_() { return Utilities.formatDate(new Date(), 'Europe/Moscow', 'dd.MM.yyyy HH:mm'); }
