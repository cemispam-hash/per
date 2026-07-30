{{-- Интерактивный калькулятор с живой ценой.
     Пропсы: $calc = ['cities' => ..., 'json' => ...], $calcTitle, $from, $to --}}
<div class="calc" id="calc">
  <div class="calc__hazard" aria-hidden="true"></div>
  <div class="calc__body">
    <p class="calc__title">{{ $calcTitle ?? 'Калькулятор перевозки' }}</p>
    <p class="calc__note">Предварительная цена — сразу, точная — за 15 минут по телефону</p>
    <form data-lead-form data-calc action="{{ route('leads.store') }}" method="post">
      @csrf
      <div class="field-row field-row--swap">
        <div class="field">
          <label for="city-from">Откуда</label>
          <select id="city-from" name="city_from" data-calc-from required>
            <option value="" disabled {{ isset($from) ? '' : 'selected' }}>Город отправки</option>
            @foreach ($calc['cities'] as $city)
              <option value="{{ $city }}" @selected(($from ?? null) === $city)>{{ $city }}</option>
            @endforeach
            <option value="other">Другой город…</option>
          </select>
        </div>
        <button type="button" class="calc__swap" data-calc-swap aria-label="Поменять города местами">⇄</button>
        <div class="field">
          <label for="city-to">Куда</label>
          <select id="city-to" name="city_to" data-calc-to required>
            <option value="" disabled {{ isset($to) ? '' : 'selected' }}>Город доставки</option>
            @foreach ($calc['cities'] as $city)
              <option value="{{ $city }}" @selected(($to ?? null) === $city)>{{ $city }}</option>
            @endforeach
            <option value="other">Другой город…</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label for="car-type">Тип автомобиля</label>
        <select id="car-type" name="car_type" data-calc-type>
          <option value="sedan">Легковой седан / хэтчбек</option>
          <option value="crossover">Кроссовер</option>
          <option value="suv">Внедорожник / минивэн</option>
          <option value="pickup">Пикап / микроавтобус</option>
          <option value="moto">Мотоцикл / квадроцикл</option>
        </select>
      </div>

      {{-- Живой результат --}}
      <div class="calc__result" data-calc-result hidden>
        <div class="calc__result-price">
          <small>Предварительная стоимость</small>
          <b class="num"><span data-calc-price>—</span></b>
        </div>
        <div class="calc__result-meta">
          <span data-calc-days></span>
          <span data-calc-km></span>
        </div>
        <a class="calc__result-link" data-calc-link href="#" hidden>Подробнее о маршруте →</a>
      </div>
      <p class="calc__custom" data-calc-custom hidden>По этому направлению цену рассчитает логист — оставьте телефон, перезвоним за 15 минут.</p>

      <div class="field">
        <label for="phone">Телефон для точного расчёта</label>
        <input id="phone" name="phone" type="tel" inputmode="tel" placeholder="+7 (___) ___-__-__" required>
      </div>
      <button type="submit" class="btn btn--accent btn--block">Получить точную цену</button>
      <p class="calc__legal">Нажимая кнопку, вы соглашаетесь с <a href="#">политикой обработки персональных данных</a></p>
    </form>
  </div>
  <div class="calc__success" role="status">
    <p class="h3">Заявка принята ✓</p>
    <p>Логист уже считает ваш маршрут. Перезвоним в течение 15 минут в рабочее время.</p>
  </div>
</div>

<script>window.CALC_ROUTES = {!! $calc['json'] !!};</script>
