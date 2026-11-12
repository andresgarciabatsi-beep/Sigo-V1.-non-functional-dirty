"""SIGO Fetch: localiza cinco campos usando las reglas de patrones.json.

No descarga páginas ni interpreta el HTML de nuevo: recibe el resultado
preparado por fuentes.preparar_fuentes().

Para ampliar selectores, claves o rutas conocidas, basta editar patrones.json.
"""

import html as html_std
import re


# Evita confundir artículos relacionados con el producto de la ficha.
_ZONA_AJENA = re.compile(
    r"related|recommend|upsell|cross.sell|also.bought|breadcrumb|"
    r"newsletter|footer|sidebar|cookie",
    re.IGNORECASE,
)


def _limpiar(valor):
    """Convierte valores HTML/JSON a texto; conserva saltos de línea."""
    if valor is None:
        return ""

    if isinstance(valor, list):
        return "\n".join(texto for item in valor if (texto := _limpiar(item)))

    if isinstance(valor, dict):
        # Ej.: {"name": "Voltaje", "value": "12 V"}.
        nombre = valor.get("name", valor.get("Name"))
        dato = valor.get("values", valor.get("value"))
        if nombre is not None and dato is not None:
            return f"{_limpiar(nombre)}: {_limpiar(dato)}"

        # Contenedores de especificaciones: mantener los datos como texto.
        partes = []
        for clave, dato in valor.items():
            if clave in {"@type", "type", "id", "__typename", "generated"}:
                continue
            texto = _limpiar(dato)
            if texto:
                partes.append(f"{clave}: {texto}")
        return "\n".join(partes)

    texto = html_std.unescape(str(valor))
    if "<" in texto and ">" in texto:
        texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.I)
        texto = re.sub(r"</(?:p|div|li|tr|h[1-6])\s*>", "\n", texto, flags=re.I)
        texto = re.sub(r"<[^>]*>", " ", texto)
    lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
    return "\n".join(linea for linea in lineas if linea).strip()


def _prosa_antes_de_apendice(nodo):
    """Reconoce párrafos iniciales seguidos de un apéndice técnico aislado.

    No recorta si después aparecen otros párrafos: pueden ser avisos,
    instrucciones o una continuación de la descripción.
    """
    hijos = []
    hijo = nodo.child
    while hijo is not None:
        if hijo.tag not in {"-text", "-comment", "style", "script"}:
            hijos.append(hijo)
        elif hijo.tag == "-text" and hijo.text(strip=True):
            return ""
        hijo = hijo.next

    if hijos and hijos[0].tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        hijos = hijos[1:]

    partes = []
    indice = 0
    while indice < len(hijos) and hijos[indice].tag == "p":
        partes.append(hijos[indice].text(separator=" ", strip=True))
        indice += 1

    prosa = "\n".join(p for p in partes if p)
    if len(prosa.split()) < 25 or indice == len(hijos):
        return ""

    entradas = []
    for apendice in hijos[indice:]:
        if not apendice.text(strip=True):
            continue
        if apendice.tag == "p" or apendice.css("p"):
            return ""
        bloques = (
            [apendice] if apendice.tag in {"li", "tr", "pre"}
            else apendice.css("li, tr, pre")
        )
        if not bloques and apendice.tag not in {
            "h1", "h2", "h3", "h4", "h5", "h6", "hr"
        }:
            return ""
        for bloque in bloques:
            texto = bloque.text(separator=" ", strip=True)
            entradas.extend(texto.splitlines() if bloque.tag == "pre" else [texto])

    entradas = [e.strip() for e in entradas if e.strip()]
    if len(entradas) < 3:
        return ""
    tecnicas = sum(bool(re.search(r"\d|\w\s*:", e)) for e in entradas)
    return prosa if tecnicas / len(entradas) >= 0.6 else ""


def _ruta(objeto, ruta):
    """Lee rutas como offers.price, offers.0.price o properties.name.

    Si una propiedad contiene una lista, consulta todos sus elementos.
    Así no perdemos ofertas de distintas variantes.
    """
    resultados = [objeto]
    for clave in ruta.split("."):
        siguientes = []
        for actual in resultados:
            if isinstance(actual, list):
                if clave.isdigit():
                    indice = int(clave)
                    if indice < len(actual):
                        siguientes.append(actual[indice])
                else:
                    for elemento in actual:
                        if isinstance(elemento, dict):
                            siguientes.extend(_ruta(elemento, clave))
            elif isinstance(actual, dict):
                for nombre, dato in actual.items():
                    if nombre.casefold() == clave.casefold():
                        siguientes.append(dato)
                        break
        resultados = siguientes
        if not resultados:
            break
    return resultados


def _objetos_tipo(datos, tipo="Product"):
    """Busca objetos Product sin asumir su posición dentro de @graph."""
    encontrados = []

    def visitar(objeto):
        if isinstance(objeto, list):
            for elemento in objeto:
                visitar(elemento)
        elif isinstance(objeto, dict):
            tipos = objeto.get("@type", objeto.get("type", []))
            if not isinstance(tipos, list):
                tipos = [tipos]
            if any(str(t).rstrip("/").split("/")[-1].casefold() == tipo.casefold()
                   for t in tipos):
                encontrados.append(objeto)
            # Solo seguimos relaciones estructurales, no productos sugeridos.
            for clave in ("@graph", "graph", "mainEntity"):
                if clave in objeto:
                    visitar(objeto[clave])

    visitar(datos)
    return encontrados


def _ajeno(nodo, ignorar_layout_global=False):
    """Excluye coincidencias situadas en navegación o productos relacionados."""
    actual = nodo
    for _ in range(16):
        if actual is None:
            break
        if actual.tag in {"html", "body"} and ignorar_layout_global:
            # Clases como right-sidebar describen el layout, no este bloque.
            break
        if actual.tag in {"html", "body"}:
            # Las clases del documento describen el layout global (por
            # ejemplo, «ast-no-sidebar») y no convierten todo el producto en
            # una zona ajena.
            actual = actual.parent
            continue
        if actual.tag in {"nav", "footer", "aside"}:
            return True
        atributos = actual.attributes
        identificacion = f"{atributos.get('id', '')} {atributos.get('class', '')}"
        if _ZONA_AJENA.search(identificacion):
            return True
        actual = actual.parent
    return False



