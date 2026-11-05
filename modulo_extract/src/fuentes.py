"""Preparación de fuentes para SIGO Fetch.

Este módulo NO localiza nombre, precio, disponibilidad, descripción ni
especificaciones. Recibe el HTML ya descargado y prepara las representaciones
que consultará localizadores.py.

Instalación: pip install selectolax extruct
"""

import json


def _leer_json(texto):
    """Interpreta un bloque JSON; ignora scripts que no contienen JSON válido."""
    if not texto:
        return None
    try:
        return json.loads(texto.strip().lstrip("\ufeff"))
    except (ValueError, TypeError):
        return None


def _resolver_referencias(objeto, cache, visitados=None, nivel=0):
    """Sigue referencias internas VTEX del tipo {'type': 'id', 'id': '...'}.

    No ejecuta JavaScript ni realiza peticiones a la tienda.
    """
    if nivel > 30:
        return objeto
    if visitados is None:
        visitados = frozenset()

    if isinstance(objeto, list):
        return [
            _resolver_referencias(elemento, cache, visitados, nivel + 1)
            for elemento in objeto
        ]

    if not isinstance(objeto, dict):
        return objeto

    referencia = objeto.get("id")
    if (
        objeto.get("type") == "id"
        and isinstance(referencia, str)
        and referencia in cache
        and referencia not in visitados
    ):
        return _resolver_referencias(
            cache[referencia], cache, visitados | {referencia}, nivel + 1
        )

    return {
        clave: _resolver_referencias(valor, cache, visitados, nivel + 1)
        for clave, valor in objeto.items()
    }


def _agregar_json(documentos, datos):
    """Guarda objetos JSON; para VTEX conserva productos, no todo el estado."""
    if isinstance(datos, dict) and any(
        clave.startswith("Product:") for clave in datos
    ):
        productos = [
            valor
            for clave, valor in datos.items()
            if clave.startswith("Product:")
            and isinstance(valor, dict)
            and isinstance(valor.get("productName"), str)
        ]
        for producto in productos:
            documentos.append(_resolver_referencias(producto, datos))
    elif isinstance(datos, (dict, list)):
        documentos.append(datos)


def _extraer_json_embebido(arbol):
    """Lee JSON convencional y estados de hidratación de aplicaciones web."""
    documentos = []

    # Ej.: Next.js (__NEXT_DATA__) y scripts con JSON explícito.
    for script in arbol.css('script[type="application/json"], script#__NEXT_DATA__'):
        _agregar_json(documentos, _leer_json(script.text()))

    # VTEX puede guardar el estado dentro de un <template>. En Lexbor, su
    # contenido NO es descendiente normal del DOM: se accede mediante fragments.
    if hasattr(arbol, "template_fragments"):
        for fragmento in arbol.template_fragments():
            plantilla = fragmento.parent
            if plantilla is None:
                continue
            atributos = plantilla.attributes
            if atributos.get("data-varname") != "__STATE__":
                continue
            for script in fragmento.css("script"):
                _agregar_json(documentos, _leer_json(script.text()))

    return documentos


def _extraer_meta(arbol):
    """Recoge los metadatos conservando varias apariciones de una misma clave."""
    metadatos = {}
    for nodo in arbol.css("meta[name], meta[property]"):
        atributos = nodo.attributes
        clave = (atributos.get("property") or atributos.get("name") or "").strip().lower()
        valor = (atributos.get("content") or "").strip()
        if clave and valor:
            grupo = metadatos.setdefault(clave, [])
            if valor not in grupo:
                grupo.append(valor)

    titulo = arbol.css_first("head title")
    if titulo is not None:
        texto = titulo.text(strip=True)
        if texto:
            metadatos["title"] = [texto]

    return metadatos


def _extraer_opengraph(datos_extruct, metadatos):
    """Unifica Open Graph de Extruct con las metaetiquetas disponibles."""
    resultado = {}
    for bloque in datos_extruct.get("opengraph", []):
        for clave, valor in bloque.get("properties", []):
            clave = str(clave).lower()
            grupo = resultado.setdefault(clave, [])
            if valor not in grupo:
                grupo.append(valor)

    # Respaldo para propiedades de producto que Extruct no haya incluido.
    for clave, valores in metadatos.items():
        if clave.startswith(("og:", "product:")):
            grupo = resultado.setdefault(clave, [])
            for valor in valores:
                if valor not in grupo:
                    grupo.append(valor)

    return resultado


def preparar_fuentes(html, url_base=None):
    """Prepara todas las fuentes una sola vez.

    Args:
        html: cadena o bytes del HTML de una ficha de producto ya descargada.
        url_base: URL real de la ficha (recomendada para resolver URLs relativas).

    Returns:
        dict con las claves: html, jsonld, microdata, opengraph, meta,
        json_embebido. Las listas o diccionarios pueden estar vacíos.

    Importante: esta función no valida si los datos pertenecen al producto.
    Esa decisión corresponde a localizadores.py.
    """
    try:
        from selectolax.lexbor import LexborHTMLParser
        import extruct
    except ImportError as exc:
        raise ImportError(
            "Faltan dependencias. Ejecuta: pip install selectolax extruct"
        ) from exc

    if not isinstance(html, (str, bytes)):
        raise TypeError("html debe ser una cadena de texto o bytes")

    arbol = LexborHTMLParser(html)

    # Extruct interpreta las tres fuentes estructuradas de interés.
    # No analizamos RDFa ni microformatos porque aún no hay patrones para ellos.
    datos = extruct.extract(
        html,
        base_url=url_base,
        syntaxes=["json-ld", "microdata", "opengraph"],
    )

    metadatos = _extraer_meta(arbol)
    return {
        "html": arbol,
        "jsonld": datos.get("json-ld", []),
        "microdata": datos.get("microdata", []),
        "opengraph": _extraer_opengraph(datos, metadatos),
        "meta": metadatos,
        "json_embebido": _extraer_json_embebido(arbol),
    }
