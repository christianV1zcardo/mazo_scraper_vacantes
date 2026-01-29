"""Scraper orchestration utilities."""

from __future__ import annotations

import gc
import logging
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from .bumeran import BumeranScraper
from .computrabajo import ComputrabajoScraper
from .indeed import IndeedScraper
from .laborum import LaborumScraper
from .core.base import BaseScraper, BlockDetected
from .utils import guardar_resultados
from concurrent.futures import ThreadPoolExecutor, as_completed

JobRecord = Dict[str, str]

logger = logging.getLogger(__name__)

DEFAULT_SOURCES: Sequence[str] = ("bumeran", "computrabajo", "indeed", "laborum")


def _collect_bumeran(
    scraper: BumeranScraper,
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
) -> List[JobRecord]:
    results: List[JobRecord] = []
    seen: Set[str] = set()

    def _extract_with(scraper_inst: BumeranScraper, wait: float) -> List[JobRecord]:
        scraper_inst.abrir_pagina_empleos(hoy=dias == 1, dias=dias if dias in (2, 3) else 0)
        scraper_inst.buscar_vacante(busqueda)
        # Reducir espera inicial para mayor velocidad
        effective_wait = min(wait, 1.0)
        logger.info("[bumeran] Esperando %.1f s para carga inicial", effective_wait)
        time.sleep(effective_wait)
        return scraper_inst.extraer_todos_los_puestos(timeout=6, page_wait=page_wait)

    def _fallback_no_headless() -> List[JobRecord]:
        temp = BumeranScraper(headless=False)
        try:
            puestos_tmp = _extract_with(temp, initial_wait * 1.5)
            logger.info("[bumeran] Fallback sin headless produjo %d puestos", len(puestos_tmp))
            return puestos_tmp
        finally:
            try:
                temp.close()
            except Exception:
                logger.exception("[bumeran] Error cerrando scraper fallback")
    try:
        puestos = _with_retries(
            label="bumeran.extract",
            operation=lambda: _extract_with(scraper, initial_wait),
            fallback_operation=_fallback_no_headless,
        )
        logger.info("[bumeran] puestos extraídos (raw): %d", len(puestos))
        dropped = 0
        for puesto in puestos:
            url = puesto.get("url")
            normalized = _normalize_url(url)
            if not normalized or normalized in seen:
                dropped += 1
                continue
            seen.add(normalized)
            results.append({"fuente": "Bumeran", **puesto, "url": normalized})
        if dropped:
            logger.debug("[bumeran] Ofertas descartadas por duplicado/URL vacía: %d", dropped)
        logger.info("[bumeran] puestos finales tras normalizar/dedup: %d", len(results))
    except Exception:
        logger.exception("[bumeran] Error durante la recolección")
    return results


def _collect_computrabajo(
    scraper: ComputrabajoScraper,
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
) -> List[JobRecord]:
    results: List[JobRecord] = []
    seen: Set[str] = set()

    def _extract_with(scraper_inst: ComputrabajoScraper, wait: float) -> List[JobRecord]:
        scraper_inst.abrir_pagina_empleos(dias=dias)
        scraper_inst.buscar_vacante(busqueda)
        # Reducir espera inicial para Computrabajo
        effective_wait = min(wait, 1.5)
        logger.info("[computrabajo] Esperando %.1f s para carga inicial", effective_wait)
        time.sleep(effective_wait)
        return scraper_inst.extraer_todos_los_puestos(timeout=8, page_wait=page_wait)

    def _fallback_no_headless() -> List[JobRecord]:
        temp = ComputrabajoScraper(headless=False)
        try:
            puestos_tmp = _extract_with(temp, initial_wait * 1.5)
            logger.info("[computrabajo] Fallback sin headless produjo %d puestos", len(puestos_tmp))
            return puestos_tmp
        finally:
            try:
                temp.close()
            except Exception:
                logger.exception("[computrabajo] Error cerrando scraper fallback")
    try:
        puestos = _with_retries(
            label="computrabajo.extract",
            operation=lambda: _extract_with(scraper, initial_wait),
            fallback_operation=_fallback_no_headless,
        )
        logger.info("[computrabajo] puestos extraídos (raw): %d", len(puestos))
        dropped = 0
        for puesto in puestos:
            url = puesto.get("url")
            normalized = _normalize_url(url)
            if not normalized or normalized in seen:
                dropped += 1
                continue
            seen.add(normalized)
            results.append({"fuente": "Computrabajo", **puesto, "url": normalized})
        if dropped:
            logger.debug("[computrabajo] Ofertas descartadas por duplicado/URL vacía: %d", dropped)
        logger.info("[computrabajo] puestos finales tras normalizar/dedup: %d", len(results))
    except Exception:
        logger.exception("[computrabajo] Error durante la recolección")
    return results


