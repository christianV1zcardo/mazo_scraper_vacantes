"""Bumeran scraper implementation."""

from __future__ import annotations

import time
import urllib.parse as urlparse
from typing import Any, Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

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
        """Extrae puestos usando JavaScript para máxima velocidad."""
        try:
            if self.detecta_bloqueo():
                raise BlockDetected("Captcha o bloqueo detectado en Bumeran")
            return self._extract_with_js()
        except BlockDetected:
            raise
        except Exception:
            return []

    def _extract_with_js(self) -> List[JobData]:
        """Extrae todos los datos con una sola llamada JavaScript."""
        raw_jobs = self.driver.execute_script('''
            const anchors = document.querySelectorAll('a[href*="/empleos/"]');
            if (!anchors.length) return [];
            
            const excludeTokens = ['busqueda-', 'publicacion-menor', 'relevantes=', 'recientes='];
            
            return Array.from(anchors).map(anchor => {
                const href = anchor.getAttribute('href') || '';
                if (!href.includes('/empleos/')) return null;
                if (excludeTokens.some(t => href.includes(t))) return null;
                
                // Título: buscar h1-h5
                let titulo = '';
                for (const tag of ['h1', 'h2', 'h3', 'h4', 'h5']) {
                    const el = anchor.querySelector(tag);
                    if (el) {
                        const txt = (el.textContent || '').trim().split('\\n')[0];
                        if (txt && !txt.toLowerCase().startsWith('publicado')) {
                            titulo = txt;
                            break;
                        }
                    }
                }
                if (!titulo) {
                    titulo = (anchor.textContent || '').trim().split('\\n')[0];
                }
                if (!titulo) return null;
                
                // Empresa: buscar h3 que no sea título ni "Publicado..."
                let empresa = '';
                const h3s = anchor.querySelectorAll('h3');
                for (const h3 of h3s) {
                    const txt = (h3.textContent || '').trim().split('\\n')[0];
                    if (!txt) continue;
                    const lower = txt.toLowerCase();
                    if (lower.startsWith('publicado') || lower.startsWith('hace ')) continue;
                    if (txt === titulo) continue;
                    empresa = txt;
                    break;
                }
                
                return { href, titulo, empresa };
            }).filter(j => j && j.titulo);
        ''')
        
        if not raw_jobs:
            return []
        
        payloads: List[JobData] = []
        seen = set()
        base_url = "https://www.bumeran.com.pe"
        for job in raw_jobs:
            href = job.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            # Convertir URLs relativas a absolutas
            if href.startswith("/"):
                full_url = f"{base_url}{href}"
            else:
                full_url = href
            payloads.append({
                "titulo": job.get("titulo", ""),
                "url": full_url,
                "empresa": job.get("empresa", ""),
            })
        
        return payloads

    def extraer_todos_los_puestos(self, timeout: int = 10, page_wait: float = 1.0) -> List[JobData]:
        # Reducir page_wait para mayor velocidad
        effective_wait = min(page_wait, 0.5)
        return self.gather_paginated(
            extractor=lambda: self.extraer_puestos(timeout=timeout),
            navigator=self.navegar_a_pagina,
            page_wait=effective_wait,
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
            time.sleep(0.3)  # Reducido para mayor velocidad
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