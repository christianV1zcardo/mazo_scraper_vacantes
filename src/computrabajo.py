"""Computrabajo scraper implementation."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from selenium.webdriver.common.by import By

from .core.base import BaseScraper, BlockDetected

JobData = Dict[str, Any]


class ComputrabajoScraper(BaseScraper):
    BASE_URL = "https://www.computrabajo.com.pe/"
    SITE_ROOT = "https://pe.computrabajo.com"

    def __init__(self, driver=None, headless: Optional[bool] = True) -> None:
        super().__init__(driver=driver, headless=headless)
        self.pubdate = 0
        self.last_keyword = ""
        self._last_page_url: str = ""

    def abrir_pagina_empleos(self, hoy: bool = False, dias: int = 0) -> None:
        if dias == 1:
            self.pubdate = 1
        elif dias == 3:
            self.pubdate = 3
        else:
            self.pubdate = 0
        self.driver.get(self.BASE_URL)
        self._last_page_url = getattr(self.driver, "current_url", self.BASE_URL)

    def buscar_vacante(self, palabra_clave: str = "") -> None:
        keyword = palabra_clave.replace(" ", "-").lower()
        url = f"{self.SITE_ROOT}/trabajo-de-{keyword}"
        if self.pubdate:
            url = f"{url}?pubdate={self.pubdate}"
        try:
            self.driver.get(url)
            self.last_keyword = palabra_clave
            self._last_page_url = getattr(self.driver, "current_url", url)
        except Exception:
            pass

    def extraer_puestos(self, timeout: int = 10) -> List[JobData]:
        """Extrae puestos usando JavaScript para máxima velocidad."""
        try:
            if self.detecta_bloqueo():
                raise BlockDetected("Captcha o bloqueo detectado en Computrabajo")
            
            # Extraer todos los datos con JavaScript (mucho más rápido)
            raw_jobs = self.driver.execute_script('''
                const articles = document.querySelectorAll('article[data-id]');
                if (!articles.length) return [];
                
                return Array.from(articles).map(article => {
                    // El título está en h2 > a.js-o-link
                    const titleLink = article.querySelector('h2 a.js-o-link');
                    if (!titleLink) return null;
                    
                    const href = titleLink.getAttribute('href') || '';
                    const titulo = (titleLink.textContent || '').trim();
                    
                    // La URL debe contener /ofertas-de-trabajo/ para ser válida
                    if (!href.includes('/ofertas-de-trabajo/')) return null;
                    
                    // Empresa: buscar en p.dFlex o a.fc_base.t_ellipsis (no el del título)
                    let empresa = '';
                    
                    // Primero buscar el link de la empresa
                    const companyLink = article.querySelector('p.dFlex a.fc_base.t_ellipsis');
                    if (companyLink) {
                        empresa = (companyLink.textContent || '').trim();
                    }
                    
                    // Si no hay link, buscar en el párrafo dFlex
                    if (!empresa) {
                        const companyP = article.querySelector('p.dFlex.vm_fx.fs16.fc_base');
                        if (companyP) {
                            // Obtener solo el texto directo, no de spans internos
                            const txt = (companyP.textContent || '').trim();
                            // Limpiar rating y texto extra
                            const cleanTxt = txt.replace(/[\\d,]+\\s*★?/g, '').trim();
                            if (cleanTxt && !cleanTxt.includes('Importante empresa')) {
                                empresa = cleanTxt.split('\\n')[0].trim();
                            }
                        }
                    }
                    
                    return { href, titulo, empresa };
                }).filter(j => j && j.titulo && j.href);
            ''')
            
            if not raw_jobs:
                return []
            
            payloads: List[JobData] = []
            seen = set()
            for job in raw_jobs:
                href = job.get("href", "")
                # Construir URL completa
                if href.startswith("/"):
                    detail_url = f"{self.SITE_ROOT}{href.split('#')[0]}"
                else:
                    detail_url = href.split('#')[0]
                
                if not detail_url or detail_url in seen:
                    continue
                seen.add(detail_url)
                payloads.append({
                    "titulo": job.get("titulo", ""),
                    "url": detail_url,
                    "empresa": job.get("empresa", ""),
                })
            
            return payloads
            
        except BlockDetected:
            raise
        except Exception:
            return []

    def extraer_todos_los_puestos(self, timeout: int = 10, page_wait: float = 1.0) -> List[JobData]:
        # Usar page_wait reducido para mayor velocidad
        effective_wait = min(page_wait, 0.5)
        return self.gather_paginated(
            extractor=lambda: self.extraer_puestos(timeout=timeout),
            navigator=self.navegar_a_pagina,
            page_wait=effective_wait,
            source_label="computrabajo",
        )

    def navegar_a_pagina(self, numero: int) -> bool:
        try:
            current = self.driver.current_url or ""
            if "p=" in current:
                target = re.sub(r"p=\d+", f"p={numero}", current)
            else:
                separator = "&" if "?" in current else "?"
                target = f"{current}{separator}p={numero}"
            if self._last_page_url and target == self._last_page_url:
                return False
            self.driver.get(target)
            # Esperar mínimo para que cargue la página
            time.sleep(0.15)
            new_url = getattr(self.driver, "current_url", target)
            # Si la URL no cambia, asumimos que no hay más páginas
            if self._last_page_url and new_url == self._last_page_url:
                return False
            self._last_page_url = new_url
            return True
        except Exception:
            return False

    def _build_base_search_url(self) -> str:
        keyword = self.last_keyword.replace(" ", "-").lower() if self.last_keyword else ""
        url = f"{self.SITE_ROOT}/trabajo-de-{keyword}"
        if self.pubdate:
            url = f"{url}?pubdate={self.pubdate}"
        return url

    def _build_detail_url(self, href: str, base_search: str) -> Optional[str]:
        normalized = href or ""
        fragment = normalized.split("#", 1)[1] if "#" in normalized else ""
        base_candidate = normalized.split("#", 1)[0]
        if base_candidate.startswith("/"):
            base_candidate = f"{self.SITE_ROOT}{base_candidate}"

        if fragment and re.match(r"^[A-Za-z0-9]{3,}$", fragment):
            candidate_base = base_candidate or base_search
            if self.pubdate and "/trabajo-de-" in candidate_base and "pubdate=" not in candidate_base:
                separator = "&" if "?" in candidate_base else "?"
                candidate_base = f"{candidate_base}{separator}pubdate={self.pubdate}"
            return f"{candidate_base}#{fragment}"

        tokens = re.findall(r"([A-Za-z0-9]{8,})", normalized)
        token = None
        for candidate in tokens:
            if re.search(r"\d", candidate):
                token = candidate
                break
        if not token and tokens:
            token = max(tokens, key=len)
        if token:
            return f"{base_search}#{token}"

        # Skip anchors that are not job detail links
        if "/trabajo-de-" not in normalized:
            return None
        if normalized.startswith("/"):
            return f"{self.SITE_ROOT}{normalized}"
        return normalized

    def _extract_company(self, anchor, title_text: str) -> str:
        # In Computrabajo, the company name is usually within the same article card.
        try:
            card = anchor.find_element(By.XPATH, "ancestor::article[1]")
        except Exception:
            card = None

        selectors = [
            "span.fs16.fc_base.mt5.fc_base.fc_base",
            "span.fs13.fc_aux.tx_ellipsis",
            "a.fc_base",
            "span[class*='fc_aux']",
        ]

        search_roots = [anchor]
        if card:
            search_roots.insert(0, card)

        for root in search_roots:
            for sel in selectors:
                elems = root.find_elements(By.CSS_SELECTOR, sel)
                for e in elems:
                    txt = e.text.strip()
                    if not txt:
                        continue
                    # Evita confundir el título con la empresa y textos relativos al tiempo
                    if txt == title_text:
                        continue
                    if txt.lower().startswith("hace "):
                        continue
                    return txt.split("\n")[0]
        return ""

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