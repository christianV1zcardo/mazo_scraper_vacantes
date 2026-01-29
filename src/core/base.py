"""Common scraper behaviour abstractions."""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

import logging

from selenium.webdriver.remote.webdriver import WebDriver

from .browser import create_firefox_driver, create_stealth_driver

JobPayload = Dict[str, str]

logger = logging.getLogger(__name__)


class BlockDetected(Exception):
    """Indica que un scraper encontró un captcha/bloqueo y no debe reintentar."""


class BaseScraper:
    """Base Selenium scraper with pagination helpers."""

    max_pages: int = 50

    def __init__(
        self,
        driver: Optional[WebDriver] = None,
        headless: Optional[bool] = True,
        use_stealth: bool = False,
    ) -> None:
        if driver:
            self.driver = driver
        elif use_stealth:
            self.driver = create_stealth_driver(headless=headless)
        else:
            self.driver = create_firefox_driver(headless=headless)

    def close(self) -> None:
        """Terminate the underlying browser session."""
        if not getattr(self, "driver", None):
            return
        try:
            self.driver.quit()
        finally:
            self.driver = None  # type: ignore[assignment]

    def gather_paginated(
        self,
        extractor: Callable[[], List[JobPayload]],
        navigator: Optional[Callable[[int], bool]] = None,
        page_wait: float = 1.0,
        source_label: Optional[str] = None,
        low_yield_threshold: Optional[int] = None,
        low_yield_patience: int = 2,
    ) -> List[JobPayload]:
        """Aggregate job payloads across paginated listings."""
        results: List[JobPayload] = []
        seen: set[str] = set()
        page = 1
        low_yield_streak = 0
        consecutive_errors = 0
        max_consecutive_errors = 3
        label = (source_label or getattr(self, "source_label", self.__class__.__name__)).lower()
        prefix = f"[{label}] " if label else ""
        logger.info("%sPaginación iniciada (max_pages=%s, page_wait=%.2fs)", prefix, self.max_pages, page_wait)
        while page <= self.max_pages:
            logger.debug("%sProcesando página %d", prefix, page)
            start_page = time.perf_counter()
            if page > 1:
                if navigator and not navigator(page):
                    logger.info("%sPaginación detenida: navegador devolvió False en página %d", prefix, page)
                    break
                if page_wait:
                    logger.debug("%sEsperando %.2fs antes de extraer página %d", prefix, page_wait, page)
                    time.sleep(page_wait)
            try:
                current = extractor()
                consecutive_errors = 0  # Reset error counter on success
            except BlockDetected:
                raise
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning("%sPaginación detenida tras %d errores consecutivos en página %d: %s", 
                                 prefix, consecutive_errors, page, exc)
                    break
                logger.debug("%sError en página %d (intento %d/%d): %s", 
                           prefix, page, consecutive_errors, max_consecutive_errors, exc)
                page += 1
                continue
            new_found = 0
            for payload in current:
                url = payload.get("url")
                if not url or url in seen:
                    if url:
                        logger.debug("%sURL duplicada descartada en página %d: %s", prefix, page, url)
                    continue
                seen.add(url)
                results.append(payload)
                new_found += 1
            if new_found == 0:
                logger.info("%sPaginación detenida: página %d sin nuevos resultados", prefix, page)
                break
            if low_yield_threshold is not None:
                if new_found <= low_yield_threshold:
                    low_yield_streak += 1
                    if low_yield_streak > max(0, low_yield_patience):
                        logger.info(
                            "%sPaginación detenida: %d páginas consecutivas con <=%d nuevos",
                            prefix,
                            low_yield_streak,
                            low_yield_threshold,
                        )
                        break
                else:
                    low_yield_streak = 0
            page += 1
            elapsed = time.perf_counter() - start_page
            logger.info(
                "%sPágina %d procesada en %.2fs (nuevos=%d, acumulados=%d)",
                prefix,
                page - 1,
                elapsed,
                new_found,
                len(results),
            )
        logger.info("%sPaginación finalizada con %d resultados únicos", prefix, len(results))
        return results
