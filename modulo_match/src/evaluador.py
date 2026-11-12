"""Preparación, validación y clasificación de Match. Sin llamadas a la API."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ESTADOS = frozenset('CNU')
PREFERENCIA = re.compile(r'\b(preferentemente|preferible|opcional(?:es)?|deseable(?:s)?)\b', re.I)


class ErrorDatos(ValueError):
    """Los archivos o la respuesta del modelo no tienen el formato esperado."""


def leer_json(ruta: Path) -> Any:
    if not ruta.is_file():
        raise FileNotFoundError(f'No se encuentra {ruta}')
    return json.loads(ruta.read_text(encoding='utf-8-sig'))


def guardar_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def preparar_items(raiz: Path, item_elegido: int | None = None) -> list[dict]:
    """Une los JSON por número de ítem y prepara una lista ordenada de requisitos."""
    tdr = leer_json(raiz / 'inputs' / 'tdr.json')
    datos = leer_json(raiz / 'inputs' / 'productos_candidatos.json')
    if not isinstance(tdr, dict) or not isinstance(tdr.get('items'), list):
        raise ErrorDatos('tdr.json debe tener una lista items')
    if not isinstance(datos, list):
        raise ErrorDatos('productos_candidatos.json debe ser una lista de ítems')

    por_item: dict[int, list] = {}
    for bloque in datos:
        numero = int(bloque['item'])
        if numero in por_item:
            raise ErrorDatos(f'Ítem {numero} repetido en productos_candidatos.json')
        resultados = bloque.get('resultados')
        if not isinstance(resultados, list):
            raise ErrorDatos(f'El ítem {numero} no contiene resultados[]')
        por_item[numero] = resultados

    preparados = []
    vistos = set()
    for item in tdr['items']:
        numero = int(item['numero_item'])
        if numero in vistos:
            raise ErrorDatos(f'Ítem {numero} repetido en tdr.json')
        vistos.add(numero)
        if item_elegido is not None and numero != item_elegido:
            continue
        if numero not in por_item:
            raise ErrorDatos(f'No hay bloque de candidatos para el ítem {numero}')

        requisitos, preferencias = [], []
        especificaciones = item.get('especificaciones_tecnicas') or {}
        for grupo in especificaciones.get('grupos', []):
            for texto in grupo.get('requisitos', []):
                if not isinstance(texto, str) or not texto.strip():
                    continue
                if PREFERENCIA.search(texto):
                    # Se preserva como preferencia; no determina un NO APTO.
                    preferencias.append(texto.strip())
                else:
                    requisitos.append({'r': len(requisitos) + 1, 'texto': texto.strip()})

        for accesorio in especificaciones.get('accesorios_obligatorios', []):
            nombre = str(accesorio.get('nombre', '')).strip()
            detalles = [str(x).strip() for x in accesorio.get('requisitos', []) if x]
            cantidad = (accesorio.get('cantidad') or {}).get('valor')
            texto = f'Accesorio exigido: {nombre}'
            if cantidad is not None:
                texto += f' (cantidad: {cantidad})'
            if detalles:
                texto += '; ' + '; '.join(detalles)
            requisitos.append({'r': len(requisitos) + 1, 'texto': texto})
        if not requisitos:
            raise ErrorDatos(f'El ítem {numero} carece de requisitos exigibles')

        productos = []
        for i, producto in enumerate(por_item[numero], 1):
            if not isinstance(producto, dict):
                raise ErrorDatos(f'Producto mal formado en ítem {numero}')
            productos.append({
                'id': f'P{i}',
                'nombre': producto.get('nombre'),
                'tienda': producto.get('tienda'),
                'url': producto.get('url'),
                'descripcion': producto.get('descripcion'),
                'especificaciones': producto.get('especificaciones'),
                # Precio y disponibilidad permanecen fuera de Match.
            })
        preparados.append({
            'item': numero,
            'nombre': item.get('nombre', ''),
            'requisitos': requisitos,
            'preferencias': preferencias,
            'productos': productos,
        })

    if not preparados:
        raise ErrorDatos(f'No se encontró el ítem {item_elegido}')
    return preparados


def entrada_requisitos(bloque: dict) -> dict:
    return {'numero_item': bloque['item'], 'nombre': bloque['nombre'],
            'requisitos': bloque['requisitos']}


def entrada_productos(bloque: dict, modo: str, ids: set[str] | None = None) -> dict:
    campos = ('id', 'nombre', 'tienda', 'url')
    if modo != 'api_driven':
        campos += ('descripcion', 'especificaciones')
    productos = [{k: p.get(k) for k in campos} for p in bloque['productos']
                 if ids is None or p['id'] in ids]
    return {'item': bloque['item'], 'resultados': productos}


def _evidencia_valida(ev: Any, r: int, web_habilitada: bool) -> bool:
    if not isinstance(ev, dict) or ev.get('r') != r:
        return False
    if not str(ev.get('v', '')).strip():
        return False
    f = ev.get('f')
    if f not in {'nombre', 'descripcion', 'especificaciones', 'web'}:
        return False
    if f == 'web' and (not web_habilitada or not str(ev.get('url', '')).startswith(('http://', 'https://'))):
        return False
    return True


NUMERICO = re.compile(r'(\d+(?:[.,]\d+)?)\s*(MB/s|GHz|MHz|Hz|cd\s*/\s*m2|nits?|pulgadas?|["″]|GB|TB|a[nñ]os?|bits?)(?=\W|$)', re.I)
MINIMO = re.compile(r'\b(m[ií]nim[oa]|al\s+menos)\b', re.I)
MAXIMO = re.compile(r'\b(m[aá]xim[oa]|a\s+lo\s+sumo)\b', re.I)


def _numero_unidad(texto: str) -> list[tuple[float, str]]:
    resultados = []
    for v, unidad in NUMERICO.findall(texto.replace('m²', 'm2')):
        try:
            n = float(v.replace(',', '.'))
        except ValueError:
            continue
        u = unidad.lower().replace(' ', '').replace('nits', 'cd/m2').replace('nit', 'cd/m2')
        if u in ('"', '″', 'pulgada', 'pulgadas'):
            u = 'pulgadas'
        if u in ('año', 'años', 'ano', 'anos'):
            u = 'años'
        resultados.append((n, u))
    return resultados


def _corregir_comparacion_numerica(texto_requisito: str, evidencias: list[dict], r: int) -> str | None:
    """Devuelve 'N' solo si una comparación simple y unívoca contradice un mínimo/máximo.

    NO intenta interpretar requisitos compuestos, unidades distintas o texto contextual.
    """
    minimo = bool(MINIMO.search(texto_requisito))
    maximo = bool(MAXIMO.search(texto_requisito))
    if minimo == maximo:
        return None
    reqs = _numero_unidad(texto_requisito)
    if len(reqs) != 1:
        return None
    umbral, unidad = reqs[0]
    datos = []
    for ev in evidencias:
        if ev.get('r') == r:
            datos.extend(v for v in _numero_unidad(str(ev.get('v', ''))) if v[1] == unidad)
    if len(datos) != 1:
        return None
    valor = datos[0][0]
    if (minimo and valor < umbral) or (maximo and valor > umbral):
        return 'N'
    return None


def validar_respuesta(respuesta: Any, bloque: dict, ids: set[str],
                     web_habilitada: bool, solo_web: bool = False) -> tuple[dict[str, dict], list[str]]:
    """Valida estructura; evita eliminar por N sin evidencia verificable."""
    if not isinstance(respuesta, dict) or respuesta.get('item') != bloque['item']:
        raise ErrorDatos(f'Respuesta con número de ítem incorrecto: esperado {bloque["item"]}')
    candidatos = respuesta.get('c')
    if not isinstance(candidatos, list):
        raise ErrorDatos('Falta c[] en respuesta del modelo')
    mapa: dict[str, dict] = {}
    advertencias = []
    n = len(bloque['requisitos'])
    for candidato in candidatos:
        if not isinstance(candidato, dict):
            raise ErrorDatos('Candidato de respuesta debe ser un objeto')
        pid, s = candidato.get('id'), candidato.get('s')
        if pid not in ids or pid in mapa:
            raise ErrorDatos(f'ID duplicado o no esperado: {pid}')
        if not isinstance(s, str) or len(s) != n or any(x not in ESTADOS for x in s):
            raise ErrorDatos(f'{pid}: la cadena s debe tener {n} letras C/N/U')
        ev = candidato.get('ev', [])
        inc = candidato.get('inc', [])
        if not isinstance(ev, list) or not isinstance(inc, list):
            raise ErrorDatos(f'{pid}: ev/inc deben ser listas')
        validas = [e for e in ev if isinstance(e, dict) and isinstance(e.get('r'), int)
                   and 1 <= e['r'] <= n and _evidencia_valida(e, e['r'], web_habilitada)
                   and (not solo_web or e.get('f') == 'web')]
        estados = list(s)
        for i, estado in enumerate(estados):
            r = i + 1
            evidencia_req = [e for e in validas if e['r'] == r]
            if estado == 'N' and not evidencia_req:
                estados[i] = 'U'
                advertencias.append(f'{pid}, r{r}: N sin evidencia válida → U')
            elif estado == 'C' and _corregir_comparacion_numerica(
                    bloque['requisitos'][i]['texto'], evidencia_req, r) == 'N':
                estados[i] = 'N'
                advertencias.append(f'{pid}, r{r}: C contradice mínimo/máximo de evidencia → N')
        incidencias = [x for x in inc if isinstance(x, dict) and isinstance(x.get('r'), list)
                      and all(isinstance(v, int) and 1 <= v <= n for v in x['r'])
                      and str(x.get('tipo', '')).strip()]
        mapa[pid] = {'id': pid, 's': ''.join(estados), 'ev': validas, 'inc': incidencias}
    if set(mapa) != ids:
        raise ErrorDatos(f'Candidatos faltantes: {sorted(ids - set(mapa))}')
    return mapa, advertencias


def aplicar_parche_pendientes(actual: dict[str, dict], nuevos: dict[str, dict]) -> None:
    """Solo sustituye posiciones U; nunca altera estados ya confirmados."""
    for pid, candidato in nuevos.items():
        if pid not in actual:
            continue
        anterior = actual[pid]
        estados = list(anterior['s'])
        for i, nuevo in enumerate(candidato['s']):
            if estados[i] == 'U' and nuevo in ('C', 'N'):
                estados[i] = nuevo
                anterior['ev'].extend(e for e in candidato['ev'] if e.get('r') == i + 1)
        anterior['s'] = ''.join(estados)
        anterior['inc'].extend(candidato['inc'])


def aplicar_correcciones(actual: dict[str, dict], salida: Any,
                         bloque: dict, permitir_web: bool) -> list[str]:
    avisos = []
    if not isinstance(salida, dict) or salida.get('item') != bloque['item']:
        raise ErrorDatos('El resolutor devolvió un ítem diferente')
    if not isinstance(salida.get('correcciones'), list):
        raise ErrorDatos('El resolutor debe devolver correcciones[]')
    for cambio in salida['correcciones']:
        pid, r, s = cambio.get('id'), cambio.get('r'), cambio.get('s')
        if pid not in actual or not isinstance(r, int) or not 1 <= r <= len(bloque['requisitos']):
            avisos.append(f'Corrección no esperada: {pid}/{r}')
            continue
        if s not in ESTADOS:
            avisos.append(f'Corrección con estado inválido: {pid}/{r}')
            continue
        if not any(r in inc['r'] for inc in actual[pid]['inc']):
            avisos.append(f'{pid}/{r}: requisito sin incidencia registrada')
            continue
        ev = cambio.get('ev')
        if s in ('C', 'N'):
            fuente_web_previa = (isinstance(ev, dict) and ev.get('f') == 'web' and
                                any(v.get('f') == 'web' and v.get('url') == ev.get('url')
                                    for v in actual[pid]['ev']))
            if not _evidencia_valida(dict(ev, r=r) if isinstance(ev, dict) else ev,
                                    r, permitir_web or fuente_web_previa):
                avisos.append(f'{pid}/{r}: falta evidencia válida en corrección')
                continue
        estados = list(actual[pid]['s'])
        if estados[r - 1] != 'U':
            avisos.append(f'{pid}/{r}: no se altera estado confirmado')
            continue
        estados[r - 1] = s
        actual[pid]['s'] = ''.join(estados)
        if s in ('C', 'N'):
            actual[pid]['ev'].append({'r': r, **ev})
    return avisos


def clasificar(bloque: dict, mapa: dict[str, dict]) -> dict:
    resultados = []
    n = len(bloque['requisitos'])
    for p in bloque['productos']:
        evaluacion = mapa[p['id']]
        estados = evaluacion['s']
        clasificacion = 'NO_APTO' if 'N' in estados else ('PENDIENTE' if 'U' in estados else 'APTO')
        resultados.append({
            'id': p['id'], 'nombre': p['nombre'], 'tienda': p['tienda'], 'url': p['url'],
            'clasificacion': clasificacion,
            'puntaje_cumplimiento': 100 if clasificacion == 'APTO' else (0 if clasificacion == 'NO_APTO' else None),
            'verificacion_favorable_pct': round(100 * estados.count('C') / n, 2),
            'requisitos_cumplen': estados.count('C'), 'requisitos_no_cumplen': estados.count('N'),
            'requisitos_sin_evidencia': estados.count('U'), 'requisitos_totales': n,
            's': estados, 'ev': evaluacion['ev'], 'inc': evaluacion['inc'],
        })
    prioridad = {'APTO': 0, 'PENDIENTE': 1, 'NO_APTO': 2}
    resultados.sort(key=lambda x: (prioridad[x['clasificacion']],
                                   -x['verificacion_favorable_pct'] if x['clasificacion'] != 'NO_APTO' else 0,
                                   int(x['id'][1:]) if x['id'][1:].isdigit() else x['id']))
    return {'item': bloque['item'], 'nombre': bloque['nombre'],
            'requisitos': bloque['requisitos'], 'preferencias': bloque['preferencias'],
            'resultados': resultados}
