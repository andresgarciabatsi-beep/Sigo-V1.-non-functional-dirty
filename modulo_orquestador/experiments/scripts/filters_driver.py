"""Conductor experimental: Search -> puertas -> Fetch/Extract -> resultados.

Ejecutar este archivo usa las rutas del bloque de prueba al final.
Las salidas de revisión y descarte conservan el contexto original de Search.
"""

from copy import deepcopy
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

if __package__:
    from .is_response_code_valid import evaluar_respuesta
    from .is_collection_in_html import is_collection_in_html
else:
    from is_response_code_valid import evaluar_respuesta
    from is_collection_in_html import is_collection_in_html


ORQUESTADOR_DIR = Path(__file__).resolve().parents[2]
PROYECTO_DIR = ORQUESTADOR_DIR.parent
CAMPOS = ("nombre", "precio", "disponibilidad", "descripcion", "especificaciones")


def _preparar_importaciones():
    """Compatibilidad con los imports planos de Fetch y Extract actuales."""
    for carpeta in (
        PROYECTO_DIR,
        PROYECTO_DIR / "modulo_fetch",
        PROYECTO_DIR / "modulo_extract" / "src",
    ):
        if str(carpeta) not in sys.path:
            sys.path.insert(0, str(carpeta))


def fetch_get_url(url):
    """Carga Fetch al utilizarlo; permite probar el conductor con simulaciones."""
    _preparar_importaciones()
    from modulo_fetch.main import fetch_get_url as fetch

    return fetch(url)


def extract_product(respuesta_fetch):
    """Entrega a Extract la respuesta completa sin volver a descargar."""
    _preparar_importaciones()
    from modulo_extract.src.main2 import extract_product as extract

    return extract(respuesta_fetch)


def _url_valida(url):
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        partes = urlsplit(url.strip())
        return partes.scheme in {"http", "https"} and bool(partes.hostname)
    except ValueError:
        return False


def _decision(accion, etapa, motivo, respuesta=None, error=None):
    respuesta = respuesta if isinstance(respuesta, dict) else {}
    return {
        "accion": accion,
        "diagnostico": {
            "etapa": etapa,
            "motivo": motivo,
            "status_code": respuesta.get("status_code"),
            "error": error if error is not None else respuesta.get("error"),
            "url_final": respuesta.get("url_final"),
        },
    }


def procesar_enlace(url):
    """Procesa una URL y devuelve extraidos, revision o descartados."""
    if not _url_valida(url):
        return _decision("revision", "entrada", "url_invalida")
    url = url.strip()

    try:
        respuesta = fetch_get_url(url)
    except Exception as error:
        return _decision(
            "revision", "fetch", "error_fetch",
            error=f"{type(error).__name__}: {error}",
        )

    evaluacion = evaluar_respuesta(respuesta)
    if evaluacion["accion"] != "continuar":
        accion = "descartados" if evaluacion["accion"] == "descartar" else "revision"
        return _decision(accion, "puerta_2", evaluacion["motivo"], respuesta)

    url_final = respuesta.get("url_final") or url
    if not _url_valida(url_final):
        return _decision("revision", "redireccion", "url_final_invalida", respuesta)

    if is_collection_in_html(respuesta):
        return _decision("descartados", "puerta_3", "coleccion_detectada_en_html", respuesta)

    try:
        campos = extract_product(respuesta)
        if not isinstance(campos, dict) or any(campo not in campos for campo in CAMPOS):
            raise ValueError("Extract debe devolver un diccionario con los cinco campos")
        if any(valor is not None and not isinstance(valor, str) for valor in (campos[c] for c in CAMPOS)):
            raise ValueError("Los campos de Extract deben ser texto o null")
    except Exception as error:
        return _decision(
            "revision", "extract", "error_extraccion", respuesta,
            error=f"{type(error).__name__}: {error}",
        )

    return {
        "accion": "extraidos",
        "url": url_final,
        "datos": {campo: campos[campo] for campo in CAMPOS},
    }


def _validar_registros(registros):
    """Verifica el sobre de Search antes de empezar las descargas."""
    if not isinstance(registros, list):
        raise ValueError("La entrada de Search debe ser una lista")
    for indice, registro in enumerate(registros):
        if not isinstance(registro, dict) or not isinstance(registro.get("resultados"), list):
            raise ValueError(f"Registro {indice}: se requiere un objeto con una lista resultados")
        numero = registro.get("numero_item")
        if not isinstance(numero, (int, str)) or isinstance(numero, bool):
            raise ValueError(f"Registro {indice}: numero_item inválido")
        if any(not isinstance(resultado, dict) for resultado in registro["resultados"]):
            raise ValueError(f"Registro {indice}: cada resultado debe ser un objeto")


def procesar_resultados(registros):
    """Mantiene los grupos originales en revisión/descarte y agrupa extraídos por ítem."""
    _validar_registros(registros)
    salida = {"extraidos": [], "revision": [], "descartados": []}
    items_extraidos = {}

    for registro in registros:
        pendientes = {"revision": [], "descartados": []}
        for resultado in registro["resultados"]:
            decision = procesar_enlace(resultado.get("url"))
            accion = decision["accion"]
            print(f"Ítem {registro['numero_item']} | {registro.get('tienda', '')} | "
                  f"{accion}: {resultado.get('url')}")

            if accion == "extraidos":
                numero = registro["numero_item"]
                if numero not in items_extraidos:
                    items_extraidos[numero] = {"item": numero, "resultados": []}
                    salida["extraidos"].append(items_extraidos[numero])
                items_extraidos[numero]["resultados"].append({
                    "tienda": registro.get("tienda", ""),
                    "url": decision["url"],
                    **decision["datos"],
                })
            else:
                copia = deepcopy(resultado)
                clave = "revision" if accion == "revision" else "descarte"
                copia[clave] = decision["diagnostico"]
                pendientes[accion].append(copia)

        for accion, enlaces in pendientes.items():
            if enlaces:
                copia = deepcopy(registro)
                copia["resultados"] = enlaces
                salida[accion].append(copia)

    return salida


def guardar_resultados(resultados, directorio_salida):
    directorio = Path(directorio_salida)
    directorio.mkdir(parents=True, exist_ok=True)
    for categoria, registros in resultados.items():
        archivo = directorio / f"resultados_{categoria}.json"
        archivo.write_text(
            json.dumps(registros, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def driver(archivo_entrada, directorio_salida) -> dict:
    """Ejecuta el lote y escribe extraídos, revisión y descartes.

    El archivo de entrada puede ser cualquier búsqueda de Search.
    Los tres archivos de salida se reemplazan en cada ejecución.
    """
    with Path(archivo_entrada).open(encoding="utf-8-sig") as archivo:
        registros = json.load(archivo)
    resultados = procesar_resultados(registros)
    guardar_resultados(resultados, directorio_salida)
    print("\nResumen del conductor:")
    for categoria, grupos in resultados.items():
        total = sum(len(grupo["resultados"]) for grupo in grupos)
        print(f"  {categoria}: {total} enlaces")
    print(f"Salidas: {Path(directorio_salida).resolve()}")
    return resultados


# ============================================================
# PRUEBA DEL CONDUCTOR - CAMBIAR LAS RUTAS AQUÍ
# ============================================================

if __name__ == "__main__":
    archivo_entrada = ORQUESTADOR_DIR / "resources" / "resultados_filtrados_memorias.json"
    directorio_salida = ORQUESTADOR_DIR / "experiments" / "results"

    resultados = driver(archivo_entrada, directorio_salida)
