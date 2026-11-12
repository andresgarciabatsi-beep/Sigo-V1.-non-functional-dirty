import csv
import json
import time
from pathlib import Path

import requests

from filtrar_resultados import pertenece_a_tienda


# --------------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------------

SEARXNG_URL = "http://localhost:8888/search"

BASE = Path(__file__).resolve().parent

ARCHIVO_TIENDAS = BASE / "mercados_y_tiendas.json"

ARCHIVO_JSON = BASE / "experimento_motores_todas_tiendas.json"

ARCHIVO_CSV = BASE / "resumen_motores_todas_tiendas.csv"

ARCHIVO_MATRIZ = BASE / "matriz_motores_tiendas.csv"


# --------------------------------------------------------
# PRODUCTO DE PRUEBA
# --------------------------------------------------------

PRODUCTO_PRUEBA = (
    "Pantalla interactiva táctil de 86 pulgadas "
    "4K con sistema operativo integrado"
)


# --------------------------------------------------------
# MOTORES A PROBAR INDIVIDUALMENTE
# --------------------------------------------------------

MOTORES = [
    {
        "nombre": "Bing",
        "bang": "!bi"
    },
    {
        "nombre": "Brave",
        "bang": "!br"
    },
    {
        "nombre": "Yahoo",
        "bang": "!yh"
    }
]


# --------------------------------------------------------
# PAUSA ENTRE CONSULTAS
# --------------------------------------------------------

# Como queremos analizar los motores y no provocar bloqueos,
# dejamos una pausa entre cada solicitud.

PAUSA = 6


# --------------------------------------------------------
# CARGAR TODAS LAS TIENDAS
# --------------------------------------------------------

def cargar_tiendas():

    with open(
        ARCHIVO_TIENDAS,
        "r",
        encoding="utf-8"
    ) as archivo:

        datos = json.load(
            archivo
        )


    tiendas = []


    for mercado, lista_tiendas in datos["mercados"].items():

        for tienda in lista_tiendas:

            tiendas.append(
                {
                    "mercado": mercado,
                    "tienda": tienda["nombre"],
                    "dominio": tienda["dominio"]
                }
            )


    return tiendas


# --------------------------------------------------------
# PROBAR UN MOTOR EN UNA TIENDA
# --------------------------------------------------------

def probar_motor(
    tienda_preparada,
    motor
):

    mercado = tienda_preparada["mercado"]

    nombre_tienda = tienda_preparada["tienda"]

    dominio = tienda_preparada["dominio"]


    # Consulta normal que usaría SIGO
    consulta_original = (
        f"{PRODUCTO_PRUEBA} {dominio}"
    )


    # Consulta que realmente recibe SearXNG
    consulta_searxng = (
        f"{motor['bang']} {consulta_original}"
    )


    parametros = {
        "q": consulta_searxng,
        "format": "json"
    }


    inicio = time.perf_counter()


    try:

        respuesta = requests.get(
            SEARXNG_URL,
            params=parametros,
            timeout=30
        )

        respuesta.raise_for_status()

        datos = respuesta.json()


        tiempo = (
            time.perf_counter()
            - inicio
        )


        resultados = datos.get(
            "results",
            []
        )


        motores_no_disponibles = datos.get(
            "unresponsive_engines",
            []
        )


        # ------------------------------------------------
        # FILTRAR SOLO RESULTADOS DEL DOMINIO
        # ------------------------------------------------

        resultados_dominio = []


        for resultado in resultados:

            url = resultado.get(
                "url",
                ""
            )


            if pertenece_a_tienda(
                url,
                dominio
            ):

                resultados_dominio.append(
                    resultado
                )


        # ------------------------------------------------
        # ELIMINAR URLs DUPLICADAS
        # ------------------------------------------------

        urls_unicas = set()


        for resultado in resultados_dominio:

            url = resultado.get(
                "url",
                ""
            )


            if url:

                urls_unicas.add(
                    url
                )


        # ------------------------------------------------
        # RESULTADO DE LA PRUEBA
        # ------------------------------------------------

        return {
            "mercado": mercado,
            "tienda": nombre_tienda,
            "dominio": dominio,

            "motor": motor["nombre"],
            "bang": motor["bang"],

            "consulta": consulta_original,

            "tiempo_segundos": round(
                tiempo,
                2
            ),

            "resultados_brutos": len(
                resultados
            ),

            "resultados_dominio": len(
                resultados_dominio
            ),

            "urls_unicas_dominio": len(
                urls_unicas
            ),

            "motores_no_disponibles":
                motores_no_disponibles,

            "urls_dominio": sorted(
                urls_unicas
            )
        }


    except (
        requests.RequestException,
        ValueError
    ) as error:

        tiempo = (
            time.perf_counter()
            - inicio
        )


        return {
            "mercado": mercado,
            "tienda": nombre_tienda,
            "dominio": dominio,

            "motor": motor["nombre"],
            "bang": motor["bang"],

            "consulta": consulta_original,

            "tiempo_segundos": round(
                tiempo,
                2
            ),

            "resultados_brutos": 0,

            "resultados_dominio": 0,

            "urls_unicas_dominio": 0,

            "motores_no_disponibles": [],

            "urls_dominio": [],

            "error": str(error)
        }


