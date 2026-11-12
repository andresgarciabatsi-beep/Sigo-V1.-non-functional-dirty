from concurrent.futures import ThreadPoolExecutor
import os
import requests

from filtrar_resultados import pertenece_a_tienda


# --------------------------------------------------------
# CONFIGURACIÓN DE ENLACES PARA SEARXNG
# --------------------------------------------------------

# Desarrollo local:
# http://localhost:8888
#
# Docker:
# http://searxng:8080

SEARXNG_BASE_URL = os.getenv(
    "SEARXNG_URL",
    "http://127.0.0.1:8888"
)

SEARXNG_URL = (
    SEARXNG_BASE_URL.rstrip("/")
    + "/search"
)


# --------------------------------------------------------
# ORDEN DE MOTORES
# --------------------------------------------------------

# Para cada tienda se prueban de forma SECUENCIAL.
#
# En cuanto un motor encuentra al menos una URL
# perteneciente al dominio objetivo, se detiene la
# búsqueda de motores para esa tienda.

MOTORES_SEARXNG = [
    ("Brave", "!br"),
    ("Yahoo", "!yh"),
    ("Google", "!goc"),
    ("Bing", "!bi")
]


# --------------------------------------------------------
# REALIZAR UNA CONSULTA PARA UNA TIENDA
# --------------------------------------------------------

def realizar_consulta(consulta_preparada):
    """
    Realiza la búsqueda correspondiente a una combinación:

        ítem + tienda

    Los motores se prueban de forma secuencial:

        Brave -> Yahoo -> Google -> Bing

    Si uno encuentra al menos una URL del dominio objetivo,
    se detiene la búsqueda de motores para esa tienda.
    """

    consulta = consulta_preparada["consulta"]
    dominio_tienda = consulta_preparada["dominio"]

    motores_no_disponibles_acumulados = []


    # --------------------------------------------------------
    # PROBAR MOTORES SECUENCIALMENTE
    # --------------------------------------------------------

    for nombre_motor, bang_motor in MOTORES_SEARXNG:

        consulta_searxng = (
            f"{bang_motor} {consulta}"
        )

        parametros_para_busqueda = {
            "q": consulta_searxng,
            "format": "json"
        }


        # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

        print(
            f"Ítem {consulta_preparada['numero_item']} | "
            f"{consulta_preparada['tienda']} | "
            f"Probando {nombre_motor}"
        )

        # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


        try:

            respuesta = requests.get(
                SEARXNG_URL,
                params=parametros_para_busqueda,
                timeout=30
            )

            respuesta.raise_for_status()

            datos_de_respuesta_json = respuesta.json()


            resultados = datos_de_respuesta_json.get(
                "results",
                []
            )


            motores_no_disponibles = datos_de_respuesta_json.get(
                "unresponsive_engines",
                []
            )


            motores_no_disponibles_acumulados.extend(
                motores_no_disponibles
            )


            # --------------------------------------------------------
            # COMPROBAR SI ESTE MOTOR ENCONTRÓ LA TIENDA
            # --------------------------------------------------------

            encontro_tienda = any(
                pertenece_a_tienda(
                    resultado.get("url", ""),
                    dominio_tienda
                )
                for resultado in resultados
            )


            # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

            print(
                f"Ítem {consulta_preparada['numero_item']} | "
                f"{consulta_preparada['tienda']} | "
                f"{nombre_motor}: "
                f"{len(resultados)} resultados brutos"
            )

            if encontro_tienda:

                print(
                    f"Ítem {consulta_preparada['numero_item']} | "
                    f"{consulta_preparada['tienda']} | "
                    f"{nombre_motor}: "
                    f"se encontró {dominio_tienda} -> STOP"
                )

            else:

                print(
                    f"Ítem {consulta_preparada['numero_item']} | "
                    f"{consulta_preparada['tienda']} | "
                    f"{nombre_motor}: "
                    f"no se encontró {dominio_tienda}"
                )


            if motores_no_disponibles:

                print(
                    f"Ítem {consulta_preparada['numero_item']} | "
                    f"{consulta_preparada['tienda']} | "
                    f"Motores no disponibles: "
                    f"{motores_no_disponibles}"
                )

            # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


            # --------------------------------------------------------
            # SI ENCONTRÓ LA TIENDA, DETENER LOS MOTORES
            # --------------------------------------------------------

            if encontro_tienda:

                return {
                    "numero_item":
                        consulta_preparada["numero_item"],

                    "nombre_item":
                        consulta_preparada["nombre_item"],

                    "mercado":
                        consulta_preparada["mercado"],

                    "prioridad":
                        consulta_preparada["prioridad"],

                    "tienda":
                        consulta_preparada["tienda"],

                    "dominio":
                        dominio_tienda,

                    "consulta":
                        consulta,

                    "resultados":
                        resultados,

                    "motores_no_disponibles":
                        motores_no_disponibles_acumulados
                }


            # Si no encontró la tienda,
            # el for continúa con el siguiente motor.


        except (
            requests.RequestException,
            ValueError
        ) as error:

            # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

            print(
                f"Ítem {consulta_preparada['numero_item']} | "
                f"{consulta_preparada['tienda']} | "
                f"{nombre_motor}: "
                f"Error al consultar SearXNG: {error}"
            )

            print(
                f"Ítem {consulta_preparada['numero_item']} | "
                f"{consulta_preparada['tienda']} | "
                f"Se probará el siguiente motor."
            )

            # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

            continue


    # --------------------------------------------------------
    # NINGÚN MOTOR ENCONTRÓ LA TIENDA
    # --------------------------------------------------------

    return {
        "numero_item":
            consulta_preparada["numero_item"],

        "nombre_item":
            consulta_preparada["nombre_item"],

        "mercado":
            consulta_preparada["mercado"],

        "prioridad":
            consulta_preparada["prioridad"],

        "tienda":
            consulta_preparada["tienda"],

        "dominio":
            dominio_tienda,

        "consulta":
            consulta,

        "resultados":
            [],

        "motores_no_disponibles":
            motores_no_disponibles_acumulados
    }


