import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from src.bumeran import BumeranScraper
from src.computrabajo import ComputrabajoScraper
from src.indeed import IndeedScraper


class BlockDetectionTests(unittest.TestCase):
    def test_bumeran_detecta_captcha(self) -> None:
        driver = MagicMock()
        driver.page_source = "<html><body>Por favor complete el captcha</body></html>"
        scraper = BumeranScraper(driver=driver)
        self.assertTrue(scraper.detecta_bloqueo())

    def test_computrabajo_detecta_captcha(self) -> None:
        driver = MagicMock()
        driver.page_source = "<html><body>Are you human? access denied</body></html>"
        scraper = ComputrabajoScraper(driver=driver)
        self.assertTrue(scraper.detecta_bloqueo())

    def test_indeed_detecta_captcha_marker(self) -> None:
        driver = MagicMock()
        driver.page_source = "<html><title>captcha required</title></html>"
        driver.current_url = "https://pe.indeed.com/jobs"
        scraper = IndeedScraper(driver=driver)
        self.assertTrue(scraper.detecta_bloqueo_cloudflare())


if __name__ == "__main__":
    unittest.main()
