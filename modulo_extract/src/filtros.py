
"""Extract - filtros integrados para los cinco campos.

Entrada: JSON de coincidencias brutas en memoria y árbol Lexbor de Selectolax.
Salida: ficha candidata + diagnósticos. No descarga URLs ni exige archivos.

Funciones usadas por main3.py:
    leer_candidatos_brutos, agrupar_duplicados,
    select_nombre, select_precio, select_stock,
    select_descripcion, select_especificaciones, validar_ficha.

Nota: heurísticas de PoC. Mantiene la evidencia; una selección no garantiza exactitud.
"""

import html as html_lib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser

CAMPOS = ("nombre", "precio", "disponibilidad", "descripcion", "especificaciones")

SECUNDARIAS = re.compile(
    r"related|recommend|upsell|cross.?sell|similar.?product|recently.?viewed|"
    r"also.?bought|you.?may.?like|mini.?cart|breadcrumb|newsletter|"
    r"product.?card|product.?tile|product.?item|products?.?grid|product.?listing|"
    r"product.?loop|wd.?products?.?nav|wd.?product.?wrapper|"
    r"swiper|slick.?slide|owl.?item|uk.?slider|carousel|best.?selling",
    re.I,
)

ANCLAS = {
    "product-info-main", "product-info-price", "product-detail-main",
    "product-details-main", "product-detail", "product-details",
    "product-main", "product-summary", "product-description",
    "product-specifications", "product-specification", "product-attributes",
    "product-technical-details", "product-overview", "product-features",
    "product-information", "product-data", "product-form", "entry-summary",
    "woocommerce-product-details-short-description",
}

TITULOS = (
    "h1.product_title", "h1.product-name", "h1.product-title",
    "#productName h1", ".product-info-main h1", "main h1", "h1",
    "h2.product_title", "h3.product_title", "h2.product-title",
    "h3.product-title", "h2.product-name", "h3.product-name",
)

CODIGO = re.compile(
    r"(?:function\s*\([^)]*\)\s*\{|document\.querySelector\s*\(|"
    r"window\.[\w$]+\s*\(|"
    r"[.#][\w-]+\s*\{\s*[\w-]+\s*:|"
    r"\b(?:display|font-size|background-color|position)\s*:\s*[^;]{1,80};)",
    re.I,
)

TECNICO = re.compile(
    r"\b(?:ram|ssd|cpu|gpu|usb|hdmi|voltaje|voltage|potencia|power|"
    r"procesador|memoria|memory|modelo|model|capacidad|capacity|"
    r"pantalla|screen|dimensiones|dimensions|resoluci[oó]n|resolution|"
    r"caracter[ií]sticas|especificaciones|specifications|technical|"
    r"bluetooth|wi.?fi|ethernet|frecuencia|frequency)\b|"
    r"\b\d+(?:[.,]\d+)?\s*(?:gb|tb|mhz|ghz|mah|wh|w|v|a|mm|cm|kg|hz)\b",
    re.I,
)

PATRON_TECNICO = re.compile(
    r"spec|especific|caracter|technical|attribute|feature|product.?data|"
    r"tech.?detail|ficha|details.?content|tab.?additional",
    re.I,
)


# ============================================================
# 1. LIMPIEZA DE CONTENIDO
# ============================================================

