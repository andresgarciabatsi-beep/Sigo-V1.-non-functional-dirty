"""Ejecución individual de Match con selector de arquitectura en consola."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evaluador import (
    ErrorDatos, aplicar_correcciones, aplicar_parche_pendientes, clasificar,
    entrada_productos, entrada_requisitos, guardar_json, preparar_items,
    validar_respuesta,
)
from openai_client import ClienteMatch

RAIZ = Path(__file__).resolve().parents[1]
MODOS = {
    '1': 'api_driven',
    '2': 'api_as_fallback_for_specs',
    '3': 'api_as_fallback_for_specs_or_missing_specs',
}


def seleccionar_modo() -> str:
    print('\nMATCH — Selector de arquitectura')
    print('1. API Driven (investigar todos los productos en internet)')
    print('2. API como respaldo (web solo si faltan datos utilizables)')
    print('3. API como respaldo + requisitos pendientes (web selectiva)')
    while True:
        eleccion = input('Elige 1, 2 o 3: ').strip()
        if eleccion in MODOS:
            return MODOS[eleccion]
        print('Opción no válida.')


def seleccionar_item() -> int | None:
    valor = input('Ítem a evaluar (número o Enter para todos): ').strip()
    if not valor:
        return None
    if not valor.isdigit() or int(valor) < 1:
        raise ValueError('El número de ítem debe ser un entero positivo')
    return int(valor)


def leer_prompt(raiz: Path, nombre: str) -> str:
    ruta = raiz / 'resources' / 'prompts_api' / f'{nombre}.md'
    if not ruta.is_file():
        raise FileNotFoundError(f'Falta prompt: {ruta}')
    contenido = ruta.read_text(encoding='utf-8-sig')
    # Compatibilidad con versiones de los prompts que mencionaban nombres anteriores.
    return (contenido.replace('tdr_memorias(3).json', 'tdr.json')
                     .replace('resultados_extraidos(3).json', 'productos_candidatos.json'))


def solicitud(bloque: dict, productos: dict, fase: str, **otros) -> dict:
    return {'tdr.json': entrada_requisitos(bloque),
            'productos_candidatos.json': productos, 'fase': fase, **otros}



def hacer_consulta(cliente: ClienteMatch, prompt: str, bloque: dict,
                   productos: dict, ids: set[str], fase: str,
                   *, web: bool, forzar: bool = False, instruccion: str = '',
                   solo_web: bool = False, **otros) -> tuple[dict[str, dict], list[str]]:
    """Reintenta una vez solo los candidatos con estados malformados."""

    n = len(bloque['requisitos'])

    prompt_final = (
        prompt + ('\n' + instruccion if instruccion else '') +
        f'\nFORMATO OBLIGATORIO: hay exactamente {n} requisitos. '
        f'Cada cadena s debe contener exactamente {n} letras C, N o U, '
        'en el orden de r. No copies la longitud de los ejemplos del prompt.'
    )

    def consultar(lista_productos, etapa, aviso=''):
        return cliente.consultar(
            prompt_final + aviso,
            solicitud(bloque, lista_productos, fase, **otros),
            item=bloque['item'],
            etapa=etapa,
            web=web,
            forzar_busqueda=forzar
        )

    def revisar(datos, esperados):
        if not isinstance(datos, dict) or datos.get('item') != bloque['item']:
            raise ErrorDatos(f'{fase}: ítem incorrecto en respuesta de OpenAI')

        lista = datos.get('c')
        if not isinstance(lista, list):
            raise ErrorDatos(f'{fase}: respuesta sin c[]')

        por_id = {}

        for candidato in lista:
            if not isinstance(candidato, dict):
                raise ErrorDatos(f'{fase}: candidato sin estructura válida')

            pid = candidato.get('id')

            if pid not in esperados or pid in por_id:
                raise ErrorDatos(f'{fase}: candidato duplicado o inesperado: {pid}')

            por_id[pid] = candidato

        errores = esperados - set(por_id)

        for pid, candidato in por_id.items():
            s = candidato.get('s')
            normalizada = ''.join(s.split()) if isinstance(s, str) else None

            if (normalizada is None or len(normalizada) != n
                    or any(c not in 'CNU' for c in normalizada)):
                print(
                    f'AVISO: {fase}/{pid}, s={s!r}; '
                    f'se esperaban {n} C/N/U.',
                    flush=True
                )
                errores.add(pid)

        return por_id, errores

    # Primera evaluación
    salida = consultar(productos, fase)
    por_id, errores = revisar(salida, ids)

    if errores:
        # Repetir únicamente los candidatos con errores.
        repetidos = [
            p for p in productos['resultados']
            if p['id'] in errores
        ]

        if len(repetidos) != len(errores):
            raise ErrorDatos(
                f'{fase}: faltan datos originales de {sorted(errores)}'
            )

        print(
            f'Reintentando una sola vez: {sorted(errores)}',
            flush=True
        )

        nuevos, pendientes = revisar(
            consultar(
                {'item': bloque['item'], 'resultados': repetidos},
                f'{fase}_reintento_formato',
                '\nIMPORTANTE: este es el único reintento. '
                f'Devuelve los {n} estados completos por candidato, '
                'con evidencias. No inventes estados para rellenar posiciones.'
            ),
            errores
        )

        if pendientes:
            raise ErrorDatos(
                f'{fase}: formato inválido tras un reintento: '
                f'{sorted(pendientes)}'
            )

        # Conservar respuestas válidas y sustituir solo las erróneas.
        por_id.update(nuevos)

        salida = {
            'item': bloque['item'],
            'c': [
                por_id[p['id']]
                for p in productos['resultados']
            ]
        }

    return validar_respuesta(
        salida, bloque, ids,
        web_habilitada=web,
        solo_web=solo_web
    )



def evaluar_item(cliente: ClienteMatch, bloque: dict, modo: str,
                 prompt: str, prompt_resolver: str | None,
                 *, resolver_web: bool = False) -> tuple[dict, list[str]]:
    avisos: list[str] = []
    ids = {p['id'] for p in bloque['productos']}
    if not ids:
        return {'item': bloque['item'], 'nombre': bloque['nombre'], 'requisitos': bloque['requisitos'],
                'preferencias': bloque['preferencias'], 'resultados': []}, avisos

    if modo == 'api_driven':
        mapa, observaciones = hacer_consulta(
            cliente, prompt, bloque, entrada_productos(bloque, 'api_driven'), ids,
            'web_inicial', web=True, forzar=True, solo_web=True)
        avisos.extend(observaciones)
    else:
        mapa, observaciones = hacer_consulta(
            cliente, prompt, bloque, entrada_productos(bloque, modo), ids,
            'evaluacion_local', web=False,
            instruccion=('FASE LOCAL OBLIGATORIA: no uses internet ni conocimientos externos. '
                         'Evalúa exclusivamente los campos recibidos. Si no hay evidencia, usa U. '
                         'No intentes ejecutar búsquedas: Python las decidirá después.'))
        avisos.extend(observaciones)

        # Una U en todos los requisitos significa que nada ha podido verificarse con los datos locales.
        sin_datos = {pid for pid, x in mapa.items() if set(x['s']) == {'U'}}
        if sin_datos:
            web_total, observaciones = hacer_consulta(
                cliente, prompt, bloque, entrada_productos(bloque, 'api_driven', sin_datos),
                sin_datos, 'web_ficha_completa', web=True, forzar=True, solo_web=True,
                instruccion=('FASE WEB POR AUSENCIA DE EVIDENCIA LOCAL: estos candidatos no '
                             'tuvieron ningún requisito verificable. Busca su ficha técnica '
                             'para evaluar todos los requisitos. No inventes características.'))
            avisos.extend(observaciones)
            mapa.update(web_total)

        if modo == 'api_as_fallback_for_specs_or_missing_specs':
            # No ejecutar otra búsqueda para los candidatos cuya ficha ya fue investigada.
            pendientes = {
                pid for pid, x in mapa.items()
                if pid not in sin_datos and 'U' in x['s'] and 'N' not in x['s']
            }
            if pendientes:
                productos = []
                for p in bloque['productos']:
                    if p['id'] not in pendientes:
                        continue
                    estado = mapa[p['id']]['s']
                    productos.append({
                        'id': p['id'], 'nombre': p['nombre'], 'tienda': p['tienda'], 'url': p['url'],
                        's_previa': estado,
                        'faltantes': [req for req in bloque['requisitos']
                                     if estado[req['r'] - 1] == 'U'],
                    })
                nuevo, observaciones = hacer_consulta(
                    cliente, prompt, bloque,
                    {'item': bloque['item'], 'resultados': productos}, pendientes,
                    'web_requisitos_pendientes', web=True, forzar=True, solo_web=True,
                    instruccion=('FASE WEB PARA PENDIENTES: cada producto contiene s_previa '
                                 'y faltantes. Investiga SOLO los requisitos de faltantes. '
                                 'Devuelve s completa: conserva EXACTAMENTE los estados C/N '
                                 'previamente conocidos y modifica solo posiciones U, con '
                                 'evidencia y URL para cualquier conclusión obtenida en web.'))
                avisos.extend(observaciones)
                aplicar_parche_pendientes(mapa, nuevo)

    if prompt_resolver:
        casos = []
        por_id = {p['id']: p for p in bloque['productos']}
        for pid, x in mapa.items():
            if 'N' in x['s']:
                continue  # No gastar en productos descartados.
            posiciones = sorted({r for inc in x['inc'] for r in inc['r']
                                 if x['s'][r - 1] == 'U'})
            if not posiciones:
                continue
            p = por_id[pid]
            usar_web = resolver_web and modo != 'api_as_fallback_for_specs'
            # Sin web, una segunda llamada sin datos útiles a contrastar no aporta valor.
            evidencias = [str(p.get(k) or '').strip() for k in
                          ('nombre', 'descripcion', 'especificaciones')]
            textos_distintos = {v for v in evidencias if v}
            if not usar_web and len(textos_distintos) < 2:
                avisos.append(f'{pid}: incidencia sin fuentes suficientes para otra llamada; permanece U')
                continue
            caso = {
                'id': pid, 'nombre': p['nombre'], 'tienda': p['tienda'], 'url': p['url'],
                'requisitos': [{**bloque['requisitos'][r - 1], 'estado_anterior': x['s'][r - 1]}
                               for r in posiciones],
                'incidencias': [inc for inc in x['inc'] if any(r in posiciones for r in inc['r'])],
                'evidencias_anteriores': [ev for ev in x['ev'] if ev.get('r') in posiciones],
            }
            if modo != 'api_driven':
                caso.update({'descripcion': p['descripcion'], 'especificaciones': p['especificaciones']})
            casos.append(caso)
        if casos:
            # La búsqueda en el resolutor está deshabilitada por defecto (ahorra costes).
            habilitar_web = resolver_web and modo in (
                'api_driven', 'api_as_fallback_for_specs_or_missing_specs')
            salida = cliente.consultar(
                prompt_resolver,
                {'item': bloque['item'], 'permitir_web': habilitar_web, 'casos': casos},
                item=bloque['item'], etapa='resolver_incidencias', web=habilitar_web)
            avisos.extend(aplicar_correcciones(mapa, salida, bloque, habilitar_web))

    return clasificar(bloque, mapa), avisos


def ejecutar_modo(modo: str, *, item: int | None = None,
                  raiz: Path = RAIZ, modelo: str | None = None,
                  esfuerzo: str | None = None, resolver: bool = True,
                  resolver_web: bool = False, dry_run: bool = False) -> dict:
    """Función reutilizable por el comparador; no muestra menús."""
    if modo not in MODOS.values():
        raise ValueError(f'Modo no válido: {modo}')
    bloques = preparar_items(raiz, item)
    if dry_run:
        resumen = {'modo': modo, 'dry_run': True,
                   'items': [{'item': b['item'], 'requisitos': len(b['requisitos']),
                              'candidatos': len(b['productos']),
                              'preferencias': b['preferencias'],
                              'fragmento_enviado_inicialmente': {
                                  'tdr.json': entrada_requisitos(b),
                                  'productos_candidatos.json': entrada_productos(b, modo)}}
                             for b in bloques]}
        guardar_json(raiz / 'outputs' / f'preview_{modo}.json', resumen)
        return resumen

    cliente = ClienteMatch(raiz, modelo=modelo, esfuerzo=esfuerzo)
    prompt = leer_prompt(raiz, f'modo_{modo}')
    prompt_resolver = leer_prompt(raiz, 'resolver_incidencias') if resolver else None
    resultado = {'modo': modo, 'modelo': cliente.modelo, 'esfuerzo': cliente.esfuerzo,
                 'items': [], 'advertencias': []}
    destino = raiz / 'outputs' / f'{modo}.json'
    try:
        for bloque in bloques:
            print(f'\nÍtem {bloque["item"]}: {len(bloque["productos"])} candidatos / '
                  f'{len(bloque["requisitos"])} requisitos — {modo}', flush=True)
            item_resultado, avisos = evaluar_item(
                cliente, bloque, modo, prompt, prompt_resolver, resolver_web=resolver_web)
            resultado['items'].append(item_resultado)
            resultado['advertencias'].extend(f'Ítem {bloque["item"]}: {aviso}' for aviso in avisos)
            # Guardado incremental: no se pierde el trabajo completado si falla un ítem posterior.
            resultado['metricas'] = cliente.resumen()
            resultado['detalle_llamadas'] = cliente.registros
            guardar_json(destino, resultado)
    finally:
        resultado['metricas'] = cliente.resumen()
        resultado['detalle_llamadas'] = cliente.registros
        guardar_json(destino, resultado)
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description='Match — ejecutor de una arquitectura')
    parser.add_argument('--modo', choices=list(MODOS.values()), help='Sin --modo aparece selector')
    parser.add_argument('--item', type=int, help='Número de ítem; omitido = todos')
    parser.add_argument('--modelo', default=None)
    parser.add_argument('--esfuerzo', choices=['none', 'low', 'medium', 'high'], default=None)
    parser.add_argument('--dry-run', action='store_true', help='Prepara y valida JSON sin gastar API')
    parser.add_argument('--sin-resolver', action='store_true', help='Desactiva segunda llamada por incidencias')
    parser.add_argument('--resolver-web', action='store_true', help='Permite web al resolver (coste extra)')
    parser.add_argument('--si', action='store_true', help='Omite confirmación de coste API')
    args = parser.parse_args()
    try:
        modo = args.modo or seleccionar_modo()
        item = args.item if args.item is not None or args.modo else seleccionar_item()
        if not args.dry_run and not args.si:
            print('\nAVISO: esta ejecución consume saldo de OpenAI API y puede realizar búsquedas pagadas.')
            if input('Escribe SI para continuar: ').strip() != 'SI':
                print('Ejecución cancelada; no se han enviado solicitudes.')
                return
        resultado = ejecutar_modo(modo, item=item, modelo=args.modelo,
                                esfuerzo=args.esfuerzo, resolver=not args.sin_resolver,
                                resolver_web=args.resolver_web, dry_run=args.dry_run)
        print('\nResultado:', RAIZ / 'outputs' / (f'preview_{modo}.json' if args.dry_run else f'{modo}.json'))
        if not args.dry_run:
            print('Métricas:', resultado['metricas'])
    except (ErrorDatos, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
