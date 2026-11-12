from urllib.parse import urlparse
import json


def pertenece_a_tienda(url, dominio_tienda):
    """
    Comprueba si una URL pertenece al dominio exacto
    de la tienda consultada.

    Ejemplo:

    dominio_tienda = "amazon.com"

    https://www.amazon.com/producto   -> True
    https://amazon.com/producto       -> True
    https://amazon.es/producto        -> False
    https://www.amazon.com.mx/...     -> False
    """

    try:

        # Obtener el dominio de la URL del resultado
        dominio_resultado = urlparse(url).netloc.lower()

        # Eliminar "www." del dominio del resultado
        if dominio_resultado.startswith("www."):
            dominio_resultado = dominio_resultado[4:]

        # Limpiar el dominio de la tienda
        dominio_tienda = dominio_tienda.lower().strip()

        # Eliminar "www." si estuviera presente
        if dominio_tienda.startswith("www."):
            dominio_tienda = dominio_tienda[4:]

        # Comparar ambos dominios
        return dominio_resultado == dominio_tienda

    except Exception:
        return False


def filtrar_resultados(resultados_searxng):
    """
    Filtra los resultados obtenidos de SearXNG.

    Hace dos cosas:

    1. Conserva únicamente los resultados cuya URL pertenece
       al dominio de la tienda consultada.

    2. Conserva únicamente los campos necesarios de cada resultado:
       - title
       - content
       - url
       - engines
       - score

    Entrada:
    - Lista generada por consultar_searxng.py

    Salida:
    - Lista de resultados filtrados y simplificados.
    """

    resultados_filtrados = []

    # --------------------------------------------------------
    # Recorrer cada consulta realizada
    # --------------------------------------------------------

    for consulta in resultados_searxng:

        dominio_tienda = consulta["dominio"]

        resultados_validos = []

        # ----------------------------------------------------
        # Recorrer los resultados de la consulta
        # ----------------------------------------------------

        for resultado in consulta["resultados"]:

            url = resultado.get("url", "")

            # ------------------------------------------------
            # Comprobar si la URL pertenece a la tienda
            # ------------------------------------------------

            if pertenece_a_tienda(
                url,
                dominio_tienda
            ):

                # --------------------------------------------
                # Conservar únicamente los campos necesarios
                # --------------------------------------------

                resultado_limpio = {
                    "title": resultado.get("title", ""),
                    "content": resultado.get("content", ""),
                    "url": resultado.get("url", ""),
                    "engines": resultado.get("engines", []),
                    "score": resultado.get("score", 0)
                }

                resultados_validos.append(
                    resultado_limpio
                )

        # ----------------------------------------------------
        # Guardar la consulta con sus resultados válidos
        # ----------------------------------------------------

        resultados_filtrados.append(
            {
                "numero_item": consulta["numero_item"],
                "nombre_item": consulta["nombre_item"],
                "mercado": consulta["mercado"],
                "prioridad": consulta["prioridad"],
                "tienda": consulta["tienda"],
                "dominio": dominio_tienda,
                "consulta": consulta["consulta"],
                "resultados": resultados_validos,
                "motores_no_disponibles": consulta.get(
                    "motores_no_disponibles",
                    []
                )
            }
        )

    return resultados_filtrados


# ============================================================
# DEBUGGING
# ============================================================

# if __name__ == "__main__":

#     # Leer los resultados generados por SearXNG
#     with open(
#         "resultados_searxng.json",
#         "r",
#         encoding="utf-8"
#     ) as archivo:

#         resultados = json.load(archivo)

#     # Aplicar el filtro
#     resultados_filtrados = filtrar_resultados(
#         resultados
#     )

#     # Guardar los resultados filtrados
#     with open(
#         "resultados_filtrados.json",
#         "w",
#         encoding="utf-8"
#     ) as archivo:

#         json.dump(
#             resultados_filtrados,
#             archivo,
#             ensure_ascii=False,
#             indent=2
#         )

#     # --------------------------------------------------------
#     # Mostrar resumen
#     # --------------------------------------------------------

#     print("RESULTADOS DEL FILTRO")
#     print("=" * 70)

#     for consulta in resultados_filtrados:

#         print(
#             f"Ítem {consulta['numero_item']} | "
#             f"{consulta['mercado']} | "
#             f"{consulta['tienda']} | "
#             f"{len(consulta['resultados'])} resultados válidos"
#         )

#     print()
#     print(
#         "Archivo generado: resultados_filtrados.json"
#     )