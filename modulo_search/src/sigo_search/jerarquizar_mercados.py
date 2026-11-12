import math



def normalizar_plazo_de_ejecucion(plazo_ejecucion):
    """
    Convierte el plazo de ejecución a días calendario.

    Ejemplo:
    Entrada esperada:
    {
        "valor": 10,
        "unidad": "Días",
        "tipo": "Laborables"
    }

    Ejemplo de salida:
    14 días calendario
    """

    # Datos del JSON del TDR
    valor = plazo_ejecucion["valor"]
    unidad = plazo_ejecucion["unidad"]  # Puede ser "Días", "Semanas" o "Meses"
    tipo = plazo_ejecucion["tipo"]  # Puede ser "Laborables", "Calendario" o null

    # Verificar que existan los datos necesarios
    if valor is None:
        raise ValueError(
            "jerarquizar_mercados.py: No se pudo determinar el valor del plazo de ejecución: no hay valor en el plazo"
        )

    if unidad is None:
        raise ValueError(
            "jerarquizar_mercados.py: No se pudo determinar la unidad del plazo de ejecución: no hay unidad en el plazo"
        )

    # Limpiar texto de unidad
    unidad = unidad.lower().strip()

    # Si existe tipo, limpiar también su texto
    if tipo is not None:
        tipo = tipo.lower().strip()

    # --------------------------------------------------------
    # 1. Convertir la unidad (que puede estar en semanas o meses) a días
    # --------------------------------------------------------

    match unidad:

        case "día" | "días" | "dia" | "dias":
            dias = valor

        case "semana" | "semanas":
            dias = valor * 7

        case "mes" | "meses":
            dias = valor * 30

        case _:
            raise ValueError(
                f"jerarquizar_mercados.py: Unidad de plazo no reconocida para el calculo del plazo de ejecución: {unidad}"
            )

    # --------------------------------------------------------
    # 2. Convertir días laborables a días calendario
    # --------------------------------------------------------

    match tipo:

        case "laborable" | "laborables"|"habil" | "hábil" | "habiles" | "hábiles":
            dias = math.ceil(dias * 7 / 5)

        case "calendario" | None:
            # Si el tipo es null, se considera calendario
            # únicamente para efectos de jerarquización.
            pass

        case _:
            raise ValueError(
                f"jerarquizar_mercados.py: Tipo de plazo no reconocido para el calculo del plazo de ejecución: {tipo}"
            )

    return dias


def jerarquizar_mercados(plazo_ejecucion):
    """
    Determina el orden de prioridad de los mercados
    según el plazo de ejecución.

    Ejemplo de salida:
    [("Nacionales", 1), ("Estados Unidos", 2), ("China", 3)]
    """

    dias = normalizar_plazo_de_ejecucion(plazo_ejecucion)

    match dias:

        # Menos de 15 días
        case _ if dias < 15:
            jerarquia = [
                ("Nacionales", 1),
                ("Estados Unidos", 2),
                ("China", 3)
            ]

        # Entre 15 y 40 días
        case _ if 15 <= dias <= 40:
            jerarquia = [
                ("Estados Unidos", 1),
                ("China", 2),
                ("Nacionales", 3)
            ]

        # Más de 40 días
        case _ if dias > 40:
            jerarquia = [
                ("China", 1),
                ("Estados Unidos", 2),
                ("Nacionales", 3)
            ]

    return jerarquia

#DEBUGGING
# if __name__ == "__main__":
#    import json
#     with open("tdr.json", "r", encoding="utf-8") as archivo:
#         tdr = json.load(archivo)

#     plazo = tdr["plazo_ejecucion"]

#     dias = normalizar_plazo_de_ejecucion(plazo)
#     jerarquia = jerarquizar_mercados(plazo)

#     print("Plazo original:")
#     print(plazo)

#     print("\nPlazo normalizado:")
#     print(dias, "días calendario equivalentes")

#     print("\nJerarquía de mercados:")
#     print(jerarquia)