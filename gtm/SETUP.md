# Настройка GTM и Метрики для витрины Polka

Витрина сама шлёт события в `window.dataLayer`. В GTM нужно поймать их и передать в Метрику как цели.

## 1. Счётчик Метрики

1. Создай счётчик на адрес витрины (`https://yzinchenko-data.github.io/traffic-quality-lab/`).
2. Включи Вебвизор.
3. Создай JavaScript-цели с идентификаторами `add_to_cart`, `form_submit`, `scroll_50`, `click_phone`.
4. Номера целей `add_to_cart` и `form_submit` впиши в `.env` (`METRIKA_GOAL_ADD_TO_CART`, `METRIKA_GOAL_FORM_SUBMIT`).

## 2. Контейнер GTM

ID контейнера впиши в `site/assets/config.js` (`gtmId`).

### Переменные

| Имя | Тип | Значение |
|---|---|---|
| `CONST — Metrika ID` | Константа | номер счётчика |
| `DLV — product_id` | Переменная уровня данных | `product_id` |
| `DLV — value` | Переменная уровня данных | `value` |

### Триггеры

| Имя | Тип | Условие |
|---|---|---|
| `CE — add_to_cart` | Пользовательское событие | `add_to_cart` |
| `CE — form_submit` | Пользовательское событие | `form_submit` |
| `CE — scroll_50` | Пользовательское событие | `scroll_50` |
| `CE — click_phone` | Пользовательское событие | `click_phone` |

### Теги

| Имя | Тип | Триггер |
|---|---|---|
| `Metrika — counter` | Пользовательский HTML: код счётчика с `{{CONST — Metrika ID}}` | All Pages |
| `Metrika — goal add_to_cart` | Пользовательский HTML: `<script>ym({{CONST — Metrika ID}}, 'reachGoal', 'add_to_cart', {product: {{DLV — product_id}}, value: {{DLV — value}}});</script>` | `CE — add_to_cart` |
| `Metrika — goal form_submit` | Пользовательский HTML: `<script>ym({{CONST — Metrika ID}}, 'reachGoal', 'form_submit');</script>` | `CE — form_submit` |
| `Metrika — goal scroll_50` | то же для `scroll_50` | `CE — scroll_50` |
| `Metrika — goal click_phone` | то же для `click_phone` | `CE — click_phone` |

Для тегов целей в «Расширенных настройках → Порядок активации тегов» поставь `Metrika — counter` тегом настройки, чтобы `ym` уже был объявлен.

## 3. Проверка

1. Режим предварительного просмотра GTM → открыть витрину → положить товар в корзину и отправить форму.
2. В Tag Assistant видно события `add_to_cart` и `form_submit` и сработавшие теги.
3. В Метрике: «Конверсии» → цели появляются в течение нескольких минут.

Локально без GTM события видны в консоли браузера: `[dataLayer] {event: "add_to_cart", ...}`.
