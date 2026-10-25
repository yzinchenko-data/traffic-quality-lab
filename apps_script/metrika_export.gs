/**
 * Выгрузка Яндекс Метрики в Google Sheets.
 *
 * Как пользоваться:
 * 1. Расширения → Apps Script → вставить этот файл.
 * 2. Настройки проекта → Свойства скрипта: METRIKA_TOKEN = OAuth-токен Метрики.
 * 3. Запустить setup() — появится лист «⚙️ Отчёты» с примером строки.
 * 4. Заполнить строки и запустить runAll() (или повесить на триггер по времени).
 *
 * Одна строка листа «⚙️ Отчёты» = одна выгрузка:
 *   Лист | Счётчик | Дата с | Дата по | Группировки | Метрики | Фильтр | Вкл
 */

const SETTINGS_SHEET = '⚙️ Отчёты';
const API_URL = 'https://api-metrika.yandex.net/stat/v1/data';
const PAGE_SIZE = 10000;
const HEADER = ['Лист', 'Счётчик', 'Дата с', 'Дата по', 'Группировки', 'Метрики', 'Фильтр', 'Вкл', 'Статус'];

function setup() {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(SETTINGS_SHEET) || ss.insertSheet(SETTINGS_SHEET, 0);
  sh.clear();
  sh.getRange(1, 1, 1, HEADER.length).setValues([HEADER])
    .setFontWeight('bold').setBackground('#0F766E').setFontColor('#FFFFFF');
  sh.getRange(2, 1, 1, 8).setValues([[
    'metrika_visits', '00000000', '2026-09-01', '2026-09-30',
    'ym:s:date,ym:s:UTMSource,ym:s:UTMMedium,ym:s:UTMCampaign,ym:s:UTMContent',
    'ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:robotPercentage',
    '', true,
  ]]);
  sh.setFrozenRows(1);
  sh.autoResizeColumns(1, HEADER.length);
}

function runAll() {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(SETTINGS_SHEET);
  const rows = sh.getRange(2, 1, Math.max(sh.getLastRow() - 1, 0), 8).getValues();
  rows.forEach((r, i) => {
    const [sheetName, counter, d1, d2, dims, metrics, filter, enabled] = r;
    if (!enabled || !sheetName) return;
    const statusCell = sh.getRange(i + 2, 9);
    try {
      const n = exportReport_(ss, sheetName, String(counter), fmt_(d1), fmt_(d2), dims, metrics, filter);
      statusCell.setValue('OK: ' + n + ' строк, ' + new Date().toLocaleString('ru-RU')).setFontColor('#027A48');
    } catch (e) {
      statusCell.setValue('Ошибка: ' + e.message).setFontColor('#B42318');
    }
  });
}

function exportReport_(ss, sheetName, counter, date1, date2, dims, metrics, filter) {
  const token = PropertiesService.getScriptProperties().getProperty('METRIKA_TOKEN');
  if (!token) throw new Error('нет METRIKA_TOKEN в свойствах скрипта');

  const dimList = String(dims).split(',').map(s => s.trim()).filter(String);
  const metList = String(metrics).split(',').map(s => s.trim()).filter(String);
  const rows = [];
  let offset = 1;
  let total = Infinity;

  while (offset <= total) {
    const params = {
      ids: counter, date1: date1, date2: date2,
      dimensions: dimList.join(','), metrics: metList.join(','),
      accuracy: 'full', limit: PAGE_SIZE, offset: offset,
    };
    if (filter) params.filters = filter;
    const url = API_URL + '?' + Object.keys(params)
      .map(k => k + '=' + encodeURIComponent(params[k])).join('&');

    const resp = fetchWithRetry_(url, token);
    const data = JSON.parse(resp.getContentText());
    total = data.total_rows;
    data.data.forEach(item => {
      rows.push(item.dimensions.map(d => d.name).concat(item.metrics));
    });
    offset += PAGE_SIZE;
  }

  const sh = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  sh.clearContents();
  const header = dimList.concat(metList).map(s => s.replace('ym:s:', ''));
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  if (rows.length) sh.getRange(2, 1, rows.length, header.length).setValues(rows);
  sh.setFrozenRows(1);
  return rows.length;
}

function fetchWithRetry_(url, token) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const resp = UrlFetchApp.fetch(url, {
      headers: { Authorization: 'OAuth ' + token },
      muteHttpExceptions: true,
    });
    const code = resp.getResponseCode();
    if (code === 200) return resp;
    if (code !== 429 && code < 500) throw new Error('HTTP ' + code + ': ' + resp.getContentText().slice(0, 200));
    Utilities.sleep(2000 * (attempt + 1));
  }
  throw new Error('API не ответил после 4 попыток');
}

function fmt_(d) {
  return d instanceof Date ? Utilities.formatDate(d, 'Europe/Moscow', 'yyyy-MM-dd') : String(d);
}