def _extraer_regla(campo, regla, fuentes):
    """
    Ejecuta una regla de localización.

    Devuelve pares (indice, valor).
    El índice identifica la posición original de la coincidencia,
    necesaria para comprobar su contexto en filtros.py.

    No realiza una extracción bruta adicional.
    """
    origen = regla["fuente"].lower()

    if origen == "html":
        arbol = fuentes.get("html")

        if arbol is None:
            return []

        try:
            nodos = arbol.css(regla["selector"])
        except ValueError:
            return []

        encontrados = []

        for indice, nodo in enumerate(nodos[:25], start=1):

            if _ajeno(nodo, ignorar_layout_global=campo == "especificaciones"):
                continue

            atributo = regla.get("atributo")

            if atributo:
                valor = nodo.attributes.get(atributo, "")
            else:
                nodo_texto = nodo
                if campo in {"descripcion", "especificaciones"}:
                    # El código incrustado no es contenido del producto y puede
                    # invalidar todo el candidato en filtros. No mutar el DOM
                    # compartido, necesario para resolver índices y contexto.
                    nodo_texto = nodo.clone()
                    nodo_texto.strip_tags(["style", "script"])
                valor = nodo_texto.text(
                    separator="\n" if campo == "especificaciones" else " ",
                    strip=True,
                )

                if campo == "descripcion":
                    valor = _prosa_antes_de_apendice(nodo_texto) or valor

                if not valor:
                    valor = nodo.attributes.get(
                        "content",
                        nodo.attributes.get("value", "")
                    )

            if valor is not None:
                encontrados.append((indice, valor))

        return encontrados

    if origen in ("meta", "opengraph"):

        valores = fuentes.get(origen, {}).get(
            regla["clave"].lower(),
            []
        )

    elif origen in ("jsonld", "microdata"):

        objetos = _objetos_tipo(
            fuentes.get(origen, []),
            regla.get("tipo", "Product")
        )

        if campo == "precio" and regla["ruta"].split(".")[-1].casefold() in {
            "price", "lowprice", "highprice"
        }:
            # La moneda pertenece a la misma oferta, no a otra variante
            # ni al primer priceCurrency encontrado en toda la página.
            ruta_padre, _, clave = regla["ruta"].rpartition(".")
            valores = []
            for objeto in objetos:
                padres = _ruta(objeto, ruta_padre) if ruta_padre else [objeto]
                for padre in padres:
                    for oferta in padre if isinstance(padre, list) else [padre]:
                        monedas = _ruta(oferta, "priceCurrency")
                        moneda = str(monedas[0]).strip().upper() if len(monedas) == 1 else ""
                        for dato in _ruta(oferta, clave):
                            valores.append(
                                f"{moneda} {dato}"
                                if re.fullmatch(r"[A-Z]{3}", moneda) else dato
                            )
            return list(enumerate(valores, start=1))

        valores = [
            dato
            for objeto in objetos
            for dato in _ruta(objeto, regla["ruta"])
        ]

    elif origen == "json_embebido":

        valores = [
            dato
            for objeto in fuentes.get("json_embebido", [])
            for dato in _ruta(objeto, regla["ruta"])
        ]

    else:
        return []

    if not isinstance(valores, list):
        valores = [valores]

    return list(enumerate(valores, start=1))


# ============================================================
# DESCUBRIMIENTO ESTRUCTURAL (sin selectores por tienda)
# ============================================================

_TITULOS_SECCION = (
    "h1, h2, h3, h4, h5, h6, summary, [role=heading]"
)

_SECCION_DESCRIPCION = re.compile(
    r"^(?:descripci[oó]n(?: del producto)?|descripci[oó]n general|"
    r"description|product description|general description|"
    r"descriptif|pr[eé]sentation du produit|"
    r"product overview|overview|resumen|"
    r"detalles del producto|product details|"
    r"informaci[oó]n del producto|acerca de(?:l)? producto|"
    r"about(?: this)? product)\b[\s:.\-–]*",
    re.I,
)

_SECCION_ESPECIFICACIONES = re.compile(
    r"^(?:especificaciones(?: del producto| t[eé]cnicas)?|"
    r"ficha t[eé]cnica|caracter[ií]sticas(?: del producto| t[eé]cnicas)?|"
    r"datos t[eé]cnicos|detalles t[eé]cnicos|detalles adicionales|"
    r"informaci[oó]n (?:t[eé]cnica|adicional)|"
    r"specifications?|product specifications|technical "
    r"(?:details|specifications?|data)|specs|tech(?:nical)? specs|"
    r"additional (?:details|information)|attributes|"
    r"caract[eé]ristiques(?: techniques)?|fiche technique|"
    r"sp[eé]cifications(?: techniques)?|"
    r"especifica[çc][õo]es(?: t[eé]cnicas)?|"
    r"principais caracter[ií]sticas|caracter[ií]sticas principais|"
    r"d[eé]tails techniques|"
    r"informations techniques|"
    r"(?:key |product |technical |main )?features(?: & specs?|"
    r" and specs?| &amp; specs?)?|highlights|technical highlights|"
    r"puntos (?:clave|destacados)|aspectos destacados)"
    r"\b[\s:.\-–]*",
    re.I,
)

# Zonas que suelen contener tablas y listas ajenas a la ficha técnica.
_ZONA_NO_ESPECIFICACIONES = re.compile(
    r"price|precio|shipping|env[ií]o|delivery|entrega|payment|pago|"
    r"compare|comparaci[oó]n|variant|variante|review|rese[ñn]a|rating|"
    r"related|recommend|upsell|cross.sell|also.bought|breadcrumb|"
    r"newsletter|footer|sidebar|cookie|coupon|cup[oó]n",
    re.I,
)

