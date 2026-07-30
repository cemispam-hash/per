/* ПеревозАвто — интерактив лендинга */
(function () {
  'use strict';

  /* ---------- Мобильное меню ---------- */
  var burger = document.getElementById('burger');
  var nav = document.getElementById('nav');
  if (burger && nav) {
    burger.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('is-open');
        burger.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- Маска телефона ---------- */
  function formatPhone(value) {
    var digits = value.replace(/\D/g, '');
    if (digits.startsWith('8')) digits = '7' + digits.slice(1);
    if (!digits.startsWith('7')) digits = '7' + digits;
    digits = digits.slice(0, 11);
    var out = '+7';
    if (digits.length > 1) out += ' (' + digits.slice(1, 4);
    if (digits.length >= 4) out += ') ' + digits.slice(4, 7);
    if (digits.length >= 7) out += '-' + digits.slice(7, 9);
    if (digits.length >= 9) out += '-' + digits.slice(9, 11);
    return out;
  }

  document.querySelectorAll('input[type="tel"]').forEach(function (input) {
    input.addEventListener('input', function () {
      if (input.value.trim() === '' || input.value === '+') return;
      input.value = formatPhone(input.value);
    });
  });

  /* ---------- Отправка лид-форм ----------
     Сейчас — имитация. На Laravel заменить на
     fetch('/api/leads', { method: 'POST', body: new FormData(form) }) */
  document.querySelectorAll('[data-lead-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();

      var phone = form.querySelector('input[type="tel"]');
      if (phone && phone.value.replace(/\D/g, '').length < 11) {
        phone.focus();
        phone.setCustomValidity('Введите номер телефона полностью');
        phone.reportValidity();
        phone.addEventListener('input', function () { phone.setCustomValidity(''); }, { once: true });
        return;
      }

      var calc = form.closest('.calc');
      if (calc) {
        calc.classList.add('is-sent');
      } else {
        var btn = form.querySelector('button[type="submit"]');
        btn.textContent = 'Заявка принята ✓';
        btn.disabled = true;
        form.querySelectorAll('input').forEach(function (i) { i.disabled = true; });
      }
    });
  });

  /* ---------- Дата ближайшей загрузки (сегодня + 2 дня) ---------- */
  var nextLoad = new Date();
  nextLoad.setDate(nextLoad.getDate() + 2);
  var months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var label = nextLoad.getDate() + ' ' + months[nextLoad.getMonth()];
  document.querySelectorAll('[data-next-load]').forEach(function (el) {
    el.textContent = label;
  });
})();
