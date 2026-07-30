<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token() }}">
  <title>@yield('title', 'Перевозка автомобилей автовозом по России | ПеревозАвто')</title>
  <meta name="description" content="@yield('meta_description', 'Перевозка автомобилей автовозом между городами России. Страховка до 5 млн ₽, договор, ГЛОНАСС-контроль.')">
  <link rel="canonical" href="@yield('canonical', url()->current())">
  <meta property="og:title" content="@yield('title', 'Перевозка автомобилей автовозом по России | ПеревозАвто')">
  <meta property="og:description" content="@yield('meta_description', 'Доставим ваш автомобиль в любой город России.')">
  <meta property="og:type" content="website">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=Unbounded:wght@500;600;700&display=swap" rel="stylesheet">
  <link rel="preload" as="image" href="{{ asset('img/hero-tow.jpg') }}" media="(min-width: 761px)">
  <link rel="stylesheet" href="{{ asset('css/style.css') }}">
  @stack('jsonld')
</head>
<body>

  @include('partials.header')

  @yield('content')

  @include('partials.footer')

  <div class="sticky-cta">
    <a class="btn btn--call num" href="tel:{{ config('landing.phone_href') }}">📞 Позвонить</a>
    <a class="btn btn--accent" href="#calc">Рассчитать стоимость</a>
  </div>

  <script src="{{ asset('js/main.js') }}" defer></script>
</body>
</html>
