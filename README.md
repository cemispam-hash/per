# ПеревозАвто — лендинг перевозки автомобилей между городами

Высококонверсионный лендинг + шаблон SEO-страниц «город — город».
Статическая вёрстка, спроектированная под последующий перенос на **Laravel + PostgreSQL**.

## Структура

```
index.html                        — главный лендинг
avtovoz-moskva-vladivostok.html   — шаблон SEO-страницы маршрута (будущая Blade-вьюха)
css/style.css                     — единая дизайн-система (токены в :root)
js/main.js                        — меню, маска телефона, формы, дата загрузки
data/routes.json                  — прообраз таблицы routes в PostgreSQL
```

## Дизайн-система

Концепция «ночная трасса»: тёмный асфальт `#10151d`, янтарная разметка/фары `#ffb020`,
мотив пунктирной осевой линии и «сигнальной ленты» автовоза (амбер-штриховка).

- Дисплейный шрифт: **Unbounded** (заголовки, цифры-акценты)
- Текстовый: **Golos Text**
- Все токены — CSS-переменные в `:root` (`css/style.css`), менять палитру можно в одном месте.

## Конверсионные элементы

- Калькулятор-форма в первом экране (главный лид-магнит) + предзаполнение маршрута на SEO-страницах
- Телефон 8-800 в липкой шапке, липкая CTA-панель на мобильных
- «Ближайшая загрузка» — дата генерируется JS (сегодня + 2 дня), создаёт срочность
- Оплата после доставки, страховка, договор — сняты ключевые страхи ЦА
- Таблица маршрутов с ценами (транзакционный интент), отзывы с маршрутами, FAQ

## SEO

- Уникальные title/description на каждой странице, canonical, Open Graph
- Schema.org JSON-LD: `MovingCompany`, `Service` + `Offer`, `FAQPage`, `BreadcrumbList`
- Перелинковка: таблица маршрутов → страницы маршрутов → «другие направления» в футере
- SEO-текст с H2/H3 и вхождениями «перевозка автомобилей {город} — {город}», «автовоз»

## План переноса на Laravel + PostgreSQL

### 1. Миграция `routes`

```php
Schema::create('routes', function (Blueprint $table) {
    $table->id();
    $table->string('slug')->unique();          // moskva-vladivostok
    $table->string('city_from');
    $table->string('city_to');
    $table->string('city_from_gen')->nullable(); // «из Москвы» — родительный падеж
    $table->string('city_to_gen')->nullable();
    $table->unsignedInteger('distance_km');
    $table->unsignedTinyInteger('days_min');
    $table->unsignedTinyInteger('days_max');
    $table->unsignedInteger('price_sedan');
    $table->unsignedInteger('price_crossover')->nullable();
    $table->unsignedInteger('price_suv')->nullable();
    $table->unsignedInteger('price_pickup')->nullable();
    $table->unsignedInteger('price_moto')->nullable();
    $table->unsignedInteger('price_closed_sedan')->nullable();
    $table->jsonb('waypoints')->nullable();    // города по пути
    $table->jsonb('highways')->nullable();     // трассы
    $table->text('seo_text')->nullable();      // уникальный текст страницы
    $table->string('meta_title')->nullable();  // переопределение шаблонного title
    $table->string('meta_description')->nullable();
    $table->boolean('is_popular')->default(false);
    $table->timestamps();
});

Schema::create('leads', function (Blueprint $table) {
    $table->id();
    $table->string('phone');
    $table->string('city_from')->nullable();
    $table->string('city_to')->nullable();
    $table->string('car_type')->nullable();
    $table->string('page_url')->nullable();    // с какой страницы пришёл лид
    $table->string('utm_source')->nullable();
    $table->timestamps();
});
```

Стартовые данные — в `data/routes.json` (сидер).

### 2. Роутинг

```php
Route::get('/', HomeController::class);
Route::get('/avtovoz-{route:slug}', RouteController::class); // model binding по slug
Route::post('/api/leads', LeadController::class);
```

### 3. Blade-разметка

`avtovoz-moskva-vladivostok.html` режется на layout и partials:

| Фрагмент HTML                    | Blade                                  |
|----------------------------------|----------------------------------------|
| `<head>` + шапка + футер         | `layouts/app.blade.php`                |
| `.calc` (форма-калькулятор)      | `partials/calc.blade.php` (пропсы from/to) |
| `.routes-table`                  | `partials/routes-table.blade.php`      |
| `.faq` + FAQPage JSON-LD         | `partials/faq.blade.php`               |
| страница маршрута                | `pages/route.blade.php`                |

Шаблонные метатеги в `route.blade.php`:

```
title: «Автовоз {city_from} — {city_to}: перевозка автомобилей,
        цена от {price_sedan} ₽ | ПеревозАвто»
h1:    «Автовоз {city_from} — {city_to}: перевозка автомобилей от {price_sedan} ₽»
```

Для избежания дублей у сотен страниц — заполнять `seo_text` уникальным текстом
(хотя бы для топ-20 маршрутов) и держать `meta_title` переопределяемым.

### 4. Формы

В `js/main.js` отправка помечена комментарием — заменить имитацию на
`fetch('/api/leads', ...)`, добавить CSRF-токен и уведомление в Telegram/CRM.

### 5. Sitemap

`spatie/laravel-sitemap`: главная + все `routes` → `/sitemap.xml`, обновлять по cron.

## Что заменить перед запуском

- Телефон `8 (800) 550-44-70`, e-mail, адрес, ИНН — плейсхолдеры
- Домен `perevozavto.example` в canonical/OG/JSON-LD
- Ссылки-заглушки `href="#"` на страницы маршрутов — по мере создания страниц
- Политика ПДн и оферта — подключить реальные документы
