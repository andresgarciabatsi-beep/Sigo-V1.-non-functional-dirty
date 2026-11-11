# Línea base de extracción sobre `htmls_ampliado`

Generado con `src/recorrer_htmls.py`, que usa `src/main3.py` sobre cada HTML.

## Alcance

- HTML encontrados: **71**
- HTML procesados sin excepción: **71**
- Campos posibles: **355** (71 × 5)
- Campos con valor: **341** (96,1 %)
- Tiempo total: **52,5 s**

> Importante: esto mide **cobertura** (si el campo quedó lleno), no **corrección**.
> Para medir acierto hace falta comparar contra una ficha esperada por página.

## Cobertura por campo

| Campo | Llenos | % |
|---|---:|---:|
| nombre | 71/71 | 100,0 % |
| precio | 67/71 | 94,4 % |
| disponibilidad | 63/71 | 88,7 % |
| descripción | 70/71 | 98,6 % |
| especificaciones | 70/71 | 98,6 % |

## Campos llenos por página

| Campos | Páginas |
|---:|---:|
| 5/5 | 61 |
| 4/5 | 6 |
| 3/5 | 4 |

## Estado de validación

| Estado | Páginas |
|---|---:|
| `provisional` | 49 |
| `revision_requerida` | 22 |

## Advertencias más frecuentes

| Aviso | Veces |
|---|---:|
| `DISPONIBILIDAD_SIN_CONFIRMACION_DOM_PRINCIPAL` | 42 |
| `PRECIO_SIN_CONFIRMACION_DOM_PRINCIPAL` | 38 |
| `ESPECIFICACIONES_BLOQUES_COMPLEMENTARIOS_COMBINADOS` | 25 |
| `PRECIO_MONEDA_DOLAR_NO_CONFIRMADA` | 21 |
| `NOMBRE_SIN_CONFIRMACION_DOM_PRINCIPAL` | 11 |
| `PRECIO_ALTERNATIVOS_REVISAR` | 11 |
| `DISPONIBILIDAD_NO_INTERPRETABLE` | 8 |
| `CAMPO_FALTANTE:disponibilidad` | 8 |
| `PRECIO_SIN_CANDIDATO_VALIDO` | 4 |
| `CAMPO_FALTANTE:precio` | 4 |
| `DISPONIBILIDAD_CONTRADICTORIA_O_VARIANTES` | 2 |
| `DESCRIPCION_SIN_CANDIDATO_VALIDO` | 1 |
| `ESPECIFICACIONES_SIN_CANDIDATO_VALIDO` | 1 |

## Páginas con campos faltantes

| Archivo | Campos faltantes |
|---|---|
| `05_mundotek.html` | descripción, especificaciones |
| `06_ekustore.html` | disponibilidad |
| `14_novicompu.html` | disponibilidad |
| `15_amazon.html` | precio, disponibilidad |
| `18_aliexpress.html` | precio, disponibilidad |
| `23_compumillenium.html` | precio, disponibilidad |
| `25_tecnologia_en_linea.html` | disponibilidad |
| `35_lcsc_electronics.html` | precio |
| `N011_soldered.html` | disponibilidad |
| `N032_soldered.html` | disponibilidad |

## Observaciones de calidad

- **62 de 71 páginas** tienen descripción y especificaciones solapadas: el mismo texto
  o un bloque contenido en el otro. Hoy `select_especificaciones` reutiliza bloques
  de descripción cuando no encuentra especificaciones propias.
- **Disponibilidad** es el campo más débil: 8 páginas sin valor y 8 con texto no
  interpretable. Muchas tiendas usan frases o estructuras que no están cubiertas.
- **Precio**: 4 páginas sin valor, 21 con moneda `$` no confirmada y 11 con
  importes alternativos. Hay que revisar rangos, cuotas y precios por variante.
- **Ruido**: aparecen textos de boilerplate como descripción
  (`Smarter Shopping, Better Living! Aliexpress.com`) y títulos no comerciales.
- **Confianza DOM**: 38 selecciones de precio y 42 de disponibilidad quedaron
  fuera del contenedor principal según la heurística de contexto.

## Archivos generados

- `resultados_brutos.json`: los 71 resultados completos (campos + diagnóstico).
- `paginas/*.json`: un resultado por HTML.
- `resumen_paginas.csv`: tabla comparativa por página.
- `resumen_general.json`: totales de la ejecución.
