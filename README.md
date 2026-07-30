# ПеревозАвто — лендинг перевозки автомобилей (Laravel + PostgreSQL)

Высококонверсионный лендинг + генерируемые из базы SEO-страницы «город — город».
Laravel 13, PHP 8.4, PostgreSQL.

## Быстрый старт

```bash
composer install
cp .env.example .env          # уже настроен на PostgreSQL
php artisan key:generate

# создать базу perevozavto в PostgreSQL, затем:
php artisan migrate --seed    # 8 стартовых маршрутов из database/seeders/data/routes.json
php artisan serve
```

Для локальной разработки без PostgreSQL достаточно указать в `.env`
`DB_CONNECTION=sqlite` и создать файл `database/database.sqlite`.

## Как это устроено

| Что | Где |
|---|---|
| Главная | `GET /` → `HomeController` → `resources/views/home.blade.php` |
| SEO-страница маршрута | `GET /avtovoz-{slug}` → `RouteController` → `route.blade.php` |
| Приём заявок | `POST /leads` → `LeadController` (JSON, throttle 10/мин) |
| Sitemap | `GET /sitemap.xml` → `SitemapController` (все маршруты из базы) |
| Данные маршрутов | таблица `routes`, модель `App\Models\TransportRoute` |
| Заявки | таблица `leads`, модель `App\Models\Lead` |
| Контакты и реквизиты | `config/landing.php` — заменить перед запуском |
| Стили (дизайн-токены в `:root`) | `public/css/style.css` |
| JS: маска телефона, формы, меню | `public/js/main.js` |

**Новая SEO-страница = одна запись в таблице `routes`** (сидер или админка в будущем):
slug, города (+ падежные формы `city_from_gen` «из Москвы», `city_to_gen` «во Владивосток»),
расстояние, сроки, цены по типам кузова, `waypoints`/`highways` (jsonb), опциональные
`seo_text`, `meta_title`, `meta_description`. Всё остальное — заголовки, метатеги,
таблица цен (недостающие типы кузова досчитываются коэффициентами в
`TransportRoute::price()`), Schema.org (Service, Offer, FAQPage, BreadcrumbList),
перелинковка и sitemap — собирается автоматически.

## Дизайн-система

Концепция «ночная трасса»: тёмный асфальт `#10151d`, янтарная разметка `#ffb020`,
пунктирная осевая линия, «сигнальная лента» на CTA. В hero — фотография перевозки
автомобиля эвакуатором, затонированная под палитру (обесцвечивание + синий подтон,
поверх — градиентное затемнение в CSS). Шрифты: Unbounded (заголовки) + Golos Text.

Фото: Wikimedia Commons, «Car carrier loading Maybach in Tokyo», лицензия CC0
(public domain) — можно использовать без атрибуции; чужой брендинг на платформе замыт.

## Конверсионные элементы

- Калькулятор-форма в первом экране; на страницах маршрутов — с предзаполненными городами
- Телефон 8-800 в липкой шапке + липкая CTA-панель на мобильных
- «Ближайшая загрузка» — дата (сегодня + 2 дня) в JS, элемент срочности
- Снятие страхов: оплата после доставки, страховка до 5 млн ₽, договор, ГЛОНАСС, фотоотчёт
- Таблицы цен, отзывы с маршрутами, FAQ-аккордеон с разметкой FAQPage

## Что доделать перед продакшеном

- Заменить контакты в `config/landing.php` и домен в `APP_URL`
- Подключить уведомления о лидах (Telegram/CRM) в `LeadController@store` — место помечено
- Страницы политики ПДн и оферты (ссылки в футере — заглушки)
- Заполнить `seo_text` уникальными текстами хотя бы для топ-маршрутов
- Кэширование: `php artisan config:cache route:cache view:cache`, кэш ответов страниц маршрутов
