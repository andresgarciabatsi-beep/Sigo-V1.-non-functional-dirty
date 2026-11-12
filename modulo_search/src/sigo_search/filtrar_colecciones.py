"""Segundo filtro de SIGO Search: descarta catálogos y búsquedas usando la URL.

No realiza solicitudes HTTP y no determina si una página está bloqueada.
Las rutas desconocidas se conservan para no descartar productos por error.
"""

from urllib.parse import unquote, urlsplit, parse_qs

# Segmentos usados habitualmente para catálogos, categorías y colecciones.
SEGMENTOS_COLECCION = {
    "category", "categories", "categoria", "categorias",
    "categoria-producto", "product-category", "producto-categoria",
    "collection", "collections", "coleccion", "colecciones",
    "catalog", "catalogo",
    "showroom", "search", "busqueda", "buscar", "tag", "tags",
    "brand", "brands", "marcas", "marca", "searching",
    "s", "q", "k", "query",
}

# Segmentos que suelen identificar la ficha de UN producto.
SEGMENTOS_PRODUCTO = {
    "producto", "product", "products", "product-detail",
    "item", "itm", "dp",
}

# Parámetros que normalmente representan una página de resultados de búsqueda.
PARAMETROS_BUSQUEDA = {"s", "q", "k", "search", "query", "keyword", "keywords", "_nkw"}


def clasificar_url(url):
    """Devuelve: PRODUCTO, AGRUPADO, COLECCION o DESCONOCIDO."""
    try:
        partes = urlsplit(url)
        if partes.scheme not in {"http", "https"} or not partes.hostname:
            return "DESCONOCIDO"

        dominio = partes.hostname.lower()
        ruta = unquote(partes.path).lower()
        segmentos = [segmento for segmento in ruta.split("/") if segmento]
        parametros = {clave.lower() for clave in parse_qs(partes.query)}

        # Página principal, con o sin parámetros de seguimiento.
        if not segmentos and not (parametros & PARAMETROS_BUSQUEDA):
            return "COLECCION"

        # Categorías y colecciones comunes entre plataformas.
        if any(segmento in SEGMENTOS_COLECCION for segmento in segmentos):
            return "COLECCION"

        # Rutas de catálogos y búsquedas de marketplaces.
        if segmentos:
            if "amazon." in dominio and segmentos[0] in {"s", "clp"}:
                return "COLECCION"
            if "aliexpress." in dominio and segmentos[0] in {"w", "wholesale"}:
                return "COLECCION"
            if "ebay." in dominio and segmentos[0] == "b":
                return "COLECCION"
            if "ebay." in dominio and segmentos[0] == "p":
                return "AGRUPADO"  # Una referencia de producto con varias ofertas.

        # Patrones habituales de fichas individuales.
        if any(segmento in SEGMENTOS_PRODUCTO for segmento in segmentos):
            return "PRODUCTO"
        if segmentos and segmentos[-1] == "p":  # VTEX: /nombre-del-producto/p
            return "PRODUCTO"

        # Página de búsqueda por parámetros (?s=..., ?k=..., etc.).
        if parametros & PARAMETROS_BUSQUEDA:
            return "COLECCION"

        # No descartar una URL válida solo por no reconocer la plataforma.
        return "DESCONOCIDO"
    except (TypeError, ValueError):
        return "DESCONOCIDO"


def filtrar_colecciones(resultados_pf):
    """Mantiene la estructura del JSON y retira solo URLs clasificadas como COLECCION."""
    resultado_final = []

    for consulta in resultados_pf:
        copia = dict(consulta)
        copia["resultados"] = [
            dict(resultado)
            for resultado in consulta.get("resultados", [])
            if clasificar_url(resultado.get("url", "")) != "COLECCION"
        ]
        resultado_final.append(copia)

    return resultado_final
