# -*- coding: utf-8 -*-
"""Сверка адресов ЕГРЮЛ с OpenStreetMap."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ru_schools import osm_bulk


def make_index(elements):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"elements": elements}, fh, ensure_ascii=False)
    try:
        return osm_bulk.index(path)
    finally:
        os.unlink(path)


class Row(dict):
    """Строка из details: sqlite3.Row читается как словарь."""


class TestNormalisation(unittest.TestCase):
    def test_street_kinds_dropped(self):
        # «УЛ. СУВОРОВА» из ЕГРЮЛ и «улица Суворова» из OSM — одна улица.
        self.assertEqual(
            osm_bulk._norm_street("УЛ. СУВОРОВА"),
            osm_bulk._norm_street("улица Суворова"),
        )
        self.assertEqual(
            osm_bulk._norm_street("УЛ. ИМЕНИ В. И. ЛЕНИНА"),
            osm_bulk._norm_street("улица Ленина"),
        )

    def test_place_kinds_dropped(self):
        self.assertEqual(
            osm_bulk._norm_place("Г. МАГНИТОГОРСК"),
            osm_bulk._norm_place("Магнитогорск"),
        )
        self.assertEqual(
            osm_bulk._norm_place("С. ВЕРХНЕНАЗАРОВСКОЕ"),
            osm_bulk._norm_place("Верхненазаровское"),
        )

    def test_different_streets_stay_different(self):
        self.assertNotEqual(
            osm_bulk._norm_street("УЛ. СУВОРОВА"),
            osm_bulk._norm_street("улица Кутузова"),
        )

    def test_house_number(self):
        self.assertEqual(osm_bulk._norm_house("Д. 25"), "25")
        self.assertEqual(osm_bulk._norm_house("60А"), "60а")
        self.assertEqual(osm_bulk._norm_house("136/4"), "136")
        self.assertEqual(osm_bulk._norm_house(""), "")


class TestMatch(unittest.TestCase):
    ELEMENTS = [
        {
            "type": "node",
            "tags": {
                "amenity": "school",
                "name": "Школа 22",
                "addr:city": "Магнитогорск",
                "addr:street": "улица Суворова",
                "addr:housenumber": "25",
                "phone": "+7 3519 220659",
                "email": "sch22@mail.ru",
            },
        },
        {
            # Без дома — сверять не с чем, в указатель попасть не должно.
            "type": "node",
            "tags": {"amenity": "school", "addr:city": "Москва", "addr:street": "улица Мира"},
        },
    ]

    def setUp(self):
        self.osm = make_index(self.ELEMENTS)

    def test_only_full_addresses_indexed(self):
        self.assertEqual(len(self.osm), 1)

    def test_match_by_city(self):
        row = Row(
            address="455017, ЧЕЛЯБИНСКАЯ ОБЛАСТЬ, Г. МАГНИТОГОРСК, УЛ. СУВОРОВА, Д. 25",
            city="Г. МАГНИТОГОРСК", settlement="", street="УЛ. СУВОРОВА",
        )
        tags = osm_bulk.match(row, self.osm)
        self.assertIsNotNone(tags)
        self.assertEqual(tags["name"], "Школа 22")

    def test_other_house_does_not_match(self):
        row = Row(
            address="455017, ЧЕЛЯБИНСКАЯ ОБЛАСТЬ, Г. МАГНИТОГОРСК, УЛ. СУВОРОВА, Д. 76А",
            city="Г. МАГНИТОГОРСК", settlement="", street="УЛ. СУВОРОВА",
        )
        self.assertIsNone(osm_bulk.match(row, self.osm))

    def test_other_city_does_not_match(self):
        row = Row(
            address="123456, МОСКВА, УЛ. СУВОРОВА, Д. 25",
            city="Г. МОСКВА", settlement="", street="УЛ. СУВОРОВА",
        )
        self.assertIsNone(osm_bulk.match(row, self.osm))

    def test_match_by_settlement(self):
        # У сёл город в выписке пуст, населённый пункт лежит отдельно.
        osm = make_index([{
            "type": "node",
            "tags": {
                "amenity": "school", "addr:place": "Верхненазаровское",
                "addr:street": "Почтовая улица", "addr:housenumber": "53",
                "phone": "+7 900 000-00-00",
            },
        }])
        row = Row(
            address="385334, РЕСПУБЛИКА АДЫГЕЯ, С. ВЕРХНЕНАЗАРОВСКОЕ, УЛ. ПОЧТОВАЯ, Д. 53",
            city="", settlement="С. ВЕРХНЕНАЗАРОВСКОЕ", street="УЛ. ПОЧТОВАЯ",
        )
        self.assertIsNotNone(osm_bulk.match(row, osm))


class TestContactOf(unittest.TestCase):
    def test_phone_and_email(self):
        c = osm_bulk.contact_of({
            "phone": "+7 3519 220659;+7 3519 220660",
            "email": "sch22@mail.ru",
            "website": "https://sch22.ru",
        })
        self.assertEqual(c.email, "sch22@mail.ru")
        self.assertEqual(len(c.phones), 2)
        self.assertEqual(c.website, "https://sch22.ru")
        self.assertEqual(c.source, "OpenStreetMap")

    def test_contact_prefixed_tags(self):
        c = osm_bulk.contact_of({"contact:phone": "8 (999) 123-45-67"})
        self.assertEqual(c.phones, ["+7 (999) 123-45-67"])

    def test_site_alone_is_not_a_contact(self):
        # Один сайт без телефона и почты закрывать школу не должен.
        self.assertIsNone(osm_bulk.contact_of({"website": "https://sch22.ru"}))


if __name__ == "__main__":
    unittest.main()
