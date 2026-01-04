import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from selenium.webdriver.common.by import By

from src.bumeran import BumeranScraper
from src.computrabajo import ComputrabajoScraper
from src.core.base import BlockDetected
from src import pipeline


def load_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text(encoding="utf-8")


class FakeElement:
    def __init__(self, text: str = "", href: str | None = None, selector_map=None, tag_map=None, attrs=None, xpath_map=None):
        self.text = text
        self._href = href
        self.selector_map = selector_map or {}
        self.tag_map = tag_map or {}
        self.attrs = attrs or {}
        self.xpath_map = xpath_map or {}

    def get_attribute(self, name: str):
        if name == "href":
            return self._href
        return self.attrs.get(name)

    def find_elements(self, by=None, value=None):
        if by == By.TAG_NAME:
            return self.tag_map.get(value, [])
        if by == By.CSS_SELECTOR:
            return self.selector_map.get(value, [])
        return []

    def find_element(self, by=None, value=None):
        if by == By.XPATH:
            if value in self.xpath_map:
                return self.xpath_map[value]
            raise Exception("not found")
        elems = self.find_elements(by, value)
        if not elems:
            raise Exception("not found")
        return elems[0]


class FakeContainer(FakeElement):
    def __init__(self, anchors):
        super().__init__()
        self.anchors = anchors

    def find_elements(self, by=None, value=None):
        if by == By.TAG_NAME and value == "a":
            return self.anchors
        if by == By.CSS_SELECTOR and value in {"article a.js-o-link.fc_base", "article a.js-o-link, article a.fc_base"}:
            return self.anchors
        return super().find_elements(by, value)

    def find_element(self, by=None, value=None):
        elems = self.find_elements(by, value)
        if not elems:
            raise Exception("not found")
        return elems[0]


class DummyWait:
    def __init__(self, driver, container):
        self.driver = driver
        self.container = container

    def until(self, condition):
        # If a callable, evaluate; otherwise just return pre-set container
        if callable(condition):
            return condition(self.driver)
        return self.container


class FakeDriver:
    def __init__(self, anchors):
        self.anchors = anchors
        self.current_url = ""

    def find_elements(self, *_args, **_kwargs):
        return self.anchors

    def get(self, url):
        self.current_url = url


class ScraperParsingTests(unittest.TestCase):
    def test_bumeran_extrae_puestos_con_fallback(self):
        html = load_fixture("bumeran_sample.html")
        # Parse fixture into simple elements
        anchors = [
            FakeElement(
                href="https://www.bumeran.com.pe/empleos/dev-123",
                tag_map={"h2": [FakeElement(text="Desarrollador Backend")]},
                selector_map={"h3.sc-igZVbQ": [FakeElement(text="Empresa Uno")]},
            ),
            FakeElement(
                href="https://www.bumeran.com.pe/empleos/dev-123",
                tag_map={"h2": [FakeElement(text="Desarrollador Backend")]},
                selector_map={"h3.sc-igZVbQ": [FakeElement(text="Empresa Uno")]},
            ),
            FakeElement(
                href="https://www.bumeran.com.pe/empleos/otro-456",
                tag_map={"h2": [FakeElement(text="Data Engineer")]},
                selector_map={"h3.sc-ebDnpS": [FakeElement(text="Empresa Dos")]},
            ),
            FakeElement(href="https://www.bumeran.com.pe/empleos-busqueda-irrelevante"),
        ]
        container = FakeContainer(anchors)
        driver = FakeDriver(anchors)

        scraper = BumeranScraper(driver=driver)
        with patch("src.bumeran.WebDriverWait", lambda d, t: DummyWait(d, container)):
            puestos = scraper.extraer_puestos(timeout=5)

        self.assertEqual(len(puestos), 2)
        urls = {p["url"] for p in puestos}
        self.assertIn("https://www.bumeran.com.pe/empleos/dev-123", urls)
        self.assertIn("https://www.bumeran.com.pe/empleos/otro-456", urls)

    def test_computrabajo_extrae_y_normaliza(self):
        anchors = [
            FakeElement(
                href="/trabajo-de-data-scientist#XYZ987",
                text="Data Scientist\nLima",
                xpath_map={
                    "ancestor::article[1]": FakeElement(
                        selector_map={"span.fs16.fc_base.mt5.fc_base.fc_base": [FakeElement(text="Tech Corp")]}
                    )
                },
            ),
            FakeElement(
                href="/trabajo-de-data-engineer#XYZ988",
                text="Data Engineer\nRemoto",
                xpath_map={
                    "ancestor::article[1]": FakeElement(
                        selector_map={"span.fs16.fc_base.mt5.fc_base.fc_base": [FakeElement(text="DataWorks")]}
                    )
                },
            ),
            FakeElement(href="/otras-cosas", text="Ignorar"),
            FakeElement(href="/trabajo-de-data-scientist#XYZ987"),  # duplicate URL to be skipped
        ]
        container = FakeContainer(anchors)
        driver = FakeDriver(anchors)

        scraper = ComputrabajoScraper(driver=driver)
        scraper.abrir_pagina_empleos(dias=1)
        scraper.buscar_vacante("Data Scientist")
        with patch("src.computrabajo.WebDriverWait", lambda d, t: DummyWait(d, container)):
            puestos = scraper.extraer_puestos(timeout=5)

        # Expect 2 valid, duplicates/irrelevant filtered out
        urls = {p["url"] for p in puestos}
        self.assertEqual(len(urls), 2)
        self.assertIn("https://pe.computrabajo.com/trabajo-de-data-scientist?pubdate=1#XYZ987", urls)
        self.assertIn("https://pe.computrabajo.com/trabajo-de-data-engineer?pubdate=1#XYZ988", urls)

    def test_with_retries_aborts_on_block(self):
        with patch("src.pipeline.time.sleep") as mock_sleep, patch("src.pipeline.logger") as mock_logger:
            result = pipeline._with_retries(
                label="test.block",
                operation=lambda: (_ for _ in ()).throw(BlockDetected("blocked")),
                retries=3,
                fallback_operation=lambda: [
                    {"fuente": "X", "url": "https://fallback"}
                ],
            )
        self.assertEqual(result, [{"fuente": "X", "url": "https://fallback"}])
        mock_sleep.assert_not_called()
        self.assertTrue(mock_logger.warning.call_args_list)
        self.assertTrue(mock_logger.info.call_args_list)
        warn_args, _ = mock_logger.warning.call_args_list[0]
        self.assertEqual(warn_args[1], "test.block")
        self.assertIsInstance(warn_args[2], BlockDetected)


if __name__ == "__main__":
    unittest.main()
