"""Laborum Perú scraper implementation."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from selenium.webdriver.common.by import By

from .core.base import BaseScraper, BlockDetected

JobData = Dict[str, Any]
logger = logging.getLogger(__name__)

# Patrones para parsear texto de fecha relativa
_DIAS_REGEX = re.compile(r"hace\s+(\d+)\s*d[ií]as?", re.IGNORECASE)
_HORAS_REGEX = re.compile(r"hace\s+(\d+)\s*horas?", re.IGNORECASE)
_MINUTOS_REGEX = re.compile(r"hace\s+(\d+)\s*minutos?", re.IGNORECASE)

# Meses en inglés para parsear formato "13 Jan", "8 Feb"
_MESES_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_FECHA_EN_REGEX = re.compile(r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.IGNORECASE)


def _parse_dias_desde_fecha_en(texto: str) -> Optional[int]:
    """Convierte fecha en formato inglés '13 Jan' a días desde hoy."""
    match = _FECHA_EN_REGEX.search(texto.lower())
    if not match:
        return None
    
    dia = int(match.group(1))
    mes = _MESES_EN.get(match.group(2).lower())
    if not mes:
        return None
    
    hoy = datetime.now()
    # Asumir el año actual, pero si la fecha es futura, usar año anterior
    anio = hoy.year
    try:
        fecha_pub = datetime(anio, mes, dia)
        if fecha_pub > hoy:
            fecha_pub = datetime(anio - 1, mes, dia)
        dias = (hoy - fecha_pub).days
        return max(0, dias)
    except ValueError:
        return None


def _parse_dias_desde_texto(texto: str) -> Optional[int]:
    """Convierte texto de fecha relativa a número de días.
    
    Ejemplos:
        - "Hace 2 horas" -> 0 (hoy)
        - "Hace 1 día" -> 1
        - "Hace 3 días" -> 3
        - "Esta semana" -> 3 (aproximado)
        - "Semana pasada" -> 10 (fuera de rango reciente)
        - "Hace 1 mes" -> 30
    """
    if not texto:
        return None
    
    texto_lower = texto.lower().strip()
    
    # Hoy / Recién publicado
    if any(x in texto_lower for x in ("hoy", "recién", "recien", "just")):
        return 0
    
    # Hace X minutos -> hoy
    if _MINUTOS_REGEX.search(texto_lower):
        return 0
    
    # Hace X horas -> hoy
    if _HORAS_REGEX.search(texto_lower):
        return 0
    
    # Hace X días
    match = _DIAS_REGEX.search(texto_lower)
    if match:
        return int(match.group(1))
    
    # Esta semana -> aprox 3-4 días
    if "esta semana" in texto_lower:
        return 4
    
    # Semana pasada -> más de 7 días
    if "semana pasada" in texto_lower:
        return 10
    
    # Hace 1 mes, hace X meses
    if "mes" in texto_lower:
        return 30
    
    # Ayer
    if "ayer" in texto_lower:
        return 1
    
    return None


class LaborumScraper(BaseScraper):
    """Scraper de ofertas laborales para Laborum Perú.
    
    Laborum usa scroll infinito (no paginación tradicional). El filtrado por
    fecha se hace post-extracción basándose en el texto relativo de fecha.
    """

    SITE_ROOT = "https://www.laborum.pe"
    MAX_SCROLLS = 100  # Máximo de scrolls para cargar todos los resultados
    SCROLL_PAUSE = 0.3  # Optimizado para velocidad

    def __init__(self, driver=None, headless: Optional[bool] = True) -> None:
        super().__init__(driver=driver, headless=headless)
        self._last_job_count = 0
        self._dias_filtro: int = 0  # Días máximos de antigüedad

    def abrir_pagina_empleos(self, dias: int = 0) -> None:
        """Abre la página principal de Laborum.
        
        Args:
            dias: Número de días máximos de antigüedad para filtrar.
                  Se aplica post-extracción basándose en el texto de fecha.
        """
        self._dias_filtro = dias
        self.driver.get(self.SITE_ROOT)

    def buscar_vacante(self, palabra_clave: str = "") -> None:
        """Realiza una búsqueda navegando directamente a la URL de búsqueda."""
        if not palabra_clave:
            return
        
        try:
            # Navegar directamente a la URL de búsqueda
            search_url = f"{self.SITE_ROOT}/search-jobs?q={quote(palabra_clave)}"
            self.driver.get(search_url)
            
            # Esperar a que cargue la página de resultados
            time.sleep(2)
            logger.debug("[laborum] Búsqueda directa: %s -> %s", palabra_clave, self.driver.current_url)
            
        except Exception as exc:
            logger.warning("[laborum] Error en búsqueda: %s", exc)

    def extraer_puestos(self, timeout: int = 10) -> List[JobData]:
        """Extrae los puestos visibles en la página actual."""
        try:
            if self.detecta_bloqueo():
                raise BlockDetected("Captcha o bloqueo detectado en Laborum")
            return self._extract_job_cards()
        except BlockDetected:
            raise
        except Exception as exc:
            logger.debug("[laborum] Error extrayendo puestos: %s", exc)
            return []

    def extraer_todos_los_puestos(
        self, timeout: int = 10, page_wait: float = 1.0
    ) -> List[JobData]:
        """Extrae todos los puestos usando scroll infinito con filtrado por fecha."""
        all_jobs: List[JobData] = []
        seen_urls: set[str] = set()
        scroll_count = 0
        no_new_jobs_count = 0
        
        # Si hay filtro de días, se aplica al final
        dias_max = self._dias_filtro if self._dias_filtro > 0 else 999
        
        logger.info(
            "[laborum] Iniciando extracción (max_scrolls=%d, filtro_dias=%d)",
            self.MAX_SCROLLS, dias_max if dias_max < 999 else 0
        )
        
        while scroll_count < self.MAX_SCROLLS:
            # Extraer puestos visibles
            current_jobs = self._extract_job_cards()
            
            # Agregar solo los nuevos (sin filtrar por fecha aún)
            new_count = 0
            for job in current_jobs:
                url = job.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(job)
                    new_count += 1
            
            logger.debug(
                "[laborum] Scroll %d: encontrados %d, nuevos %d, total %d",
                scroll_count + 1, len(current_jobs), new_count, len(all_jobs)
            )
            
            # Si no hay nuevos puestos, puede que hayamos llegado al final
            if new_count == 0:
                no_new_jobs_count += 1
                if no_new_jobs_count >= 5:
                    logger.info("[laborum] Sin nuevos resultados tras %d scrolls", no_new_jobs_count)
                    break
            else:
                no_new_jobs_count = 0
            
            # Hacer scroll hacia abajo
            self._scroll_down()
            scroll_count += 1
            time.sleep(self.SCROLL_PAUSE)
            
            # Log de progreso cada 10 scrolls
            if scroll_count % 10 == 0:
                logger.info("[laborum] Progreso: scroll %d, total %d puestos", scroll_count, len(all_jobs))
        
        logger.info("[laborum] Extracción completada: %d puestos totales", len(all_jobs))
        
        # Aplicar filtro de fecha al final
        if dias_max < 999:
            filtered_jobs = []
            filtrados_count = 0
            sin_fecha_count = 0
            for job in all_jobs:
                dias_pub = job.get("dias_publicado")
                if dias_pub is None:
                    # Si hay filtro activo, EXCLUIR puestos sin fecha detectada
                    sin_fecha_count += 1
                    continue
                if dias_pub <= dias_max:
                    filtered_jobs.append(job)
                else:
                    filtrados_count += 1
            
            logger.info(
                "[laborum] Filtro de fecha (≤%d días): %d válidos, %d muy antiguos, %d sin fecha",
                dias_max, len(filtered_jobs), filtrados_count, sin_fecha_count
            )
            return filtered_jobs
        
        return all_jobs

    def _scroll_down(self) -> None:
        """Hace scroll hacia abajo en el contenedor de resultados."""
        try:
            # Laborum usa un UL con scroll interno, no el body
            self.driver.execute_script("""
                // Buscar el contenedor de lista de trabajos (UL con overflow)
                const listContainer = document.querySelector('ul.MuiList-root.isJob') 
                    || document.querySelector('ul.MuiList-root[class*="jss"]')
                    || document.querySelector('ul.MuiList-root');
                
                if (listContainer) {
                    // Scroll dentro del contenedor
                    listContainer.scrollTop = listContainer.scrollHeight;
                } else {
                    // Fallback: scroll del body
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
        except Exception as exc:
            logger.debug("[laborum] Error en scroll: %s", exc)

    def _extract_job_cards(self) -> List[JobData]:
        """Extrae información de los cards de empleo visibles usando JavaScript.
        
        Optimización: extrae todos los datos con un solo execute_script
        en lugar de múltiples llamadas find_elements por cada card.
        """
        try:
            # Extraer todos los datos con JavaScript (mucho más rápido)
            raw_jobs = self.driver.execute_script('''
                const cards = document.querySelectorAll('li.MuiListItem-root a[href*="/job/"]');
                if (!cards.length) return [];
                
                const fechaEnRegex = /^(\\d{1,2})\\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)$/i;
                const fechaEsKeywords = ['hace', 'hoy', 'ayer', 'semana', 'mes'];
                
                return Array.from(cards).map(card => {
                    const href = card.getAttribute('href') || '';
                    if (!href.includes('/job/')) return null;
                    
                    // Título
                    const h6 = card.querySelector('h6') || card.querySelector('h5');
                    const titulo = h6 ? (h6.textContent || '').trim() : '';
                    
                    // Empresa
                    const p = card.querySelector('p');
                    const empresa = p ? (p.textContent || '').trim() : '';
                    
                    // Fecha - buscar en spans
                    let fechaTexto = '';
                    const spans = card.querySelectorAll('span');
                    for (const span of spans) {
                        const txt = (span.textContent || '').trim();
                        if (!txt) continue;
                        const lower = txt.toLowerCase();
                        // Formato español
                        if (fechaEsKeywords.some(k => lower.includes(k))) {
                            fechaTexto = txt;
                            break;
                        }
                        // Formato inglés "13 Jan"
                        if (fechaEnRegex.test(txt)) {
                            fechaTexto = txt;
                            break;
                        }
                    }
                    
                    return { href, titulo, empresa, fechaTexto };
                }).filter(j => j && j.titulo);
            ''')
            
            if not raw_jobs:
                return []
            
            # Procesar resultados en Python (parsear fechas)
            payloads: List[JobData] = []
            for job in raw_jobs:
                href = job.get("href", "")
                url = href if href.startswith("http") else f"{self.SITE_ROOT}{href}"
                fecha_texto = job.get("fechaTexto", "")
                
                # Parsear días
                dias_publicado = None
                if fecha_texto:
                    dias_publicado = _parse_dias_desde_texto(fecha_texto)
                    if dias_publicado is None:
                        dias_publicado = _parse_dias_desde_fecha_en(fecha_texto)
                
                result: JobData = {
                    "titulo": job.get("titulo", ""),
                    "empresa": job.get("empresa", ""),
                    "url": url,
                }
                if fecha_texto:
                    result["fecha_texto"] = fecha_texto
                if dias_publicado is not None:
                    result["dias_publicado"] = dias_publicado
                
                payloads.append(result)
            
            logger.debug("[laborum] Cards extraídos (JS): %d", len(payloads))
            return payloads
            
        except Exception as exc:
            logger.debug("[laborum] Error en extracción JS: %s", exc)
            return []

    def _parse_job_card(self, card) -> Optional[JobData]:
        """Parsea un card de empleo y extrae título, empresa, URL y fecha."""
        try:
            # URL del empleo
            href = card.get_attribute("href") or ""
            if not href or "/job/" not in href:
                return None
            
            url = href if href.startswith("http") else f"{self.SITE_ROOT}{href}"
            
            # Título (h6 dentro del card) - usar textContent como fallback
            titulo = ""
            title_selectors = ["h6", "h5"]
            for sel in title_selectors:
                elems = card.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    # Intentar .text primero, luego textContent
                    titulo = elems[0].text.strip()
                    if not titulo:
                        titulo = (elems[0].get_attribute("textContent") or "").strip()
                    if titulo:
                        break
            
            # Si no hay h6/h5, intentar extraer del título del enlace
            if not titulo:
                titulo = (card.get_attribute("title") or "").strip()
            
            # Empresa (p después del título)
            empresa = ""
            company_selectors = [
                "p[class*='body1']",
                "p",
            ]
            for sel in company_selectors:
                elems = card.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    empresa = elems[0].text.strip()
                    if not empresa:
                        empresa = (elems[0].get_attribute("textContent") or "").strip()
                    if empresa and empresa != titulo:
                        break
            
            # Fecha de publicación
            # Formato 1: texto relativo "Hace X días", "Hoy", etc.
            # Formato 2: fecha directa "13 Jan", "8 Feb" (para avisos destacados)
            fecha_texto = ""
            dias_publicado: Optional[int] = None
            
            # Primero intentar formato español (más común)
            fecha_selectors = [
                "span[color='textSecondary']",
                "span.jss92",
            ]
            for sel in fecha_selectors:
                elems = card.find_elements(By.CSS_SELECTOR, sel)
                for elem in elems:
                    txt = (elem.get_attribute("textContent") or "").strip()
                    if txt and any(x in txt.lower() for x in ("hace", "hoy", "ayer", "semana", "mes")):
                        fecha_texto = txt
                        dias_publicado = _parse_dias_desde_texto(txt)
                        break
                if fecha_texto:
                    break
            
            # Si no encontró formato español, buscar formato inglés "13 Jan"
            if not fecha_texto:
                all_spans = card.find_elements(By.CSS_SELECTOR, "span")
                for span in all_spans:
                    txt = (span.get_attribute("textContent") or "").strip()
                    if txt and _FECHA_EN_REGEX.search(txt.lower()):
                        fecha_texto = txt
                        dias_publicado = _parse_dias_desde_fecha_en(txt)
                        break
            
            if not titulo:
                return None
            
            result: JobData = {
                "titulo": titulo,
                "empresa": empresa,
                "url": url,
            }
            
            if fecha_texto:
                result["fecha_texto"] = fecha_texto
            if dias_publicado is not None:
                result["dias_publicado"] = dias_publicado
            
            return result
            
        except Exception:
            return None

    def detecta_bloqueo(self) -> bool:
        """Detecta si hay un captcha o bloqueo en la página."""
        try:
            source = (getattr(self.driver, "page_source", "") or "").lower()
            current_url = getattr(self.driver, "current_url", "") or ""
        except Exception:
            return False
        
        # Indicadores de bloqueo
        indicators = (
            "captcha",
            "recaptcha",
            "challenge-running",
            "cf_chl_",
            "blocked",
            "access denied",
        )
        
        return any(marker in source for marker in indicators)

    def navegar_a_pagina(self, numero: int) -> bool:
        """No usado - Laborum usa scroll infinito."""
        return False