# --------------------------------------------------------
# EJECUTAR TODO EL EXPERIMENTO
# --------------------------------------------------------

def ejecutar_experimento():

    tiendas = cargar_tiendas()

    resultados_experimento = []


    total_pruebas = (
        len(tiendas)
        * len(MOTORES)
    )


    numero_prueba = 0


    print("=" * 70)

    print(
        f"Tiendas: {len(tiendas)}"
    )

    print(
        f"Motores: {len(MOTORES)}"
    )

    print(
        f"Total de pruebas: {total_pruebas}"
    )

    print("=" * 70)


    for tienda in tiendas:

        print()

        print(
            f"{tienda['mercado']} | "
            f"{tienda['tienda']}"
        )

        print("-" * 70)


        for motor in MOTORES:

            numero_prueba += 1


            print(
                f"[{numero_prueba}/{total_pruebas}] "
                f"{motor['nombre']}"
            )


            resultado = probar_motor(
                tienda,
                motor
            )


            resultados_experimento.append(
                resultado
            )


            print(
                "Resultados brutos:",
                resultado["resultados_brutos"]
            )

            print(
                "URLs del dominio:",
                resultado["urls_unicas_dominio"]
            )

            print(
                "Tiempo:",
                resultado["tiempo_segundos"],
                "s"
            )


            if resultado[
                "motores_no_disponibles"
            ]:

                print(
                    "Motores no disponibles:",
                    resultado[
                        "motores_no_disponibles"
                    ]
                )


            if "error" in resultado:

                print(
                    "Error:",
                    resultado["error"]
                )


            print()


            # No esperar después de la última prueba
            if numero_prueba < total_pruebas:

                time.sleep(
                    PAUSA
                )


    return resultados_experimento


# --------------------------------------------------------
# GUARDAR RESULTADOS COMPLETOS EN JSON
# --------------------------------------------------------

def guardar_json(resultados):

    with open(
        ARCHIVO_JSON,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados,
            archivo,
            ensure_ascii=False,
            indent=4
        )


# --------------------------------------------------------
# GUARDAR RESUMEN CSV
# --------------------------------------------------------

def guardar_csv(resultados):

    campos = [
        "mercado",
        "tienda",
        "dominio",
        "motor",
        "tiempo_segundos",
        "resultados_brutos",
        "resultados_dominio",
        "urls_unicas_dominio",
        "motores_no_disponibles"
    ]


    with open(
        ARCHIVO_CSV,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as archivo:

        escritor = csv.DictWriter(
            archivo,
            fieldnames=campos
        )


        escritor.writeheader()


        for resultado in resultados:

            escritor.writerow(
                {
                    "mercado":
                        resultado["mercado"],

                    "tienda":
                        resultado["tienda"],

                    "dominio":
                        resultado["dominio"],

                    "motor":
                        resultado["motor"],

                    "tiempo_segundos":
                        resultado["tiempo_segundos"],

                    "resultados_brutos":
                        resultado["resultados_brutos"],

                    "resultados_dominio":
                        resultado["resultados_dominio"],

                    "urls_unicas_dominio":
                        resultado["urls_unicas_dominio"],

                    "motores_no_disponibles":
                        str(
                            resultado[
                                "motores_no_disponibles"
                            ]
                        )
                }
            )


# --------------------------------------------------------
# CREAR MATRIZ TIENDA × MOTOR
# --------------------------------------------------------

def guardar_matriz(resultados):

    matriz = {}


    for resultado in resultados:

        clave = (
            resultado["mercado"],
            resultado["tienda"],
            resultado["dominio"]
        )


        if clave not in matriz:

            matriz[clave] = {
                "mercado":
                    resultado["mercado"],

                "tienda":
                    resultado["tienda"],

                "dominio":
                    resultado["dominio"],

                "Bing": 0,

                "Brave": 0,

                "Yahoo": 0
            }


        matriz[
            clave
        ][
            resultado["motor"]
        ] = resultado[
            "urls_unicas_dominio"
        ]


    campos = [
        "mercado",
        "tienda",
        "dominio",
        "Bing",
        "Brave",
        "Yahoo"
    ]


    with open(
        ARCHIVO_MATRIZ,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as archivo:

        escritor = csv.DictWriter(
            archivo,
            fieldnames=campos
        )


        escritor.writeheader()


        for fila in matriz.values():

            escritor.writerow(
                fila
            )


# --------------------------------------------------------
# EJECUCIÓN
# --------------------------------------------------------

if __name__ == "__main__":

    resultados = ejecutar_experimento()


    guardar_json(
        resultados
    )


    guardar_csv(
        resultados
    )


    guardar_matriz(
        resultados
    )


    print()
    print("=" * 70)

    print(
        "EXPERIMENTO FINALIZADO"
    )

    print()

    print(
        "JSON completo:"
    )

    print(
        ARCHIVO_JSON
    )

    print()

    print(
        "CSV detallado:"
    )

    print(
        ARCHIVO_CSV
    )

    print()

    print(
        "Matriz tienda × motor:"
    )

    print(
        ARCHIVO_MATRIZ
    )

    print("=" * 70)