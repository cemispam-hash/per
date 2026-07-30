<header class="header">
  <div class="container header__in">
    <a class="logo" href="{{ route('home') }}">Перевоз<b>Авто</b><span class="logo__mark" aria-hidden="true"></span></a>

    <nav class="nav" id="nav" aria-label="Основное меню">
      <a href="{{ route('home') }}#routes">Направления</a>
      <a href="{{ route('home') }}#services">Цены</a>
      <a href="{{ route('home') }}#how">Как работаем</a>
      <a href="{{ route('home') }}#reviews">Отзывы</a>
      <a href="{{ route('home') }}#faq">Вопросы</a>
    </nav>

    <div class="header__phone">
      <a href="tel:{{ config('landing.phone_href') }}" class="num">{{ config('landing.phone') }}</a>
      <small>Бесплатно по России, 24/7</small>
    </div>

    <a class="btn btn--accent" href="#calc">Рассчитать стоимость</a>

    <button class="burger" id="burger" aria-label="Открыть меню" aria-expanded="false" aria-controls="nav">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>