def _collect_indeed(
    scraper: IndeedScraper,
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
) -> List[JobRecord]:
    results: List[JobRecord] = []
    seen: Set[str] = set()

    def _extract_with(scraper_inst: IndeedScraper, wait: float, per_page_wait: float) -> List[JobRecord]:
        scraper_inst.abrir_pagina_empleos(dias=dias)
        scraper_inst.buscar_vacante(busqueda)
        logger.info(
            "[indeed] Esperando %.1f s inicial, page_wait=%.2f s",
            wait,
            per_page_wait,
        )
        time.sleep(wait)
        return scraper_inst.extraer_todos_los_puestos(timeout=6, page_wait=per_page_wait)

    def _fallback_no_headless() -> List[JobRecord]:
        temp = IndeedScraper(headless=False)
        try:
            puestos_tmp = _extract_with(temp, max(1.5, initial_wait * 1.5), max(0.5, page_wait))
            logger.info("[indeed] Fallback sin headless produjo %d puestos", len(puestos_tmp))
            return puestos_tmp
        finally:
            try:
                temp.close()
            except Exception:
                logger.exception("[indeed] Error cerrando scraper fallback")
    try:
        effective_initial_wait = min(initial_wait, 1.0)
        effective_page_wait = max(0.1, page_wait * 0.5)
        puestos = _with_retries(
            label="indeed.extract",
            operation=lambda: _extract_with(scraper, effective_initial_wait, effective_page_wait),
            fallback_operation=_fallback_no_headless,
            retries=1,
            initial_delay=1.0,
            backoff=1.5,
        )
        if not puestos and scraper.detecta_bloqueo_cloudflare():
            logger.warning("[indeed] Se detectó un challenge de Cloudflare, reintentando con más espera")
            time.sleep(3)
            try:
                scraper.buscar_vacante(busqueda)
            except Exception:
                logger.exception("[indeed] Fallo al relanzar la búsqueda tras challenge")
            else:
                time.sleep(4)
                try:
                    puestos = scraper.extraer_todos_los_puestos(
                        timeout=8,
                        page_wait=max(0.2, effective_page_wait),
                    )
                except Exception:
                    logger.exception("[indeed] Reintento tras challenge falló")
                    puestos = []
        logger.info("[indeed] puestos extraídos (raw): %d", len(puestos))
        dropped = 0
        for puesto in puestos:
            url = puesto.get("url")
            normalized = _normalize_url(url)
            if not normalized or normalized in seen:
                dropped += 1
                continue
            seen.add(normalized)
            results.append({"fuente": "Indeed", **puesto, "url": normalized})
        if dropped:
            logger.debug("[indeed] Ofertas descartadas por duplicado/URL vacía: %d", dropped)
        logger.info("[indeed] puestos finales tras normalizar/dedup: %d", len(results))
    except Exception:
        logger.exception("[indeed] Error durante la recolección")
    return results


def _collect_laborum(
    scraper: LaborumScraper,
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
) -> List[JobRecord]:
    results: List[JobRecord] = []
    seen: Set[str] = set()

    def _extract_with(scraper_inst: LaborumScraper, wait: float) -> List[JobRecord]:
        scraper_inst.abrir_pagina_empleos(dias=dias)
        scraper_inst.buscar_vacante(busqueda)
        # Reducir espera inicial
        effective_wait = min(wait, 1.5)
        logger.info("[laborum] Esperando %.1f s para carga inicial", effective_wait)
        time.sleep(effective_wait)
        return scraper_inst.extraer_todos_los_puestos(timeout=8, page_wait=page_wait)

    def _fallback_no_headless() -> List[JobRecord]:
        temp = LaborumScraper(headless=False)
        try:
            puestos_tmp = _extract_with(temp, initial_wait * 1.5)
            logger.info("[laborum] Fallback sin headless produjo %d puestos", len(puestos_tmp))
            return puestos_tmp
        finally:
            try:
                temp.close()
            except Exception:
                logger.exception("[laborum] Error cerrando scraper fallback")

    try:
        puestos = _with_retries(
            label="laborum.extract",
            operation=lambda: _extract_with(scraper, initial_wait),
            fallback_operation=_fallback_no_headless,
        )
        logger.info("[laborum] puestos extraídos (raw): %d", len(puestos))
        dropped = 0
        for puesto in puestos:
            url = puesto.get("url")
            normalized = _normalize_url(url)
            if not normalized or normalized in seen:
                dropped += 1
                continue
            seen.add(normalized)
            results.append({"fuente": "Laborum", **puesto, "url": normalized})
        if dropped:
            logger.debug("[laborum] Ofertas descartadas por duplicado/URL vacía: %d", dropped)
        logger.info("[laborum] puestos finales tras normalizar/dedup: %d", len(results))
    except Exception:
        logger.exception("[laborum] Error durante la recolección")
    return results


