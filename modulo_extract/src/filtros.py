
"""SIGO Extract - filtros integrados para los cinco campos.

Entrada: JSON de coincidencias brutas en memoria y árbol Lexbor de Selectolax.
Salida: ficha candidata + diagnósticos. No descarga URLs ni exige archivos.

Funciones usadas por main2.py:
    leer_candidatos_brutos, agrupar_duplicados,
    select_nombre, select_precio, select_stock,
    select_descripcion, select_especificaciones, validar_ficha.

Nota: heurísticas de PoC. Mantiene la evidencia; una selección no garantiza exactitud.
"""

import html as html_lib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
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
    r"(?:function\s*\(|document\.querySelector\s*\(|window\.[\w$]+|"
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


def _main_titulo(titulo):

    if titulo is None:
        return None

    for ancestro in _ancestros(titulo.parent):

        if (
            ancestro.tag == "main"
            or ancestro.attributes.get("id")
            in {"main", "content", "primary"}
        ):
            return ancestro

    return None


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
            and len(partes[1]) in {1, 2}
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
        return format(Decimal(numero), ".2f")
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

    else:
        for iso in (
            "COP", "MXN", "CLP", "PEN", "ARS", "CAD"
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
            r"in\s*stock|available|disponible|"
            r"dispon[ií]vel|en\s+stock|"
            r"em\s+estoque|only\s+\d+\s+left|"
            r"solo\s+quedan\s+\d+",
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
        r"back[- ]?order|bajo\s+pedido",
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

    campo = c["campo"]
    patron = c["patron"].lower()

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
    contenedor = _main_titulo(titulo)

    candidatos = []
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

            nodos = []

            if fuente == "html":

                if patron not in cache:

                    try:
                        cache[patron] = arbol.css(patron)

                    except Exception as error:
                        cache[patron] = []

                        errores.append(
                            f"{campo}/{patron}: {error}"
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


def _opciones(grupos, campo):

    opciones = []

    for grupo in grupos:

        if grupo["campo"] != campo:
            continue

        elegibles = [
            c
            for c in grupo["candidatos"]
            if (
                c["valido"]
                and c["contexto"] != "zona_ajena_probable"
            )
        ]

        if not elegibles:
            continue

        mejor = max(
            elegibles,
            key=lambda c: c["puntaje"]
        )

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


# ============================================================
# 9. SELECCIÓN DEL NOMBRE
# ============================================================

def select_nombre(grupos, logs):

    opciones = _opciones(grupos, "nombre")

    if not opciones:
        logs.append("NOMBRE_SIN_CANDIDATO_VALIDO")
        return None, []

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

def select_precio(grupos, logs):

    opciones = _opciones(grupos, "precio")

    if not opciones:
        logs.append("PRECIO_SIN_CANDIDATO_VALIDO")
        return None, []

    _, elegido, candidato = opciones[0]

    info = candidato["interpretacion"]
    primero = info["importe"]

    alternativas = []

    for _, _, otro in opciones[1:]:

        importe = otro["interpretacion"]["importe"]

        try:
            distinto = (
                Decimal(importe) != Decimal(primero)
            )
        except (TypeError, InvalidOperation):
            distinto = importe != primero

        if (
            distinto
            and importe is not None
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

    return {
        "importe": primero,
        "moneda": info["moneda"],
        "iva": info["iva"],
        "texto_original": candidato["valor_original"],
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

    bloques = []
    ids = []

    for _, grupo, candidato in opciones:

        texto = candidato["valor_limpio"]

        if not isinstance(texto, str):
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
