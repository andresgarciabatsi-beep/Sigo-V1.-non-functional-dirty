
from pathlib import Path
import json
from src.filter_item_urls_region import agrupar_resultados
from src.process_item import process_item
from src.save_results import save_results


# ============================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================

ORQUESTADOR_DIR = Path(__file__).resolve().parent

# Archivo recibido de Search
ARCHIVO_ENTRADA = (
    ORQUESTADOR_DIR
    / "resources"
    / "resultados_filtrados_ups.json"
)




# ============================================================
# CONFIGURACIÓN DE EJECUCIÓN
# ============================================================

# None = procesar todos los ítems
# 1 = procesar solamente el primer ítem
LIMITE_ITEMS = None


# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================

def main():

    print("\n========== SIGO ORQUESTADOR ==========")

    # 1. Ejecutar primer filtro
    print("\n[1] Agrupando resultados de Search...")

    with ARCHIVO_ENTRADA.open("r", encoding="utf-8") as archivo:
        registros = json.load(archivo)

    items = agrupar_resultados(registros)

    # 2. Limitar ítems para pruebas
    if LIMITE_ITEMS is not None:
        items = items[:LIMITE_ITEMS]

    print(f"\n[2] Ítems a procesar: {len(items)}")

    # 3. Procesar ítems
    resultados = []

    for item in items:

        resultado_item = process_item(item)

        resultados.append(resultado_item)

    # 4. Guardar resultados consolidados
    print("\n[3] Guardando resultados...")

    archivo_salida = save_results(resultados)

    # 5. Resumen de ejecución
    total_productos = sum(
        len(item["resultados"])
        for item in resultados
    )

    print("\n========== RESUMEN ==========")
    print(f"Ítems procesados: {len(resultados)}")
    print(f"Productos extraídos: {total_productos}")
    print(f"Archivo de salida: {archivo_salida}")
    print("================================")


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