# --------------------------------------------------------
# AGRUPAR CONSULTAS POR ÍTEM
# --------------------------------------------------------

def agrupar_consultas_por_item(consultas_preparadas):
    """
    Agrupa las consultas según numero_item.

    Mantiene:
    - el orden en que aparecen los ítems;
    - el orden de las tiendas dentro de cada ítem.
    """

    grupos = {}


    for consulta in consultas_preparadas:

        numero_item = consulta["numero_item"]


        if numero_item not in grupos:

            grupos[numero_item] = []


        grupos[numero_item].append(
            consulta
        )


    return list(
        grupos.values()
    )


# --------------------------------------------------------
# PROCESAR LAS TIENDAS DE UN ÍTEM
# --------------------------------------------------------

def procesar_item(
    consultas_item,
    max_workers_tiendas=2
):
    """
    Procesa las tiendas correspondientes a un solo ítem.

    Dentro del ítem se ejecutan como máximo:

        2 tiendas simultáneamente

    Cada tienda mantiene internamente la política secuencial:

        Brave -> Yahoo -> Google -> Bing
    """

    numero_item = consultas_item[0][
        "numero_item"
    ]


    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

    print()
    print(
        f"INICIANDO ÍTEM {numero_item}"
    )
    print(
        f"Consultas del ítem: "
        f"{len(consultas_item)}"
    )
    print("-" * 70)

    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


    resultados_item = []


    # --------------------------------------------------------
    # MULTIHILO DE TIENDAS
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=max_workers_tiendas
    ) as executor_tiendas:


        # executor.map conserva el orden original
        # de las consultas del ítem.

        resultados = executor_tiendas.map(
            realizar_consulta,
            consultas_item
        )


        for resultado in resultados:

            resultados_item.append(
                resultado
            )


    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

    print()
    print(
        f"FINALIZADO ÍTEM {numero_item}"
    )
    print("-" * 70)

    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


    return resultados_item


# --------------------------------------------------------
# CONSULTAR SEARXNG
# MULTIHILO 2 × 2
# --------------------------------------------------------

