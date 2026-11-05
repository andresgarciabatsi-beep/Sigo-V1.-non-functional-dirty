import sys
from pathlib import Path

# Rutas de los módulos
PROYECTO_DIR = Path(__file__).resolve().parents[2]

FETCH_DIR = PROYECTO_DIR / "modulo_fetch"
EXTRACT_DIR = PROYECTO_DIR / "modulo_extract"

# Preparar rutas de importación
for carpeta in (
    PROYECTO_DIR,
    FETCH_DIR,
    EXTRACT_DIR / "src",
):
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))

# Funciones públicas de Fetch y Extract
from modulo_fetch.main import fetch_get_url
from modulo_extract.src.main2 import extract_product


def process_url(url: str) -> dict | None:
    """
    Coordina Fetch y Extract para una URL.

    Devuelve la URL final y los cinco campos extraídos.
    Si ocurre un error, devuelve None.
    """

    # 1. Enviar URL a Fetch
    try:
        resultado_fetch = fetch_get_url(url)

    except Exception as error:
        print(f"ERROR Orquestador - Fetch: {url}: {error}")
        return None

    # 2. Comprobar resultado de Fetch
    if not isinstance(resultado_fetch, dict):
        print(f"ERROR Orquestador: Respuesta Fetch inválida: {url}")
        return None

    if not resultado_fetch.get("exito"):
        print(
            f"ERROR Fetch: {url} | "
            f"HTTP: {resultado_fetch.get('status_code')} | "
            f"{resultado_fetch.get('error')}"
        )
        return None

    # 3. Enviar respuesta completa a Extract
    try:
        resultado_extract = extract_product(resultado_fetch)

    except Exception as error:
        print(f"ERROR Orquestador - Extract: {url}: {error}")
        return None

    # 4. Comprobar respuesta de Extract
    if not isinstance(resultado_extract, dict):
        print(f"ERROR Orquestador: Respuesta Extract inválida: {url}")
        return None

    # 5. Devolver información extraída
    return {
        "url": resultado_fetch.get("url_final") or url,
        "datos": resultado_extract
    }
