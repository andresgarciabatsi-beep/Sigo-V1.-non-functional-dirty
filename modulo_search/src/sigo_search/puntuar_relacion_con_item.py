from collections import Counter, defaultdict
import math
import re
import unicodedata


def tokenizar(texto):
    """Normaliza mayúsculas y acentos; conserva unidades como '750va'."""
    sin_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", sin_acentos.lower())


def puntajes_bm25(documentos, consulta, k1=1.5, b=0.75):
    """Calcula BM25 clásico con IDF no negativo para todo el corpus recibido."""
    tokens = [tokenizar(documento) for documento in documentos]
    terminos = set(tokenizar(consulta))
    cantidad = len(tokens)
    if not cantidad or not terminos:
        return [0.0] * cantidad

    longitud_media = sum(map(len, tokens)) / cantidad or 1.0
    frecuencia_documental = Counter(
        termino for documento in tokens for termino in set(documento)
    )

    puntajes = []
    for documento in tokens:
        frecuencias = Counter(documento)
        longitud = len(documento)
        puntaje = 0.0
        for termino in terminos:
            veces = frecuencias[termino]
            if not veces:
                continue
            df = frecuencia_documental[termino]
            idf = math.log(1 + (cantidad - df + 0.5) / (df + 0.5))
            denominador = veces + k1 * (1 - b + b * longitud / longitud_media)
            puntaje += idf * veces * (k1 + 1) / denominador
        puntajes.append(puntaje)

    return puntajes


def puntuar_relacion_con_item(resultados_sf, peso_titulo=2.0, peso_contenido=1.0):
    """Compara todas las tiendas de una región, pero nunca mezcla regiones o ítems.

    La estructura por tienda se mantiene para no romper generar_html.py.
    Dentro de cada tienda se ordenan sus resultados por puntaje; cada
    resultado añade la posición global que obtuvo dentro de su región.
    """
    salida = []
    grupos = defaultdict(list)

    for consulta in resultados_sf:
        copia = dict(consulta)
        copia["resultados"] = [dict(r) for r in consulta.get("resultados", [])]
        salida.append(copia)
        clave = (consulta["numero_item"], consulta["mercado"])
        for resultado in copia["resultados"]:
            grupos[clave].append((copia, resultado))

    for (numero_item, mercado), referencias in grupos.items():
        if not referencias:
            continue

        titulo_consulta = referencias[0][0]["nombre_item"]
        titulos = [resultado.get("title", "") for _, resultado in referencias]
        contenidos = [resultado.get("content", "") for _, resultado in referencias]

        puntuaciones_titulo = puntajes_bm25(titulos, titulo_consulta)
        puntuaciones_contenido = puntajes_bm25(contenidos, titulo_consulta)

        for (_, resultado), score_titulo, score_contenido in zip(
            referencias, puntuaciones_titulo, puntuaciones_contenido
        ):
            resultado["puntaje_bm25"] = round(
                peso_titulo * score_titulo + peso_contenido * score_contenido, 5
            )

        # `sort` estable: los empates conservan el orden de llegada.
        ordenados = sorted(
            (resultado for _, resultado in referencias),
            key=lambda r: r["puntaje_bm25"],
            reverse=True,
        )
        for posicion, resultado in enumerate(ordenados, start=1):
            resultado["posicion_region"] = posicion

    # Se preserva la agrupación por tienda del JSON original.
    for consulta in salida:
        consulta["resultados"].sort(
            key=lambda r: r.get("puntaje_bm25", 0), reverse=True
        )

    return salida
