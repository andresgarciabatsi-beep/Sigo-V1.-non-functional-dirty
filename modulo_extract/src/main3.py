"""SIGO Extract - extraccion de los cinco campos desde un unico HTML.

Uso:
    python main3.py ../recursos/htmls_ampliado/01_tecnit.html
    python main3.py ../recursos/htmls_ampliado/01_tecnit.html --url https://...
    python main3.py ../recursos/htmls_ampliado/01_tecnit.html --solo-campos
    python main3.py ../recursos/htmls_ampliado/01_tecnit.html --salida ficha.json
    python main3.py ../recursos/htmls_ampliado/01_tecnit.html --auditoria

Tambien puede importarse:

    from main3 import extraer_html, extraer_archivo

No descarga URLs ni exige una respuesta de Fetch. Recibe un HTML ya
descargado y ejecuta el pipeline existente:

    fuentes.preparar_fuentes
        -> localizadores.localizar_*
        -> filtros.leer_candidatos_brutos / agrupar_duplicados / select_*
        -> cinco campos + diagnostico
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import filtros  # noqa: E402

from fuentes import preparar_fuentes  # noqa: E402

from localizadores import (  # noqa: E402
    localizar_nombre,
    localizar_precio,
    localizar_disponibilidad,
    localizar_descripcion,
    localizar_especificaciones,
)

BASE = Path(__file__).resolve().parent.parent
PATRONES = BASE / "recursos" / "patrones.json"

CAMPOS = filtros.CAMPOS

LOCALIZADORES = {
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
# 1. PATRONES Y CANDIDATOS
# ============================================================

def cargar_patrones(ruta: str | Path = PATRONES) -> dict:
    """Carga patrones.json y comprueba que existan los cinco campos."""

    with open(ruta, "r", encoding="utf-8-sig") as archivo:
        patrones = json.load(archivo)

    configuracion = patrones.get("campos", {})

    for campo in CAMPOS:
        if not isinstance(configuracion.get(campo), list):
            raise ValueError(
                f"No se encontraron patrones para: {campo}"
            )

    return patrones


def localizar_candidatos(fuentes: dict, patrones: dict) -> dict:
    """Ejecuta una localizacion por campo y conserva los candidatos."""

    resultados = {}

    for campo, funcion in LOCALIZADORES.items():
        _, candidatos = funcion(
            fuentes,
            patrones,
            detalle=True,
        )
        resultados[campo] = candidatos

    return resultados


def adaptar_candidatos(localizados: dict) -> dict:
    """Transforma los candidatos al formato de filtros.leer_candidatos_brutos."""

    evidencia = {"resultado": {}}

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
                        "valor": candidato["valor"],
                    }
                ],
            })

        evidencia["resultado"][campo] = reglas

    return evidencia


# ============================================================
# 2. FILTROS Y SELECCION
# ============================================================

def aplicar_filtros(
    localizados: dict,
    arbol,
    incluir_auditoria: bool = False,
) -> tuple[dict, dict]:
    """Aplica limpieza, contexto, agrupacion, puntuacion y seleccion."""

    evidencia = adaptar_candidatos(localizados)

    candidatos, info = filtros.leer_candidatos_brutos(
        evidencia,
        arbol,
    )

    grupos = filtros.agrupar_duplicados(candidatos)

    advertencias = list(info.get("errores_selectores", []))

    ficha = {}
    seleccionados = {}

    for campo, funcion in SELECTORES.items():
        ficha[campo], seleccionados[campo] = funcion(
            grupos,
            advertencias,
        )

    estado = filtros.validar_ficha(
        ficha,
        grupos,
        advertencias,
    )

    diagnostico = {
        "estado_validacion": estado,
        "advertencias": list(dict.fromkeys(advertencias)),
        "titulo_referencia": info.get("titulo_referencia"),
        "candidatos_localizados": {
            campo: len(valores)
            for campo, valores in localizados.items()
        },
        "candidatos_evaluados": len(candidatos),
        "grupos": len(grupos),
        "grupos_seleccionados": seleccionados,
    }

    if incluir_auditoria:
        diagnostico["candidatos"] = candidatos
        diagnostico["grupos_detalle"] = grupos

    return ficha, diagnostico


# ============================================================
# 3. NORMALIZACION DE LOS CINCO CAMPOS
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


def normalizar_campos(ficha: dict) -> dict:
    """Convierte la ficha interna al contrato de cinco campos."""

    return {
        "nombre": ficha.get("nombre"),
        "precio": convertir_precio(ficha.get("precio")),
        "disponibilidad": convertir_disponibilidad(
            ficha.get("disponibilidad")
        ),
        "descripcion": ficha.get("descripcion"),
        "especificaciones": ficha.get("especificaciones"),
    }


# ============================================================
# 4. EXTRACCION DESDE UN HTML
# ============================================================

def _decodificar(datos: bytes) -> str:
    """Decodifica un HTML de disco probando las codificaciones habituales."""

    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue

    return datos.decode("utf-8", errors="replace")


def extraer_html(
    html: str | bytes,
    url: str | None = None,
    incluir_auditoria: bool = False,
) -> tuple[dict, dict]:
    """Extrae los cinco campos de un unico HTML.

    Args:
        html: HTML completo como texto o bytes.
        url: URL real de la ficha, si se conoce. Se usa como url_base para
            resolver URLs relativas de JSON-LD/microdata.
        incluir_auditoria: si es True, el diagnostico incluye todos los
            candidatos y grupos evaluados.

    Returns:
        (campos, diagnostico), donde campos contiene exactamente las cinco
        claves del contrato de Extract.
    """

    if isinstance(html, (bytes, bytearray)):
        html = _decodificar(bytes(html))

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML vacio o invalido")

    patrones = cargar_patrones()

    fuentes = preparar_fuentes(
        html,
        url_base=url or "https://ejemplo.invalid/",
    )

    localizados = localizar_candidatos(fuentes, patrones)

    ficha, diagnostico = aplicar_filtros(
        localizados,
        fuentes["html"],
        incluir_auditoria=incluir_auditoria,
    )

    return normalizar_campos(ficha), diagnostico


def extraer_archivo(
    ruta: str | Path,
    url: str | None = None,
    incluir_auditoria: bool = False,
) -> dict:
    """Lee un archivo HTML y devuelve un sobre con campos y diagnostico."""

    ruta = Path(ruta)

    html = _decodificar(ruta.read_bytes())
    campos, diagnostico = extraer_html(
        html,
        url,
        incluir_auditoria=incluir_auditoria,
    )

    return {
        "archivo": ruta.name,
        "ruta": str(ruta),
        "url": url,
        "campos": campos,
        "diagnostico": diagnostico,
    }


# ============================================================
# 5. INTERFAZ DE LINEA DE COMANDOS
# ============================================================

def _es_archivo(entrada: str) -> bool:
    try:
        return Path(entrada).is_file()
    except (OSError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extrae los cinco campos de un unico HTML usando los "
            "submodulos actuales de modulo_extract."
        )
    )

    parser.add_argument(
        "entrada",
        help="Ruta a un archivo .html o el propio HTML como texto.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL real de la ficha (opcional, para resolver URLs relativas).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="Archivo JSON donde guardar el resultado (opcional).",
    )
    parser.add_argument(
        "--solo-campos",
        action="store_true",
        help="Imprime solo los cinco campos, sin el sobre de diagnostico.",
    )
    parser.add_argument(
        "--auditoria",
        action="store_true",
        help="Incluye candidatos y grupos en el diagnostico.",
    )

    args = parser.parse_args(argv)

    try:
        if _es_archivo(args.entrada):
            sobre = extraer_archivo(
                args.entrada,
                args.url,
                incluir_auditoria=args.auditoria,
            )

        elif "<" in args.entrada and ">" in args.entrada:
            campos, diagnostico = extraer_html(
                args.entrada,
                args.url,
                incluir_auditoria=args.auditoria,
            )
            sobre = {
                "archivo": None,
                "ruta": None,
                "url": args.url,
                "campos": campos,
                "diagnostico": diagnostico,
            }

        else:
            raise FileNotFoundError(
                f"No existe el archivo HTML: {args.entrada}"
            )

    except Exception as error:
        print(f"ERROR main3: {error}", file=sys.stderr)
        return 1

    contenido = sobre["campos"] if args.solo_campos else sobre
    texto = json.dumps(
        contenido,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    print(texto)

    if args.salida is not None:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
