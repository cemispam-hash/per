{{-- Форма-калькулятор. Пропсы: $calcTitle, $from, $to, $cities (datalist) --}}
<div class="calc" id="calc">
  <div class="calc__hazard" aria-hidden="true"></div>
  <div class="calc__body">
    <p class="calc__title">{{ $calcTitle ?? 'Расчёт стоимости перевозки' }}</p>
    <p class="calc__note">Точная цена и ближайшая дата загрузки — ответим за 15 минут</p>
    <form data-lead-form action="{{ route('leads.store') }}" method="post">
      @csrf
      <div class="field-row">
        <div class="field">
          <label for="city-from">Откуда</label>
          <input id="city-from" name="city_from" @isset($cities) list="cities" @endisset
                 value="{{ $from ?? '' }}" placeholder="Москва" required autocomplete="off">
        </div>
        <div class="field">
          <label for="city-to">Куда</label>
          <input id="city-to" name="city_to" @isset($cities) list="cities" @endisset
                 value="{{ $to ?? '' }}" placeholder="Владивосток" required autocomplete="off">
        </div>
      </div>
      <div class="field">
        <label for="car-type">Тип автомобиля</label>
        <select id="car-type" name="car_type">
          <option>Легковой седан / хэтчбек</option>
          <option>Кроссовер / внедорожник</option>
          <option>Минивэн / микроавтобус</option>
          <option>Пикап</option>
          <option>Мотоцикл / квадроцикл</option>
          <option>Другое</option>
        </select>
      </div>
      <div class="field">
        <label for="phone">Телефон</label>
        <input id="phone" name="phone" type="tel" inputmode="tel" placeholder="+7 (___) ___-__-__" required>
      </div>
      <button type="submit" class="btn btn--accent btn--block">Рассчитать стоимость</button>
      <p class="calc__legal">Нажимая кнопку, вы соглашаетесь с <a href="#">политикой обработки персональных данных</a></p>
    </form>
  </div>
  <div class="calc__success" role="status">
    <p class="h3">Заявка принята ✓</p>
    <p>Логист уже считает ваш маршрут. Перезвоним в течение 15 минут в рабочее время.</p>
  </div>
</div>

@isset($cities)
  <datalist id="cities">
    @foreach ($cities as $city)
      <option value="{{ $city }}"></option>
    @endforeach
  </datalist>
@endisset
