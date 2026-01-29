import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from tests.selenium_stub import ensure_selenium_stub
from src import pipeline

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ensure_selenium_stub()


class PipelineTests(unittest.TestCase):
    def test_run_combined_merges_and_deduplicates(self) -> None:
        bumeran_instance = Mock()
        bumeran_instance.driver = None
        bumeran_instance.extraer_todos_los_puestos.return_value = [
            {"url": "https://jobs.com/a", "titulo": "Role A", "empresa": "A"},
            {"url": "https://jobs.com/b", "titulo": "Role B", "empresa": "B"},
        ]

        computrabajo_instance = Mock()
        computrabajo_instance.driver = None
        computrabajo_instance.extraer_todos_los_puestos.return_value = [
            {"url": "https://jobs.com/b", "titulo": "Role B", "empresa": "B"},
            {"url": "https://jobs.com/c", "titulo": "Role C", "empresa": "C"},
        ]

        indeed_instance = Mock()
        indeed_instance.driver = None
        indeed_instance.extraer_todos_los_puestos.return_value = [
            {"url": "https://jobs.com/c", "titulo": "Role C", "empresa": "C"},
            {"url": "https://jobs.com/d", "titulo": "Role D", "empresa": "D"},
        ]

        with patch("src.pipeline.BumeranScraper", return_value=bumeran_instance), patch(
            "src.pipeline.ComputrabajoScraper", return_value=computrabajo_instance
        ), patch("src.pipeline.IndeedScraper", return_value=indeed_instance), patch(
            "src.pipeline.guardar_resultados"
        ) as mock_save, patch("src.pipeline._cleanup_driver") as mock_cleanup:
            result = pipeline.run_combined("Analista", dias=1, initial_wait=0, page_wait=0)

        bumeran_instance.abrir_pagina_empleos.assert_called_once()
        bumeran_instance.buscar_vacante.assert_called_once_with("Analista")
        bumeran_instance.extraer_todos_los_puestos.assert_called()
        bumeran_instance.close.assert_called_once()
        mock_cleanup.assert_called_once_with(bumeran_instance, "bumeran")

        computrabajo_instance.abrir_pagina_empleos.assert_called_once_with(dias=1)
        computrabajo_instance.buscar_vacante.assert_called_once_with("Analista")
        computrabajo_instance.extraer_todos_los_puestos.assert_called()
        computrabajo_instance.close.assert_called_once()

        indeed_instance.abrir_pagina_empleos.assert_called_once_with(dias=1)
        indeed_instance.buscar_vacante.assert_called_once_with("Analista")
        indeed_instance.extraer_todos_los_puestos.assert_called()
        indeed_instance.close.assert_called_once()

        mock_save.assert_called_once()
        saved_records = mock_save.call_args.args[0]
        # Validar que los registros correctos están presentes, sin importar la fuente de la URL duplicada
        urls_fuentes = {r["url"]: r["fuente"] for r in saved_records}
        # Siempre deben estar estas URLs
        self.assertIn("https://jobs.com/a", urls_fuentes)
        self.assertIn("https://jobs.com/b", urls_fuentes)
        self.assertIn("https://jobs.com/c", urls_fuentes)
        self.assertIn("https://jobs.com/d", urls_fuentes)
        # La fuente de 'a' y 'b' debe ser Bumeran
        self.assertEqual(urls_fuentes["https://jobs.com/a"], "Bumeran")
        self.assertEqual(urls_fuentes["https://jobs.com/b"], "Bumeran")
        # La fuente de 'd' debe ser Indeed
        self.assertEqual(urls_fuentes["https://jobs.com/d"], "Indeed")
        # La fuente de 'c' puede ser Computrabajo o Indeed (depende del orden de ejecución paralela)
        self.assertIn(urls_fuentes["https://jobs.com/c"], ["Computrabajo", "Indeed"])
        # Verifica que los datos de cada registro sean correctos
        def get_by_url(records, url):
            return next(r for r in records if r["url"] == url)
        self.assertEqual(get_by_url(saved_records, "https://jobs.com/a")['titulo'], "Role A")
        self.assertEqual(get_by_url(saved_records, "https://jobs.com/b")['titulo'], "Role B")
        self.assertEqual(get_by_url(saved_records, "https://jobs.com/c")['titulo'], "Role C")
        self.assertEqual(get_by_url(saved_records, "https://jobs.com/d")['titulo'], "Role D")
        # El resultado devuelto debe ser igual al guardado
        self.assertEqual(sorted(result, key=lambda x: x["url"]), sorted(saved_records, key=lambda x: x["url"]))

    def test_run_combined_filters_sources(self) -> None:
        indeed_instance = Mock()
        indeed_instance.driver = None
        indeed_instance.extraer_todos_los_puestos.return_value = [
            {"url": "https://jobs.com/only", "titulo": "Only", "empresa": "OnlyCorp"}
        ]

        with patch("src.pipeline.BumeranScraper") as bumeran_cls, patch(
            "src.pipeline.ComputrabajoScraper"
        ) as computrabajo_cls, patch(
            "src.pipeline.IndeedScraper", return_value=indeed_instance
        ), patch("src.pipeline.guardar_resultados") as mock_save, patch(
            "src.pipeline._cleanup_driver"
        ) as mock_cleanup:
            result = pipeline.run_combined(
                "Analista", dias=0, initial_wait=0, page_wait=0, sources=["indeed"]
            )

        bumeran_cls.assert_not_called()
        computrabajo_cls.assert_not_called()
        indeed_instance.abrir_pagina_empleos.assert_called_once_with(dias=0)
        indeed_instance.buscar_vacante.assert_called_once_with("Analista")
        indeed_instance.extraer_todos_los_puestos.assert_called()
        indeed_instance.close.assert_called_once()
        mock_cleanup.assert_not_called()
        mock_save.assert_called_once()
        saved_records = mock_save.call_args.args[0]
        expected = [
            {
                "fuente": "Indeed",
                "url": "https://jobs.com/only",
                "titulo": "Only",
                "empresa": "OnlyCorp",
            }
        ]
        self.assertEqual(sorted(saved_records, key=lambda x: x["url"]), sorted(expected, key=lambda x: x["url"]))
        self.assertEqual(sorted(result, key=lambda x: x["url"]), sorted(expected, key=lambda x: x["url"]))

    def test_collect_jobs_logs_duration_and_totals(self) -> None:
        fake_scraper = Mock()
        fake_scraper.close = Mock()

        def fake_factory(headless=None):
            return fake_scraper

        def fake_collector(scraper, busqueda, dias, initial_wait, page_wait):
            return [
                {
                    "fuente": "Fake",
                    "url": "https://jobs.com/fake",
                    "titulo": "Role",
                    "empresa": "FakeCorp",
                }
            ]

        with patch.dict(
            "src.pipeline.SCRAPER_REGISTRY",
            {"fake": (fake_factory, fake_collector, False, False)},
            clear=True,
        ), patch("src.pipeline.logger") as mock_logger, patch(
            "src.pipeline.time.perf_counter", side_effect=[100.0, 101.5]
        ):
            combined, executed = pipeline.collect_jobs(
                busqueda="Analista",
                dias=0,
                initial_wait=0,
                page_wait=0,
                sources=["fake"],
            )

        self.assertEqual(executed, ["fake"])
        self.assertEqual(
            combined,
            [
                {
                    "fuente": "Fake",
                    "url": "https://jobs.com/fake",
                    "titulo": "Role",
                    "empresa": "FakeCorp",
                }
            ],
        )
        fake_scraper.close.assert_called_once()
        mock_logger.info.assert_any_call(
            "Iniciando scraper '%s' (dias=%s, initial_wait=%.2fs, page_wait=%.2fs, headless=%s)",
            "fake",
            0,
            0,
            0,
            None,
        )
        mock_logger.info.assert_any_call(
            "Scraper '%s' finalizado en %.2fs con %d ofertas", "fake", 1.5, 1
        )
        mock_logger.info.assert_any_call(
            "Total ofertas combinadas tras deduplicación: %d", 1
        )

    def test_collect_jobs_logs_exception_and_skips_results(self) -> None:
        failing_scraper = Mock()
        failing_scraper.close = Mock()

        def failing_factory(headless=None):
            return failing_scraper

        def failing_collector(scraper, busqueda, dias, initial_wait, page_wait):
            raise RuntimeError("boom")

        with patch.dict(
            "src.pipeline.SCRAPER_REGISTRY",
            {"failing": (failing_factory, failing_collector, False, False)},
            clear=True,
        ), patch("src.pipeline.logger") as mock_logger, patch(
            "src.pipeline.time.perf_counter", side_effect=[5.0, 7.0]
        ):
            combined, executed = pipeline.collect_jobs(
                busqueda="Analista",
                dias=0,
                initial_wait=0,
                page_wait=0,
                sources=["failing"],
            )


    def test_normalize_url_preserves_fragment_ids(self) -> None:
        url_with_fragment = "https://pe.computrabajo.com/trabajo-de-data#ABC123"
        normalized = pipeline._normalize_url(url_with_fragment)
        self.assertEqual(normalized, url_with_fragment.rstrip("/"))

    def test_collect_jobs_deduplicates_normalized_urls(self) -> None:
        scraper = Mock()
        scraper.close = Mock()

        def factory(headless=None):
            return scraper

        def collector(_scraper, *_args, **_kwargs):
            return [
                {"fuente": "X", "url": "https://jobs.com/viewjob?jk=123&from=serp", "titulo": "Uno", "empresa": "C"},
                {"fuente": "X", "url": "https://jobs.com/viewjob?jk=123&start=10", "titulo": "Uno dup", "empresa": "C"},
            ]

        with patch.dict(
            "src.pipeline.SCRAPER_REGISTRY",
            {"x": (factory, collector, False, False)},
            clear=True,
        ):
            combined, executed = pipeline.collect_jobs(
                busqueda="Analista",
                dias=0,
                initial_wait=0,
                page_wait=0,
                sources=["x"],
            )

        self.assertEqual(executed, ["x"])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["url"], "https://jobs.com/viewjob?jk=123")

    def test_collect_jobs_deduplicates_across_all_sources_including_laborum(self) -> None:
        """Verifica que la deduplicación funciona entre TODAS las fuentes incluyendo Laborum."""
        bumeran = Mock()
        bumeran.close = Mock()
        computrabajo = Mock()
        computrabajo.close = Mock()
        laborum = Mock()
        laborum.close = Mock()
        indeed = Mock()
        indeed.close = Mock()

        def bumeran_factory(headless=None):
            return bumeran

        def computrabajo_factory(headless=None):
            return computrabajo

        def laborum_factory(headless=None):
            return laborum

        def indeed_factory(headless=None):
            return indeed

        # Simular que cada fuente devuelve una URL común y una única
        def bumeran_collector(_s, *_a, **_k):
            return [
                {"fuente": "Bumeran", "url": "https://jobs.com/shared1", "titulo": "Job1", "empresa": "C1"},
                {"fuente": "Bumeran", "url": "https://jobs.com/bumeran-only", "titulo": "BumeranJob", "empresa": "C1"},
            ]

        def computrabajo_collector(_s, *_a, **_k):
            return [
                {"fuente": "Computrabajo", "url": "https://jobs.com/shared1", "titulo": "Job1", "empresa": "C1"},  # dup
                {"fuente": "Computrabajo", "url": "https://jobs.com/shared2", "titulo": "Job2", "empresa": "C2"},
            ]

        def laborum_collector(_s, *_a, **_k):
            return [
                {"fuente": "Laborum", "url": "https://jobs.com/shared2", "titulo": "Job2", "empresa": "C2"},  # dup
                {"fuente": "Laborum", "url": "https://jobs.com/laborum-only", "titulo": "LaborumJob", "empresa": "C3"},
            ]

        def indeed_collector(_s, *_a, **_k):
            return [
                {"fuente": "Indeed", "url": "https://jobs.com/laborum-only", "titulo": "LaborumJob", "empresa": "C3"},  # dup
                {"fuente": "Indeed", "url": "https://jobs.com/indeed-only", "titulo": "IndeedJob", "empresa": "C4"},
            ]

        with patch.dict(
            "src.pipeline.SCRAPER_REGISTRY",
            {
                "bumeran": (bumeran_factory, bumeran_collector, False, False),
                "computrabajo": (computrabajo_factory, computrabajo_collector, False, False),
                "laborum": (laborum_factory, laborum_collector, False, False),
                "indeed": (indeed_factory, indeed_collector, False, True),  # serial
            },
            clear=True,
        ):
            combined, executed = pipeline.collect_jobs(
                busqueda="Test",
                dias=0,
                initial_wait=0,
                page_wait=0,
                sources=["bumeran", "computrabajo", "laborum", "indeed"],
            )

        # Debe haber 5 URLs únicas en total (shared1, shared2, bumeran-only, laborum-only, indeed-only)
        urls = {r["url"] for r in combined}
        self.assertEqual(len(urls), 5)
        self.assertIn("https://jobs.com/shared1", urls)
        self.assertIn("https://jobs.com/shared2", urls)
        self.assertIn("https://jobs.com/bumeran-only", urls)
        self.assertIn("https://jobs.com/laborum-only", urls)
        self.assertIn("https://jobs.com/indeed-only", urls)

    def test_normalize_sources_handles_all_keyword(self) -> None:
        """Verifica que 'all' expande a todas las fuentes."""
        result = pipeline._normalize_sources(["all"])
        self.assertEqual(result, list(pipeline.DEFAULT_SOURCES))

    def test_normalize_sources_removes_duplicates(self) -> None:
        """Verifica que duplicados se eliminan preservando orden."""
        result = pipeline._normalize_sources(["bumeran", "indeed", "bumeran"])
        self.assertEqual(result, ["bumeran", "indeed"])


if __name__ == "__main__":
    unittest.main()