# Etiquetas que no describen el producto y no deben convertirse en pares.
_CLAVE_NO_ESPECIFICACION = re.compile(
    r"^(?:precio|price|env[ií]o|shipping|entrega|delivery|"
    r"descuento|discount|iva|vat|total|subtotal|cantidad|quantity|"
    r"qty|stock|disponibilidad|disponible|availability|"
    r"unit\s*price|prix\s*unitaire|precio\s*unitario|savings|"
    r"ahorro|price\s*per|precio\s*por|"
    r"cat[eé]gorie|categor[ií]a|category|subcategor|"
    r"añadir|add to|comprar|buy|\d)",
    re.I,
)

_PLAZO = re.compile(
    r"\b\d+\s*(?:months?|years?|meses?|mes|años?|año|mo|yr)\b",
    re.I,
)

_IMPORTE = re.compile(r"[$€£]\s*\d")

# Importes visibles: símbolos y códigos ISO habituales. El símbolo "$"
# por sí solo no identifica la divisa; se completa con la moneda declarada.
_MONEDA_HTML = re.compile(
    r"(?:US\$|R\$|S/\.?|Rs\.?|\$|€|£|₹)\s*\d"
    r"|\b(?:USD|EUR|GBP|BRL|PEN|MXN|COP|CLP|ARS|CAD|AUD|INR|JPY|CNY|CHF)\b\s*\d"
    r"|\d[\d.,]*\s*(?:€|£|₹|"
    r"\b(?:USD|EUR|GBP|BRL|PEN|MXN|COP|CLP|ARS|CAD|AUD|INR|JPY|CNY|CHF)\b)",
    re.I,
)

_ISO_MONEDA = re.compile(r"[A-Z]{3}")

_FISCAL = re.compile(
    r"base\s*imponible|\b(?:iva|vat|tax|impuesto)\b\s*(?::|\d{1,2}\s*%)",
    re.I,
)

_ENVIO = re.compile(
    r"env[ií]o|shipping|delivery|entrega|flete|frete",
    re.I,
)

_CUOTA = re.compile(
    r"cuotas?|installment|financ|mensual|monthly|msi\b|"
    r"\bparcel|\bmeses?\b|\bpago\b",
    re.I,
)

_DESCUENTO = re.compile(
    r"descuento|discount|ahorro|saving|rebaja|promo|descont|\boff\b|%\s*(?:off|dto)",
    re.I,
)

_VIEJO = re.compile(
    r"old|regular|compare|list.?price|was.?price|before|"
    r"anterior|tachado|strikethrough|precio.?viejo|"
    r"precio.?lista|precio.?normal",
    re.I,
)

_TIER = re.compile(
    r"tier|bulk|volume|mayoreo|mayorista|quantity|qty|"
    r"unidades|uds\b|piezas|pcs\b",
    re.I,
)

_TIER_RANGO = re.compile(
    r"\d+\s*(?:[-–—]|\ba\b)\s*\d+",
    re.I,
)

_TIER_ABIERTO = re.compile(
    r"(?:≥|>=|^\s*>|\b(?:más|mas)\s+de\b|^\s*\+|\+\s*$|"
    r"\b(?:min|desde)\b)",
    re.I,
)

_TAGS_IMPORTE = (
    "span, div, p, b, strong, bdi, ins, del, em, i, "
    "td, li, h2, h3, h4, dt, dd, label, a"
)

_STOCK_NEGATIVO = re.compile(
    r"\bout\s*of\s*stock\b|\bsold\s*out\b|\bunavailable\b|"
    r"\bnot\s*available\b|\bno\s+disponible\b|\bsin\s+stock\b|"
    r"\bagotad|\besgotad|\bsem\s+estoque\b|"
    r"\bindispon|\brupture\s+de\s+stock\b",
    re.I,
)

_STOCK_POSITIVO = re.compile(
    r"\bin\s*stock\b|\bavailable\b|\bdisponibles?\b|\bdispon[ií]vel\b|"
    r"\ben\s+stock\b|\bem\s+estoque\b|\bonly\s+\d+\s+left\b|"
    r"\bsolo\s+quedan\s+\d+\b|\benv[ií]o\s+inmediato\b|"
    r"\bready\s+to\s+ship\b|\búltimas\s+unidades\b",
    re.I,
)

_STOCK_PREVENTA = re.compile(
    r"\bpre[- ]?order\b|\bpreventa\b|\bpr[eé]commande\b",
    re.I,
)

_STOCK_PEDIDO = re.compile(
    r"\b(?:on\s+)?back[- ]?order(?:ed)?\b(?!s)|\bbajo\s+pedido\b",
    re.I,
)

# Frases de interfaz y políticas que mencionan stock sin describir el
# estado actual del producto (filtros, avisos, alternativas, variantes).
_STOCK_UI = re.compile(
    r"\bnotify\s+me\b|\bfilters?\b|\bsort(?:ed|ing)?\b|\bcompare\b|"
    r"\bwishlist\b|\bsubscribe\b|\bnewsletter\b|\balerts?\b|"
    r"\bin\s+stock\s+only\b|\bout\s+of\s+stock\s+only\b|"
    r"\balternatives?\b|\bvariations?\b|\boptions?\b|"
    r"\bback[- ]?orders?\s+(?:allowed|accepted|available)\b|"
    r"\ballow(?:ed|s)?\s+back[- ]?orders?\b|"
    r"\bdiscounts?\b|\bcoupons?\b|\bpromotions?\b|\bpromos?\b",
    re.I,
)

_VARIANTE_ATRIBUTOS = (
    "[data-sku], [data-variant], [data-variant-id], [data-option], "
    "[data-option-value]"
)

_TAGS_STOCK = (
    "span, div, p, button, a, li, strong, b, em, small, "
    "td, dt, dd, label, h2, h3, h4, h5"
)

