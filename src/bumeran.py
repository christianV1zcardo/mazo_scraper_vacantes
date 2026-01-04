"""Bumeran scraper implementation."""

from __future__ import annotations

import time
import urllib.parse as urlparse
from typing import Any, Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .core.base import BaseScraper, BlockDetected

JobData = Dict[str, Any]


class BumeranScraper(BaseScraper):
    """Scraper de ofertas laborales para Bumeran Perú."""

    def __init__(self, driver=None, headless: Optional[bool] = True) -> None:
        super().__init__(driver=driver, headless=headless)

    def abrir_pagina_empleos(self, hoy: bool = False, dias: int = 0) -> None:
        url = self._build_listing_url(hoy=hoy, dias=dias)
        self.driver.get(url)

    def buscar_vacante(self, palabra_clave: str = "") -> None:
        keyword = palabra_clave.replace(" ", "-").lower()
        try:
            current = self.driver.current_url or ""
            parsed = urlparse.urlparse(current)
            prefix = self._resolve_search_prefix(parsed.path)
            new_path = f"/{prefix}{keyword}.html"
            new_url = f"{parsed.scheme}://{parsed.netloc}{new_path}"
            self.driver.get(new_url)
        except Exception:
            self._fallback_search(palabra_clave)

    def extraer_puestos(self, timeout: int = 10) -> List[JobData]:
        try:
            if self.detecta_bloqueo():
                raise BlockDetected("Captcha o bloqueo detectado en Bumeran")
            return self._extract_from_links(timeout=timeout)
        except Exception:
            # Reintento rápido con un selector alternativo
            try:
                if self.detecta_bloqueo():
                    raise BlockDetected("Captcha o bloqueo detectado en Bumeran (fallback)")
                return self._extract_fallback(timeout=max(2, timeout // 2))
            except Exception:
                return []

    def extraer_todos_los_puestos(self, timeout: int = 10, page_wait: float = 1.0) -> List[JobData]:
        return self.gather_paginated(
            extractor=lambda: self.extraer_puestos(timeout=timeout),
            navigator=self.navegar_a_pagina,
            page_wait=page_wait,
            source_label="bumeran",
        )

    def navegar_a_pagina(self, numero: int) -> bool:
        try:
            current = self.driver.current_url or ""
            parsed = urlparse.urlparse(current)
            query = urlparse.parse_qs(parsed.query)
            query["page"] = [str(numero)]
            new_query = urlparse.urlencode(query, doseq=True)
            refreshed = urlparse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
            )
            self.driver.get(refreshed)
            time.sleep(1)
            return True
        except Exception:
            return False

    def _build_listing_url(self, hoy: bool, dias: int) -> str:
        if hoy or dias == 1:
            return "https://www.bumeran.com.pe/empleos-publicacion-hoy.html"
        if dias == 2:
            return "https://www.bumeran.com.pe/empleos-publicacion-menor-a-2-dias.html"
        if dias == 3:
            return "https://www.bumeran.com.pe/empleos-publicacion-menor-a-3-dias.html"
        return "https://www.bumeran.com.pe/empleos-busqueda.html"

    def _resolve_search_prefix(self, path: str) -> str:
        if "publicacion-hoy" in path:
            return "empleos-publicacion-hoy-busqueda-"
        if "publicacion-menor-a-2-dias" in path:
            return "empleos-publicacion-menor-a-2-dias-busqueda-"
        if "publicacion-menor-a-3-dias" in path:
            return "empleos-publicacion-menor-a-3-dias-busqueda-"
        return "empleos-busqueda-"

    def _fallback_search(self, palabra_clave: str) -> None:
        try:
            input_elem = self.driver.find_element(By.ID, "react-select-4-input")
            input_elem.clear()
            input_elem.send_keys(palabra_clave)
            input_elem.send_keys(Keys.RETURN)
        except Exception:
            pass

    def _extract_from_links(self, timeout: int) -> List[JobData]:
        wait = WebDriverWait(self.driver, timeout)
        container = wait.until(EC.presence_of_element_located((By.ID, "listado-avisos")))
        anchors = container.find_elements(By.TAG_NAME, "a")
        payloads: List[JobData] = []
        seen = set()
        for anchor in anchors:
            try:
                href = anchor.get_attribute("href")
                if not href:
                    continue
                if "/empleos/" not in href:
                    continue
                if any(token in href for token in ("busqueda-", "publicacion-menor", "relevantes=", "recientes=")):
                    continue
                if href in seen:
                    continue
                title = self._extract_title(anchor)
                if not title:
                    continue
                company = self._extract_company(anchor)
                payloads.append({"titulo": title, "url": href, "empresa": company})
                seen.add(href)
            except Exception:
                continue
        return payloads

    def _extract_fallback(self, timeout: int) -> List[JobData]:
        wait = WebDriverWait(self.driver, timeout)
        # Buscar tarjetas comunes cuando el contenedor cambia de ID
        wait.until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/empleos/']")
        )
        anchors = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/empleos/']")
        payloads: List[JobData] = []
        seen = set()
        for anchor in anchors:
            try:
                href = anchor.get_attribute("href")
                if not href or "/empleos/" not in href:
                    continue
                if any(token in href for token in ("busqueda-", "publicacion-menor", "relevantes=", "recientes=")):
                    continue
                if href in seen:
                    continue
                title = self._extract_title(anchor)
                if not title:
                    continue
                company = self._extract_company(anchor)
                payloads.append({"titulo": title, "url": href, "empresa": company})
                seen.add(href)
            except Exception:
                continue
        return payloads

    def detecta_bloqueo(self) -> bool:
        try:
            source = (getattr(self.driver, "page_source", "") or "").lower()
        except Exception:
            return False
        tokens = (
            "captcha",
            "no soy un robot",
            "are you human",
            "unusual traffic",
            "cloudflare",
            "access denied",
        )
        return any(token in source for token in tokens)

    def _extract_title(self, anchor) -> str:
        for tag in ("h1", "h2", "h3", "h4", "h5"):
            elements = anchor.find_elements(By.TAG_NAME, tag)
            if elements:
                text = elements[0].text.strip()
                if text:
                    return text
        return (anchor.text or "").split("\n")[0].strip()

    def _extract_company(self, anchor) -> str:
        """Extract company name from Bumeran card.

        Based on provided markup, company appears as an H3 under a span wrapper
        (e.g., <h3 class="sc-igZVbQ ...">FINANCIERA ADES</h3>) or
        <h3 class="sc-ebDnpS ...">Lindcorp</h3>.
        We avoid picking 'Publicado ...' or the job title itself.
        """
        # Try specific likely patterns first
        specific_selectors = [
            "span.sc-Ehqfj h3",
            "h3.sc-igZVbQ",
            "h3.sc-ebDnpS",
        ]

        def _clean(txt: str) -> str:
            return (txt or "").strip().split("\n")[0]

        # Obtain the job title text to avoid confusing it with company
        title_elems = anchor.find_elements(By.CSS_SELECTOR, "h2")
        title_text = _clean(title_elems[0].text) if title_elems else ""

        # Filters to exclude non-company h3s
        def _is_company_candidate(txt: str) -> bool:
            if not txt:
                return False
            low = txt.lower()
            if low.startswith("publicado") or low.startswith("hace "):
                return False
            if title_text and txt == title_text:
                return False
            return True

        for sel in specific_selectors:
            elems = anchor.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                txt = _clean(el.text)
                if _is_company_candidate(txt):
                    return txt

        # Generic fallback: any h3 inside the anchor that passes filters
        for el in anchor.find_elements(By.CSS_SELECTOR, "h3"):
            txt = _clean(el.text)
            if _is_company_candidate(txt):
                return txt

        return ""