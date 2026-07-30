@extends('layouts.app')

@php
  use App\Models\TransportRoute;
  $priceFrom = TransportRoute::money($route->price_sedan);
  $days = $route->days_min . '–' . $route->days_max;
  $daysWord = $route->days_max >= 5 ? 'дней' : 'дня';
  $fromPhrase = $route->from_phrase;   // «из Москвы»
  $toPhrase = $route->to_phrase;       // «во Владивосток»
@endphp

@section('title', $route->meta_title ?: "Автовоз {$route->title}: перевозка автомобилей, цена от {$priceFrom} ₽ | ПеревозАвто")
@section('meta_description', $route->meta_description ?: "Перевозка автомобилей автовозом {$fromPhrase} {$toPhrase}: " . TransportRoute::money($route->distance_km) . " км за {$days} {$daysWord}, цена от {$priceFrom} ₽. Страховка до 5 млн ₽, договор, ГЛОНАСС-трекинг, оплата после доставки.")

@push('jsonld')
<script type="application/ld+json">
{!! json_encode([
    '@context' => 'https://schema.org',
    '@type' => 'Service',
    'name' => "Перевозка автомобилей автовозом {$route->title}",
    'provider' => ['@type' => 'MovingCompany', 'name' => 'ПеревозАвто', 'telephone' => config('landing.phone_href')],
    'areaServed' => [$route->city_from, $route->city_to],
    'offers' => ['@type' => 'Offer', 'price' => (string) $route->price_sedan, 'priceCurrency' => 'RUB',
                 'description' => 'Легковой автомобиль на открытом автовозе'],
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) !!}
</script>
<script type="application/ld+json">
{!! json_encode([
    '@context' => 'https://schema.org',
    '@type' => 'BreadcrumbList',
    'itemListElement' => [
        ['@type' => 'ListItem', 'position' => 1, 'name' => 'Главная', 'item' => route('home')],
        ['@type' => 'ListItem', 'position' => 2, 'name' => 'Направления', 'item' => route('home') . '#routes'],
        ['@type' => 'ListItem', 'position' => 3, 'name' => $route->title],
    ],
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) !!}
</script>
@endpush

@section('content')

  <!-- ============ Hero маршрута ============ -->
  <section class="hero">
    <div class="container">
      <div class="hero__in">
        <div>
          <nav class="breadcrumbs" aria-label="Хлебные крошки">
            <a href="{{ route('home') }}">Главная</a> / <a href="{{ route('home') }}#routes">Направления</a> / <span>{{ $route->title }}</span>
          </nav>
          <h1 class="h1">Автовоз <em>{{ $route->title }}</em>: перевозка автомобилей от {{ $priceFrom }} ₽</h1>
          <p class="hero__sub">Перевезём ваш автомобиль {{ $fromPhrase }} {{ $toPhrase }} — {{ TransportRoute::money($route->distance_km) }} км по федеральным трассам. Автовозы уходят 2–3 раза в неделю в обе стороны.</p>
          <ul class="hero__points">
            <li>Срок доставки {{ $days }} {{ $daysWord }}</li>
            <li>Страховка груза до 5 млн ₽</li>
            <li>ГЛОНАСС-трекинг всего рейса</li>
            <li>Оплата после доставки</li>
          </ul>
        </div>

        @include('partials.calc', [
          'calcTitle' => "Расчёт по маршруту {$route->title}",
          'from' => $route->city_from,
          'to' => $route->city_to,
        ])
      </div>
    </div>
  </section>

  <!-- ============ Ключевые параметры маршрута ============ -->
  <section class="section section--tight">
    <div class="container">
      <div class="route-facts">
        <div class="route-fact"><small>Расстояние</small><b class="num">{{ TransportRoute::money($route->distance_km) }} <em>км</em></b></div>
        <div class="route-fact"><small>Срок доставки</small><b class="num">{{ $days }} <em>{{ $daysWord }}</em></b></div>
        <div class="route-fact"><small>Легковое авто</small><b class="num">от {{ $priceFrom }} <em>₽</em></b></div>
        <div class="route-fact route-fact--hot"><small>Ближайшая загрузка</small><b data-next-load>уточняется</b></div>
      </div>
    </div>
  </section>

  @if ($route->waypoints)
    <!-- ============ Маршрут следования ============ -->
    <section class="section section--tight">
      <div class="container">
        <div class="section-head">
          <div class="eyebrow">Маршрут следования</div>
          <h2 class="h2">Как идёт автовоз {{ $fromPhrase }} {{ $toPhrase }}</h2>
        </div>

        <div class="waypoints" aria-label="Города по маршруту">
          @foreach ($route->waypoints as $city)
            @if (!$loop->first)<i></i>@endif<span>{{ $city }}</span>
          @endforeach
        </div>

        @if ($route->highways)
          <div class="prose" style="margin-top: 28px;">
            <p>Автовоз идёт по трассам {{ implode(', ', $route->highways) }}. По пути возможна догрузка и выдача автомобилей в крупных городах — доставка до промежуточного города стоит пропорционально дешевле.</p>
          </div>
        @endif
      </div>
    </section>
  @endif

  <!-- ============ Цены по типам авто ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Цены</div>
        <h2 class="h2">Стоимость перевозки {{ $route->title }}</h2>
        <p class="lead">Цены при полной загрузке автовоза. Действуют в обе стороны — обратная загрузка часто дешевле, уточните у логиста.</p>
      </div>

      <div class="routes-table-wrap">
        <table class="routes-table">
          <thead>
            <tr>
              <th scope="col">Тип автомобиля</th>
              <th scope="col">Открытый автовоз</th>
              <th scope="col">Закрытый автовоз</th>
              <th scope="col">Срок</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><b>Легковой седан / хэтчбек</b></td>
              <td class="price">от {{ TransportRoute::money($route->price('sedan')) }} ₽</td>
              <td class="price">от {{ TransportRoute::money($route->price('closed_sedan')) }} ₽</td>
              <td>{{ $days }} {{ $daysWord }}</td>
            </tr>
            <tr>
              <td><b>Кроссовер</b></td>
              <td class="price">от {{ TransportRoute::money($route->price('crossover')) }} ₽</td>
              <td class="price">по запросу</td>
              <td>{{ $days }} {{ $daysWord }}</td>
            </tr>
            <tr>
              <td><b>Внедорожник / минивэн</b></td>
              <td class="price">от {{ TransportRoute::money($route->price('suv')) }} ₽</td>
              <td class="price">по запросу</td>
              <td>{{ $days }} {{ $daysWord }}</td>
            </tr>
            <tr>
              <td><b>Пикап / микроавтобус</b></td>
              <td class="price">от {{ TransportRoute::money($route->price('pickup')) }} ₽</td>
              <td class="price">по запросу</td>
              <td>{{ $days }} {{ $daysWord }}</td>
            </tr>
            <tr>
              <td><b>Мотоцикл</b></td>
              <td class="price">от {{ TransportRoute::money($route->price('moto')) }} ₽</td>
              <td class="price">по запросу</td>
              <td>{{ $days }} {{ $daysWord }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- ============ Гарантии ============ -->
  <section class="section assure">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Гарантии</div>
        <h2 class="h2">{{ TransportRoute::money($route->distance_km) }} км под полным контролем</h2>
      </div>
      <div class="cards cards--4">
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>
          </div>
          <h3 class="h3">Страховка до 5 млн ₽</h3>
          <p>Полное покрытие стоимости автомобиля на весь маршрут.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 4h11l3 3v13H5z"/><path d="M9 12h6M9 16h6M9 8h3"/></svg>
          </div>
          <h3 class="h3">Договор и акты</h3>
          <p>Состояние машины фиксируется в акте с фото при погрузке и выдаче.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 1 8 8c0 5-8 12-8 12S4 15 4 10a8 8 0 0 1 8-8z"/></svg>
          </div>
          <h3 class="h3">ГЛОНАСС-трекинг</h3>
          <p>Вы видите автовоз на карте на всех этапах пути.</p>
        </article>
        <article class="card">
          <div class="card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12h9M4 7h13M4 17h6"/><path d="M15 15l3 3 5-5"/></svg>
          </div>
          <h3 class="h3">Оплата после доставки</h3>
          <p>Осматриваете авто при выдаче — и только потом платите.</p>
        </article>
      </div>
    </div>
  </section>

  <!-- ============ FAQ маршрута ============ -->
  <section class="section" id="faq">
    <div class="container">
      <div class="section-head">
        <div class="eyebrow">Вопросы и ответы</div>
        <h2 class="h2">Частые вопросы о маршруте {{ $route->title }}</h2>
      </div>

      @include('partials.faq', ['faq' => [
        ['q' => "Сколько идёт автовоз по маршруту {$route->title}?",
         'a' => "Стандартный срок доставки — {$days} {$daysWord} в зависимости от сезона и количества выдач по пути. Зимой сроки могут увеличиваться на 1–2 дня из-за погодных условий."],
        ['q' => "Можно ли отправить машину в обратную сторону?",
         'a' => 'Да, автовозы ходят в обе стороны. Обратная загрузка часто дешевле — уточните стоимость у логиста. Принимаем машины по доверенности, в том числе у продавцов и дилеров.'],
        ['q' => 'Как отслеживать автомобиль в пути?',
         'a' => 'После загрузки логист присылает ссылку на ГЛОНАСС-мониторинг — положение автовоза видно в реальном времени. Дополнительно водитель отправляет фотоотчёты с ключевых точек маршрута.'],
        ['q' => 'Что входит в цену перевозки?',
         'a' => 'Погрузка, крепление, страховка груза, топливо и платные участки дорог. Доплаты возможны только за нестандартные габариты и обездвиженный автомобиль — логист предупредит заранее.'],
      ]])
    </div>
  </section>

  <!-- ============ CTA-полоса ============ -->
  <section class="cta-band">
    <div class="container cta-band__in">
      <div>
        <h2 class="h2">Забронируйте место на ближайший рейс</h2>
        <p>Автовозы {{ $route->title }} уходят 2–3 раза в неделю. Расчёт и бронь — за 15 минут.</p>
        <div class="messengers">
          <a class="messenger messenger--wa" href="{{ config('landing.whatsapp') }}" rel="noopener">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm5.4 14.1c-.2.7-1.3 1.3-1.9 1.4-.5.1-1.1.1-1.8-.1-.4-.1-.9-.3-1.6-.6-2.9-1.2-4.7-4.1-4.9-4.3-.1-.2-1.1-1.5-1.1-2.9 0-1.4.7-2 1-2.3.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.4.2.5.7 1.8.8 1.9.1.1.1.3 0 .5l-.4.6c-.1.2-.3.3-.1.6.1.3.6 1 1.4 1.7.9.8 1.7 1.1 2 1.2.3.1.4.1.6-.1l.8-.9c.2-.2.3-.2.6-.1l1.9.9c.3.1.5.2.5.3.1.2.1.7-.1 1.1z"/></svg>
            WhatsApp
          </a>
          <a class="messenger messenger--tg" href="{{ config('landing.telegram') }}" rel="noopener">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21.9 4.6 18.9 19c-.2 1-.8 1.2-1.6.8l-4.6-3.4-2.2 2.1c-.2.2-.4.4-.9.4l.3-4.6L18.3 6.7c.4-.3-.1-.5-.6-.2L7.5 12.9l-4.4-1.4c-1-.3-1-1 .2-1.4L20.6 3.2c.8-.3 1.5.2 1.3 1.4z"/></svg>
            Telegram
          </a>
        </div>
      </div>
      <form class="cta-band__form" data-lead-form action="{{ route('leads.store') }}" method="post">
        @csrf
        <input type="hidden" name="city_from" value="{{ $route->city_from }}">
        <input type="hidden" name="city_to" value="{{ $route->city_to }}">
        <input name="phone" type="tel" inputmode="tel" placeholder="+7 (___) ___-__-__" required aria-label="Телефон">
        <button type="submit" class="btn">Жду звонка</button>
      </form>
    </div>
  </section>

  @if ($route->seo_text)
    <!-- ============ Уникальный SEO-текст маршрута ============ -->
    <section class="section">
      <div class="container seo-text">
        {!! $route->seo_text !!}
      </div>
    </section>
  @else
    <section class="section">
      <div class="container seo-text">
        <h2 class="h2">Перевозка автомобилей {{ $fromPhrase }} {{ $toPhrase }}</h2>
        <p>Доставка автомобиля автовозом по маршруту {{ $route->title }} — надёжная альтернатива перегону своим ходом. Машина не получает {{ TransportRoute::money($route->distance_km) }} км пробега, не изнашивает ресурс и не рискует на трассе, а приезжает закреплённой на платформе в том же состоянии, в каком была передана водителю.</p>
        <h3 class="h3">Сроки и особенности</h3>
        <p>Стандартный срок доставки — {{ $days }} {{ $daysWord }}. При срочной необходимости возможна индивидуальная перевозка эвакуатором или неполная загрузка автовоза за доплату. Передать и принять автомобиль может любой человек по простой доверенности.</p>
      </div>
    </section>
  @endif

@endsection