_TAGS_SECCION = {
    "section", "article", "div", "li", "dl", "details", "table",
}

_ETIQUETAS_TITULO = {
    "h1", "h2", "h3", "h4", "h5", "h6", "summary",
}


def _texto_visible(nodo, multilinea=True):
    """Texto de un nodo sin estilos ni scripts, sin modificar el DOM."""

    if nodo is None:
        return ""

    copia = nodo.clone()
    copia.strip_tags([
        "style", "script", "noscript", "template",
        "pre", "code", "kbd", "samp",
    ])

    return copia.text(
        separator="\n" if multilinea else " ",
        strip=True,
    )


def _selector_nodo(nodo):
    """Construye un selector CSS único para recuperar el nodo después."""

    partes = []
    actual = nodo

    while actual is not None and actual.tag != "html":

        padre = actual.parent

        if padre is None:
            break

        indice = 1
        anterior = actual.prev

        while anterior is not None:
            if anterior.tag == actual.tag:
                indice += 1
            anterior = anterior.prev

        partes.append(f"{actual.tag}:nth-of-type({indice})")
        actual = padre

    partes.append("html")
    return " > ".join(reversed(partes))


def _zona_ajena(nodo):
    """Excluye encabezados de navegación, relacionados o pie de página."""

    actual = nodo

    for _ in range(16):

        if actual is None:
            return False

        if actual.tag in {"nav", "footer", "aside"}:
            return True

        if actual.tag in {"html", "body"}:
            # Las clases del documento describen el layout global (por
            # ejemplo, «no-sidebar») y no convierten todo el producto en
            # una zona ajena.
            actual = actual.parent
            continue

        identificacion = (
            f"{actual.attributes.get('id', '')} "
            f"{actual.attributes.get('class', '')}"
        )

        if _ZONA_AJENA.search(identificacion):
            return True

        actual = actual.parent

    return False


def _en_pestanas(nodo):
    """Detecta encabezados que solo etiquetan una pestaña de navegación."""

    actual = nodo

    for _ in range(3):

        if actual is None:
            return False

        role = str(actual.attributes.get("role") or "").lower()
        clases = set(
            str(actual.attributes.get("class") or "").lower().split()
        )

        if role in {"tab", "tablist"}:
            return True

        if (
            actual.tag in {"li", "ul", "ol"}
            and clases & {"tab", "tabs"}
        ):
            return True

        actual = actual.parent

    return False


def _contenido_vinculado(arbol, encabezado):
    """Sigue aria-controls, data-target o href="#id" hacia el contenido."""

    actual = encabezado

    for _ in range(4):

        if actual is None:
            break

        atributos = actual.attributes

        for nombre in (
            "aria-controls", "data-target", "data-controls", "href"
        ):

            valor = atributos.get(nombre) or ""

            if nombre == "href" and not valor.startswith("#"):
                continue

            ident = valor.lstrip("#").strip()

            if not ident:
                continue

            try:
                destino = arbol.css_first(f'[id="{ident}"]')
            except Exception:
                destino = None

            if destino is not None and _texto_visible(destino):
                return destino

        actual = actual.parent

    return None


def _densidad_ficha(texto):
    """Proporción de líneas cortas, típicas de tablas clave-valor."""

    lineas = [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip()
    ]

    if len(lineas) < 6:
        return 0.0

    cortas = sum(
        1 for linea in lineas if len(linea.split()) <= 4
    )

    return cortas / len(lineas)


def _fin_seccion(hermano):
    """Indica si el nodo inicia otra sección o zona ajena."""

    if hermano is None:
        return True

    if hermano.tag in _ETIQUETAS_TITULO:
        return True

    if (
        str(hermano.attributes.get("role") or "").lower()
        == "heading"
    ):
        return True

    return hermano.tag in {"nav", "footer", "aside"}


def _bloques_hermanos(encabezado):
    """Recoge el contenido que sigue al encabezado hasta otra sección."""

    partes = []
    primero = None
    hermano = encabezado.next

    while hermano is not None and len(partes) < 10:

        if hermano.tag == "-text":
            hermano = hermano.next
            continue

        if _fin_seccion(hermano):
            break

        valor = _texto_visible(hermano)

        if valor:
            if primero is None:
                primero = hermano
            partes.append(valor)

        hermano = hermano.next

    if len(partes) == 1:
        return primero, partes[0]

    if partes:
        return encabezado.parent or primero, "\n".join(partes)

    return None, ""


def _compactar(texto):
    """Une líneas visibles y elimina líneas vacías sin perder el orden."""

    return "\n".join(
        linea
        for linea in (
            " ".join(fragmento.split())
            for fragmento in texto.splitlines()
        )
        if linea
    )


def _zona_no_especificaciones(nodo):
    """Evita tablas y listas de precio, envío, comparativas o relacionados."""

    actual = nodo

    for _ in range(12):

        if actual is None:
            return False

        if actual.tag in {"nav", "footer", "aside"}:
            return True

        identificacion = (
            f"{actual.attributes.get('id', '')} "
            f"{actual.attributes.get('class', '')}"
        )

        if _ZONA_NO_ESPECIFICACIONES.search(identificacion):
            return True

        actual = actual.parent

    return False


def _par(clave_dato, valor_dato, max_valor=40, max_clave=8):
    """Normaliza un par clave/valor si ambos son breves y útiles."""

    nombre = " ".join(clave_dato.split()).strip(" :\u00a0")
    valor = " ".join(valor_dato.split()).strip(" :\u00a0")

    if not nombre or not valor:
        return None

    if not re.search(r"\w", nombre) or not re.search(r"\w", valor):
        return None

    if (
        len(nombre.split()) > max_clave
        or len(valor.split()) > max_valor
    ):
        return None

    if _CLAVE_NO_ESPECIFICACION.match(nombre):
        return None

    return f"{nombre}: {valor}"


