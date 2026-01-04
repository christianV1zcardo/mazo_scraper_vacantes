
# orem_scraper_vacantes

Scraper de vacantes laborales para Bumeran, Computrabajo e Indeed, con arquitectura modular, pruebas unitarias y salida en CSV/JSON.

## Requisitos

- Python 3.10+
- Firefox y geckodriver en PATH (para Selenium)
- Google Chrome (Indeed usa un driver stealth basado en Chrome)
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

El asistente pregunta por la búsqueda, filtro de días y plataformas (Bumeran, Computrabajo, Indeed o `all`).

Modo por argumentos (ejemplos):

```bash
python3 main.py "Analista de datos" --dias 1
python3 main.py "Analista" --dias 2 --initial-wait 2 --page-wait 1
python3 main.py "Desarrollador" --source indeed
python3 main.py "Fullstack" --source bumeran --source computrabajo
python3 main.py "Data" --log-level debug --page-wait 0.5
```

- `--source` puede repetirse para elegir plataformas específicas o usar `--source all` para ejecutar todas (valor por defecto).
- `--no-headless` desactiva el modo headless para depuración local; `--headless` lo fuerza explícitamente (equivalente al valor por defecto).
- `--log-level` controla la verbosidad (`debug`, `info`, `warning`, `error`, `critical`). Con `debug` verás deduplicación y tiempos por scraper.

Salida: los archivos se guardan en `output/` con nombre `<fuente>_<query>_<YYYY-MM-DD>.(json|csv)`.

Los CSV incluyen las columnas `fuente`, `empresa`, `titulo` y `url` (en ese orden). Cuando la empresa no se puede inferir se deja vacío, pero se mantiene el encabezado fijo para facilitar el post-procesamiento. Los JSON contienen los mismos campos.

### Logging y tiempos de espera

- Cada scraper reporta su duración y número de ofertas; al final se anota el total combinado tras la deduplicación.
- El ruido de Selenium se reduce automáticamente al nivel `WARNING` o al nivel de logging que selecciones, lo que ocurra primero.
- Puedes ajustar `--initial-wait` y `--page-wait` si detectas páginas lentas. Indeed aplica internamente esperas reducidas para mantener la paginación ágil.

## Estructura del proyecto

- `src/core/`: Infraestructura compartida
  - `base.py`: Clase base para scrapers (gestión de paginación, cierre)
  - `browser.py`: Factoría de WebDriver (Firefox) con soporte para `SCRAPER_HEADLESS`
- `src/bumeran.py`: Scraper de Bumeran (hereda de `BaseScraper`)
- `src/computrabajo.py`: Scraper de Computrabajo (hereda de `BaseScraper`)
- `src/indeed.py`: Scraper de Indeed (hereda de `BaseScraper`)
- `src/pipeline.py`: Orquestación para ejecutar los scrapers y combinar resultados
- `src/utils.py`: Guardado de resultados a JSON/CSV
- `main.py`: CLI que delega en `pipeline.run_combined`

## Pruebas

El proyecto incluye pruebas unitarias con `unittest`. Durante las pruebas se stubbea Selenium para no requerir el navegador real.

Ejecuta las pruebas:

```bash
python3 -m unittest discover tests
```

## Notas

- El modo headless viene activado por defecto; usa `--no-headless` o `SCRAPER_HEADLESS=0` cuando necesites abrir la ventana del navegador.
- Ejecuta con `--log-level debug` para ver mensajes adicionales de deduplicación, esperas y liberación de recursos.
- Si necesitas bloquear versiones exactas, genera un lock con tu herramienta preferida (Poetry o pip-tools). Este repo incluye `requirements.txt` para instalaciones simples con pip.
- El driver stealth de Indeed rota user-agent, idioma y tamaño de ventana para reducir bloqueos. Si quieres desactivarlo, utiliza `SCRAPER_RANDOMIZE_FP=0`.
