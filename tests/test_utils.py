import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.selenium_stub import ensure_selenium_stub

ensure_selenium_stub()

from datetime import datetime as real_datetime

from src.utils import guardar_resultados, copy_top_from_csv


class GuardarResultadosTests(unittest.TestCase):
    def test_guardar_resultados_creates_json_and_csv(self) -> None:
        records = [
            {"titulo": "Analista", "url": "https://example.com/a"},
            {"titulo": "Cientifico", "url": "https://example.com/b"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            guardar_resultados(records, "Analista", output_dir=tmpdir, source="combined")

            import glob
            all_files = sorted(glob.glob(os.path.join(tmpdir, "*")))
            filenames = [os.path.basename(f) for f in all_files]
            print(f"\nFiles created: {filenames}")
            
            # Solo se crea el CSV con formato corto DD_MM_query.csv (sin combined ni JSON)
            self.assertEqual(len(all_files), 1, f"Expected 1 file but got: {filenames}")
            
            # Verificar que el archivo tiene el formato corto correcto
            short_csvs = [f for f in filenames if f.endswith("_analista.csv")]
            self.assertEqual(len(short_csvs), 1, f"Expected 1 short format CSV but got: {short_csvs}")

            # Verify the short CSV has correct content
            short_csv_path = os.path.join(tmpdir, short_csvs[0])
            with open(short_csv_path, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], "Fuente,Empresa,Titulo,Url")

    def test_guardar_resultados_handles_empty_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            guardar_resultados([], "Data", output_dir=tmpdir, source="bumeran")

            import glob
            # Solo se crea el CSV con formato corto DD_MM_data.csv
            csv_files = glob.glob(os.path.join(tmpdir, "*_data.csv"))
            self.assertEqual(len(csv_files), 1)
            
            with open(csv_files[0], "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()

        self.assertEqual(rows, ["Fuente,Empresa,Titulo,Url"])

    def test_guardar_resultados_preserves_extra_fields_union(self) -> None:
        records = [
            {"fuente": "A", "titulo": "Uno", "url": "https://a"},
            {"fuente": "B", "titulo": "Dos", "url": "https://b", "ciudad": "Lima"},
            {"fuente": "C", "titulo": "Tres", "url": "https://c", "salario": "1000", "ciudad": "Cusco"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            guardar_resultados(records, "Prueba", output_dir=tmpdir, source="mix")

            import glob
            # Solo se crea el CSV con formato corto DD_MM_prueba.csv
            csv_files = glob.glob(os.path.join(tmpdir, "*_prueba.csv"))
            self.assertEqual(len(csv_files), 1)
            
            with open(csv_files[0], "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()

        header = rows[0]
        # Ahora solo 4 columnas fijas con headers capitalizados
        self.assertEqual(header, "Fuente,Empresa,Titulo,Url")

    def test_guardar_resultados_dedup_and_top_csv_and_clipboard(self) -> None:
        records = [
            {"fuente": "X", "titulo": "Analista", "empresa": "BCP", "url": "https://example.com/a"},
            {"fuente": "X", "titulo": "Analista duplicada", "empresa": "BCP", "url": "https://example.com/a"},
            {"fuente": "Y", "titulo": "Data", "empresa": "Startup", "url": "https://example.com/b"},
            {"fuente": "Z", "titulo": "Cientifico", "empresa": "Scotiabank Peru", "url": "https://example.com/c"},
            {"fuente": "Z", "titulo": "Contador", "empresa": "caja arequipa", "url": "https://example.com/d"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.pyperclip.copy") as mock_copy:
                guardar_resultados(records, "Analista", output_dir=tmpdir, source="combined")

            import glob
            # Verificar que se creó el CSV con formato corto
            csv_files = glob.glob(os.path.join(tmpdir, "*_analista.csv"))
            self.assertEqual(len(csv_files), 1)
            
            with open(csv_files[0], "r", encoding="utf-8") as handle:
                import csv as csv_module
                # Headers capitalizados
                reader = csv_module.DictReader(handle)
                data = list(reader)

            # Dedupe should drop the duplicate URL (but keep non-top entries like caja)
            self.assertEqual(len(data), 4)
            urls = {item["Url"] for item in data}
            self.assertEqual(urls, {
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
                "https://example.com/d",
            })

            # Top file should exist and include only whitelisted companies
            top_files = glob.glob(os.path.join(tmpdir, "top_analista*.csv"))
            self.assertEqual(len(top_files), 1)
            with open(top_files[0], "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(rows[0], "Fuente,Empresa,Titulo,Url")  # Headers capitalizados
            self.assertEqual(len(rows), 3)  # header + 2 top rows
            top_empresas = {row.split(",")[1] for row in rows[1:]}
            self.assertEqual(top_empresas, {"BCP", "Scotiabank Peru"})

            # Clipboard should have been invoked with formatted summary
            mock_copy.assert_called_once()
            clipboard_text = mock_copy.call_args[0][0]
            self.assertIn("🗣️ BCP", clipboard_text)
            self.assertIn("🗣️ SCOTIABANK PERU", clipboard_text)
            self.assertIn("↳ Analista", clipboard_text)
            self.assertIn("✅ example.com/a", clipboard_text)
            self.assertIn("↳ Cientifico", clipboard_text)
            self.assertIn("✅ example.com/c", clipboard_text)
            self.assertNotIn("caja", clipboard_text.lower())

    def test_copy_top_from_csv_reads_and_copies_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "top_demo.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write("fuente,empresa,titulo,url\n")
                handle.write("A,Falabella,Analista,https://example.com/1\n")
                handle.write("B,FALEBELLA,Senior,https://example.com/3\n")
                handle.write("C,FALEBELLA,Lead,//www.bumeran.com.pe/empleos/dev-123\n")
                handle.write("D,Startup,Junior,https://example.com/2\n")
            with patch("src.utils.pyperclip.copy") as mock_copy:
                summary = copy_top_from_csv(csv_path)
            mock_copy.assert_called_once()
            self.assertIn("🗣️ FALEBELLA", summary)
            self.assertIn("Analista", summary)
            self.assertIn("Senior", summary)
            self.assertIn("https://www.bumeran.com.pe/empleos/dev-123", summary)
            # grouped once despite different casing
            self.assertEqual(summary.count("🗣️ FALEBELLA"), 1)
            self.assertNotIn("Startup", summary)  # no whitelist match, so ignored

    def test_shorten_url_for_bumeran_id(self) -> None:
        from src.utils import _shorten_url_for_display

        url = "https://www.bumeran.com.pe/empleos/analista-de-producto-seguros-vida-y-decesos-mapfre-peru-compania-de-seguros-y-reaseguros-1118085708.html"
        shortened = _shorten_url_for_display(url)
        self.assertEqual(shortened, "https://www.bumeran.com.pe/empleos/1118085708.html")

    def test_excluded_job_keywords_are_filtered(self) -> None:
        """Test that jobs with excluded keywords are removed."""
        records = [
            {"fuente": "Test", "titulo": "Analista de Sistemas", "empresa": "Test Co", "url": "https://example.com/1"},
            {"fuente": "Test", "titulo": "Asesor Call Center", "empresa": "Test Co", "url": "https://example.com/2"},
            {"fuente": "Test", "titulo": "Asesor de Ventas", "empresa": "Test Co", "url": "https://example.com/3"},
            {"fuente": "Test", "titulo": "Ejecutivo de Cobranza", "empresa": "Test Co", "url": "https://example.com/4"},
            {"fuente": "Test", "titulo": "Ingeniero Senior", "empresa": "Test Co", "url": "https://example.com/5"},
            {"fuente": "Test", "titulo": "Mozo de Almacén", "empresa": "Test Co", "url": "https://example.com/6"},
            {"fuente": "Test", "titulo": "Asesor de Atención al Cliente", "empresa": "Test Co", "url": "https://example.com/7"},
            {"fuente": "Test", "titulo": "Asesor Financiero", "empresa": "Test Co", "url": "https://example.com/8"},
            {"fuente": "Test", "titulo": "Asesor de Negocios", "empresa": "Test Co", "url": "https://example.com/9"},
            {"fuente": "Test", "titulo": "Consultor de Ventas", "empresa": "Test Co", "url": "https://example.com/10"},
            {"fuente": "Test", "titulo": "Gerente de Proyectos", "empresa": "Test Co", "url": "https://example.com/11"},
            {"fuente": "Test", "titulo": "Escuela de Analista de créditos", "empresa": "Test Co", "url": "https://example.com/12"},
            {"fuente": "Test", "titulo": "Call Center Supervisor", "empresa": "Test Co", "url": "https://example.com/13"},
            {"fuente": "Test", "titulo": "Operario", "empresa": "Test Co", "url": "https://example.com/14"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            guardar_resultados(records, "Test", output_dir=tmpdir, source="test")

            import glob
            # Solo se crea el CSV con formato corto DD_MM_test.csv
            csv_files = glob.glob(os.path.join(tmpdir, "*_test.csv"))
            self.assertEqual(len(csv_files), 1)
            
            with open(csv_files[0], "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()

        # Should have header + 3 valid records (Analista de Sistemas, Ingeniero Senior, Gerente de Proyectos)
        # Filtered out: All "Asesor" roles, "Consultor de Ventas", "Escuela de", "Call Center", "Operario", "Ejecutivo de Cobranza", "Mozo de Almacén"
        self.assertEqual(len(rows), 4)  # header + 3 records
        titles = [row.split(",")[2] for row in rows[1:]]
        titles_lower = [t.lower() for t in titles]
        self.assertIn("analista de sistemas", titles_lower)
        self.assertIn("ingeniero senior", titles_lower)
        self.assertIn("gerente de proyectos", titles_lower)
        # Verify excluded keywords are not in the results
        for title in titles_lower:
            self.assertNotIn("asesor", title)
            self.assertNotIn("call center", title)
            self.assertNotIn("consultor de ventas", title)
            self.assertNotIn("escuela de", title)
            self.assertNotIn("operario", title)
            self.assertNotIn("ejecutivo de cobranza", title)
            self.assertNotIn("mozo", title)