class _TextoHTML(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self.oculto = [], 0

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta in {"script", "style", "noscript"}:
            self.oculto += 1

        elif not self.oculto and etiqueta in {
            "p", "div", "li", "br", "tr", "section"
        }:
            self.partes.append("\n")
            if etiqueta == "li":
                self.partes.append("- ")

    def handle_endtag(self, etiqueta):
        if etiqueta in {"script", "style", "noscript"}:
            self.oculto = max(0, self.oculto - 1)

        elif not self.oculto and etiqueta in {
            "p", "div", "li", "tr", "section"
        }:
            self.partes.append("\n")

    def handle_data(self, datos):
        if not self.oculto:
            self.partes.append(datos)


def limpiar(valor, multilinea=False):
    """Limpia texto sin alterar su significado técnico."""

    if not isinstance(valor, str):
        return valor

    texto = valor

    if re.search(
        r"</?(?:p|div|ul|li|span|br|table|tr|td|style|script)\b",
        texto,
        re.I
    ):
        lector = _TextoHTML()
        lector.feed(texto)
        texto = "".join(lector.partes)

    for _ in range(2):
        nuevo = html_lib.unescape(texto)

        if nuevo == texto:
            break

        texto = nuevo

    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\xa0", " ").replace("\u202f", " ")
    texto = re.sub(r"[\u200b-\u200d\ufeff]", "", texto)

    if multilinea:
        lineas = [
            " ".join(linea.split())
            for linea in texto.splitlines()
        ]

        return re.sub(
            r"\n{3,}",
            "\n\n",
            "\n".join(lineas)
        ).strip()

    return " ".join(texto.split())


def clave(valor):
    """Normalización para comparación de duplicados."""

    if not isinstance(valor, str):
        return json.dumps(
            valor,
            ensure_ascii=False,
            sort_keys=True,
            default=str
        )

    valor = unicodedata.normalize("NFKC", valor).casefold()

    valor = (
        valor.replace("″", '"')
        .replace("“", '"')
        .replace("”", '"')
    )

    return " ".join(valor.split())


# ============================================================
# 2. IDENTIFICACIÓN DEL CONTEXTO DOM
# ============================================================

def _ancestros(nodo):

    while nodo is not None:
        yield nodo
        nodo = nodo.parent


def _marcas(nodo):

    attrs = nodo.attributes

    return [
        attrs.get("id") or ""
    ] + (attrs.get("class") or "").split()


def _ruta(nodo):
    """Obtiene una ruta estructural del nodo HTML."""

    if nodo is None:
        return None

    partes = []

    for actual in _ancestros(nodo):
        indice = 1
        anterior = getattr(actual, "prev", None)

        while anterior is not None:
            if anterior.tag == actual.tag:
                indice += 1

            anterior = getattr(anterior, "prev", None)

        partes.append(f"{actual.tag}[{indice}]")

    return "/".join(reversed(partes))


def _contiene(raiz, nodo):

    a, b = _ruta(raiz), _ruta(nodo)

    return bool(
        a and b and (
            b == a or b.startswith(a + "/")
        )
    )


def _secundaria(nodo, titulo=None):
    """Detecta contenedores ajenos al producto principal."""

    for ancestro in _ancestros(nodo):

        if ancestro.tag in {
            "header", "footer", "nav", "aside"
        }:
            return True

        if ancestro.tag in {"html", "body"}:
            break

        marcas = _marcas(ancestro)

        if any(
            re.search(
                r"(?:^|[-_])sidebar(?:$|[-_])",
                m,
                re.I
            )
            for m in marcas
        ):
            return True

        if any(SECUNDARIAS.search(m) for m in marcas):
            if titulo is None or not _contiene(
                ancestro, titulo
            ):
                return True

    return False


def _titulo_principal(arbol):
    """Localiza un encabezado representativo del producto."""

    for selector in TITULOS:

        try:
            nodos = arbol.css(selector)
        except Exception:
            continue

        for nodo in nodos:
            if (
                nodo.text(strip=True)
                and not _secundaria(nodo)
            ):
                return nodo

    return None


def _raiz_titulo(titulo):

    if titulo is None:
        return None

    fuertes = {
        "product-info-main",
        "product-detail-main",
        "product-details-main",
        "product-details",
        "product-detail",
        "product-main",
        "product-summary",
        "product-page",
        "product-view",
        "type-product",
        "single-product",
    }

    for ancestro in _ancestros(titulo.parent):

        marcas = {
            m.lower().replace("_", "-")
            for m in _marcas(ancestro)
        }

        if marcas & fuertes:
            return ancestro

    return None


_COMPRA = re.compile(
    r"add to (?:cart|basket|bag)|buy now|in stock|pre.?order|"
    r"comprar|añadir al carrito|agregar al carrito|en stock",
    re.I,
)


def _es_region_principal(nodo):
    """Reconoce contenedores semánticos del contenido principal."""

    marcas = {
        m.lower().replace("_", "-")
        for m in _marcas(nodo)
    }

    return (
        nodo.tag == "main"
        or str(nodo.attributes.get("role") or "").lower()
        == "main"
        or bool(marcas & {"main", "content", "primary"})
    )


def _evidencia_producto(region):
    """Busca señales de ficha de producto dentro de una región."""

    try:
        if region.css_first(
            '[itemtype*="Product"], [itemprop="price"], '
            '[itemprop="offers"]'
        ):
            return 2
    except Exception:
        pass

    try:
        controles = region.css(
            'form[action*="cart"], a[href*="cart"], '
            'button, input[type="submit"]'
        )
    except Exception:
        return 0

    for nodo in controles[:40]:

        texto = (
            nodo.text(strip=True)
            or nodo.attributes.get("value")
            or ""
        )

        if _COMPRA.search(texto):
            return 1

    return 0


def _main_titulo(arbol, titulo):
    """Elige la región principal aunque no exista un encabezado."""

    regiones = {}

    for nodo in arbol.css(
        "main, [role=main], #main, #content, #primary"
    ):

        if nodo.tag in {"html", "body"}:
            continue

        ruta = _ruta(nodo)

        if ruta and ruta not in regiones:
            regiones[ruta] = nodo

    if not regiones:
        return None

    candidatas = list(regiones.values())

    if titulo is not None:

        contienen = [
            r
            for r in candidatas
            if _contiene(r, titulo)
        ]

        if contienen:
            return min(
                contienen,
                key=lambda r: len(_ruta(r) or "")
            )

    con_evidencia = [
        r
        for r in candidatas
        if _evidencia_producto(r)
    ]

    if con_evidencia:
        return max(
            con_evidencia,
            key=lambda r: len(r.text(strip=True))
        )

    return max(
        candidatas,
        key=lambda r: len(r.text(strip=True))
    )


def _contexto(nodo, titulo, raiz, contenedor):

    if nodo is None:
        return "indeterminado"

    if any(
        a.tag == "head"
        for a in _ancestros(nodo)
    ):
        return "sin_contexto_dom"

    if _secundaria(nodo, titulo):
        return "zona_ajena_probable"

    if titulo is not None and _ruta(nodo) == _ruta(titulo):
        return "principal_probable"

    if raiz is not None and _contiene(raiz, nodo):
        return "principal_probable"

    for ancestro in _ancestros(nodo):

        if ancestro.tag in {"html", "body"}:
            break

        marcas = {
            m.lower().replace("_", "-")
            for m in _marcas(ancestro)
        }

        if (
            marcas & ANCLAS
            or {"product", "attribute", "description"} <= marcas
        ):
            if (
                contenedor is not None
                and not _contiene(contenedor, nodo)
            ):
                return "contexto_amplio"

            return "principal_probable"

    if (
        contenedor is not None
        and _contiene(contenedor, nodo)
    ):
        return "contexto_amplio"

    return "indeterminado"


# ============================================================
# 3. INTERPRETACIÓN DE PRECIOS
# ============================================================

def _importe_simple(texto):
    """Interpreta importes evitando seleccionar rangos ambiguos."""

    texto = texto.strip()

    caso_euro = re.fullmatch(
        r"([\d][\d .]*)\s*€\s*(\d{2})",
        texto
    )

    if caso_euro:
        entero = (
            caso_euro.group(1)
            .replace(" ", "")
            .replace(".", "")
        )

        return f"{entero}.{caso_euro.group(2)}"

    texto = re.sub(
        r"\b(?:IVA|VAT|tax)\s*\d{1,2}\s*%",
        "",
        texto,
        flags=re.I
    )

    valores = re.findall(
        r"(?<!\w)\d+(?:[\s.,]\d+)*(?!\w)",
        texto
    )

    if len(valores) != 1:
        return None

    numero = (
        re.sub(r"\s+", "", valores[0])
        .rstrip(".,")
    )

    if "." in numero and "," in numero:

        decimal = (
            "."
            if numero.rfind(".") > numero.rfind(",")
            else ","
        )

        miles = "," if decimal == "." else "."

        numero = (
            numero.replace(miles, "")
            .replace(decimal, ".")
        )

    elif "," in numero or "." in numero:

        sep = "," if "," in numero else "."
        partes = numero.split(sep)

        if (
            len(partes) == 2
            and len(partes[1]) in {1, 2, 4}
        ):
            numero = partes[0] + "." + partes[1]

        elif (
            len(partes) >= 2
            and all(len(p) == 3 for p in partes[1:])
        ):
            numero = "".join(partes)

        else:
            return None

    try:
        return format(
            Decimal(numero).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            ".2f",
        )
    except (InvalidOperation, ValueError):
        return None


def _precio(texto):

    moneda = None

    if re.search(r"\bBRL\b|R\$", texto, re.I):
        moneda = "BRL"

    elif re.search(r"\bUSD\b|US\$", texto, re.I):
        moneda = "USD"

    elif re.search(r"\bEUR\b|€", texto, re.I):
        moneda = "EUR"

    elif re.search(r"\bGBP\b|£", texto, re.I):
        moneda = "GBP"

    elif re.search(r"\bINR\b|₹|\bRs\.?\s", texto, re.I):
        moneda = "INR"

    elif re.search(r"\bS/\s*\d", texto, re.I):
        moneda = "PEN"

    else:
        for iso in (
            "COP", "MXN", "CLP", "PEN", "ARS", "CAD",
            "AUD", "JPY", "CNY", "CHF",
        ):
            if re.search(rf"\b{iso}\b", texto, re.I):
                moneda = iso
                break

    iva = None

    if re.search(
        r"incl\.?\s*iva|iva\s+inclu|"
        r"incluye\s+iva|tax\s+included|ttc",
        texto,
        re.I
    ):
        iva = "incluido"

    elif re.search(
        r"sin\s+iva|\+\s*iva|"
        r"excl\.?\s*iva|excl\.?\s*vat",
        texto,
        re.I
    ):
        iva = "excluido"

    return {
        "importe": _importe_simple(texto),
        "moneda": moneda,
        "iva": iva,
        "simbolo_dolar_ambiguo": (
            "$" in texto and moneda is None
        )
    }


# ============================================================
# 4. INTERPRETACIÓN DE DISPONIBILIDAD
# ============================================================

def _stock(texto):

    texto = re.sub(
        r"^https?://(?:www\.)?schema\.org/",
        "",
        texto.strip(),
        flags=re.I
    )

    # Algunas fichas publican el inventario como cantidad sin etiqueta
    # (por ejemplo, AvailableQuantity: 84). Un entero positivo indica
    # unidades disponibles; cero, agotado.
    if re.fullmatch(r"\d+", texto):
        cantidad = int(texto)
        return {
            "estado": "disponible" if cantidad > 0 else "agotado",
            "cantidad": cantidad,
        }

    patron_negativo = (
        r"out\s*of\s*stock|sold\s*out|"
        r"unavailable|not\s*available|"
        r"no\s+disponible|sin\s+stock|"
        r"agotad|esgotad|sem\s+estoque|"
        r"indispon|rupture\s+de\s+stock"
    )

    negativo = bool(
        re.search(patron_negativo, texto, re.I)
    )

    sin_negaciones = re.sub(
        patron_negativo,
        " ",
        texto,
        flags=re.I
    )

    positivo = bool(
        re.search(
            r"\bin\s*stock\b|\bavailable\b|\bdisponibles?\b|"
            r"\bdispon[ií]vel\b|\ben\s+stock\b|"
            r"\bem\s+estoque\b|\bonly\s+\d+\s+left\b|"
            r"\bsolo\s+quedan\s+\d+\b",
            sin_negaciones,
            re.I
        )
    )

    if negativo and positivo:
        estado = "contradictorio"

    elif negativo:
        estado = "agotado"

    elif re.search(
        r"pre[- ]?order|preventa|pr[eé]commande",
        texto,
        re.I
    ):
        estado = "preventa"

    elif re.search(
        r"\b(?:on\s+)?back[- ]?order(?:ed)?\b(?!s)|"
        r"\bbajo\s+pedido\b",
        texto,
        re.I
    ):
        estado = "bajo_pedido"

    else:
        estado = "disponible" if positivo else "desconocido"

    cantidad = re.search(
        r"only\s+(\d+)\s+left|solo\s+quedan\s+(\d+)",
        texto,
        re.I
    )

    return {
        "estado": estado,
        "cantidad": (
            int(cantidad.group(1) or cantidad.group(2))
            if cantidad else None
        )
    }


# ============================================================
# 5. VALIDACIÓN DEL CONTENIDO
# ============================================================

def _partes_patron(patron):
    """Separa campo, categoría y selector de un patrón descubierto.

    Formato actual: descubierto::campo::[categoria::]selector.
    """

    partes = str(patron or "").split("::", 3)

    if len(partes) == 4 and partes[0] == "descubierto":
        return partes[1], partes[2], partes[3]

    if len(partes) == 3 and partes[0] == "descubierto":
        return partes[1], None, partes[2]

    return None, None, patron


def _validar(c):

    campo = c["campo"]
    valor = c["valor_limpio"]

    if not isinstance(valor, str) or not valor.strip():
        return False, -100, "valor_vacio_o_no_textual"

    if (
        CODIGO.search(valor)
        and campo in {
            "nombre", "descripcion", "especificaciones"
        }
    ):
        return False, -80, "posible_codigo_css_js"

    if campo == "nombre":

        if (
            len(valor) < 5
            or len(valor) > 280
            or valor.casefold() in {
                "inicio", "home", "search",
                "buscar", "productos", "shop",
                "tienda", "descripcion", "description"
            }
        ):
            return False, -100, "nombre_generico"

        return True, 5, "nombre_plausible"

    if campo == "precio":

        if c["interpretacion"]["importe"] is None:
            return False, -100, "precio_ambiguo"

        return True, 6, "importe_interpretable"

    if campo == "disponibilidad":

        if c["interpretacion"]["estado"] in {
            "desconocido", "contradictorio"
        }:
            return False, -100, "estado_desconocido"

        return True, 6, "estado_interpretable"

    if len(valor) < 12 or len(valor) > 25000:
        return False, -100, "longitud_inadecuada"

    if campo == "especificaciones":

        hay_tecnicas = bool(TECNICO.search(valor))

        if not hay_tecnicas and len(valor) < 45:
            return False, -30, "sin_indicios_tecnicos"

        return (
            True,
            10 if hay_tecnicas else -4,
            "bloque_tecnico_probable"
        )

    # Una lista breve de categorías en mayúsculas no es una descripción
    # narrativa; conservarla como respaldo, sin privilegiar su fuente.
    if len(valor) < 80 and valor.isupper() and valor.count(",") >= 2:
        return True, -15, "descripcion_probable_lista_categorias"

    return (
        True,
        min(len(valor) // 150, 10),
        "descripcion_plausible"
    )


# ============================================================
# 6. PUNTUACIÓN DE RELEVANCIA
# ============================================================

def _puntuar(c):

    if not c["valido"]:
        return -9999

    score = {
        "principal_probable": 40,
        "contexto_amplio": 8,
        "sin_contexto_dom": 5,
        "indeterminado": -5,
        "zona_ajena_probable": -150,
    }.get(c["contexto"], -10)

    score += {
        "html": 12,
        "jsonld": 20,
        "microdata": 9,
        "opengraph": 10,
        "meta": 5,
        "json_embebido": 12,
    }.get(c["fuente"], 0)

    score += c["puntos_contenido"]

    patron = c["patron"].lower()

    if patron.startswith("descubierto::especificaciones::"):
        score += 20

    elif patron.startswith("descubierto::descripcion::"):
        score += 10

    campo = c["campo"]

    if campo == "nombre":

        if re.search(r"\bh1\b", patron):
            score += 20

        elif re.search(r"\bh[23]\b", patron):
            score += 14

        if (
            c["fuente"] in {"opengraph", "meta"}
            or patron == "title"
        ):
            score -= 8

    if campo == "precio":

        if "offers.price" in patron:
            score += 6

        categoria = _partes_patron(patron)[1]

        if categoria:
            score += {
                "actual": 10,
                "cantidad_base": 4,
                "cantidad_alta": -6,
                "viejo": -25,
                "cuota": -35,
                "descuento": -40,
                "envio": -45,
                "fiscal": -50,
            }.get(categoria, 0)

        # Una oferta estructurada con moneda ISO identifica importe y
        # divisa de la misma entidad. Prevalece sobre importes visibles
        # que solo muestran un símbolo ambiguo, salvo que otra regla
        # detecte un tramo de cantidad distinto del principal.
        if (
            c["fuente"] in {"jsonld", "microdata", "json_embebido"}
            and c["interpretacion"]
            and c["interpretacion"].get("moneda")
        ):
            score += 40

        if re.search(
            r"old|regular|compare|tier|bulk",
            patron
        ):
            score -= 12

        if re.search(
            r"desde|from|as low as|qty|bulk|por mayor",
            c["valor_limpio"],
            re.I
        ):
            score -= 15

    if campo in {"descripcion", "especificaciones"}:

        if PATRON_TECNICO.search(patron):
            score += (
                18 if campo == "especificaciones" else -4
            )

        if (
            campo == "especificaciones"
            and c["fuente"] in {"opengraph", "meta"}
        ):
            score -= 32

        if (
            campo == "descripcion"
            and c["fuente"] == "html"
        ):
            score += 8

    if campo == "disponibilidad":

        categoria = _partes_patron(patron)[1]

        if categoria:

            # Una etiqueta de stock junto a un selector de variantes puede
            # describir solo la variante activa. Se conserva como evidencia,
            # pero pierde frente a una fuente estructurada del producto.
            if categoria.startswith("variante_"):
                score -= 35
            else:
                score += {
                    "agotado": 45,
                    "preventa": 28,
                    "bajo_pedido": 16,
                    "disponible": 18,
                    "contradictorio": -40,
                }.get(categoria, 0)

    try:
        score += max(
            -5,
            min(
                5,
                int(c.get("prioridad_patron") or 0) // 25
            )
        )
    except (TypeError, ValueError):
        pass

    return score


def _tokens_texto(texto):

    return set(
        re.findall(
            r"\w+",
            clave(texto),
            re.UNICODE,
        )
    )


_ENCABEZADO_DESCRIPCION = re.compile(
    r"^(?:descripci[oó]n(?:\s+(?:del\s+producto|general))?|"
    r"description|product\s+description)\s*[:»\-–]?\s+",
    re.I,
)

_SECCION_TECNICA_DESCRIPCION = re.compile(
    r"\b(?:especificaciones|ficha\s+t[eé]cnica|"
    r"technical\s+specifications|specifications|"
    r"caract[eé]ristiques\s+techniques)\b",
    re.I,
)

_RESUMEN_DECLARADO = re.compile(
    r"short.?descri|short_description|resumen|summary|excerpt|"
    r"descripci[oó]n\s+corta",
    re.I,
)


def _sin_encabezado_descripcion(valor):
    """Quita un encabezado genérico de sección al inicio del texto."""

    if not isinstance(valor, str):
        return valor

    nuevo = _ENCABEZADO_DESCRIPCION.sub("", valor, count=1)

    if nuevo == valor or len(nuevo.split()) < 8:
        return valor

    return nuevo


def _sin_anexo_tecnico(texto, nodo):
    """Separa prosa de un anexo rotulado con pares etiqueta: valor.

    Exige un título independiente en el DOM y narración suficiente antes
    de él; una mención a especificaciones o una tabla sin pares explícitos
    no basta para recortar la descripción.
    """

    if nodo is None or not isinstance(texto, str):
        return texto

    for titulo in nodo.css("h1, h2, h3, h4, h5, h6, p"):
        rotulo = titulo.text(separator=" ", strip=True)
        seccion = _SECCION_TECNICA_DESCRIPCION.match(rotulo)

        if seccion is None:
            continue

        resto = clave(rotulo[seccion.end():].strip(" .:;"))
        if resto not in {"", "tecnicas", "técnicas"}:
            continue

        limite = re.search(r"\s+".join(map(re.escape, rotulo.split())), texto)
        if limite is None:
            continue

        prosa = texto[:limite.start()].rstrip()
        anexo = texto[limite.end():]
        if (
            len(prosa.split()) >= 40
            and re.search(r"[.!?…]$", prosa)
            and len(re.findall(r"[.!?…](?:\s|$)", prosa)) >= 2
            and len(re.findall(r"[^\n:]{1,60}:\s*\S", anexo)) >= 3
        ):
            return prosa

    return texto


def _lista_reclamos(texto):
    """Detecta una lista de frases promocionales o de características.

    Cada línea es una afirmación breve que no termina en puntuación de
    cierre y no continúa una frase partida por etiquetas en línea. Es el
    formato habitual de una ficha resumida de características, no el de
    una descripción narrativa.
    """

    if not isinstance(texto, str):
        return False

    lineas = [l.strip() for l in texto.splitlines() if l.strip()]

    if len(lineas) < 3:
        return False

    primeras = lineas[:8]

    cortas = sum(
        1
        for linea in primeras
        if (
            len(linea.split()) <= 18
            and not re.search(r"[.!?…]\s*$", linea)
        )
    )

    fragmentos = sum(
        1
        for linea in primeras
        if linea and (
            linea[0].islower() or linea[0] in ",.;:)!?"
        )
    )

    proporcion = cortas / len(primeras)
    fragmentacion = fragmentos / len(primeras)

    if proporcion < 0.70 or fragmentacion > 0.15:
        return False

    return not _SECCION_TECNICA_DESCRIPCION.search(
        "\n".join(lineas[:5])
    )


def _bloque_tecnico_descripcion(texto):
    """Detecta bloques dominados por pares «etiqueta: valor»."""

    if not isinstance(texto, str):
        return False

    palabras = len(texto.split())

    if palabras < 12:
        return False

    pares = len(
        re.findall(r"[^\n:]{1,60}:\s*\S", texto)
    )

    if pares < 8 or pares / palabras < 0.05:
        return False

    return not _SECCION_TECNICA_DESCRIPCION.search(texto)


def _ajustar_descripciones(candidatos):
    """Descuenta bloques descubiertos sin acuerdo con la evidencia global.

    Evita que una sección parcial o de marketing sustituya a una descripción
    ya corroborada por metadatos o datos estructurados. También separa la
    narración del producto de las listas de características y de los bloques
    técnicos, y favorece el resumen declarado por la propia página.
    """

    referencias = [
        c["valor_limpio"]
        for c in candidatos
        if (
            c["campo"] == "descripcion"
            and c["valido"]
            and c["fuente"] in {
                "meta", "opengraph", "jsonld",
                "microdata", "json_embebido",
            }
        )
    ]

    textos = [
        (
            c,
            clave(_sin_encabezado_descripcion(c["valor_limpio"])),
        )
        for c in candidatos
        if c["campo"] == "descripcion" and c["valido"]
    ]

    if referencias:

        base = set().union(
            *(_tokens_texto(t) for t in referencias)
        )

        if len(base) >= 5:

            for c, _ in textos:

                if not c["patron"].lower().startswith(
                    "descubierto::descripcion::"
                ):
                    continue

                tokens = _tokens_texto(c["valor_limpio"])
                cobertura = len(tokens & base) / len(base)

                if cobertura < 0.45:
                    c["puntaje"] -= 55
                    c["motivo"] += "+baja_coincidencia_estructurada"

    for c, texto in textos:

        if not c["patron"].lower().startswith(
            "descubierto::descripcion::"
        ):
            continue

        prefijo = any(
            otro is not c
            and len(otro_texto) > len(texto)
            and otro_texto.startswith(texto)
            for otro, otro_texto in textos
        )

        for otro, otro_texto in textos:

            if otro is c or len(otro_texto) < len(texto) * 1.2:
                continue

            if (
                not prefijo
                and len(texto) >= 40
                and texto in otro_texto
            ):
                c["puntaje"] -= 30
                c["motivo"] += "+contenido_en_bloque_mayor"
                break

    # --- Narración frente a ficha técnica ---------------------------

    descripciones = [
        c
        for c in candidatos
        if c["campo"] == "descripcion" and c["valido"]
    ]

    if not descripciones:
        return

    for c in descripciones:
        c["valor_limpio"] = _sin_encabezado_descripcion(
            c["valor_limpio"]
        )

    reclamos = {
        c["id"]: (
            _tokens_texto(c["valor_limpio"]),
            clave(c["valor_limpio"]),
        )
        for c in descripciones
        if _lista_reclamos(c["valor_limpio"])
    }

    for c in descripciones:

        texto = c["valor_limpio"]

        if not isinstance(texto, str):
            continue

        palabras = len(texto.split())

        tecnico = _bloque_tecnico_descripcion(texto)
        lista = _lista_reclamos(texto)

        if tecnico:
            c["puntaje"] -= 45
            c["motivo"] += "+bloque_tecnico"

        elif lista:
            c["puntaje"] -= 25
            c["motivo"] += "+lista_reclamos"

        elif (
            reclamos
            and c["fuente"] in {"html", "json_embebido"}
        ):
            tokens = _tokens_texto(texto)

            if tokens and any(
                len(tokens & referencia) / len(tokens) >= 0.80
                and not (
                    len(referencia_texto) > len(clave(texto))
                    and referencia_texto.startswith(clave(texto))
                )
                for referencia, referencia_texto in reclamos.values()
            ):
                c["puntaje"] -= 25
                c["motivo"] += "+lista_reclamos_duplicada"

        # Una sección declarada como resumen (short description, resumen,
        # extracto) representa mejor la descripción breve del producto que
        # una pestaña de descripción extensa.
        if (
            _RESUMEN_DECLARADO.search(c["patron"])
            and not tecnico
            and 8 <= palabras <= 250
        ):
            c["puntaje"] += 20
            c["motivo"] += "+resumen_declarado"

        # Un titular sin puntuación de cierre no es una descripción
        # narrativa; cede ante un resumen con oraciones completas.
        if (
            palabras < 20
            and not re.search(r"[.!?…](?:\s|$)", texto)
            and not _RESUMEN_DECLARADO.search(c["patron"])
        ):
            c["puntaje"] -= 15
            c["motivo"] += "+descripcion_titular"


def _ajustar_especificaciones(candidatos):
    """Evita que un fragmento descubierto sustituya a un bloque mayor."""

    textos = [
        (c, " ".join(c["valor_limpio"].split()))
        for c in candidatos
        if (
            c["campo"] == "especificaciones"
            and c["valido"]
            and isinstance(c["valor_limpio"], str)
        )
    ]

    for c, texto in textos:

        if not c["patron"].lower().startswith(
            "descubierto::especificaciones::"
        ):
            continue

        if len(texto.split()) < 40:
            continue

        for otro, otro_texto in textos:

            if (
                otro is c
                or len(otro_texto.split())
                < len(texto.split()) * 1.15
            ):
                continue

            if texto in otro_texto:
                c["puntaje"] -= 30
                c["motivo"] += "+contenido_en_bloque_mayor"
                break


# ============================================================
# 7. LECTURA DE CANDIDATOS BRUTOS
# ============================================================

def leer_candidatos_brutos(bruto, arbol):
    """Convierte las coincidencias brutas en candidatos evaluados."""

    if not isinstance(bruto.get("resultado"), dict):
        raise ValueError(
            "El JSON bruto no contiene el objeto 'resultado'"
        )

    titulo = _titulo_principal(arbol)

    raiz = _raiz_titulo(titulo)
    contenedor = _main_titulo(arbol, titulo)

    candidatos = []
    descripciones_dom = []
    errores = []
    cache = {}

    for campo in CAMPOS:

        for regla in bruto["resultado"].get(campo, []):

            fuente = str(
                regla.get("fuente") or ""
            ).lower()

            patron = str(
                regla.get("patron") or ""
            )

            _, _, selector = _partes_patron(patron)

            nodos = []

            if fuente == "html":

                if patron not in cache:

                    try:
                        cache[patron] = arbol.css(selector)

                    except Exception as error:
                        cache[patron] = []

                        errores.append(
                            f"{campo}/{selector}: {error}"
                        )

                nodos = cache[patron]

            for coincidencia in regla.get(
                "coincidencias", []
            ):

                indice = coincidencia.get("indice")

                nodo = (
                    nodos[indice - 1]
                    if (
                        fuente == "html"
                        and isinstance(indice, int)
                        and 1 <= indice <= len(nodos)
                    )
                    else None
                )

                original = coincidencia.get("valor")

                limpio = limpiar(
                    original,
                    multilinea=campo in {
                        "descripcion", "especificaciones"
                    }
                )

                contexto = (
                    _contexto(
                        nodo,
                        titulo,
                        raiz,
                        contenedor
                    )
                    if fuente == "html"
                    else "sin_contexto_dom"
                )

                if campo == "precio" and isinstance(
                    limpio, str
                ):
                    interpretacion = _precio(limpio)

                elif (
                    campo == "disponibilidad"
                    and isinstance(limpio, str)
                ):
                    interpretacion = _stock(limpio)

                else:
                    interpretacion = None

                c = {
                    "id": f"C{len(candidatos) + 1:04d}",
                    "campo": campo,
                    "fuente": fuente,
                    "patron": patron,
                    "indice": indice,
                    "prioridad_patron": regla.get(
                        "prioridad", 0
                    ),
                    "valor_original": original,
                    "valor_limpio": limpio,
                    "contexto": contexto,
                    "ruta_dom": _ruta(nodo),
                    "interpretacion": interpretacion,
                }

                (
                    c["valido"],
                    c["puntos_contenido"],
                    c["motivo"]
                ) = _validar(c)

                c["puntaje"] = _puntuar(c)

                candidatos.append(c)

                if campo == "descripcion" and fuente == "html":
                    descripciones_dom.append((c, nodo))

    _ajustar_descripciones(candidatos)
    _ajustar_especificaciones(candidatos)

    # Evalúa el acuerdo de fuentes sobre el bloque completo antes de
    # separar su anexo; los metadatos pueden describir solo dicho anexo.
    for c, nodo in descripciones_dom:
        if c["valido"]:
            c["valor_limpio"] = _sin_anexo_tecnico(c["valor_limpio"], nodo)

    return candidatos, {
        "titulo_referencia": (
            titulo.text(strip=True)
            if titulo is not None else None
        ),
        "errores_selectores": errores,
        "total_candidatos": len(candidatos),
    }


# ============================================================
# 8. AGRUPACIÓN DE DUPLICADOS
# ============================================================

def agrupar_duplicados(candidatos):
    """Agrupa evidencias del mismo nodo, sin eliminar candidatos."""

    grupos = {}

    for c in candidatos:

        if c["ruta_dom"]:

            identidad = (
                c["campo"],
                "dom",
                c["ruta_dom"],
                clave(c["valor_limpio"]),
            )

        elif c["contexto"] == "sin_contexto_dom":

            identidad = (
                c["campo"],
                "sin_dom",
                clave(c["valor_limpio"]),
            )

        else:

            identidad = (
                c["campo"],
                "sin_identidad",
                c["id"],
            )

        if identidad not in grupos:

            grupos[identidad] = {
                "id": f"G{len(grupos) + 1:04d}",
                "campo": c["campo"],
                "valor_limpio": c["valor_limpio"],
                "candidatos": [],
            }

        grupos[identidad]["candidatos"].append(c)

    for grupo in grupos.values():

        grupo["valido"] = any(
            c["valido"]
            for c in grupo["candidatos"]
        )

        grupo["puntaje"] = max(
            c["puntaje"]
            for c in grupo["candidatos"]
        )

        grupo["total_coincidencias"] = len(
            grupo["candidatos"]
        )

    return list(grupos.values())


def _opciones(grupos, campo, incluir_ajenas=False):

    opciones = []

    for grupo in grupos:

        if grupo["campo"] != campo:
            continue

        elegibles = [
            c
            for c in grupo["candidatos"]
            if (
                c["valido"]
                and (
                    incluir_ajenas
                    or c["contexto"] != "zona_ajena_probable"
                )
            )
        ]

        if not elegibles:
            continue

        mejor = max(
            elegibles,
            key=lambda c: c["puntaje"]
        )

        if (
            campo != "precio"
            and mejor["patron"].lower().startswith("descubierto::")
        ):

            fragmento = mejor["valor_limpio"]

            if isinstance(fragmento, str):

                trozo = " ".join(fragmento.split()).casefold()
                palabras = len(fragmento.split())

                for candidato in elegibles:

                    texto = candidato["valor_limpio"]

                    if (
                        candidato is mejor
                        or not isinstance(texto, str)
                        or len(texto.split()) <= palabras
                        or len(texto.split()) > 1.5 * palabras
                        or candidato["puntaje"]
                        < mejor["puntaje"] - 15
                    ):
                        continue

                    completo = " ".join(texto.split()).casefold()

                    if trozo and trozo in completo:
                        mejor = candidato
                        break

        familias = {
            c["fuente"]
            for c in elegibles
        }

        puntos = (
            mejor["puntaje"]
            + min(8, 4 * (len(familias) - 1))
        )

        opciones.append(
            (puntos, grupo, mejor)
        )

    return sorted(
        opciones,
        key=lambda x: x[0],
        reverse=True
    )


def _registrar_competencia(logs, campo, opciones):
    """Registra margen y discrepancia entre las dos mejores opciones.

    Es información de auditoría: no altera la selección ni se interpreta
    como probabilidad. Un margen corto indica que la decisión depende de
    pocos puntos; una discrepancia indica que las fuentes no coinciden en
    el contenido, aunque una de ellas tenga más prioridad.
    """

    if len(opciones) < 2:
        return

    etiqueta = campo.upper()
    margen = opciones[0][0] - opciones[1][0]

    if margen < 8:
        logs.append(f"MARGEN_CORTO_{etiqueta}")

    primero = opciones[0][2].get("valor_limpio")
    segundo = opciones[1][2].get("valor_limpio")

    if not isinstance(primero, str) or not isinstance(segundo, str):
        return

    a = clave(primero)
    b = clave(segundo)

    if a and b and a not in b and b not in a:
        logs.append(f"CANDIDATOS_DISCREPANTES_{etiqueta}")


# ============================================================
# 9. SELECCIÓN DEL NOMBRE
# ============================================================

def select_nombre(grupos, logs):

    opciones = _opciones(grupos, "nombre")

    if not opciones:
        logs.append("NOMBRE_SIN_CANDIDATO_VALIDO")
        return None, []

    _registrar_competencia(logs, "nombre", opciones)

    _, elegido, candidato = opciones[0]

    texto = candidato["valor_limpio"]

    titulos = [
        c
        for _, _, c in opciones
        if (
            c["fuente"] == "html"
            and c["contexto"] == "principal_probable"
            and re.search(
                r"\bh[123]\b",
                c["patron"],
                re.I
            )
        )
    ]

    if titulos:

        titulo = max(
            titulos,
            key=lambda c: c["puntaje"]
        )["valor_limpio"]

        if (
            clave(texto).startswith(clave(titulo))
            and len(texto) > len(titulo)
        ):

            resto = texto[len(titulo):].strip()

            if resto.startswith(("-", "–", "—", "|")):
                texto = titulo

    if candidato["contexto"] != "principal_probable":
        logs.append(
            "NOMBRE_SIN_CONFIRMACION_DOM_PRINCIPAL"
        )

    return texto, [elegido["id"]]


# ============================================================
# 10. SELECCIÓN DEL PRECIO
# ============================================================

def _mismo_importe(a, b):

    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (TypeError, InvalidOperation, ValueError):
        return a == b


def select_precio(grupos, logs):

    opciones = _opciones(grupos, "precio")
    respaldo_ajeno = False

    if not opciones:
        opciones = _opciones(
            grupos, "precio", incluir_ajenas=True
        )
        respaldo_ajeno = bool(opciones)

        if respaldo_ajeno:
            logs.append("PRECIO_SOLO_EN_ZONA_AJENA")

    if not opciones:
        logs.append("PRECIO_SIN_CANDIDATO_VALIDO")
        return None, []

    _registrar_competencia(logs, "precio", opciones)

    _, elegido, candidato = opciones[0]

    # Si la fuente estructurada publica el tramo abierto de cantidad
    # (por ejemplo, >= 1000 unidades) y la ficha muestra también un
    # tramo base en rango (500-999), se prefiere este último: el
    # estructurado está describiendo el mínimo por volumen.
    tramo_base = None
    tramos_altos = []

    for _, grupo, otro in opciones:

        categoria = _partes_patron(otro["patron"])[1]
        importe = otro["interpretacion"].get("importe")

        if importe is None:
            continue

        if categoria == "cantidad_base" and tramo_base is None:
            tramo_base = (grupo, otro)
        elif categoria == "cantidad_alta":
            tramos_altos.append(importe)

    if (
        tramo_base is not None
        and candidato["fuente"] in {
            "jsonld", "microdata", "json_embebido",
            "meta", "opengraph",
        }
        and any(
            _mismo_importe(
                candidato["interpretacion"]["importe"], alto
            )
            for alto in tramos_altos
        )
        and not _mismo_importe(
            candidato["interpretacion"]["importe"],
            tramo_base[1]["interpretacion"]["importe"],
        )
    ):
        elegido, candidato = tramo_base
        logs.append("PRECIO_TRAMO_BASE_PREFERIDO")

    info = candidato["interpretacion"]
    primero = info["importe"]

    alternativas = []

    for _, _, otro in opciones:

        if otro is candidato:
            continue

        importe = otro["interpretacion"]["importe"]

        if not _mismo_importe(importe, primero) and (
            importe is not None
            and importe not in alternativas
        ):
            alternativas.append(importe)

    if alternativas:
        logs.append("PRECIO_ALTERNATIVOS_REVISAR")

    if info["simbolo_dolar_ambiguo"]:
        logs.append(
            "PRECIO_MONEDA_DOLAR_NO_CONFIRMADA"
        )

    if candidato["contexto"] != "principal_probable":
        logs.append(
            "PRECIO_SIN_CONFIRMACION_DOM_PRINCIPAL"
        )

    original = candidato.get("valor_original")

    if (
        isinstance(original, str)
        and re.search(r"\d+[.,]\d{3,}", original)
    ):
        original = (
            f"{info['moneda']} {primero}"
            if info.get("moneda")
            else str(primero)
        )

    return {
        "importe": primero,
        "moneda": info["moneda"],
        "iva": info["iva"],
        "texto_original": original,
        "estado": (
            "provisional"
            if alternativas else "seleccionado"
        ),
        "alternativas_importe": alternativas[:15],
    }, [elegido["id"]]



# ============================================================
# 11. SELECCIÓN DE DISPONIBILIDAD
# ============================================================

def select_stock(grupos, logs):

    opciones = _opciones(
        grupos,
        "disponibilidad"
    )

    if not opciones:
        logs.append(
            "DISPONIBILIDAD_NO_INTERPRETABLE"
        )
        return None, []

    _registrar_competencia(
        logs, "disponibilidad", opciones
    )

    _, elegido, candidato = opciones[0]

    estados = {
        c["interpretacion"]["estado"]
        for _, _, c in opciones
    }

    if len(estados) > 1:
        logs.append(
            "DISPONIBILIDAD_CONTRADICTORIA_O_VARIANTES"
        )

    if candidato["contexto"] != "principal_probable":
        logs.append(
            "DISPONIBILIDAD_SIN_CONFIRMACION_DOM_PRINCIPAL"
        )

    info = candidato["interpretacion"]

    return {
        "estado": info["estado"],
        "cantidad": info["cantidad"],
        "texto_original": candidato["valor_original"],
        "provisional": (
            len(estados) > 1
            or candidato["contexto"] != "principal_probable"
        ),
    }, [elegido["id"]]


# ============================================================
# 12. SELECCIÓN DE DESCRIPCIÓN
# ============================================================

def select_descripcion(grupos, logs):

    opciones = _opciones(
        grupos,
        "descripcion"
    )

    if not opciones:
        logs.append(
            "DESCRIPCION_SIN_CANDIDATO_VALIDO"
        )
        return None, []

    _registrar_competencia(
        logs, "descripcion", opciones
    )

    _, elegido, candidato = opciones[0]

    return (
        candidato["valor_limpio"],
        [elegido["id"]]
    )


# ============================================================
# 13. SELECCIÓN DE ESPECIFICACIONES
# ============================================================

def _tokens(texto):

    return set(
        re.findall(
            r"\w+",
            clave(texto),
            re.UNICODE
        )
    )


def _pares_especificaciones(texto):
    """Cuenta líneas con formato «clave: valor»."""

    return len(
        re.findall(
            r"(?m)^\s*[^\n:]{1,80}:\s*\S",
            texto,
        )
    )


def _unir_pares(textos, max_lineas=120):
    """Une bloques, conserva orden y junta etiquetas con su valor."""

    brutas = []
    vistas = set()
    deduplicar = len(textos) > 1

    for texto in textos:

        for linea in texto.splitlines():

            linea = " ".join(linea.split())

            if not linea:
                continue

            marca = linea.casefold()

            if deduplicar and marca in vistas:
                continue

            vistas.add(marca)
            brutas.append(linea)

    lineas = []
    indice = 0

    while indice < len(brutas):

        actual = brutas[indice]

        if (
            actual.endswith(":")
            and indice + 1 < len(brutas)
            and not brutas[indice + 1].endswith(":")
        ):
            lineas.append(f"{actual} {brutas[indice + 1]}")
            indice += 2

        else:
            lineas.append(actual)
            indice += 1

        if len(lineas) >= max_lineas:
            break

    return "\n".join(lineas)


def _es_narrativo(candidato):
    """Detecta bloques de descripción que no aportan pares técnicos."""

    patron = candidato["patron"].lower()
    texto = candidato["valor_limpio"]

    if not isinstance(texto, str):
        return False

    if "description" not in patron and "descripcion" not in patron:
        return False

    if "technical" in patron:
        return False

    if _pares_especificaciones(texto) >= 3:
        return False

    lineas = [
        linea for linea in texto.splitlines()
        if linea.strip()
    ]

    if not lineas:
        return False

    media = len(texto.split()) / len(lineas)

    return len(texto.split()) >= 25 and media >= 8


def select_especificaciones(
    grupos,
    logs,
    max_bloques=5
):

    opciones = _opciones(
        grupos,
        "especificaciones"
    )

    if not opciones:
        logs.append(
            "ESPECIFICACIONES_SIN_CANDIDATO_VALIDO"
        )
        return None, []

    estructuradas = [
        opcion
        for opcion in opciones
        if not _es_narrativo(opcion[2])
    ]

    if estructuradas and len(estructuradas) < len(opciones):
        logs.append(
            "ESPECIFICACIONES_NARRATIVA_DESCARTADA"
        )
        opciones = estructuradas

    _registrar_competencia(
        logs, "especificaciones", opciones
    )

    descubiertos = []

    for puntos, grupo, candidato in opciones:

        patron = candidato["patron"].lower()

        if not patron.startswith(
            "descubierto::especificaciones::"
        ):
            continue

        texto = candidato["valor_limpio"]

        if not isinstance(texto, str):
            continue

        lineas = [
            linea for linea in texto.splitlines()
            if linea.strip()
        ]

        pares = _pares_especificaciones(texto)
        densidad = pares / max(1, len(lineas))

        descubiertos.append((
            puntos,
            grupo,
            candidato,
            pares,
            len(texto.split()),
            densidad,
        ))

    if descubiertos and max(d[4] for d in descubiertos) >= 20:

        seccion_pares = next(
            (
                dato for dato in descubiertos
                if dato[3] >= 8 and dato[5] >= 0.6
                and dato[2].get("prioridad_patron", 0) < 104
            ),
            None,
        )

        if seccion_pares is not None:
            logs.append(
                "ESPECIFICACIONES_SECCION_CON_PARES"
            )
            return (
                _unir_pares([seccion_pares[2]["valor_limpio"]]),
                [seccion_pares[1]["id"]],
            )

        tablas = [
            dato for dato in descubiertos
            if dato[3] >= 3 and dato[5] >= 0.8
        ]

        if tablas:

            tablas.sort(key=lambda d: (d[3], d[4]), reverse=True)

            textos = [tablas[0][2]["valor_limpio"]]
            ids = [tablas[0][1]["id"]]

            for _, otro_grupo, otro, _, _, _ in tablas[1:]:

                nuevas = set(
                    linea.split(":", 1)[0].casefold()
                    for linea in _unir_pares(
                        [otro["valor_limpio"]]
                    ).splitlines()
                )

                previas = set(
                    linea.split(":", 1)[0].casefold()
                    for linea in _unir_pares(textos).splitlines()
                )

                if len(nuevas - previas) < 3:
                    continue

                textos.append(otro["valor_limpio"])
                ids.append(otro_grupo["id"])

                if len(textos) >= 8:
                    break

            logs.append(
                "ESPECIFICACIONES_PARES_ESTRUCTURADOS"
            )

            return _unir_pares(textos), ids

        mejor = max(descubiertos, key=lambda d: (d[3], d[4]))

        if mejor[3] >= 5:
            puntos_elegido, grupo, candidato, pares, palabras, dens = (
                mejor
            )
        else:
            puntos_elegido, grupo, candidato, pares, palabras, dens = (
                descubiertos[0]
            )

        fragmento = " ".join(
            candidato["valor_limpio"].split()
        ).casefold()
        cantidad = len(fragmento.split())

        for otros_puntos, otro_grupo, otro in opciones:

            texto = otro["valor_limpio"]

            if (
                otro is candidato
                or not isinstance(texto, str)
                or otros_puntos < puntos_elegido - 15
            ):
                continue

            completo = " ".join(texto.split()).casefold()

            if (
                cantidad <= len(completo.split()) <= 1.5 * cantidad
                and fragmento in completo
            ):
                grupo = otro_grupo
                candidato = otro
                pares = _pares_especificaciones(completo)
                palabras = len(completo.split())
                break

        prioridad = candidato.get("prioridad_patron", 0)

        if (
            pares >= 5
            or prioridad < 104
            or palabras >= 60
        ):

            logs.append(
                "ESPECIFICACIONES_SECCION_DESCUBIERTA"
            )

            return _unir_pares([candidato["valor_limpio"]]), [
                grupo["id"]
            ]

    bloques = []
    ids = []

    for _, grupo, candidato in opciones:

        texto = candidato["valor_limpio"]

        if not isinstance(texto, str):
            continue

        if bloques and _es_narrativo(candidato):
            continue

        if (
            bloques
            and candidato["fuente"] != "html"
        ):
            # Los metadatos pueden describir el producto, pero no sustituyen
            # una sección técnica ya localizada en el documento.
            continue

        n = clave(texto)

        if any(n in clave(b) for b in bloques):
            continue

        if bloques:

            tokens = _tokens(texto)

            if any(
                len(tokens & _tokens(b))
                / max(
                    1,
                    min(
                        len(tokens),
                        len(_tokens(b))
                    )
                ) >= 0.82
                for b in bloques
            ):
                continue

            nuevos = tokens.difference(
                set().union(
                    *(_tokens(b) for b in bloques)
                )
            )

            if (
                len(nuevos) < 5
                or not TECNICO.search(texto)
            ):
                continue

        bloques.append(texto)
        ids.append(grupo["id"])

        if len(bloques) == max_bloques:
            logs.append(
                "ESPECIFICACIONES_LIMITE_BLOQUES_REVISAR"
            )
            break

    if len(bloques) > 1:
        logs.append(
            "ESPECIFICACIONES_BLOQUES_COMPLEMENTARIOS_COMBINADOS"
        )

    return (
        "\n\n".join(bloques) if bloques else None
    ), ids


# ============================================================
# 14. VALIDACIÓN FINAL
# ============================================================

def validar_ficha(ficha, grupos, logs):

    for campo in CAMPOS:

        if ficha.get(campo) is None:
            logs.append(
                f"CAMPO_FALTANTE:{campo}"
            )

    if (
        ficha.get("precio")
        and ficha["precio"].get("importe") == "0.00"
    ):
        logs.append("PRECIO_CERO_REVISAR")

    graves = (
        "CAMPO_FALTANTE:",
        "_SIN_CANDIDATO_VALIDO",
        "NO_INTERPRETABLE",
        "CONTRADICTORIA",
        "PRECIO_ALTERNATIVOS_REVISAR",
        "PRECIO_CERO_REVISAR",
    )

    return (
        "revision_requerida"
        if any(
            any(g in a for g in graves)
            for a in logs
        )
        else "provisional"
    )


# ============================================================
# 15. COMPATIBILIDAD CON PRUEBAS POR ARCHIVO
# ============================================================

def analizar_pagina(html_archivo, bruto_archivo, salida):
    """Compatibilidad con la PoC por archivos."""

    from pathlib import Path
    from selectolax.lexbor import LexborHTMLParser

    html_archivo = Path(html_archivo)
    bruto_archivo = Path(bruto_archivo)
    salida = Path(salida)

    arbol = LexborHTMLParser(
        html_archivo.read_bytes()
    )

    bruto = json.loads(
        bruto_archivo.read_text(encoding="utf-8-sig")
    )

    candidatos, info = leer_candidatos_brutos(
        bruto,
        arbol
    )

    grupos = agrupar_duplicados(candidatos)

    avisos = list(info["errores_selectores"])

    ficha = {}

    ficha["nombre"], _ = select_nombre(
        grupos, avisos
    )

    ficha["precio"], _ = select_precio(
        grupos, avisos
    )

    ficha["disponibilidad"], _ = select_stock(
        grupos, avisos
    )

    ficha["descripcion"], _ = select_descripcion(
        grupos, avisos
    )

    ficha["especificaciones"], _ = select_especificaciones(
        grupos, avisos
    )

    estado = validar_ficha(
        ficha, grupos, avisos
    )

    final = {
        **ficha,
        "estado_validacion": estado,
        "advertencias": list(dict.fromkeys(avisos))
    }

    for nombre_carpeta, contenido in (
        ("paginas", final),
        (
            "auditoria",
            {
                "archivo": html_archivo.name,
                "candidatos": candidatos,
                "grupos": grupos,
                "advertencias": final["advertencias"]
            }
        )
    ):

        carpeta = salida / nombre_carpeta

        carpeta.mkdir(
            parents=True,
            exist_ok=True
        )

        ruta = carpeta / (html_archivo.stem + ".json")

        ruta.write_text(
            json.dumps(
                contenido,
                ensure_ascii=False,
                indent=2,
                default=str
            ),
            encoding="utf-8"
        )

    return {
        "archivo": html_archivo.name,
        "estado": estado,
        "candidatos": len(candidatos),
        "grupos": len(grupos),
        "nombre": ficha["nombre"] or "",
        "precio": (
            (ficha["precio"] or {}).get("importe")
            or ""
        ),
        "disponibilidad": (
            (ficha["disponibilidad"] or {}).get("estado")
            or ""
        )
    }
