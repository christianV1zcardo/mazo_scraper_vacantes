
# orem_scraper_vacantes

Scraper de vacantes laborales para Bumeran, Computrabajo, Indeed y Laborum, con arquitectura modular, ejecución paralela, y salida en CSV.

## ⚡ Características

- **Ejecución paralela**: Los 4 scrapers se ejecutan simultáneamente (~45 segundos en total)
- **Extracción optimizada con JavaScript**: Máxima velocidad de extracción
- **Deduplicación automática**: Elimina duplicados entre todas las fuentes
- **Filtrado inteligente**: Excluye automáticamente puestos no deseados (ventas, call center, etc.)
- **CSV limpio**: 4 columnas: Fuente, Empresa, Titulo, Url

## Requisitos

- Python 3.10+
- Firefox y geckodriver en PATH (para Selenium)
- Dependencias Python: selenium, pandas

macOS (Homebrew):

```bash
brew install --cask firefox
brew install geckodriver
```

## Instalación

Con pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Variables útiles:

- `SCRAPER_HEADLESS=0` fuerza la ejecución con ventana (headless está activo por defecto). Cualquier valor distinto de `0` o `false` mantiene el modo headless.

## Uso

Modo interactivo:

```bash
python3 main.py
```

El asistente pregunta por la búsqueda, filtro de días y plataformas (Bumeran, Computrabajo, Indeed, Laborum o `all`).

Modo por argumentos (ejemplos):

```bash
python3 main.py "Analista de datos" --dias 1
python3 main.py "Analista" --dias 2 --initial-wait 2 --page-wait 1
python3 main.py "Desarrollador" --source indeed
python3 main.py "Fullstack" --source bumeran --source computrabajo
python3 main.py "Data" --source laborum --log-level debug
python3 main.py "Data" --log-level debug --page-wait 0.5
```

- `--source` puede repetirse para elegir plataformas específicas o usar `--source all` para ejecutar todas (valor por defecto).
- `--no-headless` desactiva el modo headless para depuración local; `--headless` lo fuerza explícitamente (equivalente al valor por defecto).
- `--log-level` controla la verbosidad (`debug`, `info`, `warning`, `error`, `critical`). Con `debug` verás deduplicación y tiempos por scraper.

### Salida de archivos

Los archivos se guardan en `output/` con los siguientes formatos de nombre:

- **Resultados principales**: `DD_MM_<query>.csv`
  - Ej: `29_01_analista.csv`, `29_01_practicante.csv`
  - Archivo CSV con los resultados deduplicados del puesto buscado

- **Top companies**: `top_<query>_<YYYY-MM-DD>.csv`
  - Ej: `top_analista_2026-01-29.csv`
  - Contiene solo las empresas de la lista de "whitelist" (empresas prioritarias)

Los CSV incluyen las columnas `Fuente`, `Empresa`, `Titulo` y `Url` (en ese orden, con primera letra en mayúscula). Cuando la empresa no se puede inferir se deja vacío, pero se mantiene el encabezado fijo para facilitar el post-procesamiento.

### Rendimiento

| Fuente | Tiempo aproximado | Notas |
|--------|-------------------|-------|
| Bumeran | ~8s | Extracción JS, 2-3 páginas |
| Computrabajo | ~35s | Extracción JS, ~33 páginas |
| Indeed | ~10s | Extracción JS, 1-2 páginas |
| Laborum | ~40s | Scroll infinito, ~70 scrolls |
| **Total (paralelo)** | **~45s** | Todos ejecutándose simultáneamente |

### Filtrado automático de puestos

El scraper **elimina automáticamente** los puestos que coinciden con palabras clave o patrones específicos. El filtrado es basado en coincidencias de substrings (case-insensitive), lo que captura variaciones como "Asesor de Fidelización ATC", "Asesor Scotiabank", etc.

**Palabras clave excluidas:**

- **Asesor** (catch-all): Cualquier puesto con "asesor" es excluido, ya que en Computrabajo corresponde a roles de ventas/customer service
- **Centro de llamadas**: "call center", "contact center", "telemarketing", "telefónico"
- **Roles de ventas**: "consultor de ventas", "consultor comercial", "vendedor", "ejecutivo de ventas", "ejecutivo de cobranza", "ejecutivo comercial", "gestor de ventas", "promotor"
- **Atención al cliente**: "atención al cliente", "customer service", "servicio al cliente"
- **Roles de cobranza**: "cobrador", "gestor de cobranza", "cobrador de cartera"
- **Servicios financieros**: "escuela de" (programas de formación para vendedores)
- **Roles manuales**: "mozo", "almacén", "operario", "peón", "repartidor", "conductor", "mensajero", "limpieza"
- **Otros**: "agente de seguros", "promotor inmobiliario"

Esto se aplica automáticamente en todas las búsquedas. Para ver la lista completa o modificarla, edita `EXCLUDED_JOB_KEYWORDS` en [src/utils.py](src/utils.py).

### Logging y tiempos de espera

- Cada scraper reporta su duración y número de ofertas; al final se anota el total combinado tras la deduplicación.
- El ruido de Selenium se reduce automáticamente al nivel `WARNING` o al nivel de logging que selecciones, lo que ocurra primero.
- Puedes ajustar `--initial-wait` y `--page-wait` si detectas páginas lentas. Indeed aplica internamente esperas reducidas para mantener la paginación ágil.

## Estructura del proyecto

```
src/
├── core/
│   ├── base.py      # Clase base con paginación y gestión de driver
│   └── browser.py   # Factoría de WebDriver con timeouts optimizados
├── bumeran.py       # Scraper de Bumeran (extracción JS)
├── computrabajo.py  # Scraper de Computrabajo (extracción JS)
├── indeed.py        # Scraper de Indeed (extracción JS)
├── laborum.py       # Scraper de Laborum (scroll infinito + JS)
├── pipeline.py      # Orquestación paralela con ThreadPoolExecutor
└── utils.py         # Guardado CSV, filtrado y deduplicación

tests/
├── fixtures/        # HTML de ejemplo para tests
└── test_*.py        # 62 tests unitarios

main.py              # CLI principal
```

### Arquitectura

- **BaseScraper**: Clase base que maneja paginación, reintentos y cierre de driver
- **Extracción JS**: Todos los scrapers usan `driver.execute_script()` para extraer datos en una sola llamada, evitando múltiples `find_elements`
- **Pipeline paralelo**: `ThreadPoolExecutor` ejecuta los 4 scrapers simultáneamente
- **Deduplicación global**: Las URLs se normalizan y deduplicación entre todas las fuentes

## Pruebas

El proyecto incluye 62 pruebas unitarias con `unittest`. Durante las pruebas se stubbea Selenium para no requerir el navegador real.

Ejecuta las pruebas:

```bash
poetry run python -m pytest tests/ -v
# o con unittest
python3 -m unittest discover tests
```

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md) para el historial completo de cambios.

## Notas

- El modo headless viene activado por defecto; usa `--no-headless` o `SCRAPER_HEADLESS=0` cuando necesites abrir la ventana del navegador.
- Ejecuta con `--log-level debug` para ver mensajes adicionales de deduplicación, esperas y liberación de recursos.
- Si necesitas bloquear versiones exactas, genera un lock con tu herramienta preferida (Poetry o pip-tools). Este repo incluye `requirements.txt` para instalaciones simples con pip.
