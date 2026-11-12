"""Genera una gráfica del consumo REAL de tokens registrado por Match.

Lee outputs/comparacion.csv, que se crea al ejecutar comparar_arquitecturas.py.
No realiza solicitudes a OpenAI.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

ETIQUETAS = {
    'api_driven': 'API Driven',
    'api_as_fallback_for_specs': 'API Fallback',
    'api_as_fallback_for_specs_or_missing_specs': 'API Fallback\n+ Missing Specs',
}


def graficar_tokens(
    csv_entrada: Path | None = None,
    imagen_salida: Path | None = None,
) -> Path:
    """Gráfica de barras apiladas; no suma reasoning_tokens dos veces."""
    import matplotlib.pyplot as plt

    csv_entrada = csv_entrada or (RAIZ / 'outputs' / 'comparacion.csv')
    imagen_salida = imagen_salida or (RAIZ / 'outputs' / 'consumo_tokens.png')

    if not csv_entrada.is_file():
        raise FileNotFoundError(
            f'No existe {csv_entrada}. Primero ejecuta comparar_arquitecturas.py '
            'sin --dry-run para generar métricas reales.'
        )

    with csv_entrada.open('r', encoding='utf-8-sig', newline='') as f:
        filas = [fila for fila in csv.DictReader(f) if fila.get('item') == 'TOTAL_API']

    if not filas:
        raise ValueError('El CSV no contiene filas TOTAL_API con consumo real de tokens.')

    # Respetar un orden predecible, sin asumir que las tres modalidades existen siempre.
    orden = {nombre: i for i, nombre in enumerate(ETIQUETAS)}
    filas.sort(key=lambda f: orden.get(f['arquitectura'], len(orden)))

    modos = []
    entradas = []
    salidas_visibles = []
    razonamientos = []
    for fila in filas:
        nombre = fila['arquitectura']
        entrada = int(float(fila.get('tokens_entrada') or 0))
        salida = int(float(fila.get('tokens_salida') or 0))
        razonamiento = int(float(fila.get('tokens_razonamiento') or 0))
        if min(entrada, salida, razonamiento) < 0 or razonamiento > salida:
            raise ValueError(f'Métricas de tokens inconsistentes en {nombre}')
        modos.append(ETIQUETAS.get(nombre, nombre))
        entradas.append(entrada)
        salidas_visibles.append(salida - razonamiento)
        razonamientos.append(razonamiento)

    x = list(range(len(modos)))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(x, entradas, label='Entrada')
    ax.bar(x, salidas_visibles, bottom=entradas, label='Salida sin razonamiento')
    base_razonamiento = [a + b for a, b in zip(entradas, salidas_visibles)]
    ax.bar(x, razonamientos, bottom=base_razonamiento, label='Razonamiento (parte de salida)')
    totales = [a + b + c for a, b, c in zip(entradas, salidas_visibles, razonamientos)]
    alto = max(totales) or 1
    for i, total in enumerate(totales):
        ax.text(i, total + alto * 0.025, f'{total:,}'.replace(',', '.'),
                ha='center', va='bottom', fontsize=10)
    ax.set_xticks(x, modos)
    ax.set_ylim(0, alto * 1.15)
    ax.set_ylabel('Tokens')
    ax.set_title('Consumo de tokens por arquitectura — Match')
    ax.legend()
    ax.grid(axis='y', alpha=0.2)
    ax.set_axisbelow(True)
    fig.tight_layout()
    imagen_salida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(imagen_salida, dpi=170)
    plt.close(fig)
    return imagen_salida


def main() -> None:
    parser = argparse.ArgumentParser(description='Grafica tokens desde outputs/comparacion.csv')
    parser.add_argument('--csv', type=Path, default=None)
    parser.add_argument('--salida', type=Path, default=None)
    args = parser.parse_args()
    try:
        print('Gráfica guardada en:', graficar_tokens(args.csv, args.salida))
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
