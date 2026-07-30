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

  /* ---------- Отправка лид-форм ---------- */
  var csrf = document.querySelector('meta[name="csrf-token"]');

  function showSuccess(form) {
    var calc = form.closest('.calc');
    if (calc) {
      calc.classList.add('is-sent');
    } else {
      var btn = form.querySelector('button[type="submit"]');
      btn.textContent = 'Заявка принята ✓';
      btn.disabled = true;
      form.querySelectorAll('input').forEach(function (i) { i.disabled = true; });
    }
  }

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

      var actionAttr = form.getAttribute('action') || '';
      if (actionAttr.indexOf('http') !== 0) {
        showSuccess(form); // статическое превью без бэкенда
        return;
      }

      var btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;

      fetch(form.action, {
        method: 'POST',
        headers: {
          'X-CSRF-TOKEN': csrf ? csrf.content : '',
          'Accept': 'application/json'
        },
        body: new FormData(form)
      }).then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        showSuccess(form);
      }).catch(function () {
        btn.disabled = false;
        if (phone) {
          phone.setCustomValidity('Не удалось отправить. Позвоните нам: 8 (800) 550-44-70');
          phone.reportValidity();
          phone.addEventListener('input', function () { phone.setCustomValidity(''); }, { once: true });
        }
      });
    });
  });

  /* ---------- Калькулятор с живой ценой ---------- */
  var COEF = { sedan: 1, crossover: 1.10, suv: 1.21, pickup: 1.32, moto: 0.47 };

  function fmt(n) { return n.toLocaleString('ru-RU'); }

  function findRoute(from, to) {
    var list = window.CALC_ROUTES || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].f === from && list[i].t === to) return { r: list[i], reverse: false };
    }
    for (var j = 0; j < list.length; j++) {
      if (list[j].f === to && list[j].t === from) return { r: list[j], reverse: true };
    }
    return null;
  }

  document.querySelectorAll('[data-calc]').forEach(function (form) {
    var from = form.querySelector('[data-calc-from]');
    var to = form.querySelector('[data-calc-to]');
    var type = form.querySelector('[data-calc-type]');
    var result = form.querySelector('[data-calc-result]');
    var custom = form.querySelector('[data-calc-custom]');
    var priceEl = form.querySelector('[data-calc-price]');
    var daysEl = form.querySelector('[data-calc-days]');
    var kmEl = form.querySelector('[data-calc-km]');
    var linkEl = form.querySelector('[data-calc-link]');
    var swap = form.querySelector('[data-calc-swap]');

    function update() {
      var f = from.value, t = to.value;
      if (!f || !t) { result.hidden = true; custom.hidden = true; return; }

      if (f === 'other' || t === 'other' || f === t) {
        result.hidden = true;
        custom.hidden = false;
        return;
      }

      var found = findRoute(f, t);
      if (!found) { result.hidden = true; custom.hidden = false; return; }

      var r = found.r;
      var price = Math.round(r.p * (COEF[type.value] || 1) / 1000) * 1000;
      priceEl.textContent = 'от ' + fmt(price) + ' ₽';
      daysEl.textContent = r.d1 + '–' + r.d2 + ' ' + (r.d2 >= 5 ? 'дней' : 'дня');
      kmEl.textContent = fmt(r.km) + ' км';
      if (linkEl) {
        if (!found.reverse && r.slug) {
          linkEl.href = '/avtovoz-' + r.slug;
          linkEl.hidden = window.location.pathname.indexOf(r.slug) !== -1;
        } else {
          linkEl.hidden = true;
        }
      }
      custom.hidden = true;
      result.hidden = false;
    }

    [from, to, type].forEach(function (el) { el.addEventListener('change', update); });
    if (swap) {
      swap.addEventListener('click', function () {
        if (!from.value || !to.value || from.value === 'other' || to.value === 'other') return;
        var tmp = from.value; from.value = to.value; to.value = tmp;
        update();
      });
    }
    update(); // на страницах маршрутов города предзаполнены
  });

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Появление секций при скролле ---------- */
  if (!reduceMotion && 'IntersectionObserver' in window) {
    var revealEls = document.querySelectorAll(
      '.section-head, .card, .step, .routes-table-wrap, .routes-more, ' +
      '.steps-aside, .route-facts > *, .waypoints, .cta-band__in, .seo-text'
    );
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

    revealEls.forEach(function (el, i) {
      el.classList.add('reveal');
      el.style.transitionDelay = (i % 4) * 60 + 'ms';
      io.observe(el);
    });
  }

  /* ---------- Счётчики в hero ---------- */
  function animateCount(el) {
    var target = parseInt(el.getAttribute('data-count'), 10);
    var suffix = el.getAttribute('data-suffix') || '';
    var start = null, dur = 1200;
    function tick(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(target * eased)) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  var counters = document.querySelectorAll('[data-count]');
  if (counters.length) {
    if (reduceMotion || !('IntersectionObserver' in window)) {
      // оставляем статичные значения из разметки
    } else {
      var cio = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateCount(entry.target);
            cio.unobserve(entry.target);
          }
        });
      }, { threshold: 0.4 });
      counters.forEach(function (el) { cio.observe(el); });
    }
  }

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
