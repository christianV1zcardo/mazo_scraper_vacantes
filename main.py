import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.pipeline import DEFAULT_SOURCES, run_combined
from src.utils import copy_top_from_csv


@dataclass
class RunParameters:
    busqueda: str
    dias: int
    initial_wait: float
    page_wait: float
    sources: List[str]
    log_level: int = logging.INFO
    headless: Optional[bool] = None


def prompt_interactive() -> Optional[RunParameters]:
    busqueda = input("Nombre del puesto a buscar (ej. Analista): ").strip()
    if not busqueda:
        print("No se ingresó un término de búsqueda. Abortando.")
        return None
    while True:
        dias = input("Filtrar por días (0=Todos,1=Desde ayer,2=últimos 2 días,3=últimos 3 días) [0]: ").strip()
        dias = dias or "0"
        if dias in {"0", "1", "2", "3"}:
            raw_sources = input(
                "Plataformas a ejecutar (bumeran, computrabajo, indeed, laborum, all) [all]: "
            ).strip()
            sources = parse_sources_input(raw_sources)
            return RunParameters(
                busqueda=busqueda,
                dias=int(dias),
                initial_wait=2.0,
                page_wait=1.0,
                sources=sources,
                log_level=logging.INFO,
                headless=None,
            )
        print("Opción inválida. Ingresa 0, 1, 2 o 3.")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta los scrapers de Bumeran, Computrabajo, Indeed y Laborum y guarda resultados"
    )
    parser.add_argument(
        "busqueda",
        nargs="?",
        help='Palabra clave para buscar (ej: "Analista"). Si se omite, se activa el modo interactivo.',
    )
    parser.add_argument(
        "--dias",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="Filtrar por días de publicación",
    )
    parser.add_argument("--hoy", action="store_true", help="Equivale a --dias 1")
    parser.add_argument("--initial-wait", type=float, help="Espera inicial antes de extraer")
    parser.add_argument("--page-wait", type=float, help="Espera entre páginas")
    parser.add_argument("--interactive", action="store_true", help="Forzar modo interactivo")
    parser.add_argument(
        "--source",
        action="append",
        choices=["bumeran", "computrabajo", "indeed", "laborum", "all"],
        help="Selecciona plataformas a ejecutar (usa varias veces para múltiples)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Nivel de logging a utilizar",
    )
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Forzar modo headless (habilitado por defecto)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Deshabilitar headless para depuración local",
    )
    parser.add_argument(
        "--copy-top",
        dest="copy_top_from",
        help="Ruta a un CSV top existente para copiar el resumen al portapapeles y salir",
    )
    parser.set_defaults(headless=None)
    return parser.parse_args()


def resolve_parameters(args: argparse.Namespace) -> Optional[RunParameters]:
    if args.interactive or not args.busqueda:
        return prompt_interactive()
    return RunParameters(
        busqueda=args.busqueda,
        dias=1 if args.hoy else args.dias,
        initial_wait=args.initial_wait if args.initial_wait is not None else 2.0,
        page_wait=args.page_wait if args.page_wait is not None else 1.0,
        sources=normalize_sources(args.source),
        log_level=parse_log_level(args.log_level),
        headless=args.headless,
    )


def normalize_sources(raw_sources: Optional[List[str]]) -> List[str]:
    if not raw_sources:
        return list(DEFAULT_SOURCES)
    expanded: List[str] = []
    for entry in raw_sources:
        value = (entry or "").lower()
        if value == "all":
            expanded.extend(DEFAULT_SOURCES)
        elif value:
            expanded.append(value)
    return _dedupe_preserving_order(expanded) or list(DEFAULT_SOURCES)


def parse_sources_input(raw_input: str) -> List[str]:
    if not raw_input:
        return list(DEFAULT_SOURCES)
    tokens = [token.strip().lower() for token in raw_input.replace(",", " ").split() if token.strip()]
    return normalize_sources(tokens)


def parse_log_level(value: Optional[str]) -> int:
    if not value:
        return logging.INFO
    level = getattr(logging, value.upper(), logging.INFO)
    if isinstance(level, int):
        return level
    return logging.INFO


def configure_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Reduce el ruido de bibliotecas verbosas como Selenium
    logging.getLogger("selenium").setLevel(max(logging.WARNING, level))


def _dedupe_preserving_order(values: List[str]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def main() -> None:
    args = parse_arguments()
    # Modo utilitario: copiar resumen desde un CSV ya generado
    if args.copy_top_from:
        level = parse_log_level(args.log_level)
        configure_logging(level)
        try:
            summary = copy_top_from_csv(args.copy_top_from)
            if summary:
                print("Resumen copiado al portapapeles.\n")
                print(summary)
            else:
                print("No se encontraron registros en el CSV proporcionado.")
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.exception("No se pudo copiar el resumen desde %s", args.copy_top_from)
            sys.exit(1)
        return

    params = resolve_parameters(args)
    if not params:
        return
    configure_logging(params.log_level)
    run_combined(
        busqueda=params.busqueda,
        dias=params.dias,
        initial_wait=params.initial_wait,
        page_wait=params.page_wait,
        sources=params.sources,
        headless=params.headless,
    )


if __name__ == "__main__":
    main()
