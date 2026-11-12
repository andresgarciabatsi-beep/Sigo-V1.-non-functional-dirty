#PAQUETES EXTERNOS
import subprocess
import sys
from pathlib import Path
import json
import time

#PAQUETES LOCALES
from jerarquizar_mercados import jerarquizar_mercados
from estructurar_consultas import estructurar_consultas
from consultar_searxng import consultar_searxng
from filtrar_resultados import filtrar_resultados
from filtrar_colecciones import filtrar_colecciones
from puntuar_relacion_con_item import puntuar_relacion_con_item

# --------------------------------------------------------
# RUTAS DEL PROYECTO
# --------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT / "config"
TDR_EXAMPLES_DIR = ROOT / "tdr_examples"
OUTPUTS_DIR = ROOT / "outputs"
WEB_INTERFACE_DIR = ROOT / "web_interface"

OUTPUTS_DIR.mkdir(exist_ok=True)
ARCHIVO_MERCADOS = CONFIG_DIR / "mercados_y_tiendas_actualizado.json"


#Emplear un archivo de ejemplo de TDR para pruebas
ARCHIVO_TDR = TDR_EXAMPLES_DIR / "tdr_memorias.json"


# --------------------------------------------------------

def main():

    # --------------------------------------------------------
    # 1. Leer el JSON del TDR
    # --------------------------------------------------------

    with open(ARCHIVO_TDR, "r", encoding="utf-8") as archivo:
        tdr = json.load(archivo)

    # --------------------------------------------------------
    # 2. Leer los mercados y tiendas
    # --------------------------------------------------------

    with open(
        ARCHIVO_MERCADOS,
        "r",
        encoding="utf-8"
    ) as archivo:

        mercados_y_tiendas = json.load(archivo)

    # --------------------------------------------------------
    # 3. Extraer los datos necesarios del TDR
    # --------------------------------------------------------

    plazo_ejecucion = tdr["plazo_ejecucion"]
    items = tdr["items"]

    # --------------------------------------------------------
    # 4. Determinar la jerarquía de mercados
    # --------------------------------------------------------

    jerarquia = jerarquizar_mercados(
        plazo_ejecucion
    )

    print("Jerarquía de mercados:")
    print(jerarquia)

    # --------------------------------------------------------
    # 5. Estructurar todas las consultas
    # --------------------------------------------------------

    consultas = estructurar_consultas(
        items,
        jerarquia,
        mercados_y_tiendas
    )

    print()
    print(
        f"Consultas generadas: {len(consultas)}"
    )

    # --------------------------------------------------------
    # 6. Consultar SearXNG
    # --------------------------------------------------------

    #Medir el tiempo de ejecución de la función consultar_searxng
    inicio_busqueda = time.perf_counter()
    resultados = consultar_searxng(
        consultas,
        max_workers_items=2,
        max_workers_tiendas=2
    )

    #Medir el tiempo de ejecución de la función consultar_searxng
    fin_busqueda = time.perf_counter()
    tiempo_busqueda = fin_busqueda - inicio_busqueda
    # --------------------------------------------------------
    # 7. Guardar resultados brutos
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 8. Primer filtro: dominio de la tienda
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 9. Segundo filtro: eliminar colecciones
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 10. Tercer filtro: BM25 por ítem y región
    # --------------------------------------------------------

    resultados_filtrados = puntuar_relacion_con_item(
        resultados_sf
    )

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

    ruta_generar_html = (
        WEB_INTERFACE_DIR
        / "generar_html.py"
    )

    subprocess.run(
        [sys.executable, str(ruta_generar_html)],
        check=True
    )
    # --------------------------------------------------------
    # 11. Contar resultados en cada etapa
    # --------------------------------------------------------

    total_brutos = sum(
        len(consulta["resultados"])
        for consulta in resultados
    )

    total_pf = sum(
        len(consulta["resultados"])
        for consulta in resultados_pf
    )

    total_sf = sum(
        len(consulta["resultados"])
        for consulta in resultados_sf
    )

    total_resultados_validos = sum(
        len(consulta["resultados"])
        for consulta in resultados_filtrados
    )

    #(((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))

    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)

    print(
        f"Ítems procesados: {len(items)}"
    )

    print(
        f"Consultas realizadas: {len(resultados)}"
    )

    print()
    print("RESULTADOS POR ETAPA")
    print("-" * 70)

    print(
        f"Resultados brutos de SearXNG: {total_brutos}"
    )

    print(
        f"Resultados después del primer filtro: {total_pf}"
    )

    print(
        f"Resultados después de eliminar colecciones: {total_sf}"
    )

    print(
        f"Resultados después de BM25: {total_resultados_validos}"
    )

    print()
    print("ARCHIVOS GENERADOS")
    print("-" * 70)

    print(
        f"1. {OUTPUTS_DIR / 'resultados_searxng.json'}"
    )

    print(
        f"2. {OUTPUTS_DIR / 'resultados_pf.json'}"
    )

    print(
        f"3. {OUTPUTS_DIR / 'resultados_sf.json'}"
    )

    print(
        f"4. {OUTPUTS_DIR / 'resultados_filtrados.json'}"
    )

    print("=" * 70)

    print(f"Tiempo total de búsqueda: {tiempo_busqueda:.2f} segundos")
    #(((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))


if __name__ == "__main__":
    main()
