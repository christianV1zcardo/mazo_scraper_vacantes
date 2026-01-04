import json
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
            with patch("src.utils.datetime") as mock_datetime:
                mock_datetime.now.return_value = real_datetime(2025, 1, 15)
                guardar_resultados(records, "Analista", output_dir=tmpdir, source="combined")

            base_path = os.path.join(tmpdir, "combined_analista_2025-01-15")
            json_path = f"{base_path}.json"
            csv_path = f"{base_path}.csv"

            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(csv_path))

            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data, records)

            with open(csv_path, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], "fuente,empresa,titulo,url")

    def test_guardar_resultados_handles_empty_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.datetime") as mock_datetime:
                mock_datetime.now.return_value = real_datetime(2025, 6, 2)
                guardar_resultados([], "Data", output_dir=tmpdir, source="bumeran")

            base_path = os.path.join(tmpdir, "bumeran_data_2025-06-02")
            csv_path = f"{base_path}.csv"

            with open(csv_path, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()

        self.assertEqual(rows, ["fuente,empresa,titulo,url"])

    def test_guardar_resultados_preserves_extra_fields_union(self) -> None:
        records = [
            {"fuente": "A", "titulo": "Uno", "url": "https://a"},
            {"fuente": "B", "titulo": "Dos", "url": "https://b", "ciudad": "Lima"},
            {"fuente": "C", "titulo": "Tres", "url": "https://c", "salario": "1000", "ciudad": "Cusco"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.datetime") as mock_datetime:
                mock_datetime.now.return_value = real_datetime(2025, 7, 1)
                guardar_resultados(records, "Prueba", output_dir=tmpdir, source="mix")

            base_path = os.path.join(tmpdir, "mix_prueba_2025-07-01")
            csv_path = f"{base_path}.csv"
            with open(csv_path, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()

        header = rows[0]
        # Extra fields should appear after base fields, preserving first-seen order
        self.assertEqual(header, "fuente,empresa,titulo,url,ciudad,salario")

    def test_guardar_resultados_dedup_and_top_csv_and_clipboard(self) -> None:
        records = [
            {"fuente": "X", "titulo": "Analista", "empresa": "BCP", "url": "https://example.com/a"},
            {"fuente": "X", "titulo": "Analista duplicada", "empresa": "BCP", "url": "https://example.com/a"},
            {"fuente": "Y", "titulo": "Data", "empresa": "Startup", "url": "https://example.com/b"},
            {"fuente": "Z", "titulo": "Cientifico", "empresa": "Scotiabank Peru", "url": "https://example.com/c"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.datetime") as mock_datetime, patch("src.utils.pyperclip.copy") as mock_copy:
                mock_datetime.now.return_value = real_datetime(2025, 8, 20)
                guardar_resultados(records, "Analista", output_dir=tmpdir, source="combined")

            base_path = os.path.join(tmpdir, "combined_analista_2025-08-20")
            json_path = f"{base_path}.json"
            csv_path = f"{base_path}.csv"
            top_path = os.path.join(tmpdir, "top_analista_2025-08-20.csv")

            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            # Dedupe should drop the duplicate URL
            self.assertEqual(len(data), 3)
            urls = {item["url"] for item in data}
            self.assertEqual(urls, {
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            })

            # Top file should exist and include only whitelisted companies
            self.assertTrue(os.path.exists(top_path))
            with open(top_path, "r", encoding="utf-8") as handle:
                rows = handle.read().splitlines()
            self.assertEqual(rows[0], "fuente,empresa,titulo,url")
            self.assertEqual(len(rows), 3)  # header + 2 top rows
            top_empresas = {row.split(",")[1] for row in rows[1:]}
            self.assertEqual(top_empresas, {"BCP", "Scotiabank Peru"})

            # Clipboard should have been invoked with formatted summary
            mock_copy.assert_called_once()
            clipboard_text = mock_copy.call_args[0][0]
            self.assertIn("🗣️ BCP", clipboard_text)
            self.assertIn("🗣️ SCOTIABANK PERU", clipboard_text)
            self.assertIn("↳ Analista", clipboard_text)
            self.assertIn("✅ https://example.com/a", clipboard_text)
            self.assertIn("↳ Cientifico", clipboard_text)
            self.assertIn("✅ https://example.com/c", clipboard_text)

    def test_copy_top_from_csv_reads_and_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "top_demo.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write("fuente,empresa,titulo,url\n")
                handle.write("A,Interbank,Analista,https://example.com/1\n")
                handle.write("B,Startup,Junior,https://example.com/2\n")
            with patch("src.utils.pyperclip.copy") as mock_copy:
                summary = copy_top_from_csv(csv_path)
            mock_copy.assert_called_once()
            self.assertIn("🗣️ INTERBANK", summary)
            self.assertIn("Analista", summary)
            self.assertNotIn("Startup", summary)  # no whitelist match, so only first row copied


if __name__ == "__main__":
    unittest.main()
