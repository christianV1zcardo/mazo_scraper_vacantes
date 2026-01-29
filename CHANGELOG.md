# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [2.0.0] - 2026-01-29

### ⚡ Mejoras de Rendimiento

- **Ejecución paralela de todos los scrapers**: Bumeran, Computrabajo, Indeed y Laborum ahora se ejecutan simultáneamente usando `ThreadPoolExecutor`, reduciendo el tiempo total de ~7.6 minutos a ~45 segundos
- **Extracción con JavaScript**: Todos los scrapers ahora usan `execute_script` en lugar de `find_elements`, reduciendo drásticamente el tiempo de extracción por página
- **Timeouts optimizados**: Reducido `page_load_timeout` de 120s a 30s para evitar esperas largas en páginas lentas
- **Tiempos de espera reducidos**: `page_wait` optimizado a 0.3-0.5s entre páginas

### 🐛 Correcciones

- **Computrabajo URLs corregidas**: Las URLs ahora apuntan a las páginas de detalle correctas (`/ofertas-de-trabajo/...`) en lugar de la página de búsqueda con fragmentos
- **Bumeran URLs absolutas**: Corregido el problema donde las URLs relativas (`/empleos/...`) eran descartadas por la normalización
- **Extracción de empresas mejorada**: Computrabajo ahora extrae correctamente el nombre de empresa desde los elementos `<a>` del listado

### 📝 Cambios

- **CSV simplificado**: El archivo CSV ahora solo contiene 4 columnas: `Fuente`, `Empresa`, `Titulo`, `Url` (con headers en mayúscula)
- **Laborum con filtro de fecha**: El scraper de Laborum ahora filtra por fecha de publicación basándose en el texto "Hace X días"

### 🧪 Tests

- **62 tests pasando**: Cobertura completa de la funcionalidad principal
- **Tests de extracción JS**: Nuevos tests para verificar la extracción con JavaScript
- **Tests de deduplicación global**: Verificación de que no hay duplicados entre fuentes

## [1.1.0] - 2026-01-28

### Añadido

- Soporte para Laborum como fuente adicional
- Filtrado automático por palabras clave excluidas (call center, ventas, etc.)
- Archivo `top_<query>_<fecha>.csv` con empresas prioritarias
- Copia automática al portapapeles del resumen

### Cambiado

- Mejorada la estructura del proyecto con `src/core/` para código compartido
- Logs más informativos con tiempos de ejecución por scraper

## [1.0.0] - 2026-01-15

### Añadido

- Scrapers para Bumeran, Computrabajo e Indeed
- CLI interactivo y por argumentos
- Deduplicación de resultados por URL
- Salida en formato CSV
- Modo headless por defecto
- Suite de tests unitarios
