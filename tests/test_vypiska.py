# -*- coding: utf-8 -*-
"""Тесты разбора выписки ЕГРЮЛ и вспомогательных функций."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ru_schools.contacts import extract_contacts, normalize_phone
from ru_schools.egrul import EgrulRow
from ru_schools.vypiska import parse_text

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "vypiska_sample.txt")


class TestVypiska(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.v = parse_text(fh.read())

    def test_requisites(self):
        self.assertEqual(self.v.inn, "7901013819")
        self.assertEqual(self.v.kpp, "790101001")
        self.assertEqual(self.v.ogrn, "1027900510307")

    def test_names(self):
        self.assertEqual(
            self.v.name_short, 'МБОУ "НАЧАЛЬНАЯ ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА № 14"'
        )
        self.assertIn("МУНИЦИПАЛЬНОЕ БЮДЖЕТНОЕ", self.v.name_full)

    def test_address(self):
        self.assertEqual(
            self.v.address,
            "679017, ЕВРЕЙСКАЯ АВТОНОМНАЯ ОБЛАСТЬ, Г. БИРОБИДЖАН, "
            "УЛ. 40 ЛЕТ ПОБЕДЫ, Д. 25Б",
        )
        self.assertEqual(self.v.postal_code, "679017")
        self.assertEqual(self.v.region, "ЕВРЕЙСКАЯ АВТОНОМНАЯ ОБЛАСТЬ")
        self.assertEqual(self.v.city, "Г. БИРОБИДЖАН")
        self.assertEqual(self.v.street, "УЛ. 40 ЛЕТ ПОБЕДЫ")
        # Номер дома не должен попасть в населённый пункт.
        self.assertEqual(self.v.settlement, "")

    def test_head(self):
        self.assertEqual(self.v.head_post, "Директор")
        self.assertEqual(self.v.head_name, "Зильберман Наталья Алексеевна")

    def test_okved_and_school_flag(self):
        self.assertEqual(self.v.okved_main, "85.12")
        self.assertEqual(self.v.okved_main_name, "Образование начальное общее")
        self.assertIn("56.29.2", self.v.okved_extra)
        self.assertTrue(self.v.is_general_school)

    def test_status(self):
        self.assertEqual(self.v.status, "действующая")


class TestEgrulRow(unittest.TestCase):
    def test_head_split(self):
        row = EgrulRow.from_json(
            {"i": "1", "g": "ДИРЕКТОР: Иванов Иван Иванович", "e": ""}
        )
        self.assertEqual(row.head_post, "Директор")
        self.assertEqual(row.head_name, "Иванов Иван Иванович")
        self.assertTrue(row.is_active)

    def test_terminated(self):
        row = EgrulRow.from_json({"i": "1", "e": "13.08.2008"})
        self.assertFalse(row.is_active)


class TestContacts(unittest.TestCase):
    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("8 (499) 461-75-73"), "+7 (499) 461-75-73")
        self.assertEqual(normalize_phone("+74994617573"), "+7 (499) 461-75-73")
        self.assertEqual(normalize_phone("123"), "")

    def test_extract(self):
        c = extract_contacts("Телефон: +7 (4212) 45-67-89, почта school15@edu.ru")
        self.assertEqual(c.email, "school15@edu.ru")
        self.assertIn("+7 (421) 245-67-89", c.phones)


if __name__ == "__main__":
    unittest.main()
