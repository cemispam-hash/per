# -*- coding: utf-8 -*-
"""Разбор ответов поиска и извлечение контактов."""
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ru_schools.contacts import (
    SearchUnavailable,
    XmlRiverProvider,
    extract_contacts,
    normalize_phone,
)


def answer(body: str) -> Mock:
    resp = Mock()
    resp.status_code = 200
    resp.content = (
        '<?xml version="1.0" encoding="UTF-8"?><yandexsearch version="1.0">'
        f"<response>{body}</response></yandexsearch>"
    ).encode()
    return resp


def provider(*bodies) -> XmlRiverProvider:
    http = Mock()
    http.get.side_effect = [answer(b) for b in bodies]
    return XmlRiverProvider(http, "u", "k", None)


class TestTransientErrors(unittest.TestCase):
    """Отказ поиска — это про поиск, а не про школу.

    Записать его как «контактов нет» нельзя: школа выбывает из сбора,
    хотя её ни разу не искали. Формулировок у xmlriver несколько, и
    распознаваться должны все.
    """

    BUSY = "<error code=\"15\">Заняты все доступные вам каналы для сбора данных. Попробуйте позже.</error>"
    NO_CHANNELS = "<error code=\"15\">Нет свободных каналов</error>"
    RETRY = "<error code=\"500\">Выполните перезапрос. Ответ от поисковой системы не получен.</error>"

    def test_busy_channels_requeue(self):
        with self.assertRaises(SearchUnavailable):
            provider(self.BUSY).search_docs("школа", attempts=1)

    def test_no_channels_requeue(self):
        with self.assertRaises(SearchUnavailable):
            provider(self.NO_CHANNELS).search_docs("школа", attempts=1)

    def test_retry_requeue(self):
        with self.assertRaises(SearchUnavailable):
            provider(self.RETRY).search_docs("школа", attempts=1)

    def test_permanent_error_is_not_requeued(self):
        # Неверный ключ повтором не лечится: школа тут ни при чём,
        # но и возвращать её в очередь бессмысленно.
        urls, snippets = provider('<error code="2">Неверный ключ</error>').search_docs(
            "школа", attempts=1
        )
        self.assertEqual(urls, [])
        self.assertEqual(snippets, "")

    def test_retry_then_success(self):
        good = "<results><grouping><group><doc><url>https://school1.ru/</url></doc></group></grouping></results>"
        urls, _ = provider(self.RETRY, good).search_docs("школа", attempts=2)
        self.assertEqual(urls, ["https://school1.ru/"])


class TestExtract(unittest.TestCase):
    def test_phone_formats(self):
        self.assertEqual(normalize_phone("8 (999) 123-45-67"), "+7 (999) 123-45-67")
        self.assertEqual(normalize_phone("+7 999 1234567"), "+7 (999) 123-45-67")
        self.assertEqual(normalize_phone("9991234567"), "+7 (999) 123-45-67")
        self.assertEqual(normalize_phone("123"), "")

    def test_contacts_from_page(self):
        c = extract_contacts(
            "Приёмная: 8 (3519) 22-06-59, факс 8 (3519) 22-06-60. Почта: sch22@mail.ru"
        )
        self.assertEqual(c.email, "sch22@mail.ru")
        self.assertEqual(len(c.phones), 2)

    def test_junk_email_dropped(self):
        # Служебные адреса из вёрстки за контакт школы выдавать нельзя.
        c = extract_contacts("noreply@sentry.io и your@domain.ru")
        self.assertEqual(c.email, "")


if __name__ == "__main__":
    unittest.main()
