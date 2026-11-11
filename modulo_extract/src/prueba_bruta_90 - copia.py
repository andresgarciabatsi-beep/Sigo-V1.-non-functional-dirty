"""SIGO Fetch: banco de pruebas sin filtros ni selección de candidatos.

Ejecutar desde src/:
    python prueba_bruta_90.py --htmls ../recursos/htmls --patrones ../recursos/patrones.json --salida ../resultados/prueba_bruta

Prueba TODAS las reglas sobre TODOS los HTML de la carpeta y subcarpetas.
Conserva coincidencias repetidas, poco relacionadas y con valor vacío.
No usa localizadores.py: ese módulo sí contiene filtros y selección.
Requiere: pip install selectolax extruct
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


CAMPOS = ("nombre", "precio", "disponibilidad", "descripcion", "especificaciones")


def buscar_ruta(objeto, ruta):
    """Recupera todas las coincidencias de una ruta: offers.price, offers.0.price.

    Respeta las listas, aunque haya varias variantes u ofertas. No elimina duplicados.
    """
    valores = [objeto]
    for parte in ruta.split("."):
        siguientes = []
        for actual in valores:
            if isinstance(actual, list):
                if parte.isdigit():
                    indice = int(parte)
                    if 0 <= indice < len(actual):
                        siguientes.append(actual[indice])
                else:
                    for elemento in actual:
                        siguientes.extend(buscar_ruta(elemento, parte))
            elif isinstance(actual, dict):
                for clave, valor in actual.items():
                    if clave.casefold() == parte.casefold():
                        siguientes.append(valor)
        valores = siguientes
        if not valores:
            break
    return valores


def objetos_tipo(objeto, tipo):
    """Recorre todos los objetos estructurados, incluso productos relacionados."""
    encontrados = []

    def recorrer(actual):
        if isinstance(actual, list):
            for elemento in actual:
                recorrer(elemento)
        elif isinstance(actual, dict):
            tipos = actual.get("@type", actual.get("type", []))
            if not isinstance(tipos, list):
                tipos = [tipos]
            if any(
                str(t).rstrip("/").split("/")[-1].casefold() == tipo.casefold()
                for t in tipos
            ):
                encontrados.append(actual)
            for valor in actual.values():
                if isinstance(valor, (dict, list)):
                    recorrer(valor)

    recorrer(objeto)
    return encontrados


def leer_json(texto):
    """Interpreta JSON válido (no ejecuta código JavaScript)."""
    if not texto or not texto.lstrip("\ufeff \r\t\n").startswith(("{", "[")):
        return None
    try:
        return json.loads(texto.strip().lstrip("\ufeff"))
    except (ValueError, TypeError):
        return None


def resolver_vtex(objeto, cache, visitados=frozenset(), profundidad=0):
    """Resuelve referencias de producto VTEX para que las rutas actuales funcionen."""
    if profundidad > 40:
        return objeto
    if isinstance(objeto, list):
        return [resolver_vtex(x, cache, visitados, profundidad + 1) for x in objeto]
    if not isinstance(objeto, dict):
        return objeto
    referencia = objeto.get("id")
    if (objeto.get("type") == "id" and isinstance(referencia, str)
            and referencia in cache and referencia not in visitados):
        return resolver_vtex(
            cache[referencia], cache, visitados | {referencia}, profundidad + 1
        )
    return {
        clave: resolver_vtex(valor, cache, visitados, profundidad + 1)
        for clave, valor in objeto.items()
    }


def preparar(html):
    """Prepara fuentes sin deduplicación de metadatos y sin excluir zonas HTML."""
    from selectolax.lexbor import LexborHTMLParser
    import extruct

    arbol = LexborHTMLParser(html)
    errores = []
    try:
        estructurados = extruct.extract(
            html,
            base_url="http://ejemplo.local/",
            syntaxes=["json-ld", "microdata"],
        )
    except Exception as exc:
        errores.append(f"No se pudo leer JSON-LD/Microdata: {type(exc).__name__}: {exc}")
        estructurados = {}

    estados = []
    # Cualquier script que contenga JSON directamente legible, salvo JSON-LD,
    # que ya se analiza como fuente independiente.
    for script in arbol.css("script"):
        if script.attributes.get("type", "").lower() == "application/ld+json":
            continue
        dato = leer_json(script.text())
        if isinstance(dato, (dict, list)):
            estados.append(dato)

    # Compatibilidad con el estado normalizado de VTEX en <template>.
    if hasattr(arbol, "template_fragments"):
        for fragmento in arbol.template_fragments():
            padre = fragmento.parent
            if padre is None or padre.attributes.get("data-varname") != "__STATE__":
                continue
            for script in fragmento.css("script"):
                dato = leer_json(script.text())
                if isinstance(dato, (dict, list)):
                    estados.append(dato)  # Estado original: sin eliminar elementos.
                    if isinstance(dato, dict):
                        for clave, producto in dato.items():
                            if clave.startswith("Product:") and isinstance(producto, dict):
                                estados.append(resolver_vtex(producto, dato))

    return {
        "html": arbol,
        "jsonld": estructurados.get("json-ld", []),
        "microdata": estructurados.get("microdata", []),
        "json_embebido": estados,
    }, errores


def extraer_todo(campo, regla, fuentes):
    """Devuelve TODAS las coincidencias, sin comprobar su relevancia ni su contenido."""
    origen = regla["fuente"]
    arbol = fuentes["html"]

    if origen == "html":
        nodos = arbol.css(regla["selector"])
        datos = []
        for indice, nodo in enumerate(nodos, 1):
            atributo = regla.get("atributo")
            if atributo:
                valor = nodo.attributes.get(atributo, "")
            else:
                valor = nodo.text(separator="\n" if campo == "especificaciones" else " ", strip=False)
                if not valor:
                    valor = nodo.attributes.get("content", nodo.attributes.get("value", ""))
            datos.append({"indice": indice, "valor": valor})
        return datos

    if origen in ("meta", "opengraph"):
        clave = regla["clave"].casefold()
        datos = []
        if origen == "meta" and clave == "title":
            nodos = arbol.css("head title")
            return [{"indice": i, "valor": n.text(strip=False)} for i, n in enumerate(nodos, 1)]

        for nodo in arbol.css("meta[name], meta[property]"):
            atributos = nodo.attributes
            clave_nodo = (atributos.get("property") or atributos.get("name") or "").casefold()
            if clave_nodo == clave:
                datos.append({"indice": len(datos) + 1, "valor": atributos.get("content", "")})
        return datos

    if origen in ("jsonld", "microdata"):
        datos = []
        for objeto in objetos_tipo(fuentes[origen], regla.get("tipo", "Product")):
            for valor in buscar_ruta(objeto, regla["ruta"]):
                datos.append({"indice": len(datos) + 1, "valor": valor})
        return datos

    if origen == "json_embebido":
        datos = []
        for estado in fuentes[origen]:
            for valor in buscar_ruta(estado, regla["ruta"]):
                datos.append({"indice": len(datos) + 1, "valor": valor})
        return datos

    raise ValueError(f"Fuente desconocida: {origen}")


def guardar_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def guardar_csv(ruta, filas, columnas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def ejecutar(carpeta_htmls, ruta_patrones, salida):
    patrones = json.loads(ruta_patrones.read_text(encoding="utf-8-sig"))
    reglas_por_campo = patrones["campos"]
    archivos = sorted(carpeta_htmls.rglob("*.html"))
    if not archivos:
        raise ValueError(f"No se encontraron archivos .html en {carpeta_htmls}")

    print(f"HTML encontrados: {len(archivos)}")
    if len(archivos) != 90:
        print("AVISO: la carpeta no contiene exactamente 90 HTML. Se procesarán TODOS los encontrados.")

    total_reglas = sum(len(reglas_por_campo[campo]) for campo in CAMPOS)
    print(f"Reglas por página: {total_reglas} (sin filtros, sin límites de coincidencias)")
    resumen_paginas = []
    resumen_patrones = defaultdict(lambda: {"paginas_con_coincidencias": 0, "coincidencias": 0})

    for numero, ruta in enumerate(archivos, 1):
        nombre = ruta.relative_to(carpeta_htmls).as_posix()
        registro = {"archivo": nombre, "estado": "ok", "errores": []}
        try:
            fuentes, errores = preparar(ruta.read_bytes())
            registro["errores"].extend(errores)
            resultados = {}

            for campo in CAMPOS:
                reglas_resultado = []
                conteo = 0
                patrones_con_coincidencias = 0
                for indice, regla in enumerate(reglas_por_campo[campo], 1):
                    patron = regla.get("selector", regla.get("ruta", regla.get("clave", "")))
                    identificador = (campo, indice)
                    try:
                        coincidencias = extraer_todo(campo, regla, fuentes)
                        error = None
                    except Exception as exc:
                        coincidencias = []
                        error = f"{type(exc).__name__}: {exc}"
                        registro["errores"].append(f"{campo} / {patron}: {error}")
                    cantidad = len(coincidencias)
                    conteo += cantidad
                    if cantidad:
                        patrones_con_coincidencias += 1
                        resumen_patrones[identificador]["paginas_con_coincidencias"] += 1
                        resumen_patrones[identificador]["coincidencias"] += cantidad
                    reglas_resultado.append({
                        "regla": indice,
                        "fuente": regla["fuente"],
                        "patron": patron,
                        "prioridad": regla.get("prioridad"),
                        "cantidad_coincidencias": cantidad,
                        "coincidencias": coincidencias,
                        "error": error,
                    })

                resultados[campo] = reglas_resultado
                registro[f"{campo}_coincidencias"] = conteo
                registro[f"{campo}_patrones"] = patrones_con_coincidencias

            registro["total_coincidencias"] = sum(
                registro[f"{campo}_coincidencias"] for campo in CAMPOS
            )
            # Archivo individual: mantiene coincidencias, incluidas repetidas y vacías.
            nombre_resultado = ruta.relative_to(carpeta_htmls).with_suffix(".json")
            guardar_json(salida / "paginas" / nombre_resultado, {
                "html": nombre,
                "version_patrones": patrones.get("version"),
                "reglas_probadas": total_reglas,
                "resultado": resultados,
                "errores": registro["errores"],
            })
            print(f"[{numero}/{len(archivos)}] OK    {nombre}: {registro['total_coincidencias']} coincidencias")
        except Exception as exc:
            registro["estado"] = "error"
            registro["errores"].append(f"{type(exc).__name__}: {exc}")
            print(f"[{numero}/{len(archivos)}] ERROR {nombre}: {exc}")

        registro["errores"] = " | ".join(registro["errores"])
        resumen_paginas.append(registro)

    columnas_paginas = ["archivo", "estado", "total_coincidencias"]
    for campo in CAMPOS:
        columnas_paginas.extend([f"{campo}_coincidencias", f"{campo}_patrones"])
    columnas_paginas.append("errores")
    guardar_csv(salida / "resumen_paginas.csv", resumen_paginas, columnas_paginas)

    filas_patrones = []
    for campo in CAMPOS:
        for indice, regla in enumerate(reglas_por_campo[campo], 1):
            datos = resumen_patrones[(campo, indice)]
            filas_patrones.append({
                "campo": campo,
                "regla": indice,
                "fuente": regla["fuente"],
                "patron": regla.get("selector", regla.get("ruta", regla.get("clave", ""))),
                "prioridad": regla.get("prioridad"),
                **datos,
            })
    guardar_csv(salida / "resumen_patrones.csv", filas_patrones, [
        "campo", "regla", "fuente", "patron", "prioridad",
        "paginas_con_coincidencias", "coincidencias",
    ])

    procesadas = sum(r["estado"] == "ok" for r in resumen_paginas)
    guardar_json(salida / "resumen_general.json", {
        "html_encontrados": len(archivos),
        "html_procesados": procesadas,
        "html_con_error": len(archivos) - procesadas,
        "reglas_por_html": total_reglas,
        "filtrado": "ninguno a nivel de coincidencias o candidatos",
        "nota": "El parser solo puede recuperar contenido presente en el HTML; el JSON no interpretable no es accesible por rutas JSON.",
    })
    print(f"\nCompletado: {procesadas}/{len(archivos)} HTML procesados.")
    print(f"Resultados: {salida.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Prueba bruta de todos los patrones en todos los HTML")
    parser.add_argument("--htmls", type=Path, default=Path("../recursos/htmls_ampliado"))
    parser.add_argument("--patrones", type=Path, default=Path("../recursos/patrones.json"))
    parser.add_argument("--salida", type=Path, default=Path("../resultados/prueba_bruta"))
    args = parser.parse_args()
    try:
        ejecutar(args.htmls, args.patrones, args.salida)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
