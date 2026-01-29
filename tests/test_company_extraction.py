"""Tests para la extracción de empresas usando JavaScript."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from src.bumeran import BumeranScraper
from src.computrabajo import ComputrabajoScraper


class BumeranJSExtractionTests(unittest.TestCase):
    """Tests para extracción JavaScript de Bumeran."""

    def test_bumeran_extracts_company_from_js_result(self) -> None:
        """Verifica que Bumeran extrae empresa correctamente desde JS."""
        js_result = [
            {"href": "https://bumeran.pe/empleos/test-123", "titulo": "Analista", "empresa": "TechCorp"},
        ]
        
        class FakeDriver:
            page_source = "<html></html>"
            current_url = "https://bumeran.pe"
            def get(self, url): self.current_url = url
            def execute_script(self, script): return js_result
        
        scraper = BumeranScraper(driver=FakeDriver())
        puestos = scraper.extraer_puestos()
        
        self.assertEqual(len(puestos), 1)
        self.assertEqual(puestos[0]["empresa"], "TechCorp")
        self.assertEqual(puestos[0]["titulo"], "Analista")

    def test_bumeran_deduplicates_urls(self) -> None:
        """Verifica que Bumeran no repite URLs."""
        js_result = [
            {"href": "https://bumeran.pe/empleos/test-123", "titulo": "Analista", "empresa": "A"},
            {"href": "https://bumeran.pe/empleos/test-123", "titulo": "Analista", "empresa": "A"},  # dup
            {"href": "https://bumeran.pe/empleos/test-456", "titulo": "Dev", "empresa": "B"},
        ]
        
        class FakeDriver:
            page_source = "<html></html>"
            current_url = "https://bumeran.pe"
            def get(self, url): self.current_url = url
            def execute_script(self, script): return js_result
        
        scraper = BumeranScraper(driver=FakeDriver())
        puestos = scraper.extraer_puestos()
        
        self.assertEqual(len(puestos), 2)

    def test_bumeran_handles_empty_result(self) -> None:
        """Verifica que Bumeran maneja resultado vacío."""
        class FakeDriver:
            page_source = "<html></html>"
            current_url = "https://bumeran.pe"
            def get(self, url): pass
            def execute_script(self, script): return []
        
        scraper = BumeranScraper(driver=FakeDriver())
        puestos = scraper.extraer_puestos()
        
        self.assertEqual(puestos, [])


class ComputrabajoJSExtractionTests(unittest.TestCase):
    """Tests para extracción JavaScript de Computrabajo."""

    def test_computrabajo_extracts_company_from_js_result(self) -> None:
        """Verifica que Computrabajo extrae empresa correctamente desde JS."""
        js_result = [
            {"href": "/ofertas-de-trabajo/oferta-de-trabajo-de-analista-ABC123", "titulo": "Analista Jr", "empresa": "MegaCorp"},
        ]
        
        class FakeDriver:
            page_source = "<html></html>"
            current_url = "https://pe.computrabajo.com/trabajo-de-analista?pubdate=1"
            def get(self, url): self.current_url = url
            def execute_script(self, script): return js_result
        
        scraper = ComputrabajoScraper(driver=FakeDriver())
        scraper.abrir_pagina_empleos(dias=1)
        scraper.buscar_vacante("analista")
        puestos = scraper.extraer_puestos()
        
        self.assertEqual(len(puestos), 1)
        self.assertEqual(puestos[0]["empresa"], "MegaCorp")

    def test_computrabajo_deduplicates_by_url(self) -> None:
        """Verifica que Computrabajo no repite URLs."""
        js_result = [
            {"href": "/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123", "titulo": "Job1", "empresa": "A"},
            {"href": "/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123", "titulo": "Job1", "empresa": "A"},  # dup
            {"href": "/ofertas-de-trabajo/oferta-de-trabajo-de-x-DEF456", "titulo": "Job2", "empresa": "B"},
        ]
        
        class FakeDriver:
            page_source = "<html></html>"
            current_url = "https://pe.computrabajo.com/trabajo-de-x?pubdate=1"
            def get(self, url): self.current_url = url
            def execute_script(self, script): return js_result
        
        scraper = ComputrabajoScraper(driver=FakeDriver())
        scraper.abrir_pagina_empleos(dias=1)
        scraper.buscar_vacante("x")
        puestos = scraper.extraer_puestos()
        
        self.assertEqual(len(puestos), 2)


if __name__ == "__main__":
    unittest.main()