def _fila_corta(textos, max_palabras=4):
    """Indica si todas las celdas de una fila son etiquetas breves."""

    return bool(textos) and all(
        texto
        and len(texto.split()) <= max_palabras
        for texto in textos
    )


def _filas_tabla(tabla):
    """Devuelve las celdas visibles de cada fila con contenido."""

    filas = []

    for fila in tabla.css("tr"):

        textos = [
            _texto_visible(celda, False)
            for celda in fila.css("th, td")
        ]

        textos = [texto for texto in textos if texto]

        if textos:
            filas.append(textos)

    return filas


def _pares_tabla(tabla):
    """Extrae filas de dos celdas como pares clave/valor.

    También conserva títulos de sección en filas de tres celdas y
    valores de continuación en filas de una sola celda. Descarta las
    tablas de datos con encabezado, que no son fichas clave/valor.
    """

    filas = _filas_tabla(tabla)

    if not filas:
        return []

    primera = filas[0]

    if (
        len(primera) >= 3
        and _fila_corta(primera)
        and any(len(fila) >= 3 for fila in filas[1:])
    ):
        # Tabla de datos con encabezado: no es una ficha clave/valor.
        return []

    pares = []

    for fila in tabla.css("tr"):

        celdas = fila.css("th, td")
        textos = [
            _texto_visible(celda, False) for celda in celdas
        ]

        if len(textos) == 2:

            par = _par(
                textos[0], textos[1],
                max_valor=80, max_clave=24,
            )

            if par:
                pares.append(par)

        elif len(textos) == 3:

            titulo, nombre, valor = textos

            par = _par(
                nombre, valor,
                max_valor=80, max_clave=24,
            )

            if par:
                if (
                    titulo
                    and len(titulo.split()) <= 6
                    and not titulo.endswith(":")
                ):
                    pares.append(titulo)

                pares.append(par)

        elif len(textos) == 1 and pares:

            continuacion = " ".join(textos[0].split())

            if (
                continuacion
                and len(continuacion.split()) <= 12
                and len(pares[-1].split()) <= 30
            ):
                pares[-1] = f"{pares[-1]} {continuacion}"

    return pares


def _pares_dl(lista):
    """Extrae pares dt/dd, incluyendo varios dd para un mismo dt."""

    pares = []

    for termino in lista.css("dt"):

        valores = []
        hermano = termino.next

        while hermano is not None and hermano.tag != "dt":

            if hermano.tag == "dd":
                valores.append(_texto_visible(hermano, False))

            hermano = hermano.next

        if valores:

            par = _par(
                _texto_visible(termino, False),
                ", ".join(v for v in valores if v),
            )

            if par:
                pares.append(par)

    return pares


def _pares_estructurados(arbol):
    """Descubre especificaciones en tablas, dl y listas clave/valor."""

    resultados = []
    vistos = set()

    for nodo in arbol.css("table, dl"):

        if _zona_no_especificaciones(nodo):
            continue

        if nodo.tag == "table":
            pares = _pares_tabla(nodo)
        else:
            pares = _pares_dl(nodo)

        if len(pares) < 3:
            continue

        unicos = []
        control = set()

        for par in pares:

            marca = par.casefold()

            if marca in control:
                continue

            control.add(marca)
            unicos.append(par)

        if len(unicos) < 3:
            continue

        valores = [
            par.split(":", 1)[1] if ":" in par else ""
            for par in unicos
        ]

        plazos = sum(1 for v in valores if _PLAZO.search(v))
        importes = sum(1 for v in valores if _IMPORTE.search(v))

        if (
            plazos / len(unicos) >= 0.6
            or importes / len(unicos) >= 0.6
        ):
            continue

        valor = "\n".join(unicos)

        if valor.casefold() in vistos:
            continue

        vistos.add(valor.casefold())

        resultados.append({
            "valor": valor,
            "fuente": "html",
            "patron": (
                "descubierto::especificaciones::"
                f"{_selector_nodo(nodo)}"
            ),
            "prioridad": 104,
            "estado_patron": "activo",
            "indice": 1,
        })

        if len(resultados) >= 10:
            break

    return resultados


def _descubrir_secciones(campo, fuentes):
    """Descubre descripción y especificaciones por encabezados y relaciones."""

    if campo not in {"descripcion", "especificaciones"}:
        return []

    arbol = fuentes.get("html")

    if arbol is None:
        return []

    patron = (
        _SECCION_ESPECIFICACIONES
        if campo == "especificaciones"
        else _SECCION_DESCRIPCION
    )

    prioridad = 103 if campo == "especificaciones" else 102

    resultados = []
    vistos = set()

    for encabezado in arbol.css(_TITULOS_SECCION):

        titulo = " ".join(encabezado.text(strip=True).split())

        if not titulo or len(titulo) > 160:
            continue

        if not patron.match(titulo):
            continue

        if _zona_ajena(encabezado) or _en_pestanas(encabezado):
            continue

        bloques = []
        destino = _contenido_vinculado(arbol, encabezado)

        if destino is not None:
            bloques.append(
                (destino, _texto_visible(destino), "vinculado")
            )

        elif (
            encabezado.tag == "summary"
            and encabezado.parent is not None
            and encabezado.parent.tag == "details"
        ):
            padre = encabezado.parent
            bloques.append(
                (padre, _texto_visible(padre), "details")
            )

        else:

            padre = encabezado.parent

            candidatos_padre = []

            if padre is not None and padre.tag in _TAGS_SECCION:
                candidatos_padre.append(padre)

            abuelo = padre.parent if padre is not None else None

            if (
                abuelo is not None
                and abuelo.tag in _TAGS_SECCION
                and abuelo is not padre
            ):
                candidatos_padre.append(abuelo)

            for contenedor in candidatos_padre:

                titulos = contenedor.css(_TITULOS_SECCION)
                valor = _texto_visible(contenedor)

                if (
                    len(titulos) <= 1
                    and len(valor) > len(titulo) + 40
                ):
                    bloques.append((contenedor, valor, "contenedor"))
                    break

            if not bloques:

                nodo, valor = _bloques_hermanos(encabezado)

                if nodo is not None and valor:
                    bloques.append((nodo, valor, "hermanos"))

        for nodo, valor, origen in bloques:

            valor = valor.strip()

            if valor.casefold().startswith(titulo.casefold()):
                valor = valor[len(titulo):].strip()

            valor = _compactar(valor)

            if not valor:
                continue

            if (
                campo == "descripcion"
                and _densidad_ficha(valor) > 0.55
            ):
                continue

            selector = _selector_nodo(nodo)

            if (selector, valor[:80]) in vistos:
                continue

            vistos.add((selector, valor[:80]))

            resultados.append({
                "valor": valor,
                "fuente": "html",
                "patron": f"descubierto::{campo}::{selector}",
                "prioridad": prioridad,
                "estado_patron": "activo",
                "indice": 1,
            })

        if len(resultados) >= 12:
            break

    if campo == "especificaciones":
        resultados.extend(_pares_estructurados(arbol))

    return resultados


