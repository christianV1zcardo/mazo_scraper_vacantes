import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from src.indeed import IndeedScraper


class IndeedScraperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = MagicMock()
        self.driver.current_url = ""

        def update_current(url: str) -> None:
            self.driver.current_url = url

        self.driver.get.side_effect = update_current
        self.scraper = IndeedScraper(driver=self.driver)

    def test_buscar_vacante_builds_expected_url(self) -> None:
        self.scraper.abrir_pagina_empleos(dias=1)
        self.scraper.buscar_vacante("Analista")
        called_url = self.driver.get.call_args.args[0]
        self.assertIn("q=Analista", called_url)
        self.assertIn("fromage=1", called_url)
        self.assertTrue(called_url.startswith("https://pe.indeed.com/jobs?"))

    def test_navegar_a_pagina_sets_start_parameter(self) -> None:
        self.scraper.abrir_pagina_empleos(dias=0)
        self.scraper.buscar_vacante("Data")
        self.driver.get.reset_mock()
        self.scraper.navegar_a_pagina(3)
        called_url = self.driver.get.call_args.args[0]
        self.assertIn("start=20", called_url)

    def test_navegar_a_pagina_returns_false_when_url_repeats(self) -> None:
        self.scraper.abrir_pagina_empleos(dias=0)
        self.scraper.buscar_vacante("Data")
        last_url = self.scraper._last_page_url
        self.driver.get.reset_mock()

        def repeat_current(_url: str) -> None:
            if last_url is not None:
                self.driver.current_url = last_url

        self.driver.get.side_effect = repeat_current
        result = self.scraper.navegar_a_pagina(2)

        self.assertFalse(result)
        self.driver.get.assert_called_once()

    def test_normalize_job_url_removes_duplicates(self) -> None:
        raw_url = "https://pe.indeed.com/viewjob?jk=abc123&from=serp&start=20"
        normalized = self.scraper._normalize_job_url(raw_url)
        self.assertEqual(normalized, "https://pe.indeed.com/viewjob?jk=abc123")

    def test_normalize_job_url_preserves_pagead_parameters_when_needed(self) -> None:
        raw_url = "https://pe.indeed.com/pagead/clk?jk=xyz789&foo=bar"
        normalized = self.scraper._normalize_job_url(raw_url)
        self.assertEqual(normalized, "https://pe.indeed.com/viewjob?jk=xyz789")

        sponsor_url = "https://pe.indeed.com/pagead/clk?from=serp&ad=123"
        preserved = self.scraper._normalize_job_url(sponsor_url)
        self.assertEqual(preserved, "https://pe.indeed.com/pagead/clk?from=serp&ad=123")

    def test_detecta_bloqueo_cloudflare_identifica_indicadores(self) -> None:
        self.driver.page_source = "<html><title>Just a moment...</title>__cf_chl_tk=abc</html>"
        self.driver.current_url = "https://pe.indeed.com/jobs?__cf_chl_jschl_tk__=token"
        self.assertTrue(self.scraper.detecta_bloqueo_cloudflare())


if __name__ == "__main__":
    unittest.main()