import sys
from pathlib import Path
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from src.laborum import LaborumScraper, _parse_dias_desde_texto, _parse_dias_desde_fecha_en


class ParseDiasDesdeTextoTests(unittest.TestCase):
    """Tests para la función de parseo de fechas relativas."""

    def test_hoy_returns_zero(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Hoy"), 0)
        self.assertEqual(_parse_dias_desde_texto("hoy"), 0)

    def test_hace_horas_returns_zero(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Hace 2 horas"), 0)
        self.assertEqual(_parse_dias_desde_texto("Hace 1 hora"), 0)
        self.assertEqual(_parse_dias_desde_texto("hace 23 horas"), 0)

    def test_hace_minutos_returns_zero(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Hace 30 minutos"), 0)
        self.assertEqual(_parse_dias_desde_texto("Hace 1 minuto"), 0)

    def test_hace_dias_returns_correct_number(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Hace 1 día"), 1)
        self.assertEqual(_parse_dias_desde_texto("Hace 2 días"), 2)
        self.assertEqual(_parse_dias_desde_texto("Hace 7 días"), 7)
        self.assertEqual(_parse_dias_desde_texto("hace 3 dias"), 3)

    def test_ayer_returns_one(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Ayer"), 1)

    def test_esta_semana_returns_four(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Esta semana"), 4)

    def test_semana_pasada_returns_ten(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Semana pasada"), 10)

    def test_hace_mes_returns_thirty(self) -> None:
        self.assertEqual(_parse_dias_desde_texto("Hace 1 mes"), 30)

    def test_empty_or_unknown_returns_none(self) -> None:
        self.assertIsNone(_parse_dias_desde_texto(""))
        self.assertIsNone(_parse_dias_desde_texto("Unknown text"))


class ParseDiasDesdeFechaEnTests(unittest.TestCase):
    """Tests para el parseo de fechas en formato inglés (13 Jan)."""

    def test_valid_date_returns_days(self) -> None:
        # Testeamos que el resultado sea un entero no negativo
        result = _parse_dias_desde_fecha_en("13 Jan")
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)
        
    def test_various_months(self) -> None:
        for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
            result = _parse_dias_desde_fecha_en(f"1 {month}")
            self.assertIsInstance(result, int)
    
    def test_invalid_format_returns_none(self) -> None:
        self.assertIsNone(_parse_dias_desde_fecha_en(""))
        self.assertIsNone(_parse_dias_desde_fecha_en("Hace 2 días"))
        self.assertIsNone(_parse_dias_desde_fecha_en("Hoy"))


class LaborumScraperTests(unittest.TestCase):
    def test_site_root_is_correct(self) -> None:
        scraper = LaborumScraper(driver=object())
        self.assertEqual(scraper.SITE_ROOT, "https://www.laborum.pe")

    def test_max_scrolls_default(self) -> None:
        scraper = LaborumScraper(driver=object())
        self.assertEqual(scraper.MAX_SCROLLS, 100)

    def test_navegar_a_pagina_returns_false(self) -> None:
        """Laborum usa scroll infinito, navegar_a_pagina siempre retorna False."""
        scraper = LaborumScraper(driver=object())
        self.assertFalse(scraper.navegar_a_pagina(1))
        self.assertFalse(scraper.navegar_a_pagina(5))

    def test_detecta_bloqueo_returns_false_on_clean_page(self) -> None:
        class FakeDriver:
            page_source = "<html><body>Normal content</body></html>"
            current_url = "https://www.laborum.pe"

        scraper = LaborumScraper(driver=FakeDriver())
        self.assertFalse(scraper.detecta_bloqueo())

    def test_detecta_bloqueo_returns_true_on_captcha(self) -> None:
        class FakeDriver:
            page_source = "<html><body>Please solve the captcha</body></html>"
            current_url = "https://www.laborum.pe"

        scraper = LaborumScraper(driver=FakeDriver())
        self.assertTrue(scraper.detecta_bloqueo())


if __name__ == "__main__":
    unittest.main()