def consultar_searxng(
    consultas_preparadas,
    max_workers_items=2,
    max_workers_tiendas=2
):
    """
    Ejecuta las consultas utilizando dos niveles de multihilo.

    NIVEL 1:
        Hasta 2 ítems simultáneos.

    NIVEL 2:
        Hasta 2 tiendas simultáneas dentro de cada ítem.

    Por tanto, con la configuración 2 × 2:

        máximo 4 tiendas pueden estar siendo procesadas
        simultáneamente.

    IMPORTANTE:
    Los motores NO se ejecutan simultáneamente.

    Dentro de cada tienda siguen siendo secuenciales:

        Brave -> Yahoo -> Google -> Bing
    """

    resultados_completos = []


    # --------------------------------------------------------
    # AGRUPAR CONSULTAS POR ÍTEM
    # --------------------------------------------------------

    grupos_items = agrupar_consultas_por_item(
        consultas_preparadas
    )


    total_items = len(
        grupos_items
    )


    total_consultas = len(
        consultas_preparadas
    )


    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

    print()
    print("=" * 70)
    print("MULTIHILO DE BÚSQUEDA")
    print("=" * 70)

    print(
        f"Ítems: {total_items}"
    )

    print(
        f"Consultas totales: {total_consultas}"
    )

    print(
        f"Hilos de ítems: {max_workers_items}"
    )

    print(
        f"Hilos de tiendas por ítem: "
        f"{max_workers_tiendas}"
    )

    print(
        f"Máximo teórico de tiendas simultáneas: "
        f"{max_workers_items * max_workers_tiendas}"
    )

    print("=" * 70)

    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


    # --------------------------------------------------------
    # MULTIHILO DE ÍTEMS
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=max_workers_items
    ) as executor_items:


        # Cada hilo exterior recibe un ítem completo.
        #
        # Dentro de procesar_item se crea el segundo nivel
        # de multihilo para procesar las tiendas.

        resultados_por_item = executor_items.map(
            lambda consultas_item: procesar_item(
                consultas_item,
                max_workers_tiendas
            ),
            grupos_items
        )


        # --------------------------------------------------------
        # UNIR LOS RESULTADOS
        # --------------------------------------------------------

        for resultados_item in resultados_por_item:

            resultados_completos.extend(
                resultados_item
            )


    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))

    print()
    print("=" * 70)
    print("BÚSQUEDA FINALIZADA")
    print(
        f"Resultados procesados: "
        f"{len(resultados_completos)}"
    )
    print("=" * 70)

    # ((((((((((((((((((((((((((LOGS))))))))))))))))))))))))


    return resultados_completos


# --------------------------------------------------------
# DEBUGGING
# --------------------------------------------------------

# if __name__ == "__main__":

#     consultas_prueba = [
#         {
#             "numero_item": 1,
#             "nombre_item":
#                 "Disco Duro Externo SSD 1TB",
#             "mercado": "Estados Unidos",
#             "prioridad": 1,
#             "tienda": "Amazon",
#             "dominio": "amazon.com",
#             "consulta":
#                 "Disco Duro Externo SSD 1TB amazon.com"
#         },
#         {
#             "numero_item": 1,
#             "nombre_item":
#                 "Disco Duro Externo SSD 1TB",
#             "mercado": "Estados Unidos",
#             "prioridad": 1,
#             "tienda": "eBay",
#             "dominio": "ebay.com",
#             "consulta":
#                 "Disco Duro Externo SSD 1TB ebay.com"
#         },
#         {
#             "numero_item": 2,
#             "nombre_item":
#                 "Tarjeta microSDXC 512GB U3 V30 A2",
#             "mercado": "Estados Unidos",
#             "prioridad": 1,
#             "tienda": "Amazon",
#             "dominio": "amazon.com",
#             "consulta":
#                 "Tarjeta microSDXC 512GB U3 V30 A2 amazon.com"
#         },
#         {
#             "numero_item": 2,
#             "nombre_item":
#                 "Tarjeta microSDXC 512GB U3 V30 A2",
#             "mercado": "Estados Unidos",
#             "prioridad": 1,
#             "tienda": "eBay",
#             "dominio": "ebay.com",
#             "consulta":
#                 "Tarjeta microSDXC 512GB U3 V30 A2 ebay.com"
#         }
#     ]


#     resultados = consultar_searxng(
#         consultas_prueba,
#         max_workers_items=2,
#         max_workers_tiendas=2
#     )


#     print()
#     print("RESULTADO FINAL")
#     print("=" * 70)


#     for resultado in resultados:

#         print(
#             f"Ítem {resultado['numero_item']} | "
#             f"{resultado['tienda']} | "
#             f"{len(resultado['resultados'])} "
#             f"resultados brutos"
#         )
