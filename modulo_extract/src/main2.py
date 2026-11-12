
"""
SIGO Extract

Entrada principal:
    Respuesta de Fetch (dict)

Salida:
    Cinco campos del producto.

Flujo:
    Fetch -> fuentes -> localizadores -> filtros -> resultado

Los archivos solamente se utilizan en main() para pruebas locales.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import filtros

from fuentes import preparar_fuentes

from localizadores import (
    localizar_nombre,
    localizar_precio,
    localizar_disponibilidad,
    localizar_descripcion,
    localizar_especificaciones,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE = Path(__file__).resolve().parent.parent

PATRONES = BASE / "recursos" / "patrones.json"

CAMPOS = {
    "nombre": localizar_nombre,
    "precio": localizar_precio,
    "disponibilidad": localizar_disponibilidad,
    "descripcion": localizar_descripcion,
    "especificaciones": localizar_especificaciones,
}

SELECTORES = {
    "nombre": filtros.select_nombre,
    "precio": filtros.select_precio,
    "disponibilidad": filtros.select_stock,
    "descripcion": filtros.select_descripcion,
    "especificaciones": filtros.select_especificaciones,
}


# ============================================================
# PARÁMETROS DE PRUEBA - MODIFICAR AQUÍ
# ============================================================

# Archivo JSON que contiene la respuesta completa de Fetch.
ARCHIVO_PRUEBA = BASE / "recursos" / "resultado_fetch.json"

ITEM_PRUEBA = 1

TIENDA_PRUEBA = "Tecnit"

SALIDA_PRUEBA = BASE / "resultados" / "extract_prueba.json"

DEPURAR = True


# ============================================================
# 1. CARGAR PATRONES
# ============================================================

def cargar_patrones():

    with open(PATRONES, "r", encoding="utf-8-sig") as archivo:
        patrones = json.load(archivo)

    configuracion = patrones.get("campos", {})

    for campo in CAMPOS:

        if not isinstance(configuracion.get(campo), list):
            raise ValueError(
                f"No se encontraron patrones para: {campo}"
            )

    return patrones


# ============================================================
# 2. VALIDAR RESPUESTA DE FETCH
# ============================================================

def validar_fetch(respuesta_fetch: dict):
    """
    Valida la respuesta recibida desde Fetch.

    Extrae el HTML y la URL final.
    """

    if not isinstance(respuesta_fetch, dict):
        raise TypeError(
            "Extract esperaba un diccionario de Fetch"
        )

    exito = respuesta_fetch.get("exito")
    status = respuesta_fetch.get("status_code")
    error = respuesta_fetch.get("error")

    if exito is not True:
        raise ValueError(
            f"Fetch no fue exitoso. Error: {error}"
        )

    if (
        not isinstance(status, int)
        or not 200 <= status < 300
    ):
        raise ValueError(
            f"Fetch devolvió un código HTTP no válido: {status}"
        )

    html = respuesta_fetch.get("html")

    if not isinstance(html, str) or not html.strip():
        raise ValueError(
            "Fetch no devolvió un HTML válido"
        )

    url = (
        respuesta_fetch.get("url_final")
        or respuesta_fetch.get("url_original")
    )

    return html, url


# ============================================================
# 3. LOCALIZAR CANDIDATOS
# ============================================================

def localizar_candidatos(fuentes, patrones):
    """
    Ejecuta las funciones existentes de localizadores.py.

    Se realiza una sola localización por campo.

    Los candidatos se conservan para su evaluación posterior.
    """

    resultados = {}

    for campo, funcion in CAMPOS.items():

        _, candidatos = funcion(
            fuentes,
            patrones,
            detalle=True
        )

        resultados[campo] = candidatos

    return resultados


# ============================================================
# 4. ADAPTAR CANDIDATOS A FILTROS
# ============================================================

def adaptar_candidatos(localizados):
    """
    Transforma los candidatos ya localizados al formato
    que acepta filtros.leer_candidatos_brutos().

    No ejecuta patrones.
    No vuelve a extraer valores.
    No escribe JSON intermedios.
    """

    evidencia = {
        "resultado": {}
    }

    for campo, candidatos in localizados.items():

        reglas = []

        for candidato in candidatos:

            reglas.append({
                "fuente": candidato["fuente"],
                "patron": candidato["patron"],
                "prioridad": candidato.get("prioridad", 0),
                "coincidencias": [
                    {
                        "indice": candidato.get("indice"),
                        "valor": candidato["valor"]
                    }
                ]
            })

        evidencia["resultado"][campo] = reglas

    return evidencia


# ============================================================
# 5. FILTRAR CANDIDATOS
# ============================================================

def aplicar_filtros(localizados, arbol):
    """
    Aplica contexto, limpieza, deduplicación,
    puntuación y selección final.
    """

    evidencia = adaptar_candidatos(localizados)

    candidatos, info = filtros.leer_candidatos_brutos(
        evidencia,
        arbol
    )

    grupos = filtros.agrupar_duplicados(candidatos)

    advertencias = list(
        info.get("errores_selectores", [])
    )

    ficha = {}
    seleccionados = {}

    for campo, funcion in SELECTORES.items():

        ficha[campo], seleccionados[campo] = funcion(
            grupos,
            advertencias
        )

    estado = filtros.validar_ficha(
        ficha,
        grupos,
        advertencias
    )

    diagnostico = {
        "estado_validacion": estado,
        "advertencias": list(dict.fromkeys(advertencias)),
        "candidatos_localizados": {
            campo: len(valores)
            for campo, valores in localizados.items()
        },
        "candidatos_evaluados": len(candidatos),
        "grupos": len(grupos),
        "grupos_seleccionados": seleccionados,
    }

    return ficha, diagnostico


# ============================================================
# 6. NORMALIZAR CAMPOS DE SALIDA
# ============================================================

def convertir_precio(valor):

    if isinstance(valor, str):
        return valor.strip() or None

    if not isinstance(valor, dict):
        return None

    original = valor.get("texto_original")

    if isinstance(original, str) and original.strip():
        return original.strip()

    importe = valor.get("importe")

    if importe is None:
        return None

    moneda = valor.get("moneda")

    if moneda:
        return f"{moneda} {importe}"

    return str(importe)


def convertir_disponibilidad(valor):

    if isinstance(valor, str):
        return valor.strip() or None

    if not isinstance(valor, dict):
        return None

    estado = valor.get("estado")

    if estado and estado != "desconocido":
        return str(estado)

    return None


# ============================================================
# 7. MOTOR DE EXTRACT
# ============================================================

def procesar_html(html: str, url: str | None = None):
    """
    Procesa un único HTML en memoria.

    No lee archivos.
    No guarda resultados.
    """

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML vacío o inválido")

    patrones = cargar_patrones()

    # Preparar HTML y fuentes estructuradas.
    fuentes = preparar_fuentes(
        html,
        url_base=url or "https://ejemplo.invalid/"
    )

    # Localizar candidatos una sola vez.
    localizados = localizar_candidatos(
        fuentes,
        patrones
    )

    # Evaluar los candidatos localizados.
    ficha, diagnostico = aplicar_filtros(
        localizados,
        fuentes["html"]
    )

    # Convertir al contrato de cinco campos.
    resultado = {
        "nombre": ficha.get("nombre"),
        "precio": convertir_precio(ficha.get("precio")),
        "disponibilidad": convertir_disponibilidad(
            ficha.get("disponibilidad")
        ),
        "descripcion": ficha.get("descripcion"),
        "especificaciones": ficha.get("especificaciones"),
    }

    return resultado, diagnostico


# ============================================================
# 8. PROCESAR RESPUESTA DE FETCH
# ============================================================

def procesar_fetch(respuesta_fetch: dict):
    """
    Recibe la estructura completa de Fetch.

    Devuelve los campos extraídos y el diagnóstico.
    """

    html, url = validar_fetch(respuesta_fetch)

    resultado, diagnostico = procesar_html(
        html,
        url
    )

    diagnostico["fetch"] = {
        "url_original": respuesta_fetch.get("url_original"),
        "url_final": respuesta_fetch.get("url_final"),
        "status_code": respuesta_fetch.get("status_code"),
        "tool": respuesta_fetch.get("tool"),
    }

    return resultado, diagnostico


# ============================================================
# 9. INTERFAZ PÚBLICA PARA EL ORQUESTADOR
# ============================================================

def extract_product(
    entrada: dict | str,
    url: str | None = None
) -> dict:
    """
    Interfaz de Extract.

    Forma principal:
        extract_product(respuesta_fetch)

    Compatibilidad con el contrato anterior:
        extract_product(html, url)

    Siempre devuelve únicamente los cinco campos.
    """

    if isinstance(entrada, dict):

        resultado, _ = procesar_fetch(entrada)

    elif isinstance(entrada, str):

        resultado, _ = procesar_html(entrada, url)

    else:

        raise TypeError(
            "Extract espera una respuesta Fetch o un HTML"
        )

    return resultado


# ============================================================
# 10. MAIN PARA PRUEBAS LOCALES
# ============================================================

def main():
    """
    Prueba local usando parámetros fijos.

    El Orquestador no necesita ejecutar main().
    """

    # Leer respuesta de Fetch desde archivo de prueba.

    with open(
        ARCHIVO_PRUEBA,
        "r",
        encoding="utf-8-sig"
    ) as archivo:

        respuesta_fetch = json.load(archivo)

    # Ejecutar Extract.

    resultado, diagnostico = procesar_fetch(
        respuesta_fetch
    )

    # Resolver tienda.

    url = (
        respuesta_fetch.get("url_final")
        or respuesta_fetch.get("url_original")
    )

    tienda = TIENDA_PRUEBA

    if not tienda:
        tienda = (
            urlparse(url).hostname or ""
            if url else ""
        )

    # Generar estructura de prueba.

    salida = [
        {
            "item": ITEM_PRUEBA,
            "resultados": [
                {
                    "tienda": tienda,
                    "url": url,
                    **resultado
                }
            ]
        }
    ]

    # Guardar resultado de prueba.

    SALIDA_PRUEBA.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    SALIDA_PRUEBA.write_text(
        json.dumps(
            salida,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # Guardar auditoría si está habilitada.

    if DEPURAR:

        ruta_auditoria = SALIDA_PRUEBA.with_name(
            SALIDA_PRUEBA.stem + "_auditoria.json"
        )

        ruta_auditoria.write_text(
            json.dumps(
                diagnostico,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print(f"Auditoría: {ruta_auditoria}")

    # Mostrar resultado.

    print(
        json.dumps(
            salida,
            ensure_ascii=False,
            indent=2
        )
    )

    print(f"\nResultado guardado en: {SALIDA_PRUEBA}")


if __name__ == "__main__":
    main()
