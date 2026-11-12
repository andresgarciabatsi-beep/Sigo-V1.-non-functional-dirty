def estructurar_consultas(items, jerarquia, mercados_y_tiendas):
    """
    Construye las consultas que posteriormente serán enviadas a SearXNG.

    Entradas:
    - items: lista de ítems provenientes del JSON del TDR.
    - jerarquia: lista de tuplas generada por jerarquizar_mercados.py.
      Ejemplo:
      [
          ("Estados Unidos", 1),
          ("China", 2),
          ("Nacionales", 3)
      ]
    - mercados: contenido de mercados_y_tiendas.json.

    Salida:
    - Lista de consultas estructuradas.
    """

    consultas = []

    # --------------------------------------------------------
    # 1. Recorrer ítem por ítem
    # --------------------------------------------------------

    for item in items:

        #Nombre del producto
        nombre_item = item["nombre"]
        #Numero del producto dentro del TDR
        numero_item = item["numero_item"]
        

        # ----------------------------------------------------
        # 2. Recorrer mercado por mercado según prioridad
        # ----------------------------------------------------

        for nombre_mercado, prioridad in jerarquia:

            # Obtener las tiendas pertenecientes al mercado
            tiendas = mercados_y_tiendas["mercados"][nombre_mercado]

            # ------------------------------------------------
            # 3. Recorrer tienda por tienda
            # ------------------------------------------------

            for tienda in tiendas:

                nombre_tienda = tienda["nombre"]
                dominio = tienda["dominio"]

                # Construir la consulta que recibirá SearXNG
                consulta = f"{nombre_item} {dominio}"

                consultas.append(
                    {
                        "numero_item": numero_item,
                        "nombre_item": nombre_item,
                        "mercado": nombre_mercado,
                        "prioridad": prioridad,
                        "tienda": nombre_tienda,
                        "dominio": dominio,
                        "consulta": consulta
                    }
                )

    return consultas

#DEBUGGING
# if __name__ == "__main__":

#     import json

#     # Leer los ítems del TDR
#     with open("tdr.json", "r", encoding="utf-8") as archivo:
#         tdr = json.load(archivo)

#     # Leer los mercados y sus tiendas
#     with open("mercados_y_tiendas.json", "r", encoding="utf-8") as archivo:
#         mercados = json.load(archivo)

#     items = tdr["items"]

#     # Jerarquía de prueba
#     jerarquia = [
#         ("Estados Unidos", 1),
#         ("China", 2),
#         ("Nacionales", 3)
#     ]

#     consultas = estructurar_consultas(
#         items,
#         jerarquia,
#         mercados
#     )

#     print("Consultas estructuradas:")
#     print()

#     for consulta in consultas:
#         print(consulta)