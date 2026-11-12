"""Ejecuta las 3 arquitecturas sobre los mismos ítems y compara métricas."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from main import MODOS, RAIZ, ejecutar_modo, seleccionar_item
from evaluador import ErrorDatos, guardar_json
from graficar_tokens import graficar_tokens


def comparar(item: int | None, *, modelo: str | None = None,
             esfuerzo: str | None = None, resolver: bool = True,
             resolver_web: bool = False, dry_run: bool = False,
             raiz: Path = RAIZ) -> dict:
    ejecuciones = {}
    for modo in MODOS.values():
        print(f'\n=== {modo} ===', flush=True)
        ejecuciones[modo] = ejecutar_modo(
            modo, item=item, raiz=raiz, modelo=modelo, esfuerzo=esfuerzo,
            resolver=resolver, resolver_web=resolver_web, dry_run=dry_run)
    if dry_run:
        return {'dry_run': True, 'vistas_previas': ejecuciones}

    filas = []
    clasificaciones_por_modo = {}
    for modo, ejecucion in ejecuciones.items():
        metricas = ejecucion['metricas']
        for datos_item in ejecucion['items']:
            resultados = datos_item['resultados']
            clasificaciones_por_modo[(modo, datos_item['item'])] = {
                p['id']: p['clasificacion'] for p in resultados
            }
            filas.append({
                'arquitectura': modo, 'item': datos_item['item'],
                'candidatos': len(resultados),
                'aptos': sum(p['clasificacion'] == 'APTO' for p in resultados),
                'pendientes': sum(p['clasificacion'] == 'PENDIENTE' for p in resultados),
                'no_aptos': sum(p['clasificacion'] == 'NO_APTO' for p in resultados),
                'requisitos_sin_evidencia': sum(p['requisitos_sin_evidencia'] for p in resultados),
            })
        # Métricas completas por modo; NO atribuir el total a cada ítem.
        filas.append({
            'arquitectura': modo, 'item': 'TOTAL_API',
            'candidatos': sum(len(x['resultados']) for x in ejecucion['items']),
            'aptos': sum(p['clasificacion'] == 'APTO' for x in ejecucion['items'] for p in x['resultados']),
            'pendientes': sum(p['clasificacion'] == 'PENDIENTE' for x in ejecucion['items'] for p in x['resultados']),
            'no_aptos': sum(p['clasificacion'] == 'NO_APTO' for x in ejecucion['items'] for p in x['resultados']),
            'requisitos_sin_evidencia': sum(p['requisitos_sin_evidencia'] for x in ejecucion['items']
                                           for p in x['resultados']),
            'llamadas_api': metricas['llamadas_api'],
            'tokens_entrada': metricas['tokens_entrada'],
            'tokens_salida': metricas['tokens_salida'],
            'tokens_razonamiento': metricas['tokens_razonamiento'],
            'busquedas_web': metricas['busquedas_web'],
            'segundos_api': metricas['segundos_api'],
            'costo_estimado_usd': metricas['costo_estimado_usd'],
        })

    diferencias = []
    items = sorted({x['item'] for x in ejecuciones[next(iter(MODOS.values()))]['items']})
    for numero in items:
        candidatos = sorted({pid for m in MODOS.values()
                             for pid in clasificaciones_por_modo.get((m, numero), {})},
                            key=lambda x: int(x[1:]) if x[1:].isdigit() else x)
        for pid in candidatos:
            estados = {m: clasificaciones_por_modo.get((m, numero), {}).get(pid)
                       for m in MODOS.values()}
            if len(set(estados.values())) > 1:
                diferencias.append({'item': numero, 'id': pid, 'clasificaciones': estados})

    reporte = {'comparacion': filas, 'diferencias': diferencias,
               'nota': ('Las diferencias entre arquitecturas no miden por sí solas la exactitud; '
                        'para medirla se necesita una referencia técnica verificada.')}
    salida = raiz / 'outputs'
    guardar_json(salida / 'comparacion.json', reporte)
    columnas = ['arquitectura', 'item', 'candidatos', 'aptos', 'pendientes', 'no_aptos',
                'requisitos_sin_evidencia', 'llamadas_api', 'tokens_entrada',
                'tokens_salida', 'tokens_razonamiento', 'busquedas_web',
                'segundos_api', 'costo_estimado_usd']
    with (salida / 'comparacion.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)
    reporte["grafica_tokens"] = str(graficar_tokens(salida / "comparacion.csv", salida / "consumo_tokens.png"))
    return reporte


def main() -> None:
    parser = argparse.ArgumentParser(description='Ejecuta y compara las 3 arquitecturas de Match')
    parser.add_argument('--item', type=int, help='Número del ítem; omitido = todos')
    parser.add_argument('--modelo', default=None)
    parser.add_argument('--esfuerzo', choices=['none', 'low', 'medium', 'high'], default=None)
    parser.add_argument('--sin-resolver', action='store_true')
    parser.add_argument('--resolver-web', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='No hace llamadas de API')
    parser.add_argument('--si', action='store_true', help='Omite confirmación de coste API')
    args = parser.parse_args()
    try:
        item = args.item if args.item is not None else seleccionar_item()
        if not args.dry_run and not args.si:
            print('AVISO: ejecutará TRES arquitecturas; cada una puede generar cargos de API y búsquedas web.')
            if input('Escribe SI para ejecutar las tres: ').strip() != 'SI':
                print('Cancelado, sin llamadas a OpenAI.')
                return
        reporte = comparar(item, modelo=args.modelo, esfuerzo=args.esfuerzo,
                           resolver=not args.sin_resolver, resolver_web=args.resolver_web,
                           dry_run=args.dry_run)
        if args.dry_run:
            print('\nPreparación validada sin llamadas de API.')
        else:
            print('\nComparación guardada en:', RAIZ / 'outputs' / 'comparacion.csv')
            print('\nConsumo real de tokens (por arquitectura):')
            for fila in reporte['comparacion']:
                if fila['item'] == 'TOTAL_API':
                    total = int(fila['tokens_entrada']) + int(fila['tokens_salida'])
                    print(f"  {fila['arquitectura']}: {total:,} tokens "
                          f"(entrada {fila['tokens_entrada']:,}; salida {fila['tokens_salida']:,}; "
                          f"razonamiento incluido en salida {fila['tokens_razonamiento']:,})")
            print('Gráfica de tokens:', reporte['grafica_tokens'])
            print('Candidatos con decisiones distintas:', len(reporte['diferencias']))
    except (ErrorDatos, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