def _moneda_declarada(fuentes):
    """Obtiene la divisa que la propia página declara para el producto."""

    for grupo in ("meta", "opengraph"):
        datos = fuentes.get(grupo) or {}
        if not isinstance(datos, dict):
            continue
        for clave, valor in datos.items():
            nombre = str(clave).casefold()
            if "currency" not in nombre and nombre not in {"moneda"}:
                continue
            valores = valor if isinstance(valor, list) else [valor]
            for dato in valores:
                codigo = str(dato).strip().upper()
                if _ISO_MONEDA.fullmatch(codigo):
                    return codigo

    for objeto in fuentes.get("jsonld") or []:
        if not isinstance(objeto, dict):
            continue
        for producto in _objetos_tipo(objeto):
            for ruta in (
                "offers.priceCurrency",
                "Offers.PriceCurrency",
                "priceCurrency",
            ):
                for dato in _ruta(producto, ruta):
                    codigo = str(dato).strip().upper()
                    if _ISO_MONEDA.fullmatch(codigo):
                        return codigo

    return None


def _con_moneda(texto, moneda):
    """Completa importes visibles con la divisa declarada por la página.

    No sustituye símbolos que ya identifican otra divisa (€, £, R$, S/,
    ₹). El símbolo "$" es ambiguo y solo se resuelve con esa declaración.
    """

    if not moneda or not isinstance(texto, str) or not texto.strip():
        return texto

    if re.search(
        r"\b(?:USD|EUR|GBP|BRL|PEN|MXN|COP|CLP|ARS|CAD|AUD|INR|JPY|CNY|CHF)\b",
        texto,
        re.I,
    ):
        return texto

    if re.search(r"[€£₹]|R\$|S/\.?|Rs\.?", texto, re.I):
        return texto

    if not re.search(r"\$|\d", texto):
        return texto

    limpio = re.sub(r"^(?:US)?\$\s*", "", texto.strip())

    return f"{moneda} {limpio}" if limpio else texto


def _hijo_con_importe(nodo):
    """Indica si un hijo directo ya contiene el importe (nodo contenedor)."""

    hijo = nodo.child

    while hijo is not None:

        if hijo.tag not in {"-text", "-comment", "script", "style"}:
            texto = " ".join(
                (hijo.text(separator=" ", strip=True) or "").split()
            )
            if len(texto) <= 120 and _MONEDA_HTML.search(texto):
                return True

        hijo = hijo.next

    return False


def _titulo_para_precio(arbol):
    """Elige un encabezado de producto, evitando logos y cabeceras."""

    for nodo in arbol.css("h1, h2"):

        texto = " ".join((nodo.text(strip=True) or "").split())

        if len(texto) < 8:
            continue

        marcas = " ".join(
            [
                str(nodo.attributes.get("id") or ""),
                str(nodo.attributes.get("class") or ""),
            ]
            + [
                f"{a.attributes.get('id', '')} "
                f"{a.attributes.get('class', '')}"
                for a in _ancestros_precio(nodo, 3)
            ]
        )

        if re.search(r"logo|site.?title|brand", marcas, re.I):
            continue

        if re.search(r"\b(?:nav|header|footer)\b", marcas, re.I):
            continue

        return nodo

    return None


def _ancestros_precio(nodo, limite=4):
    """Recorre los ancestros cercanos sin incluir el propio nodo."""

    actual = nodo.parent
    vistos = 0

    while actual is not None and vistos < limite:
        yield actual
        actual = actual.parent
        vistos += 1


def _etiqueta_cantidad(nodo):
    """Busca una etiqueta de tramo junto al importe (500-999, ≥1000...)."""

    for origen in (nodo, nodo.parent):

        if origen is None:
            continue

        hermano = origen.next
        saltos = 0

        while hermano is not None and saltos < 3:

            if hermano.tag not in {"-text", "-comment"}:
                texto = " ".join(
                    (hermano.text(separator=" ", strip=True) or "").split()
                )
                if texto and len(texto) <= 60:
                    if re.search(r"\d", texto):
                        return texto
                    break
                if texto:
                    break

            hermano = hermano.next
            saltos += 1

    return ""


