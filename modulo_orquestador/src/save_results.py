
import json
from pathlib import Path


ORQUESTADOR_DIR = Path(__file__).resolve().parent.parent

ARCHIVO_SALIDA = (
    ORQUESTADOR_DIR
    / "results"
    / "resultados_extraidos.json"
)


def save_results(resultados: list[dict]) -> Path:
    """
    Guarda los resultados consolidados en un JSON.
    """

    ARCHIVO_SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with ARCHIVO_SALIDA.open("w", encoding="utf-8") as archivo:
        json.dump(
            resultados,
            archivo,
            ensure_ascii=False,
            indent=2
        )

    print(
        "OK Orquestador: Resultados guardados en:",
        ARCHIVO_SALIDA
    )

    return ARCHIVO_SALIDA
