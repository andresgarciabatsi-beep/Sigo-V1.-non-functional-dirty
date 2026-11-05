
from pathlib import Path
import httpx
import json

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


# DEBUGGING
# if __name__ == "__main__":

#     url = "https://www.raspipc.es/2042"

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
