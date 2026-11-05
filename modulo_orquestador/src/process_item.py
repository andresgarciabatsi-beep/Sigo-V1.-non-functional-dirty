
from .process_url import process_url


def process_item(item: dict) -> dict:
    """
    Procesa las tiendas y URLs de un ítem.

    Agrupa los resultados extraídos bajo el número
    del ítem correspondiente.
    """

    numero_item = item["numero_item"]

    resultado_item = {
        "item": numero_item,
        "resultados": []
    }

    print(f"\nProcesando ítem: {numero_item}")
    print(f"Producto solicitado: {item.get('nombre_item', '')}")

    # Recorrer tiendas del ítem
    for tienda in item["tiendas"]:

        nombre_tienda = tienda["tienda"]

        print(f"\nTienda: {nombre_tienda}")

        # Recorrer URLs de la tienda
        for url in tienda["urls"]:

            print(f"Procesando URL: {url}")

            # Enviar a Fetch y Extract
            producto = process_url(url)

            if producto is None:
                continue

            # Asociar información con la tienda
            resultado = {
                "tienda": nombre_tienda,
                "url": producto["url"],
                **producto["datos"]
            }

            resultado_item["resultados"].append(resultado)

            print(
                "OK Orquestador: Producto extraído:",
                resultado.get("nombre")
            )

    return resultado_item
