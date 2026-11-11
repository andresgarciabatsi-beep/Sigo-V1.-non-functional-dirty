"""Recorre todos los HTML de una carpeta y extrae los cinco campos.

Usa main3.extraer_archivo() para cada HTML, por lo que el comportamiento es
exactamente el mismo que ejecutar main3.py sobre un archivo individual.

Uso:
    python recorrer_htmls.py
    python recorrer_htmls.py --htmls ../recursos/htmls_ampliado
    python recorrer_htmls.py --salida ../resultados/extraccion_htmls
    python recorrer_htmls.py --limite 5

Salidas:
    <salida>/paginas/<archivo>.json   Un resultado por HTML.
    <salida>/resultados_brutos.json   Todos los resultados en una lista.
    <salida>/resumen_paginas.csv      Tabla comparativa por HTML.
    <salida>/resumen_general.json     Totales y rutas.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main3 import CAMPOS, extraer_archivo  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
HTMLS_POR_DEFECTO = BASE / "recursos" / "htmls_ampliado"
SALIDA_POR_DEFECTO = BASE / "resultados" / "extraccion_htmls"


def _llenos(campos: dict) -> int:
    return sum(
        valor is not None and str(valor).strip() != ""
        for valor in campos.values()
    )


def _guardar_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def ejecutar(
    carpeta_htmls: str | Path,
    salida: str | Path,
    limite: int | None = None,
    incluir_auditoria: bool = False,
) -> dict:
    carpeta_htmls = Path(carpeta_htmls)
    salida = Path(salida)

    if not carpeta_htmls.is_dir():
        raise NotADirectoryError(
            f"No existe la carpeta de HTML: {carpeta_htmls}"
        )

    archivos = sorted(
        ruta
        for ruta in carpeta_htmls.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in {".html", ".htm"}
    )

    if limite is not None:
        archivos = archivos[:limite]

    if not archivos:
        raise ValueError(
            f"No se encontraron archivos .html en {carpeta_htmls}"
        )

    print(f"HTML encontrados: {len(archivos)}")
    print(f"Carpeta de salida: {salida}")

    resultados = []
    resumen = []
    inicio_total = time.perf_counter()

    for numero, ruta in enumerate(archivos, start=1):

        relativa = ruta.relative_to(carpeta_htmls)
        inicio = time.perf_counter()

        try:
            sobre = extraer_archivo(
                ruta,
                incluir_auditoria=incluir_auditoria,
            )
            sobre["archivo"] = relativa.as_posix()
            estado = "ok"
            error = None

        except Exception as exc:
            sobre = {
                "archivo": relativa.as_posix(),
                "ruta": str(ruta),
                "url": None,
                "campos": {campo: None for campo in CAMPOS},
                "diagnostico": {},
            }
            estado = "error"
            error = f"{type(exc).__name__}: {exc}"

        duracion = time.perf_counter() - inicio
        resultados.append(sobre)

        _guardar_json(
            salida / "paginas" / relativa.with_suffix(".json"),
            sobre,
        )

        campos = sobre["campos"]
        diagnostico = sobre.get("diagnostico") or {}

        resumen.append({
            "archivo": relativa.as_posix(),
            "estado": estado,
            "campos_llenos": _llenos(campos),
            "nombre": campos.get("nombre") or "",
            "precio": campos.get("precio") or "",
            "disponibilidad": campos.get("disponibilidad") or "",
            "descripcion_len": len(campos.get("descripcion") or ""),
            "especificaciones_len": len(campos.get("especificaciones") or ""),
            "estado_validacion": diagnostico.get("estado_validacion") or "",
            "advertencias": " | ".join(diagnostico.get("advertencias") or []),
            "candidatos_evaluados": diagnostico.get("candidatos_evaluados", 0),
            "grupos": diagnostico.get("grupos", 0),
            "segundos": round(duracion, 3),
            "error": error or "",
        })

        print(
            f"[{numero}/{len(archivos)}] {estado.upper():<5} "
            f"{relativa.as_posix()} "
            f"({_llenos(campos)}/5 campos, {duracion:.2f}s)"
        )

    _guardar_json(salida / "resultados_brutos.json", resultados)
    _guardar_json(salida / "resumen_general.json", {
        "carpeta_htmls": str(carpeta_htmls),
        "html_encontrados": len(archivos),
        "html_procesados": sum(r["estado"] == "ok" for r in resumen),
        "html_con_error": sum(r["estado"] == "error" for r in resumen),
        "campos_llenos_total": sum(r["campos_llenos"] for r in resumen),
        "campos_posibles_total": len(archivos) * len(CAMPOS),
        "segundos_total": round(time.perf_counter() - inicio_total, 3),
        "salida": str(salida),
    })

    with (salida / "resumen_paginas.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as archivo:
        columnas = [
            "archivo",
            "estado",
            "campos_llenos",
            "nombre",
            "precio",
            "disponibilidad",
            "descripcion_len",
            "especificaciones_len",
            "estado_validacion",
            "advertencias",
            "candidatos_evaluados",
            "grupos",
            "segundos",
            "error",
        ]
        escritor = csv.DictWriter(
            archivo,
            fieldnames=columnas,
            extrasaction="ignore",
        )
        escritor.writeheader()
        escritor.writerows(resumen)

    print(f"\nResultados brutos: {salida / 'resultados_brutos.json'}")
    print(f"Resumen CSV:       {salida / 'resumen_paginas.csv'}")

    return {
        "resultados": resultados,
        "resumen": resumen,
        "salida": salida,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recorre una carpeta de HTML y extrae los cinco campos "
            "con main3.extraer_archivo()."
        )
    )
    parser.add_argument(
        "--htmls",
        type=Path,
        default=HTMLS_POR_DEFECTO,
        help=f"Carpeta con archivos .html (por defecto: {HTMLS_POR_DEFECTO}).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=SALIDA_POR_DEFECTO,
        help=f"Carpeta de salida (por defecto: {SALIDA_POR_DEFECTO}).",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=None,
        help="Procesar solo los primeros N HTML (opcional).",
    )
    parser.add_argument(
        "--auditoria",
        action="store_true",
        help="Incluye candidatos y grupos de cada HTML en la salida.",
    )

    args = parser.parse_args(argv)

    try:
        ejecutar(
            args.htmls,
            args.salida,
            args.limite,
            incluir_auditoria=args.auditoria,
        )

    except (OSError, ValueError, ImportError) as error:
        print(f"ERROR recorrer_htmls: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
