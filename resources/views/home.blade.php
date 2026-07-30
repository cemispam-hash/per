@extends('layouts.app')

@section('title', 'Перевозка автомобилей автовозом по России — цены от 15 000 ₽ | ПеревозАвто')
@section('meta_description', 'Перевозка автомобилей автовозом между городами России. Открытые и закрытые автовозы, страховка до 5 млн ₽, договор, ГЛОНАСС-контроль. Рассчитайте стоимость за 15 минут.')

@push('jsonld')
<script type="application/ld+json">
{!! json_encode([
    '@context' => 'https://schema.org',
    '@type' => 'MovingCompany',
    'name' => 'ПеревозАвто',
    'description' => 'Перевозка автомобилей автовозами между городами России',
    'telephone' => config('landing.phone_href'),
    'areaServed' => 'RU',
    'priceRange' => '15000-150000 RUB',
    'aggregateRating' => ['@type' => 'AggregateRating', 'ratingValue' => '4.9', 'reviewCount' => '1284'],
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) !!}
</script>
@endpush

@section('content')

  <!-- ============ Hero + калькулятор ============ -->
  <section class="hero">
    <div class="container">
      <div class="hero__in">
        <div>
          <div class="eyebrow">Автовозы по всей России · 120+ городов</div>
          <h1 class="h1">Перевезём ваш автомобиль <em>в любой город России</em> — с договором и страховкой</h1>
          <p class="hero__sub">Открытые и закрытые автовозы каждую неделю по всем федеральным трассам. Вы отдаёте ключи — мы привозим машину без единой лишней царапины и километра пробега.</p>
          <ul class="hero__points">
            <li>Страховка груза до 5 млн ₽</li>
            <li>ГЛОНАСС-мониторинг рейса</li>
            <li>Фотоотчёт при погрузке и выдаче</li>
            <li>Оплата после доставки</li>
          </ul>
        </div>

        @include('partials.calc', ['cities' => $cities])
      </div>

      <div class="hero__stats">
        <div><b class="num">12 лет</b><span>перевозим автомобили</span></div>
        <div><b class="num">18 640</b><span>машин доставлено</span></div>
        <div><b class="num">120+</b><span>городов России</span></div>
        <div><b class="num">4,9 из 5</b><span>рейтинг на Яндексе</span></div>
      </div>
    </div>
  </section>

  <!-- ============ Популярные направления ============ -->
  <section class="section" id="routes">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Направления</div>
        <h2 class="h2">Популярные маршруты и цены</h2>
        <p class="lead">Стоимость указана за легковой автомобиль на открытом автовозе. Точная цена зависит от габаритов машины и даты загрузки — уточните у логиста.</p>
      </div>

      <div class="routes-table-wrap">
        <table class="routes-table">
          <thead>
            <tr>
              <th scope="col">Маршрут</th>
              <th scope="col">Расстояние</th>
              <th scope="col">Срок доставки</th>
              <th scope="col">Цена за легковое авто</th>
            </tr>
          </thead>
          <tbody>
            @foreach ($popular as $r)
              <tr>
                <td><a class="route-link" href="{{ $r->url }}">{{ $r->title }}</a></td>
                <td>{{ $r::money($r->distance_km) }} км</td>
                <td>{{ $r->days_min }}–{{ $r->days_max }} {{ $r->days_max >= 5 ? 'дней' : 'дня' }}</td>
                <td class="price">от {{ $r::money($r->price_sedan) }} ₽</td>
              </tr>
            @endforeach
          </tbody>
        </table>
      </div>

      <div class="routes-more">
        <a class="btn btn--ghost" href="#footer-routes">Все направления перевозки →</a>
      </div>
    </div>
  </section>

  <!-- ============ Типы перевозки ============ -->
  <section class="section section--tight" id="services">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Способы перевозки</div>
        <h2 class="h2">Подберём транспорт под ваш автомобиль и бюджет</h2>
      </div>

      <div class="cards">
        <article class="card card--featured">
          <span class="card__tag">Выбирают 80% клиентов</span>
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 16h20M4 16v-4h9l3-4h4v8M6.5 19a1.8 1.8 0 1 0 0-.01M17.5 19a1.8 1.8 0 1 0 0-.01"/></svg>
          </div>
          <h3 class="h3">Открытый автовоз</h3>
          <p>Стандарт рынка: до 8 машин на трале, регулярные рейсы по всем направлениям. Оптимально по цене и срокам для любых серийных автомобилей.</p>
          <div class="card__price num">от 15 000 ₽<small>цена зависит от маршрута</small></div>
        </article>

        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 8h14v9H3zM17 11h3l1 2v4h-4M6 20a1.6 1.6 0 1 0 0-.01M15 20a1.6 1.6 0 1 0 0-.01"/></svg>
          </div>
          <h3 class="h3">Закрытый автовоз</h3>
          <p>Полная защита от камней, реагентов и посторонних глаз. Для премиальных, коллекционных и новых автомобилей без пробега.</p>
          <div class="card__price num">от 40 000 ₽<small>индивидуальный расчёт</small></div>
        </article>

        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 17h20M3 17l2-7h8l4 4h4v3M7 20a1.6 1.6 0 1 0 0-.01M16 20a1.6 1.6 0 1 0 0-.01M12 10v4"/></svg>
          </div>
          <h3 class="h3">Отдельный эвакуатор</h3>
          <p>Персональная доставка «дверь в дверь» без ожидания загрузки автовоза. Для срочных перевозок и неисправных автомобилей.</p>
          <div class="card__price num">от 25 ₽ / км<small>подача от 2 часов</small></div>
        </article>
      </div>
    </div>
  </section>

  <!-- ============ Как работаем ============ -->
  <section class="section" id="how">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Порядок работы</div>
        <h2 class="h2">От заявки до выдачи ключей — 5 шагов</h2>
      </div>

      <div class="steps-grid">
        <ol class="steps">
          <li class="step">
            <div class="step__pin num" aria-hidden="true">01</div>
            <div class="step__body">
              <h3 class="h3">Заявка и расчёт</h3>
              <p>Вы оставляете заявку или звоните. Логист называет точную стоимость, срок и ближайшую дату загрузки — в течение 15 минут.</p>
            </div>
          </li>
          <li class="step">
            <div class="step__pin num" aria-hidden="true">02</div>
            <div class="step__body">
              <h3 class="h3">Договор и страховка</h3>
              <p>Заключаем договор перевозки (дистанционно или в офисе), страхуем автомобиль на полную стоимость. Предоплата не требуется.</p>
            </div>
          </li>
          <li class="step">
            <div class="step__pin num" aria-hidden="true">03</div>
            <div class="step__body">
              <h3 class="h3">Приёмка и погрузка</h3>
              <p>Водитель осматривает машину, фиксирует состояние в акте с фотографиями, надёжно крепит её на платформе автовоза.</p>
            </div>
          </li>
          <li class="step">
            <div class="step__pin num" aria-hidden="true">04</div>
            <div class="step__body">
              <h3 class="h3">Перевозка под контролем</h3>
              <p>Автовоз идёт по маршруту с ГЛОНАСС-мониторингом. Вы в любой момент видите, где машина, и получаете фотоотчёты с ключевых точек.</p>
            </div>
          </li>
          <li class="step">
            <div class="step__pin num" aria-hidden="true">05</div>
            <div class="step__body">
              <h3 class="h3">Выдача и оплата</h3>
              <p>В городе назначения сверяем состояние авто по акту приёмки. Вы убеждаетесь, что всё в порядке, — и только после этого оплачиваете перевозку.</p>
            </div>
          </li>
        </ol>

        <aside class="steps-aside">
          <h3 class="h3">Ближайшая загрузка — <span data-next-load>уточняется</span></h3>
          <p>Автовозы уходят по популярным направлениям 2–3 раза в неделю. Забронируйте место заранее — перед праздниками график заполняется за 5–7 дней.</p>
          <a class="btn btn--accent btn--block" href="#calc">Забронировать место</a>
        </aside>
      </div>
    </div>
  </section>

  <!-- ============ Гарантии ============ -->
  <section class="section assure">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Гарантии</div>
        <h2 class="h2">Ваш автомобиль под защитой на всём маршруте</h2>
        <p class="lead">Мы отвечаем за машину деньгами и репутацией — все обязательства зафиксированы в договоре.</p>
      </div>

      <div class="cards cards--4">
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>
          </div>
          <h3 class="h3">Страховка до 5 млн ₽</h3>
          <p>Каждый автомобиль застрахован на полную рыночную стоимость на весь период перевозки.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 4h11l3 3v13H5z"/><path d="M9 12h6M9 16h6M9 8h3"/></svg>
          </div>
          <h3 class="h3">Официальный договор</h3>
          <p>Работаем как юрлицо: договор перевозки, акт приёма-передачи, чеки и закрывающие документы.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 1 8 8c0 5-8 12-8 12S4 15 4 10a8 8 0 0 1 8-8z"/></svg>
          </div>
          <h3 class="h3">ГЛОНАСС-контроль</h3>
          <p>Отслеживайте автовоз на карте в реальном времени по ссылке, которую пришлёт логист.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M8 6l2-3h4l2 3"/><circle cx="12" cy="13" r="3.5"/></svg>
          </div>
          <h3 class="h3">Фотоотчёт этапов</h3>
          <p>Фотофиксация при погрузке, в пути и при выдаче — состояние машины подтверждено документально.</p>
        </article>
      </div>
    </div>
  </section>

  <!-- ============ Отзывы ============ -->
  <section class="section" id="reviews">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Отзывы</div>
        <h2 class="h2">1 284 отзыва со средней оценкой 4,9</h2>
      </div>

      <div class="cards">
        <article class="card review">
          <span class="review__route">Москва → Владивосток</span>
          <div class="review__stars" aria-label="Оценка 5 из 5">★★★★★</div>
          <p>Отправлял новый Geely дилеру во Владивосток. Переживал из-за расстояния, но машина пришла на 12-й день ровно в том виде, в каком грузили, — сверяли по фото из акта. Трекинг работал всю дорогу.</p>
          <div class="review__who"><b>Андрей К.</b> · февраль 2026</div>
        </article>
        <article class="card review">
          <span class="review__route">Краснодар → Санкт-Петербург</span>
          <div class="review__stars" aria-label="Оценка 5 из 5">★★★★★</div>
          <p>Переезжали всей семьёй, машину гнать самим было некогда. Забрали прямо от дома, привезли за 3 дня. Оплатила после осмотра — это решающий момент, почему выбрала эту компанию.</p>
          <div class="review__who"><b>Марина В.</b> · май 2026</div>
        </article>
        <article class="card review">
          <span class="review__route">Владивосток → Москва</span>
          <div class="review__stars" aria-label="Оценка 5 из 5">★★★★★</div>
          <p>Покупал праворульный Land Cruiser с аукциона. Логист сам связался с продавцом, принял машину по доверенности и держал меня в курсе на каждом этапе. Сервис уровня «отдал и забыл».</p>
          <div class="review__who"><b>Дмитрий С.</b> · июнь 2026</div>
        </article>
      </div>
    </div>
  </section>

  <!-- ============ FAQ ============ -->
  <section class="section section--tight" id="faq">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Вопросы и ответы</div>
        <h2 class="h2">Частые вопросы о перевозке автомобилей</h2>
      </div>

      @include('partials.faq', ['faq' => [
        ['q' => 'Сколько стоит перевозка автомобиля между городами?',
         'a' => 'Цена зависит от маршрута, габаритов автомобиля и типа автовоза. Ориентиры: Москва — Санкт-Петербург от 15 000 ₽, Москва — Екатеринбург от 28 000 ₽, Москва — Владивосток от 95 000 ₽. Точную стоимость логист назовёт за 15 минут после заявки.'],
        ['q' => 'Нужно ли моё присутствие при погрузке и выгрузке?',
         'a' => 'Нет. Передать и принять автомобиль может любой человек по простой доверенности — родственник, покупатель, менеджер автосалона. Мы часто забираем машины прямо с аукционов и у дилеров.'],
        ['q' => 'Что будет, если машину повредят в пути?',
         'a' => 'Каждый автомобиль застрахован на полную стоимость, а его состояние зафиксировано в акте с фотографиями при погрузке. Любое расхождение при выдаче — страховой случай, ущерб компенсируется страховой компанией.'],
        ['q' => 'Можно ли перевезти неисправный автомобиль?',
         'a' => 'Да, если автомобиль катится и управляется — погрузим лебёдкой без доплат по большинству направлений. Для полностью обездвиженных машин подберём эвакуатор или автовоз с гидробортом.'],
        ['q' => 'Какие документы нужны для перевозки?',
         'a' => 'Достаточно СТС или ПТС (можно копию) и вашего паспорта. Автомобиль перевозится как груз, поэтому ОСАГО и присутствие владельца не требуются.'],
        ['q' => 'Можно ли оставить вещи в машине?',
         'a' => 'Да, в багажнике и салоне можно перевезти до 100 кг личных вещей бесплатно. Ценности и документы рекомендуем не оставлять — они не покрываются страховкой груза.'],
      ]])
    </div>
  </section>

  <!-- ============ CTA-полоса ============ -->
  <section class="cta-band">
    <div class="container cta-band__in">
      <div>
        <h2 class="h2">Узнайте точную стоимость за 15 минут</h2>
        <p>Оставьте телефон — логист рассчитает маршрут и назовёт ближайшую дату загрузки.</p>
      </div>
      <form class="cta-band__form" data-lead-form action="{{ route('leads.store') }}" method="post">
        @csrf
        <input id="cta-phone" name="phone" type="tel" inputmode="tel" placeholder="+7 (___) ___-__-__" required aria-label="Телефон">
        <button type="submit" class="btn">Жду звонка</button>
      </form>
    </div>
  </section>

  <!-- ============ SEO-текст ============ -->
  <section class="section">
    <div class="container seo-text">
      <h2 class="h2">Перевозка автомобилей автовозом по России</h2>
      <p>Компания «ПеревозАвто» перевозит легковые автомобили, внедорожники, мотоциклы и коммерческий транспорт между городами России с 2014 года. Собственный парк открытых и закрытых автовозов и сеть проверенных партнёров позволяют отправлять машины по 120+ направлениям — от Калининграда до Владивостока — без долгого ожидания загрузки.</p>
      <h3 class="h3">Когда выгодно заказать автовоз</h3>
      <ul>
        <li>покупка автомобиля в другом городе — у дилера, с аукциона или с рук;</li>
        <li>переезд в другой регион, когда перегон своим ходом добавит тысячи километров пробега;</li>
        <li>продажа машины покупателю из другого города;</li>
        <li>сезонная доставка авто к месту отдыха или работы вахтой.</li>
      </ul>
      <h3 class="h3">Из чего складывается цена</h3>
      <p>Стоимость перевозки зависит от расстояния, габаритов и массы автомобиля, типа автовоза и загруженности направления. Обратная загрузка по популярным маршрутам позволяет предлагать цены ниже средних по рынку: логист подберёт рейс, который уже идёт в вашу сторону.</p>
    </div>
  </section>

@endsection
