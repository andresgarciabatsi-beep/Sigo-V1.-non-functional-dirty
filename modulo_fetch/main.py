
from pathlib import Path
import httpx
import json
from urllib.parse import urlparse
import re
from src.get_html import get_html_httpx, get_html_crawling


def formatear_resultado_fetch(
    url_original: str,
    url_final: str,
    html: str,
    status_code: int | None,
    tool: str,
    error: str | None = None
) -> dict:
    """
    Formatea el resultado de Fetch para entregarlo al orquestador.
    """

    exito = status_code == 200 and bool(html)

    if not exito and error is None:
        error = (
            f"HTTP {status_code}"
            if status_code is not None
            else "No se recibió una respuesta válida"
        )

    return {
        "url_original": url_original,
        "url_final": url_final,
        "html": html,
        "status_code": status_code,
        "tool": tool,
        "exito": exito,
        "error": error
    }


def fetch_get_url(url: str) -> dict:
    """
    Obtiene el HTML de una URL utilizando HTTPx como primera
    estrategia y Crawl4AI como alternativa.

    Devuelve un diccionario con el resultado de Fetch.
    """

    html = ""
    status_code = None
    url_final = url
    tool = "httpx"
    error_detalle = None

    # Primera estrategia: HTTPX
    try:
        html, status_code, url_final = get_html_httpx(url)

    except (httpx.RequestError, ValueError) as error:
        print("fetch: main.py: HTTPX error:", error)
        error_detalle = str(error)
        tool = "crawler"

    else:
        if status_code == 403:
            print("fetch: main.py: HTTP 403. Activating Crawl4AI.")
            tool = "crawler"

        elif status_code == 200:
            print("fetch: main.py: HTTPX successful.")

        else:
            print("fetch: main.py: HTTPX returned HTTP:", status_code)

    # Segunda estrategia: Crawl4AI
    if tool == "crawler":
        try:
            html, status_code, url_final = get_html_crawling(url)
            error_detalle = None

        except Exception as error:
            print("fetch: main.py: Crawl4AI error:", error)
            html = ""
            status_code = None
            error_detalle = str(error)

    # Formatear resultado
    return formatear_resultado_fetch(
        url_original=url,
        url_final=url_final,
        html=html,
        status_code=status_code,
        tool=tool,
        error=error_detalle
    )


# # DEBUGGING
# if __name__ == "__main__":

#     url = "https://tecnomegastore.ec/searchi/1/ups"

#     resultado = fetch_get_url(url)

#     results_path = Path(__file__).resolve().parent / "results"
#     results_path.mkdir(parents=True, exist_ok=True)

#     json_saved = results_path / "resultado_fetch.json"

#     with open(json_saved, "w", encoding="utf-8") as archivo:
#         json.dump(resultado, archivo, indent=4, ensure_ascii=False)

#     print("JSON guardado en:", json_saved)

#     # Guardar HTML recibido
#     if resultado["html"]:
#         results_path = Path(__file__).resolve().parent / "results"
#         results_path.mkdir(parents=True, exist_ok=True)

#         html_saved = results_path / "pagina_producto.html"

#         html_saved.write_text(
#             resultado["html"],
#             encoding="utf-8"
#         )

#         print("HTML guardado en:", html_saved)

#     # Mostrar resultados
#     print("+" * 70)
#     print("RESULTADOS")
#     print("+" * 70)

#     print("URL original:", resultado["url_original"])
#     print("URL final:", resultado["url_final"])
#     print("Estrategia utilizada:", resultado["tool"])
#     print("Código HTTP:", resultado["status_code"])
#     print("Éxito:", resultado["exito"])
#     print("Error:", resultado["error"])
#     print("Caracteres descargados:", len(resultado["html"]))


if __name__ == "__main__":

    # 1. Rutas
    BASE = Path(__file__).resolve().parent

    ARCHIVO_URLS = BASE / "experiments" / "resources" / "enlaces.json"

    CARPETA_HTML = BASE / "experiments"/ "results"/ "htmls_adicionales"

    CARPETA_HTML.mkdir(parents=True, exist_ok=True)

    ARCHIVO_REPORTE = BASE / "experiments"/ "results"/ "htmls_adicionales"/ "reporte_fetch.json"

    # 2. Leer URLs
    with ARCHIVO_URLS.open("r", encoding="utf-8") as archivo:
        urls = json.load(archivo)

    if not isinstance(urls, list):
        raise ValueError(
            "urls_externas.json debe contener una lista de URLs."
        )

    # 3. Recorrer URLs
    reporte = []

    for indice, url in enumerate(urls, start=1):

        if not isinstance(url, str) or not url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(f"URL inválida en posición {indice}: {url}")

        print(f"\n{'=' * 60}")
        print(f"[{indice}/{len(urls)}] {url}")
        print(f"{'=' * 60}")

        # Nombre del archivo basado en el dominio
        dominio = urlparse(url).netloc.lower()
        dominio = re.sub(r"[^a-z0-9]+", "_", dominio).strip("_")

        nombre_archivo = f"{indice:02d}_{dominio}.html"
        ruta_salida = CARPETA_HTML / nombre_archivo

        # 4. Ejecutar Fetch
        try:
            resultado = fetch_get_url(url)

        except Exception as error:
            resultado = {
                "url_original": url,
                "url_final": url,
                "html": "",
                "status_code": None,
                "tool": "desconocido",
                "exito": False,
                "error": str(error)
            }

        # 5. Guardar HTML si la extracción tuvo éxito
        if resultado["exito"]:

            ruta_salida.write_text(
                resultado["html"],
                encoding="utf-8"
            )

            print(f"HTML guardado: {ruta_salida}")

        else:
            print(
                f"Error al descargar: {resultado['error']}"
            )

            # Evitar conservar una descarga antigua
            # como resultado de esta ejecución fallida.
            if ruta_salida.exists():
                ruta_salida.unlink()

        # 6. Registrar resultado sin duplicar el HTML
        reporte.append({
            "url_original": resultado["url_original"],
            "url_final": resultado["url_final"],
            "archivo": nombre_archivo if resultado["exito"] else None,
            "status_code": resultado["status_code"],
            "tool": resultado["tool"],
            "exito": resultado["exito"],
            "error": resultado["error"]
        })

    # 7. Guardar reporte
    ARCHIVO_REPORTE.write_text(
        json.dumps(
            reporte,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # 8. Resumen
    exitosos = sum(1 for item in reporte if item["exito"])
    fallidos = len(reporte) - exitosos

    print(f"\n{'=' * 60}")
    print("RESUMEN FETCH")
    print(f"{'=' * 60}")
    print(f"URLs procesadas: {len(reporte)}")
    print(f"HTML descargados: {exitosos}")
    print(f"Fallidos:         {fallidos}")
    print(f"Carpeta HTML:     {CARPETA_HTML}")
    print(f"Reporte:          {ARCHIVO_REPORTE}")