def _clasificar_precio(nodo, texto):
    """Clasifica un importe visible por su papel en la ficha.

    Devuelve actual, viejo, cuota, descuento, envio, fiscal,
    cantidad_base o cantidad_alta.
    """

    marcas = " ".join(
        [
            str(nodo.attributes.get("id") or ""),
            str(nodo.attributes.get("class") or ""),
        ]
        + [
            f"{a.attributes.get('id', '')} "
            f"{a.attributes.get('class', '')}"
            for a in _ancestros_precio(nodo)
        ]
    )

    junto = f"{marcas} {texto}"

    if _FISCAL.search(junto):
        return "fiscal"

    if _ENVIO.search(junto):
        return "envio"

    if _CUOTA.search(junto):
        return "cuota"

    if _DESCUENTO.search(junto):
        return "descuento"

    if nodo.tag in {"del", "s"} or _VIEJO.search(marcas):
        return "viejo"

    if re.search(r"tachado|strikethrough|line.?through", marcas, re.I):
        return "viejo"

    etiqueta = _etiqueta_cantidad(nodo)

    tiene_tramo = bool(
        etiqueta
        and re.search(r"\d", etiqueta)
        and (
            _TIER_RANGO.search(etiqueta)
            or _TIER_ABIERTO.search(etiqueta)
        )
    )

    if tiene_tramo:
        return (
            "cantidad_alta"
            if _TIER_ABIERTO.search(etiqueta)
            else "cantidad_base"
        )

    if _TIER.search(marcas):
        return "cantidad_base"

    return "actual"


def _descubrir_precios(fuentes):
    """Descubre importes visibles próximos al título del producto.

    Solo conserva los nodos que comparten con el título la región más
    específica de la página. Así se excluyen menús, carritos y bloques de
    productos relacionados sin depender de selectores de una tienda.
    """

    arbol = fuentes.get("html")

    if arbol is None:
        return []

    titulo = _titulo_para_precio(arbol)

    if titulo is None:
        return []

    ruta_titulo = _selector_nodo(titulo).split(" > ")

    moneda = _moneda_declarada(fuentes)

    candidatos = []

    for nodo in arbol.css(_TAGS_IMPORTE):

        if nodo.tag in {"script", "style", "noscript", "template"}:
            continue

        texto = " ".join(
            (nodo.text(separator=" ", strip=True) or "").split()
        )

        if not texto or len(texto) > 90:
            continue

        if not _MONEDA_HTML.search(texto):
            continue

        if _hijo_con_importe(nodo):
            continue

        if _zona_ajena(nodo):
            continue

        ruta = _selector_nodo(nodo).split(" > ")

        comun = 0
        while (
            comun < len(ruta_titulo)
            and comun < len(ruta)
            and ruta_titulo[comun] == ruta[comun]
        ):
            comun += 1

        candidatos.append((comun, nodo, texto))

    if not candidatos:
        return []

    profundidad = max(comun for comun, _, _ in candidatos)
    limite = profundidad - 1

    resultados = []
    vistos = set()

    for comun, nodo, texto in candidatos:

        if comun < limite:
            continue

        selector = _selector_nodo(nodo)

        if selector in vistos:
            continue

        vistos.add(selector)

        categoria = _clasificar_precio(nodo, texto)

        resultados.append({
            "valor": _con_moneda(texto, moneda),
            "fuente": "html",
            "patron": (
                f"descubierto::precio::{categoria}::{selector}"
            ),
            "prioridad": 100,
            "estado_patron": "activo",
            "indice": 1,
        })

        if len(resultados) >= 16:
            break

    return resultados


def _clasificar_stock(texto):
    """Clasifica una frase visible sobre la disponibilidad del producto.

    Devuelve agotado, disponible, preventa, bajo_pedido, contradictorio
    o None cuando la frase no aporta información de stock.
    """

    if _STOCK_UI.search(texto):
        return None

    negativo = _STOCK_NEGATIVO.search(texto)

    sin_negaciones = _STOCK_NEGATIVO.sub(" ", texto)

    positivo = _STOCK_POSITIVO.search(sin_negaciones)

    if _STOCK_PREVENTA.search(texto):
        return "preventa"

    if _STOCK_PEDIDO.search(texto):
        return "bajo_pedido"

    if negativo and positivo:
        return "contradictorio"

    if negativo:
        return "agotado"

    if positivo:
        return "disponible"

    return None


def _hijo_con_stock(nodo):
    """Indica si un hijo directo ya contiene la frase de stock."""

    hijo = nodo.child

    while hijo is not None:

        if hijo.tag not in {"-text", "-comment", "script", "style"}:
            texto = " ".join(
                (hijo.text(separator=" ", strip=True) or "").split()
            )
            if len(texto) <= 120 and _clasificar_stock(texto):
                return True

        hijo = hijo.next

    return False


def _prefijo_comun(ruta_a, ruta_b):
    """Longitud del prefijo estructural compartido por dos rutas."""

    comun = 0

    while (
        comun < len(ruta_a)
        and comun < len(ruta_b)
        and ruta_a[comun] == ruta_b[comun]
    ):
        comun += 1

    return comun


