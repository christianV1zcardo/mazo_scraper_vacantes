"""Result persistence utilities."""

from __future__ import annotations

import csv
import logging
import os
import re
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

EXCLUDED_JOB_KEYWORDS = [
    # Cualquier variante de "Asesor" (excepto analista de créditos que es más profesional)
    "asesor",
    # Cualquier variante de "Consultor" de ventas
    "consultor de ventas",
    "consultor comercial",
    # Puestos de call center y customer service
    "call center",
    "contact center",
    "call center lima",
    "atención al cliente",
    "atención al estudiante",
    "customer service",
    "telemarketing",
    "telefonico",
    # Puestos de ventas puros
    "vendedor",
    "promotor",
    "promotora",
    "cobrador",
    "ejecutivo de ventas",
    "ejecutivo de cobranza",
    "ejecutivo comercial",
    "ejecutivo de servicios financieros",
    "agente",
    "representante de ventas",
    "gestor de cobranza",
    "monitor de calidad call center",
    "funcionario de crédito",
    "asistente comercial",
    # Puestos de servicio al cliente / retail
    "jefe de tienda",
    "supervisor de tienda",
    "gerente de tienda",
    "dependiente",
    "cajero",
    "reponedor",
    "operario retail",
    # Otros roles sin demanda
    "limpieza",
    "mozo",
    "ayudante de almacén",
    "operario",
    "peón",
    "asistente general",
    "auxiliar general",
    # Roles en formación (escuelas de...) - estos son prácticamente entry level de ventas
    "escuela de",
    # Trabajos muy basic
    "repartidor",
    "conductor",
    "chofer",
    "mensajero",
]


def guardar_resultados(
    puestos: Iterable[JobRecord],
    query: str,
    output_dir: str = "output",
    source: str = "bumeran",
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    year, month, day = timestamp.split("-")
    short_date = f"{day}_{month}"  # Format: DD_MM
    
    # Nombre corto para el CSV principal: DD_MM_query.csv
    short_base_name = f"{short_date}_{query.lower()}"
    
    raw_records = list(puestos)
    records = _dedupe_records(raw_records)
    short_csv_path = os.path.join(output_dir, f"{short_base_name}.csv")
    
    # Solo guardar el CSV con formato corto (sin combined JSON/CSV)
    _save_csv(records, short_csv_path)
    
    top_records = _filter_whitelist(records)
    top_base = f"top_{query.lower()}_{timestamp}"
    top_csv_path = os.path.join(output_dir, f"{top_base}.csv")
    if top_records:
        _save_csv(top_records, top_csv_path)
        summary = _copy_top_summary(top_records)
        logger.info(
            "Resultados persistidos en %s y top %s (dedup: %d -> %d, top: %d)",
            short_csv_path,
            top_csv_path,
            len(raw_records),
            len(records),
            len(top_records),
        )
        if summary:
            logger.info("Resumen top copiado al portapapeles (%d caracteres)", len(summary))
    else:
        logger.info(
            "Resultados persistidos en %s (dedup: %d -> %d, top: 0)",
            short_csv_path,
            len(raw_records),
            len(records),
        )


def _save_csv(records: List[JobRecord], path: str) -> None:
    # Solo 4 columnas en orden fijo con headers capitalizados
    base_fields = ["fuente", "empresa", "titulo", "url"]
    header_names = ["Fuente", "Empresa", "Titulo", "Url"]
    
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header_names)
        for record in records:
            row = [record.get(f, "") for f in base_fields]
            writer.writerow(row)
    logger.info("Resultados guardados en CSV: %s", path)


def _dedupe_records(records: List[JobRecord]) -> List[JobRecord]:
    seen: set[str] = set()
    deduped: List[JobRecord] = []
    dropped = 0
    excluded = 0
    for record in records:
        url = record.get("url")
        titulo = (record.get("titulo") or "").lower()
        
        # Check if job title matches excluded keywords
        if any(keyword in titulo for keyword in EXCLUDED_JOB_KEYWORDS):
            excluded += 1
            continue
        
        if url:
            if url in seen:
                dropped += 1
                continue
            seen.add(url)
        deduped.append(record)
    if dropped:
        logger.info("Se eliminaron %d duplicados por URL", dropped)
    if excluded:
        logger.info("Se eliminaron %d puestos por palabras clave excluidas", excluded)
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
        # Ignorar cajas en general aunque coincidan con la whitelist
        if "caja" in empresa:
            continue
        if any(name in empresa for name in whitelist):
            filtered.append(record)
    return filtered


def _build_top_summary(records: List[JobRecord]) -> str:
    grouped: Dict[str, Dict[str, Any]] = {}
    for record in records:
        empresa_raw = (record.get("empresa") or "").strip()
        if not empresa_raw:
            continue
        key = empresa_raw.lower()
        entry = grouped.setdefault(key, {"label": empresa_raw, "items": []})
        if not entry["label"]:
            entry["label"] = empresa_raw
        entry["items"].append(record)
    if not grouped:
        return ""

    lines: List[str] = []
    for data in grouped.values():
        label = (data.get("label") or "").upper() or "EMPRESA"
        items = data.get("items", [])
        lines.append(f"🗣️ {label}")
        for item in items:
            titulo = (item.get("titulo") or "").strip() or "(Sin título)"
            url = _shorten_url_for_display((item.get("url") or "").strip())
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


def _shorten_url_for_display(url: str) -> str:
    if not url:
        return "(sin URL)"
    original = url
    if url.startswith("//"):
        url = url[2:]
    if url.startswith("https://"):
        url = url[len("https://") :]
    elif url.startswith("http://"):
        url = url[len("http://") :]
    if url.startswith("www."):
        url = url[len("www.") :]

    # Acortado específico para Bumeran: usar solo el id numérico si está presente
    if "bumeran.com" in url:
        parts = url.split("/", 2)
        if len(parts) >= 2:
            path_rest = "/".join(parts[1:]) if len(parts) > 1 else parts[-1]
            match = re.search(r"-(\d+)\.html", path_rest)
            domain = parts[0]
            domain = domain if domain.startswith("www.") else f"www.{domain}"
            if match:
                job_id = match.group(1)
                return f"https://{domain}/empleos/{job_id}.html"
            return f"https://{domain}/{path_rest}"
    return url or original


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
