"""Tercera puerta: detecta títulos de búsqueda y evalúa tipos Schema.org.

Requiere selectolax y extruct. No descarga páginas ni escribe resultados.
"""

import logging
import re
import unicodedata
from urllib.parse import urlsplit


logger = logging.getLogger(__name__)
TIPOS_COLECCION = frozenset({"CollectionPage", "SearchResultsPage"})
TIPOS_PRODUCTO = frozenset({"Product", "ProductGroup"})
TIPOS_RECONOCIDOS = TIPOS_COLECCION | TIPOS_PRODUCTO
EXPRESIONES_BUSQUEDA = (
    "busqueda de productos",
    "resultados de busqueda",
    "resultados de la busqueda",
    "resultados para la busqueda",
    "product search results",
    "search results",
    "results for your search",
    "results for the search",
)
PATRON_TITULO_BUSQUEDA = re.compile(
    r"\b(?:" + "|".join(re.escape(frase) for frase in EXPRESIONES_BUSQUEDA) + r")\b"
)


def _titulo_de_busqueda(html):
    """Lee solo el título del documento, sin buscar en menús ni scripts."""
    from selectolax.lexbor import LexborHTMLParser

    titulo = LexborHTMLParser(html).css_first("head > title")
    if titulo is None:
        return False
    texto = unicodedata.normalize("NFKD", titulo.text().casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = " ".join(texto.split())
    return bool(PATRON_TITULO_BUSQUEDA.search(texto))


def _normalizar_tipo(valor):
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if valor in TIPOS_RECONOCIDOS:
        return valor
    try:
        partes = urlsplit(valor)
        if (
            partes.scheme.lower() in {"http", "https"}
            and partes.netloc.lower() == "schema.org"
            and not partes.query
            and not partes.fragment
        ):
            tipo = partes.path.lstrip("/")
            return tipo if tipo in TIPOS_RECONOCIDOS else None
    except ValueError:
        pass
    return None


def _extraer_tipos(datos, clave):
    """Recorre objetos, listas, @graph y propiedades anidadas."""
    tipos = set()
    pendientes = [datos]
    while pendientes:
        actual = pendientes.pop()
        if isinstance(actual, dict):
            valores = actual.get(clave, [])
            if not isinstance(valores, list):
                valores = [valores]
            for valor in valores:
                tipo = _normalizar_tipo(valor)
                if tipo:
                    tipos.add(tipo)
            pendientes.extend(actual.values())
        elif isinstance(actual, list):
            pendientes.extend(actual)
    return tipos


def is_collection_in_html(respuesta_fetch: dict) -> bool:
    """True descarta un título de búsqueda o una colección sin producto.

    El título explícito tiene prioridad incluso si hay tipos Product.
    Si no coincide o falla su lectura, se aplica la tabla de verdad.
    Sin tipos o ante un fallo al leerlos devuelve False y registra el fallo.
    El HTML vacío debe enviarse a revisión previamente en la segunda puerta.
    """
    if not isinstance(respuesta_fetch, dict):
        logger.warning("Puerta 3: respuesta de Fetch inválida; no se clasifica.")
        return False
    html = respuesta_fetch.get("html")
    if not isinstance(html, str) or not html.strip():
        logger.warning("Puerta 3: HTML no utilizable; debe evaluarse en la puerta 2.")
        return False

    try:
        if _titulo_de_busqueda(html):
            return True
    except Exception as error:
        logger.warning("Puerta 3: no se pudo leer el título: %s", error)

    url_base = respuesta_fetch.get("url_final") or respuesta_fetch.get("url_original")
    try:
        import extruct

        datos = extruct.extract(
            html,
            base_url=url_base,
            syntaxes=["json-ld", "microdata"],
            errors="strict",
        )
        tipos = _extraer_tipos(datos.get("json-ld", []), "@type")
        tipos.update(_extraer_tipos(datos.get("microdata", []), "type"))
    except Exception as error:
        logger.warning("Puerta 3: no se pudieron leer los tipos: %s", error)
        return False

    hay_coleccion = bool(tipos & TIPOS_COLECCION)
    hay_producto = bool(tipos & TIPOS_PRODUCTO)
    return hay_coleccion and not hay_producto
