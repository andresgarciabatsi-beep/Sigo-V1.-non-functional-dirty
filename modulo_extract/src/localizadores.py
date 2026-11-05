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


def _ajeno(nodo):
    """Excluye coincidencias situadas en navegación o productos relacionados."""
    actual = nodo
    for _ in range(16):
        if actual is None:
            break
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

            if _ajeno(nodo):
                continue

            atributo = regla.get("atributo")

            if atributo:
                valor = nodo.attributes.get(atributo, "")
            else:
                valor = nodo.text(
                    separator="\n" if campo == "especificaciones" else " ",
                    strip=True,
                )

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

    for regla in reglas:

        for indice, dato in _extraer_regla(campo, regla, fuentes):

            texto = _limpiar(dato)

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