def _cleanup_driver(scraper: BaseScraper, label: str | None = None) -> None:
    source_label = label or scraper.__class__.__name__
    logger.debug("Liberando recursos adicionales para '%s'", source_label)
    try:
        if hasattr(scraper, "driver") and scraper.driver:
            scraper.driver.quit()
    except Exception:
        logger.exception("Fallo al cerrar driver para '%s'", source_label)
    gc.collect()
    time.sleep(1)


CollectorFn = Callable[[Any, str, int, float, float], List[JobRecord]]
CollectorEntry = Tuple[Callable[..., BaseScraper], CollectorFn, bool, bool]


SCRAPER_REGISTRY: Dict[str, CollectorEntry] = {
    "bumeran": (
        lambda headless=None: BumeranScraper(headless=headless),
        _collect_bumeran,
        True,
        False,
    ),
    "computrabajo": (
        lambda headless=None: ComputrabajoScraper(headless=headless),
        _collect_computrabajo,
        False,
        False,
    ),
    "indeed": (
        lambda headless=None: IndeedScraper(headless=headless),
        _collect_indeed,
        False,
        False,  # Changed to parallel for speed
    ),
    "laborum": (
        lambda headless=None: LaborumScraper(headless=headless),
        _collect_laborum,
        False,
        False,  # Now parallel like others
    ),
}


def _normalize_sources(sources: Iterable[str] | None) -> List[str]:
    if not sources:
        return list(DEFAULT_SOURCES)
    expanded: List[str] = []
    for source in sources:
        normalized = source.lower()
        if normalized == "all":
            expanded.extend(DEFAULT_SOURCES)
        else:
            expanded.append(normalized)
    # Preserve order while removing duplicates
    ordered_unique: List[str] = []
    seen = set()
    for item in expanded:
        if item not in seen:
            seen.add(item)
            ordered_unique.append(item)
    return ordered_unique or list(DEFAULT_SOURCES)


def run_combined(
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
    sources: Iterable[str] | None = None,
    headless: Optional[bool] = None,
) -> List[JobRecord]:
    combined, executed = collect_jobs(
        busqueda=busqueda,
        dias=dias,
        initial_wait=initial_wait,
        page_wait=page_wait,
        sources=sources,
        headless=headless,
    )
    if not executed:
        logger.warning("No se ejecutó ningún scraper válido.")
        return []

    label = "combined" if len(executed) > 1 else executed[0]
    logger.info("Guardando %d ofertas para '%s' con etiqueta '%s'", len(combined), busqueda, label)
    guardar_resultados(combined, busqueda, output_dir="output", source=label)
    logger.info("Guardado completado.")
    return combined


