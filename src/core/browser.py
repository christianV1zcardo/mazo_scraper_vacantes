"""Browser creation utilities."""

from __future__ import annotations

import importlib
import logging
import os
import random
import sys
from typing import Optional

from selenium import webdriver
from selenium.webdriver.firefox.options import Options

_SUPPRESSED_LOGGERS = (
    "undetected_chromedriver",
    "undetected_chromedriver.patcher",
    "uc",
)
for _logger_name in _SUPPRESSED_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def _resolve_headless_flag(headless: Optional[bool]) -> bool:
    resolved = headless
    if resolved is None:
        env_value = os.getenv("SCRAPER_HEADLESS")
        if env_value is not None:
            resolved = env_value not in {"0", "false", "False"}
    if resolved is None:
        resolved = True
    return resolved


def create_firefox_driver(headless: Optional[bool] = None) -> webdriver.Firefox:
    """Create a Firefox WebDriver instance."""
    options = Options()
    if _resolve_headless_flag(headless):
        options.add_argument("-headless")
    return webdriver.Firefox(options=options)


def create_stealth_driver(headless: Optional[bool] = None) -> webdriver.Chrome:
    """Create a Chrome driver using undetected-chromedriver."""
    _ensure_distutils_available()
    try:
        import undetected_chromedriver as uc
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "undetected-chromedriver no está instalado en el entorno actual"
        ) from exc

    options = uc.ChromeOptions()
    resolved_headless = _resolve_headless_flag(headless)
    if resolved_headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    _maybe_randomize_fingerprint(options)

    # use_subprocess evita zombie processes con geckodriver/Chrome en macOS
    return uc.Chrome(options=options, use_subprocess=True)


def _ensure_distutils_available() -> None:
    """Ensure ``distutils`` imports resolve on Python 3.12+ for legacy deps."""
    if "distutils" in sys.modules:
        return
    try:  # pragma: no cover - only hits on 3.11+
        import distutils  # type: ignore  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    try:
        modules = ["", ".version", ".log", ".dir_util"]
        for suffix in modules:
            module = importlib.import_module(f"setuptools._distutils{suffix}")
            sys.modules[f"distutils{suffix}"] = module
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "setuptools._distutils no está disponible; instala setuptools>=68 "
            "o añade un backport de 'distutils' compatible con Python 3.12+."
        ) from exc


def _maybe_randomize_fingerprint(options) -> None:
    if not _should_randomize_fp():
        return
    user_agent = _random_user_agent()
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    width, height = _random_window_size()
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument(f"--window-position={random.randint(0, 100)},{random.randint(0, 100)}")
    language = random.choice((
        "es-PE,es;q=0.9,en-US;q=0.7",
        "es-ES,es;q=0.9,en;q=0.8",
        "en-US,en;q=0.9,es;q=0.6",
    ))
    # Chrome espera sólo el idioma principal en --lang
    options.add_argument(f"--lang={language.split(',')[0]}")
    prefs = {"intl.accept_languages": language}
    try:
        options.add_experimental_option("prefs", prefs)
    except Exception:  # pragma: no cover - falla silenciosa si ChromeOptions cambia
        pass


def _should_randomize_fp() -> bool:
    env_value = os.getenv("SCRAPER_RANDOMIZE_FP")
    if env_value is None:
        return True
    return env_value not in {"0", "false", "False"}


def _random_user_agent() -> str:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.224 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6110.0 Safari/537.36",
    ]
    return random.choice(user_agents)


def _random_window_size() -> tuple[int, int]:
    width = random.randint(1280, 1920)
    height = random.randint(720, 1200)
    return width, height
