<footer class="footer">
  <div class="container">
    <div class="footer__routes" id="footer-routes">
      <h3 class="h3">{{ $footerRoutesTitle ?? 'Направления перевозки автомобилей' }}</h3>
      <div class="footer__routes-grid">
        @foreach (($footerRoutes ?? collect()) as $r)
          <a href="{{ $r->url }}">{{ $r->title }}</a>
        @endforeach
      </div>
    </div>

    <div class="footer__main">
      <div>
        <a class="logo" href="{{ route('home') }}">Перевоз<b>Авто</b><span class="logo__mark" aria-hidden="true"></span></a>
        <p>Перевозка автомобилей автовозами между городами России. Работаем с 2014 года.</p>
      </div>
      <div>
        <p class="footer__phone num"><a href="tel:{{ config('landing.phone_href') }}">{{ config('landing.phone') }}</a></p>
        <p><a href="mailto:{{ config('landing.email') }}">{{ config('landing.email') }}</a></p>
        <p>{{ config('landing.work_hours') }}</p>
      </div>
      <div>
        <p>{{ config('landing.address') }}</p>
        <p><a href="#">Политика обработки персональных данных</a></p>
        <p><a href="#">Договор-оферта</a></p>
      </div>
    </div>

    <div class="footer__bottom">
      <span>© 2014–{{ now()->year }} «ПеревозАвто». {{ config('landing.company') }}</span>
      <span>Цены на сайте не являются публичной офертой</span>
    </div>
  </div>
</footer>