def collect_jobs(
    busqueda: str,
    dias: int,
    initial_wait: float,
    page_wait: float,
    sources: Iterable[str] | None = None,
    headless : Optional[bool] = None,
) -> Tuple[List[JobRecord], List[str]]:
    selected_sources = _normalize_sources(sources)
    combined: List[JobRecord] = []
    executed: List[str] = []
    seen_urls: Set[str] = set()

    parallel_tasks: List[Tuple[str, BaseScraper, CollectorFn, bool]] = []
    serial_tasks: List[Tuple[str, BaseScraper, CollectorFn, bool]] = []
    for source in selected_sources:
        entry = SCRAPER_REGISTRY.get(source)
        if not entry:
            logger.warning("Fuente desconocida '%s', se omite.", source)
            continue
        factory, collector, needs_cleanup, run_serially = entry
        scraper = factory(headless=headless)
        task = (source, scraper, collector, needs_cleanup)
        if run_serially:
            serial_tasks.append(task)
        else:
            parallel_tasks.append(task)

    def run_task(source, scraper, collector, needs_cleanup):
        logger.info(
            "Iniciando scraper '%s' (dias=%s, initial_wait=%.2fs, page_wait=%.2fs, headless=%s)",
            source,
            dias,
            initial_wait,
            page_wait,
            headless,
        )
        start_time = time.perf_counter()
        results: List[JobRecord] = []
        try:
            results = collector(scraper, busqueda, dias, initial_wait, page_wait)
        except Exception:
            logger.exception("Error no controlado ejecutando scraper '%s'", source)
        finally:
            try:
                scraper.close()
            except Exception:
                logger.exception("Error cerrando scraper '%s'", source)
            if needs_cleanup:
                _cleanup_driver(scraper, source)
        elapsed = time.perf_counter() - start_time
        logger.info("Scraper '%s' finalizado en %.2fs con %d ofertas", source, elapsed, len(results))
        return source, results

    def process_results(source: str, results: List[JobRecord]) -> None:
        if not results:
            logger.info("Scraper '%s' no produjo resultados.", source)
            return
        executed.append(source)
        dropped = 0
        for job in results:
            url = job.get("url")
            normalized = _normalize_url(url)
            if not normalized:
                logger.debug("Oferta sin URL descartada de '%s'", source)
                dropped += 1
                continue
            if normalized in seen_urls:
                logger.debug("Oferta duplicada descartada: %s", normalized)
                dropped += 1
                continue
            seen_urls.add(normalized)
            fuente = job.get("fuente") or source
            combined.append({**job, "url": normalized, "fuente": fuente})
        logger.info(
            "Scraper '%s' entregó %d ofertas (descartadas %d por duplicadas/URL vacía)",
            source,
            len(results),
            dropped,
        )

    if parallel_tasks:
        with ThreadPoolExecutor(max_workers=len(parallel_tasks)) as executor:
            future_to_source = {
                executor.submit(run_task, source, scraper, collector, needs_cleanup): source
                for source, scraper, collector, needs_cleanup in parallel_tasks
            }
            for future in as_completed(future_to_source):
                source, results = future.result()
                process_results(source, results)

    for source, scraper, collector, needs_cleanup in serial_tasks:
        source_id, results = run_task(source, scraper, collector, needs_cleanup)
        process_results(source_id, results)

    # Resumen por fuente
    if executed:
        logger.info("Resumen por fuente (sin duplicados globales):")
        for src in executed:
            # Normalizar comparación de fuente (case-insensitive)
            kept = sum(1 for job in combined if (job.get("fuente") or "").lower() == src.lower())
            logger.info(" - %s: %d ofertas finales", src, kept)
    else:
        logger.info("Sin fuentes ejecutadas para resumir.")

    logger.info("Total ofertas combinadas tras deduplicación: %d", len(combined))
    return combined, executed


def _with_retries(
    label: str,
    operation: Callable[[], List[JobRecord]],
    retries: int = 2,
    initial_delay: float = 1.5,
    backoff: float = 1.8,
    fallback_operation: Optional[Callable[[], List[JobRecord]]] = None,
) -> List[JobRecord]:
    attempt = 1
    delay = initial_delay
    while True:
        try:
            start = time.perf_counter()
            result = operation()
            elapsed = time.perf_counter() - start
            logger.info("[%s] intento %d OK en %.2fs (items=%d)", label, attempt, elapsed, len(result))
            return result
        except BlockDetected as exc:
            logger.warning(
                "[%s] bloqueo/captcha detectado: %s. Abortando scraper; intenta con --no-headless, mayor espera o rotar IP.",
                label,
                exc,
            )
            if fallback_operation:
                logger.info("[%s] Ejecutando fallback sin headless", label)
                try:
                    return fallback_operation()
                except Exception:
                    logger.exception("[%s] Fallback sin headless falló", label)
            return []
        except Exception as exc:
            if attempt > retries:
                logger.exception("[%s] fallo definitivo en intento %d", label, attempt)
                raise
            logger.warning("[%s] fallo intento %d: %s (reintento en %.1fs)", label, attempt, exc, delay)
            time.sleep(delay)
            attempt += 1
            delay *= backoff


def _normalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        query_items = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k not in {
                "from",
                "start",
                "p",
                "ad",
                "tracking",
                "trk",
                "utm_source",
                "utm_medium",
                "utm_campaign",
            }
        ]
        cleaned_query = urlencode(query_items, doseq=True)
        cleaned_path = parsed.path.rstrip("/") or "/"
        # Conservar el fragmento, ya que algunas fuentes (Computrabajo) lo usan como ID único
        cleaned = parsed._replace(query=cleaned_query, path=cleaned_path)
        return urlunparse(cleaned)
    except Exception:
        return None