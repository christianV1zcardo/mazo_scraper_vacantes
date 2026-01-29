"""Indeed scraper implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin, urlparse, urlunparse, parse_qs

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .core.base import BaseScraper
from .core.browser import create_firefox_driver

JobData = Dict[str, Any]


class IndeedScraper(BaseScraper):
    SITE_ROOT = "https://pe.indeed.com"
    SEARCH_PATH = "/jobs"
    EXPECTED_PAGE_SIZE = 15  # Indeed typically shows 15 cards per page

    def __init__(
        self,
        driver=None,
        headless: Optional[bool] = True,
        use_stealth: bool = True,
    ) -> None:
        # Use Firefox instead of Chrome to avoid ChromeDriver version mismatches
        if driver is None:
            driver = create_firefox_driver(headless=headless)
        super().__init__(driver=driver, headless=headless, use_stealth=False)
        self._search_params: Dict[str, str] = {}
        self._fromage: Optional[int] = None
        self._last_page_url: Optional[str] = None

    def abrir_pagina_empleos(self, dias: int = 0) -> None:
        self._fromage = self._map_dias_to_fromage(dias)
        landing_url = f"{self.SITE_ROOT}?r=pe"
        self.driver.get(landing_url)
        self._last_page_url = getattr(self.driver, "current_url", landing_url)

    def buscar_vacante(self, palabra_clave: str = "") -> None:
        keyword = palabra_clave.strip()
        self._search_params = {
            "q": keyword,
            "l": "",
            "radius": "25",
            "from": "searchOnDesktopSerp",
        }
        if self._fromage is not None:
            self._search_params["fromage"] = str(self._fromage)
        query = urlencode(self._search_params, doseq=True)
        url = f"{self.SITE_ROOT}{self.SEARCH_PATH}?{query}"
        self.driver.get(url)
        self._last_page_url = getattr(self.driver, "current_url", url)

    def extraer_puestos(self, timeout: int = 1) -> List[JobData]:
        # Wait only until at least one job card is present; don't over-wait for full container
        wait = WebDriverWait(self.driver, timeout)
        cards = self._locate_job_cards(wait)
        results: List[JobData] = []
        for card in cards:
            anchor = self._find_anchor(card)
            if not anchor:
                continue
            href = anchor.get_attribute("href") or ""
            if not href:
                continue
            url = href if href.startswith("http") else urljoin(self.SITE_ROOT, href)
            url = self._normalize_job_url(url)
            if not url:
                continue
            title = self._extract_title(anchor, card)
            if not title:
                continue
            company = self._extract_company(card)
            results.append({"titulo": title, "url": url, "empresa": company})
        return results

    def extraer_todos_los_puestos(self, timeout: int = 1, page_wait: float = 0.1) -> List[JobData]:
        return self.gather_paginated(
            extractor=lambda: self.extraer_puestos(timeout=timeout),
            navigator=self.navegar_a_pagina,
            page_wait=page_wait,
            source_label="indeed",
            low_yield_threshold=1,
            low_yield_patience=3,
        )

    def detecta_bloqueo_cloudflare(self) -> bool:
        try:
            source = (getattr(self.driver, "page_source", "") or "").lower()
            current_url = getattr(self.driver, "current_url", "") or ""
        except Exception:
            return False
        indicators = (
            "__cf_chl",
            "cf_chl_",
            "just a moment",
            "attention required",
            "enable javascript and cookies",
            "captcha",
            "are you human",
        )
        if any(marker in source for marker in indicators):
            return True
        return "__cf_chl" in current_url

    def navegar_a_pagina(self, numero: int) -> bool:
        if numero < 1:
            return False
        params = dict(self._search_params)
        params["start"] = str((numero - 1) * 10)
        query = urlencode(params, doseq=True)
        url = f"{self.SITE_ROOT}{self.SEARCH_PATH}?{query}"
        if self._last_page_url and url == self._last_page_url:
            return False
        try:
            self.driver.get(url)
            current_url = getattr(self.driver, "current_url", url)
            if self._last_page_url and current_url == self._last_page_url:
                return False
            self._last_page_url = current_url
            return True
        except Exception:
            return False

    def _locate_job_cards(self, wait: WebDriverWait):
        # Prefer a quick condition: at least 1 card present in either common selector
        selectors = [
            "ul.jobsearch-ResultsList li",
            "div.job_seen_beacon",
            "div.slider_item",
            "div.cardOutline",
            "td.resultContent",
        ]
        try:
            wait.until(
                lambda d: any(d.find_elements(By.CSS_SELECTOR, sel) for sel in selectors)
            )
        except Exception:
            # Fall through and try to read whatever is there
            pass

        # Read with priority: structured list first
        cards = self.driver.find_elements(By.CSS_SELECTOR, "ul.jobsearch-ResultsList li")
        if cards:
            return cards
        fallback_selectors = [
            "div.job_seen_beacon",
            "div.slider_item",
            "div.cardOutline",
            "td.resultContent",
        ]
        for selector in fallback_selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                return cards
        return []

    def _find_anchor(self, card):
        anchors = card.find_elements(
            By.CSS_SELECTOR,
            "a[data-testid='jobTitle'], a.jcs-JobTitle, a[data-jk], a.tapItem, a[id^='job_']",
        )
        return anchors[0] if anchors else None

    def _extract_title(self, anchor, card) -> str:
        for selector in (
            "h2 span[title]",
            "h2 span",
            "span[title]",
        ):
            elements = card.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                text = elements[0].text.strip()
                if text:
                    return text
        text = anchor.text.strip()
        if text:
            return text.split("\n")[0]
        return ""

    def _extract_company(self, card) -> str:
        # Indeed typically shows company name in span.companyName
        for selector in (
            "span.companyName",
            "a.companyName",
            "div.companyName",
            "[data-testid='company-name']",
        ):
            elems = card.find_elements(By.CSS_SELECTOR, selector)
            if elems:
                text = elems[0].text.strip()
                if text:
                    return text.split("\n")[0]
        return ""

    def _map_dias_to_fromage(self, dias: int) -> Optional[int]:
        if dias == 1:
            return 1
        if dias in (2, 3):
            return 3
        return None

    def _normalize_job_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        for key in ("jk", "vjk"):
            values = query_params.get(key)
            if values:
                return f"{self.SITE_ROOT}/viewjob?jk={values[0]}"
        if parsed.path.startswith("/pagead/clk"):
            cleaned = parsed._replace(fragment="")
            return urlunparse(cleaned)
        cleaned = parsed._replace(query="", fragment="")
        return urlunparse(cleaned)
