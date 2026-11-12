"""Cliente mínimo de OpenAI Responses API: JSON compacto, web opcional y métricas."""
from __future__ import annotations
import re
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv


class ClienteMatch:
    def __init__(self, raiz: Path, modelo: str | None = None, esfuerzo: str | None = None,
                 max_web_por_llamada: int = 8):
        load_dotenv(raiz / '.env')
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError('Instala las dependencias: pip install -r requirements.txt') from exc
        if not os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') == 'tu_clave_aqui':
            raise RuntimeError('Configura OPENAI_API_KEY en .env o en el entorno')
        self.modelo = modelo or os.getenv('OPENAI_MODEL', 'gpt-6-luna')
        self.esfuerzo = esfuerzo or os.getenv('OPENAI_REASONING_EFFORT', 'medium')
        self.max_web_por_llamada = max_web_por_llamada
        self.cliente = OpenAI(max_retries=0, timeout=150.0)
        self.registros: list[dict] = []
        # Solo hay estimación automática para Luna con tarifas estándar actuales.
        self.tarifas = {
            'entrada': float(os.getenv('PRECIO_INPUT_1M', '0.10')),
            'cache': float(os.getenv('PRECIO_CACHED_1M', '0.01')),
            'salida': float(os.getenv('PRECIO_OUTPUT_1M', '0.50')),
            'web': float(os.getenv('PRECIO_WEB_POR_BUSQUEDA', '0.01')),
        } if self.modelo == 'gpt-6-luna' or os.getenv('PRECIO_INPUT_1M') else None

    def consultar(self, prompt: str, contenido: dict[str, Any], *, item: int,
                  etapa: str, web: bool = False, forzar_busqueda: bool = False) -> dict:
        """Solo habilita web_search cuando web=True. No reintenta llamadas pagadas."""
        payload = {
            'model': self.modelo,
            'reasoning': {'effort': self.esfuerzo},
            'instructions': prompt,
            'input': json.dumps(contenido, ensure_ascii=False, separators=(',', ':')),
            'text': {'format': {'type': 'text' if web else 'json_object'}},
            'max_output_tokens': int(os.getenv('MAX_OUTPUT_TOKENS', '12000')),
            'store': False,
        }
        if web:
            payload.update({
                'tools': [{'type': 'web_search', 'search_context_size': 'low'}],
                'tool_choice': 'required' if forzar_busqueda else 'auto',
                'max_tool_calls': self.max_web_por_llamada,
            })
        inicio = perf_counter()
        respuesta = self.cliente.responses.create(**payload)
        segundos = round(perf_counter() - inicio, 3)

        uso = respuesta.usage
        entrada = getattr(uso, 'input_tokens', 0) or 0
        salida = getattr(uso, 'output_tokens', 0) or 0
        cache = getattr(getattr(uso, 'input_tokens_details', None), 'cached_tokens', 0) or 0
        razonamiento = getattr(getattr(uso, 'output_tokens_details', None), 'reasoning_tokens', 0) or 0
        llamadas_busqueda, acciones_web = 0, 0
        for parte in respuesta.output or []:
            if getattr(parte, 'type', None) == 'web_search_call':
                acciones_web += 1
                if getattr(getattr(parte, 'action', None), 'type', None) == 'search':
                    llamadas_busqueda += 1
        costo = None
        if self.tarifas is not None:
            t = self.tarifas
            costo = round(((entrada - cache) * t['entrada'] + cache * t['cache'] +
                          salida * t['salida']) / 1_000_000 + llamadas_busqueda * t['web'], 7)
        registro = {
            'fecha_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'item': item, 'etapa': etapa, 'modelo': self.modelo, 'esfuerzo': self.esfuerzo,
            'web_habilitada': web, 'busquedas_web': llamadas_busqueda,
            'acciones_web_totales': acciones_web, 'tokens_entrada': entrada,
            'tokens_entrada_cache': cache, 'tokens_salida': salida,
            'tokens_razonamiento': razonamiento, 'segundos': segundos,
            'costo_estimado_usd': costo, 'respuesta_id': getattr(respuesta, 'id', None),
        }
        self.registros.append(registro)
        bruto = (getattr(respuesta, 'output_text', '') or '').strip()
        try:
            if getattr(respuesta, 'status', 'completed') != 'completed':
                raise ValueError(f'Estado de respuesta: {respuesta.status}')
            patron = re.compile(
    r'("s"\s*:\s*)"([CNU\s]+)"\s*\.replace\(\s*" "\s*,\s*""\s*\)'
)
            corregido = patron.sub(
                lambda m: m.group(1) + json.dumps(
                    ''.join(m.group(2).split())
                ),
                bruto
            )

            if corregido != bruto:
                print(
                    f"AVISO: {etapa}: corregido formato JSON sin llamar nuevamente a OpenAI",
                    flush=True
                )

            datos = json.loads(corregido)
            if not isinstance(datos, dict):
                raise ValueError('Se esperaba un objeto JSON')
            return datos
        except (ValueError, json.JSONDecodeError) as exc:
            # Nunca repetimos automáticamente una llamada: podría generar más cargos.
            raise RuntimeError(f'Respuesta API no utilizable en {etapa} del ítem {item}; '
                               f'ID={registro["respuesta_id"]}. Primeros caracteres: {bruto[:300]!r}') from exc

    def resumen(self) -> dict:
        registros = self.registros
        costos = [x['costo_estimado_usd'] for x in registros]
        return {
            'llamadas_api': len(registros),
            'busquedas_web': sum(x['busquedas_web'] for x in registros),
            'acciones_web': sum(x['acciones_web_totales'] for x in registros),
            'tokens_entrada': sum(x['tokens_entrada'] for x in registros),
            'tokens_entrada_cache': sum(x['tokens_entrada_cache'] for x in registros),
            'tokens_salida': sum(x['tokens_salida'] for x in registros),
            'tokens_razonamiento': sum(x['tokens_razonamiento'] for x in registros),
            'segundos_api': round(sum(x['segundos'] for x in registros), 3),
            'costo_estimado_usd': round(sum(costos), 7) if all(x is not None for x in costos) else None,
        }
