import json
import time
from pathlib import Path

from jerarquizar_mercados import jerarquizar_mercados
from estructurar_consultas import estructurar_consultas
from consultar_searxng import consultar_searxng
from filtrar_resultados import filtrar_resultados
from filtrar_colecciones import filtrar_colecciones
from puntuar_relacion_con_item import puntuar_relacion_con_item


# --------------------------------------------------------
# RUTAS
# --------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT / "config"
OUTPUTS_DIR = ROOT / "outputs"

ARCHIVO_MERCADOS = (
    CONFIG_DIR
    / "mercados_y_tiendas.json"
)

ARCHIVO_CONFIG_MULTIHILO = (
    CONFIG_DIR
    / "config_multihilo.json"
)
# --------------------------------------------------------
# EJECUTAR SEARCH DESDE LA WEB
# --------------------------------------------------------

def ejecutar_search_web(tdr):

    # ----------------------------------------------------s
    # Leer configuración de multihilo
    # ----------------------------------------------------
    with open(
        ARCHIVO_CONFIG_MULTIHILO,
        "r",
        encoding="utf-8"
    ) as archivo:
        config_multihilo = json.load(archivo)

    # ----------------------------------------------------
    # 1. Leer mercados y tiendas
    # ----------------------------------------------------

    with open(
        ARCHIVO_MERCADOS,
        "r",
        encoding="utf-8"
    ) as archivo:

        mercados_y_tiendas = json.load(archivo)


    # ----------------------------------------------------
    # 2. Extraer información del TDR recibido
    # ----------------------------------------------------

    plazo_ejecucion = tdr["plazo_ejecucion"]
    items = tdr["items"]


    # ----------------------------------------------------
    # 3. Jerarquizar mercados
    # ----------------------------------------------------

    jerarquia = jerarquizar_mercados(
        plazo_ejecucion
    )


    # ----------------------------------------------------
    # 4. Estructurar consultas
    # ----------------------------------------------------

    consultas = estructurar_consultas(
        items,
        jerarquia,
        mercados_y_tiendas
    )


    # ----------------------------------------------------
    # 5. Consultar SearXNG
    # ----------------------------------------------------

    inicio_busqueda = time.perf_counter()

    #((((((((((((((((((((((LOGS))))))))))))))))))))))
    print("CONFIGURACIÓN DE HILOS")
    print("-" * 70)
    print(
        f"Hilos de ítems: {config_multihilo['hilos_items']}"
    )
    print(
        f"Hilos de tiendas: {config_multihilo['hilos_tiendas']}"
    )
    print("-" * 70)
    #((((((((((((((((((((((LOGS))))))))))))))))))))))
    
    resultados = consultar_searxng(
        consultas,
        max_workers_items=config_multihilo["hilos_items"],
        max_workers_tiendas=config_multihilo["hilos_tiendas"]
    )

    fin_busqueda = time.perf_counter()

    tiempo_busqueda = (fin_busqueda- inicio_busqueda)


    # ----------------------------------------------------
    # 6. Guardar resultados brutos
    # ----------------------------------------------------

    OUTPUTS_DIR.mkdir(
        exist_ok=True
    )

    with open(
        OUTPUTS_DIR / "resultados_searxng.json",
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados,
            archivo,
            ensure_ascii=False,
            indent=4
        )


    # ----------------------------------------------------
    # 7. Primer filtro
    # ----------------------------------------------------

    resultados_pf = filtrar_resultados(
        resultados
    )

    with open(
        OUTPUTS_DIR / "resultados_pf.json",
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados_pf,
            archivo,
            ensure_ascii=False,
            indent=2
        )


    # ----------------------------------------------------
    # 8. Segundo filtro
    # ----------------------------------------------------

    resultados_sf = filtrar_colecciones(
        resultados_pf
    )

    with open(
        OUTPUTS_DIR / "resultados_sf.json",
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados_sf,
            archivo,
            ensure_ascii=False,
            indent=2
        )


    # ----------------------------------------------------
    # 9. BM25
    # ----------------------------------------------------

    resultados_filtrados = (
        puntuar_relacion_con_item(
            resultados_sf
        )
    )


    #ESCRIBIR LOS RESULTADOS FILTRADOS EN UN ARCHIVO JSON
    with open(
        OUTPUTS_DIR / "resultados_filtrados.json",
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados_filtrados,
            archivo,
            ensure_ascii=False,
            indent=2
        )


    # ----------------------------------------------------
    # 10. DEVOLVER RESULTADO A LA API
    # ----------------------------------------------------

    return {
        "resultados": resultados_filtrados,
        "items_procesados": len(items),
        "consultas_realizadas": len(consultas),
        "tiempo_busqueda": tiempo_busqueda
    }