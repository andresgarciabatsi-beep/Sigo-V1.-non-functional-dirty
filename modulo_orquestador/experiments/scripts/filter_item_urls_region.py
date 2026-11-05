"""Consolida la salida de Search por ítem y tienda para SIGO."""

import json
from pathlib import Path


def agrupar_resultados(registros: list[dict]) -> list[dict]:
    """Agrupa por numero_item, conserva tiendas y elimina URLs repetidas."""
    
    #((((((((((((((((((((((((((((((((((((((((((((LOGS))))))))))))))))))))))))))))))))))))))))))))
    if not isinstance(registros, list):
        raise ValueError("ERROR from filter_item_urls_region.py in Orquestador: El JSON de Search debe contener una lista de registros.")
    else:
        print("OK from filter_item_urls_region.py in Orquestador: El JSON de Search contiene una lista de registros.")
    #((((((((((((((((((((((((((((((((((((((((((((LOGS))))))))))))))))))))))))))))))))))))))))))))

    
    items = {}
    tiendas_por_item = {}
    urls_por_tienda = {}

    for indice, registro in enumerate(registros, start=1):
        
        if not isinstance(registro, dict):
            raise ValueError(f"ERROR from filter_item_urls_region.py in Orquestador: El registro {indice} debe ser un objeto JSON.")

        numero = registro.get("numero_item")
        if numero is None:
            raise ValueError(f"ERROR from filter_item_urls_region.py in Orquestador: El registro {indice} no tiene 'numero_item'.")

        resultados = registro.get("resultados", [])
        if not isinstance(resultados, list):
            raise ValueError(f"ERROR from filter_item_urls_region.py in Orquestador: El campo 'resultados' del registro {indice} debe ser una lista.")

        # No incluimos tiendas vacías en la salida operativa.
        enlaces = []
        for resultado in resultados:
            if not isinstance(resultado, dict):
                continue
            url = resultado.get("url")
            if isinstance(url, str) and url.strip():
                enlaces.append(url.strip())

        if numero not in items:
            items[numero] = {
                "numero_item": numero,
                "nombre_item": registro.get("nombre_item", ""),
                "tiendas": [],
            }
            tiendas_por_item[numero] = {}

        if not enlaces:
            continue

        tienda = registro.get("tienda", "")
        dominio = registro.get("dominio", "")
        mercado = registro.get("mercado", "")
        prioridad = registro.get("prioridad")
        clave_tienda = (tienda, dominio, mercado, prioridad)

        if clave_tienda not in tiendas_por_item[numero]:
            bloque = {
                "tienda": tienda,
                "dominio": dominio,
                "mercado": mercado,
                "prioridad": prioridad,
                "urls": [],
            }
            tiendas_por_item[numero][clave_tienda] = bloque
            items[numero]["tiendas"].append(bloque)
            urls_por_tienda[(numero, clave_tienda)] = set()

        bloque = tiendas_por_item[numero][clave_tienda]
        urls_vistas = urls_por_tienda[(numero, clave_tienda)]
        for url in enlaces:
            if url not in urls_vistas:
                bloque["urls"].append(url)
                urls_vistas.add(url)

    return list(items.values())


def filter_results_from_search(archivo_entrada: str | Path, archivo_salida: str | Path) -> list[dict]:
    """Lee la salida de Search, consolida los ítems y escribe el nuevo JSON."""
    entrada = Path(archivo_entrada)
    salida = Path(archivo_salida)

    with entrada.open("r", encoding="utf-8") as archivo:
        registros = json.load(archivo)

    agrupados = agrupar_resultados(registros)

    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8") as archivo:
        json.dump(agrupados, archivo, ensure_ascii=False, indent=2)

    print("OK from filter_results_from_search.py in Orquestador: Se ha generado el archivo de resultados agrupados.")
    print(f"Ítems: {len(agrupados)}")
    print(f"Tiendas con enlaces: {sum(len(item['tiendas']) for item in agrupados)}")
    print(f"URLs: {sum(len(tienda['urls']) for item in agrupados for tienda in item['tiendas'])}")
    print(f"Archivo generado: {salida}")
    return agrupados

# #DEBUGGING DE LA FUNCION
if __name__ == "__main__":
    SRC_DIR = Path(__file__).resolve().parent
    ARCHIVO_ENTRADA = SRC_DIR.parent / "resources" / "resultados_filtrados_memorias.json"
    ARCHIVO_SALIDA = SRC_DIR.parent / "results" / "resultados_agrupados.json"
    filter_results_from_search(ARCHIVO_ENTRADA, ARCHIVO_SALIDA)