def _hay_variantes_cercanas(arbol, ruta_titulo):
    """Detecta selectores de variante dentro de la región del producto.

    Cuando existen, una etiqueta de stock puede describir solo la variante
    activa y no el producto completo. No se usa como selector de tienda,
    sino como señal de que hay varias opciones de compra.
    """

    umbral = max(5, len(ruta_titulo) // 2)

    for nodo in arbol.css("select"):

        opciones = [hijo for hijo in nodo.iter() if hijo.tag == "option"]

        if len(opciones) < 2:
            continue

        ruta = _selector_nodo(nodo).split(" > ")

        if _prefijo_comun(ruta_titulo, ruta) >= umbral:
            return True

    cercanos = 0

    for nodo in arbol.css(_VARIANTE_ATRIBUTOS):

        atributos = nodo.attributes

        valor = (
            atributos.get("data-sku")
            or atributos.get("data-variant")
            or atributos.get("data-variant-id")
            or atributos.get("data-option")
            or atributos.get("data-option-value")
        )

        if not valor:
            continue

        ruta = _selector_nodo(nodo).split(" > ")

        if _prefijo_comun(ruta_titulo, ruta) >= umbral:
            cercanos += 1

        if cercanos >= 2:
            return True

    return False


def _descubrir_disponibilidad(fuentes):
    """Descubre frases de stock visibles próximas al título del producto.

    Aplica el mismo criterio de región que los precios: conserva solo los
    nodos que comparten con el título la región más específica de la
    página, para excluir menús, avisos de la tienda y productos
    relacionados sin depender de selectores de una tienda concreta.
    """

    arbol = fuentes.get("html")

    if arbol is None:
        return []

    titulo = _titulo_para_precio(arbol)

    if titulo is None:
        return []

    ruta_titulo = _selector_nodo(titulo).split(" > ")

    variantes = _hay_variantes_cercanas(arbol, ruta_titulo)

    candidatos = []

    for nodo in arbol.css(_TAGS_STOCK):

        if nodo.tag in {"script", "style", "noscript", "template"}:
            continue

        texto = " ".join(
            (nodo.text(separator=" ", strip=True) or "").split()
        )

        if not texto or len(texto) > 120:
            continue

        categoria = _clasificar_stock(texto)

        if categoria is None:
            continue

        if _hijo_con_stock(nodo):
            continue

        if _zona_ajena(nodo):
            continue

        ruta = _selector_nodo(nodo).split(" > ")

        comun = 0
        while (
            comun < len(ruta_titulo)
            and comun < len(ruta)
            and ruta_titulo[comun] == ruta[comun]
        ):
            comun += 1

        candidatos.append((comun, nodo, texto, categoria))

    if not candidatos:
        return []

    profundidad = max(comun for comun, _, _, _ in candidatos)
    limite = profundidad - 1

    resultados = []
    vistos = set()

    for comun, nodo, texto, categoria in candidatos:

        if comun < limite:
            continue

        selector = _selector_nodo(nodo)

        if (selector, texto[:80]) in vistos:
            continue

        vistos.add((selector, texto[:80]))

        resultados.append({
            "valor": texto,
            "fuente": "html",
            "patron": (
                "descubierto::disponibilidad::"
                f"{'variante_' if variantes else ''}"
                f"{categoria}::{selector}"
            ),
            "prioridad": 100,
            "estado_patron": "activo",
            "indice": 1,
        })

        if len(resultados) >= 12:
            break

    return resultados


def _candidatos(campo, fuentes, patrones):
    """
    Localiza candidatos utilizando los patrones configurados.

    La deduplicación definitiva se realiza en filtros.py.
    No descarta coincidencias iguales de distintos nodos HTML,
    porque pueden pertenecer a contextos diferentes.
    """
    reglas = sorted(
        patrones["campos"][campo],
        key=lambda regla: regla.get("prioridad", 0),
        reverse=True,
    )

    encontrados = []

    moneda_pagina = (
        _moneda_declarada(fuentes) if campo == "precio" else None
    )

    for regla in reglas:

        for indice, dato in _extraer_regla(campo, regla, fuentes):

            texto = _limpiar(dato)

            if campo == "descripcion" and isinstance(dato, str):
                fragmento = html_std.unescape(dato)
                if re.search(r"<p(?:\s|>)", fragmento, re.I):
                    from selectolax.lexbor import LexborHTMLParser

                    arbol_fragmento = LexborHTMLParser(fragmento)
                    if arbol_fragmento.body is not None:
                        texto = _prosa_antes_de_apendice(arbol_fragmento.body) or texto

            if not texto:
                continue

            if campo == "precio":

                if not re.search(r"\d", texto):
                    continue

                if re.fullmatch(
                    r"\s*\d+(?:[.,]\d+)?\s*%\s*(?:off!?|descuento)?\s*",
                    texto,
                    re.I,
                ):
                    continue

                texto = _con_moneda(texto, moneda_pagina)

            if campo == "disponibilidad" and re.search(
                r"cannot be shipped|not deliverable|no se env[ií]a",
                texto,
                re.I,
            ):
                continue

            if campo == "nombre" and len(texto) < 4:
                continue

            encontrados.append({
                "valor": texto,
                "fuente": regla["fuente"].lower(),
                "patron": regla.get(
                    "selector",
                    regla.get("ruta", regla.get("clave", ""))
                ),
                "prioridad": regla.get("prioridad", 0),
                "estado_patron": regla.get("estado", "activo"),
                "indice": indice,
            })

    if campo in {"descripcion", "especificaciones"}:
        encontrados.extend(_descubrir_secciones(campo, fuentes))

    if campo == "precio":
        encontrados.extend(_descubrir_precios(fuentes))

    if campo == "disponibilidad":
        encontrados.extend(_descubrir_disponibilidad(fuentes))

    return encontrados


def _elegir(campo, fuentes, patrones, detalle=False):
    candidatos = _candidatos(campo, fuentes, patrones)
    if not candidatos:
        return (None, []) if detalle else None

    if campo != "especificaciones":
        resultado = candidatos[0]["valor"]
    else:
        # Recoger varios bloques técnicos cuando existan. La validación
        # semántica se hará después; aquí NO filtramos por palabras o unidades.
        prioridad_maxima = candidatos[0]["prioridad"]
        limite = prioridad_maxima - 18
        bloques = []
        for candidato in candidatos:
            if candidato["prioridad"] < limite:
                continue
            texto = candidato["valor"]
            if any(texto in existente for existente in bloques):
                continue
            bloques = [existente for existente in bloques if existente not in texto]
            bloques.append(texto)
            if len(bloques) >= 4:
                break
        resultado = "\n\n".join(bloques)

    return (resultado, candidatos) if detalle else resultado


def localizar_nombre(fuentes, patrones, detalle=False):
    return _elegir("nombre", fuentes, patrones, detalle)


def localizar_precio(fuentes, patrones, detalle=False):
    return _elegir("precio", fuentes, patrones, detalle)


def localizar_disponibilidad(fuentes, patrones, detalle=False):
    return _elegir("disponibilidad", fuentes, patrones, detalle)


def localizar_descripcion(fuentes, patrones, detalle=False):
    return _elegir("descripcion", fuentes, patrones, detalle)


def localizar_especificaciones(fuentes, patrones, detalle=False):
    return _elegir("especificaciones", fuentes, patrones, detalle)
