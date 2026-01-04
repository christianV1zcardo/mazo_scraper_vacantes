"""Result persistence utilities."""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List

import pyperclip

JobRecord = Dict[str, Any]

logger = logging.getLogger(__name__)

WHITELIST_COMPANIES = [
    # BANCA Y FINANZAS
    "bcp",
    "banco de credito",
    "interbank",
    "bbva",
    "scotiabank",
    "credicorp",
    "mibanco",
    "banco de la nacion",
    "caja arequipa",
    "prima afp",
    "afp integra",
    "profuturo",
    "habbitat",
    # SEGUROS
    "pacifico",
    "pacífico",
    "rimac",
    "la positiva",
    "mapfre",
    "marsh",
    # CONSUMO MASIVO Y MANUFACTURA
    "alicorp",
    "backus",
    "gloria",
    "san fernando",
    "nestle",
    "nestlé",
    "procter",
    "pg",
    "unilever",
    "belcorp",
    "yanbal",
    "kimberly-clark",
    "lindley",
    "arca continental",
    "molitalia",
    # RETAIL Y HOLDINGS
    "intercorp",
    "inretail",
    "falabella",
    "saga falabella",
    "ripley",
    "cencosud",
    "wong",
    "metro",
    "tottus",
    "sodimac",
    "promart",
    "supermercados peruanos",
    "makro",
    "plazavea",
    "plaza vea",
    "real plaza",
    "yura",
    "breca",
    # MINERÍA, ENERGÍA E INDUSTRIA PESADA
    "ferreyros",
    "antamina",
    "cerro verde",
    "southern",
    "las bambas",
    "quellaveco",
    "anglo american",
    "minsur",
    "hochschild",
    "nexa",
    "unacem",
    "engie",
    "enel",
    "luz del sur",
    "calidda",
    "petroperu",
    "repsol",
    "primax",
    "komatsu",
    "mitsui",
    # TECNOLOGÍA Y TELECOMUNICACIONES (Grandes)
    "telefonica",
    "telefónica",
    "movistar",
    "claro",
    "entel",
    "bitel",
    "ntt data",
    "globant",
    "ibm",
    "microsoft",
    "oracle",
    "sap",
    "cisco",
    "huawei",
    "indra",
    # CONSULTORÍA ESTRATÉGICA (Big 4 + Tier 1 - Pagan bien)
    "mckinsey",
    "bcg",
    "deloitte",
    "pwc",
    "kpmg",
    "ey",
    "ernst",
    # OTROS CORPORATIVOS
    "latam airlines",
    "lima airport partners",
    "lap",
    "dp world",
    "apm terminals",
    "ranza",
    "talma",
]


def guardar_resultados(
    puestos: Iterable[JobRecord],
    query: str,
    output_dir: str = "output",
    source: str = "bumeran",
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    base_name = f"{source}_{query.lower()}_{timestamp}"
    raw_records = list(puestos)
    records = _dedupe_records(raw_records)
    json_path = os.path.join(output_dir, f"{base_name}.json")
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    _save_json(records, json_path)
    _save_csv(records, csv_path)
    top_records = _filter_whitelist(records)
    top_base = f"top_{query.lower()}_{timestamp}"
    top_csv_path = os.path.join(output_dir, f"{top_base}.csv")
    if top_records:
        _save_csv(top_records, top_csv_path)
        summary = _copy_top_summary(top_records)
        logger.info(
            "Resultados persistidos en %s, %s y top %s (dedup: %d -> %d, top: %d)",
            json_path,
            csv_path,
            top_csv_path,
            len(raw_records),
            len(records),
            len(top_records),
        )
        if summary:
            logger.info("Resumen top copiado al portapapeles (%d caracteres)", len(summary))
    else:
        logger.info(
            "Resultados persistidos en %s y %s (dedup: %d -> %d, top: 0)",
            json_path,
            csv_path,
            len(raw_records),
            len(records),
        )


def _save_json(records: List[JobRecord], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    logger.info("Resultados guardados en JSON: %s", path)


def _save_csv(records: List[JobRecord], path: str) -> None:
    # Ensure fixed base order with the Empresa column between fuente and titulo
    base_fields = ["fuente", "empresa", "titulo", "url"]
    extra_fields: list[str] = []
    seen_extra: set[str] = set()
    for record in records:
        for key in record.keys():
            if key in base_fields or key in seen_extra:
                continue
            seen_extra.add(key)
            extra_fields.append(key)
    fieldnames = base_fields + extra_fields
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    logger.info("Resultados guardados en CSV: %s", path)


def _dedupe_records(records: List[JobRecord]) -> List[JobRecord]:
    seen: set[str] = set()
    deduped: List[JobRecord] = []
    dropped = 0
    for record in records:
        url = record.get("url")
        if url:
            if url in seen:
                dropped += 1
                continue
            seen.add(url)
        deduped.append(record)
    if dropped:
        logger.info("Se eliminaron %d duplicados por URL", dropped)
    return deduped


def _filter_whitelist(records: List[JobRecord]) -> List[JobRecord]:
    if not records:
        return []
    whitelist = [name.lower() for name in WHITELIST_COMPANIES]
    filtered: List[JobRecord] = []
    for record in records:
        empresa = (record.get("empresa") or "").lower()
        if not empresa:
            continue
        if any(name in empresa for name in whitelist):
            filtered.append(record)
    return filtered


def _build_top_summary(records: List[JobRecord]) -> str:
    grouped: Dict[str, List[JobRecord]] = {}
    for record in records:
        empresa = (record.get("empresa") or "").strip()
        if not empresa:
            continue
        grouped.setdefault(empresa, []).append(record)
    if not grouped:
        return ""

    lines: List[str] = []
    for empresa, items in grouped.items():
        lines.append(f"🗣️ {empresa.upper()}")
        for item in items:
            titulo = (item.get("titulo") or "").strip() or "(Sin título)"
            url = (item.get("url") or "").strip() or "(sin URL)"
            lines.append(f"↳ {titulo}")
            lines.append(f"  ✅ {url}")
        lines.append("")
    # Remove trailing blank line
    if lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _copy_top_summary(records: List[JobRecord]) -> str:
    summary = _build_top_summary(records)
    if not summary:
        return ""
    try:
        pyperclip.copy(summary)
    except Exception as exc:
        logger.warning("No se pudo copiar al portapapeles: %s", exc)
    return summary


def copy_top_from_csv(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el archivo: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        records = list(reader)
    summary = _copy_top_summary(records)
    if summary:
        logger.info("Resumen top copiado desde %s (%d líneas)", path, len(summary.splitlines()))
    else:
        logger.info("No se encontraron registros para copiar desde %s", path)
    return summary
