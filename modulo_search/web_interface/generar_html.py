import json
from pathlib import Path
from html import escape


# --------------------------------------------------------
# RUTAS
# --------------------------------------------------------

WEB_INTERFACE_DIR = Path(__file__).resolve().parent

ROOT = WEB_INTERFACE_DIR.parent

ARCHIVO_RESULTADOS = (
    ROOT
    / "outputs"
    / "resultados_filtrados.json"
)

ARCHIVO_HTML = (
    WEB_INTERFACE_DIR
    / "resultados.html"
)


# --------------------------------------------------------
# OBTENER CLASE CSS SEGÚN EL MERCADO
# --------------------------------------------------------

def obtener_clase_mercado(mercado):

    match mercado:

        case "Nacionales":
            return "nacionales"

        case "Estados Unidos":
            return "estados-unidos"

        case "China":
            return "china"

        case _:
            return "otro"


# --------------------------------------------------------
# LEER resultados_filtrados.json
# --------------------------------------------------------

with open(
    ARCHIVO_RESULTADOS,
    "r",
    encoding="utf-8"
) as archivo:

    resultados_filtrados = json.load(archivo)


# --------------------------------------------------------
# AGRUPAR RESULTADOS
#
# Ítem
#   ├── Nacionales
#   │       ├── Tecnit
#   │       ├── Computron
#   │       └── ...
#   │
#   ├── Estados Unidos
#   │       ├── Amazon
#   │       └── eBay
#   │
#   └── China
#           ├── Alibaba
#           └── AliExpress
# --------------------------------------------------------

items = {}


for consulta in resultados_filtrados:

    numero_item = consulta["numero_item"]
    nombre_item = consulta["nombre_item"]

    mercado = consulta["mercado"]
    prioridad = consulta["prioridad"]

    tienda = consulta["tienda"]


    # ----------------------------------------------------
    # Crear el ítem si todavía no existe
    # ----------------------------------------------------

    if numero_item not in items:

        items[numero_item] = {
            "nombre_item": nombre_item,
            "mercados": {}
        }


    # ----------------------------------------------------
    # Crear el mercado si todavía no existe dentro
    # de este ítem
    # ----------------------------------------------------

    if mercado not in items[numero_item]["mercados"]:

        items[numero_item]["mercados"][mercado] = {
            "prioridad": prioridad,
            "resultados": []
        }


    # ----------------------------------------------------
    # Añadir resultados encontrados por esta tienda
    # ----------------------------------------------------

    for resultado in consulta["resultados"]:

        items[numero_item]["mercados"][mercado]["resultados"].append(
            {
                "tienda": tienda,
                "title": resultado.get(
                    "title",
                    ""
                ),
                "content": resultado.get(
                    "content",
                    ""
                ),
                "url": resultado.get(
                    "url",
                    ""
                )
            }
        )


# --------------------------------------------------------
# CONSTRUIR LOS ÍTEMS DEL HTML
# --------------------------------------------------------

html_items = ""


for numero_item, datos_item in items.items():

    nombre_item = escape(
        str(datos_item["nombre_item"])
    )

    html_mercados = ""


    # ----------------------------------------------------
    # RECORRER LOS MERCADOS DEL ÍTEM
    # ----------------------------------------------------

    for mercado, datos_mercado in datos_item["mercados"].items():

        clase_mercado = obtener_clase_mercado(
            mercado
        )

        mercado_html = escape(
            str(mercado)
        )

        filas = ""


        # ------------------------------------------------
        # CREAR UNA FILA POR CADA RESULTADO
        # ------------------------------------------------

        for resultado in datos_mercado["resultados"]:

            tienda = escape(
                str(resultado["tienda"])
            )

            titulo = escape(
                str(resultado["title"])
            )

            contenido = escape(
                str(resultado["content"])
            )

            url = escape(
                str(resultado["url"]),
                quote=True
            )


            filas += f"""
                <tr>

                    <td class="tienda">
                        {tienda}
                    </td>

                    <td class="titulo">
                        {titulo}
                    </td>

                    <td class="contenido">
                        {contenido}
                    </td>

                    <td class="enlace">

                        <a
                            href="{url}"
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Abrir página"
                        >
                            ↗
                        </a>

                    </td>

                </tr>
            """


        # ------------------------------------------------
        # SI EL MERCADO NO TIENE RESULTADOS
        # ------------------------------------------------

        if not datos_mercado["resultados"]:

            filas = """
                <tr>

                    <td
                        colspan="4"
                        class="sin-resultados"
                    >
                        No se encontraron resultados.
                    </td>

                </tr>
            """


        # ------------------------------------------------
        # CREAR BLOQUE COMPLETO DEL MERCADO
        # ------------------------------------------------

        html_mercados += f"""
            <div class="mercado">

                <div class="mercado-titulo {clase_mercado}">

                    {mercado_html}

                </div>


                <div class="tabla-contenedor">

                    <table class="tabla-{clase_mercado}">

                        <thead>

                            <tr>

                                <th class="columna-tienda">
                                    Tienda
                                </th>

                                <th class="columna-titulo">
                                    Título
                                </th>

                                <th class="columna-contenido">
                                    Contenido
                                </th>

                                <th class="columna-enlace">
                                </th>

                            </tr>

                        </thead>


                        <tbody>

                            {filas}

                        </tbody>

                    </table>

                </div>

            </div>
        """


    # ----------------------------------------------------
    # CREAR BLOQUE COMPLETO DEL ÍTEM
    # ----------------------------------------------------

    html_items += f"""
        <section class="item">

            <div class="item-cabecera">

                <span class="numero-item">
                    ÍTEM {numero_item}
                </span>

                <h2>
                    {nombre_item}
                </h2>

            </div>


            {html_mercados}

        </section>
    """


# --------------------------------------------------------
# DOCUMENTO HTML COMPLETO
# --------------------------------------------------------

html_completo = f"""<!DOCTYPE html>

<html lang="es">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        Enlaces conseguidos
    </title>

    <link
        rel="stylesheet"
        href="estilos.css"
    >

</head>


<body>

    <main class="contenedor">

        <h1>
            ENLACES CONSEGUIDOS
        </h1>


        {html_items}


    </main>

</body>

</html>
"""


# --------------------------------------------------------
# GUARDAR HTML
# --------------------------------------------------------

with open(
    ARCHIVO_HTML,
    "w",
    encoding="utf-8"
) as archivo:

    archivo.write(
        html_completo
    )


print("=" * 70)

print(
    "HTML generado correctamente:"
)

print(
    ARCHIVO_HTML
)

print("=" * 70)