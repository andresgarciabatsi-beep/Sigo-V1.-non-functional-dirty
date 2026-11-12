import os
from threading import Thread

import requests
from flask import Flask, jsonify, request

from main_web import ejecutar_search_web


app = Flask(__name__)


# --------------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------------

# Desarrollo local:
# http://localhost:8888
#
# Futuro Docker:
# http://searxng:8080

SEARXNG_URL = os.getenv(
    "SEARXNG_URL",
    "http://localhost:8888"
)


# --------------------------------------------------------
# ESTADO GLOBAL DE LA BÚSQUEDA
# --------------------------------------------------------

ESTADO_BUSQUEDA = {
    "estado": "inactivo",
    "error": None,
    "resultado": None
}


# --------------------------------------------------------
# CORS
# --------------------------------------------------------

@app.after_request
def permitir_cors(respuesta):

    respuesta.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    respuesta.headers[
        "Access-Control-Allow-Headers"
    ] = "Content-Type"

    respuesta.headers[
        "Access-Control-Allow-Methods"
    ] = "GET, POST, OPTIONS"

    return respuesta


# --------------------------------------------------------
# EJECUTAR SEARCH EN SEGUNDO PLANO
# --------------------------------------------------------

def ejecutar_busqueda_en_segundo_plano(tdr):

    global ESTADO_BUSQUEDA

    try:

        ESTADO_BUSQUEDA = {
            "estado": "procesando",
            "error": None,
            "resultado": None
        }

        resultado = ejecutar_search_web(
            tdr
        )

        ESTADO_BUSQUEDA = {
            "estado": "completado",
            "error": None,
            "resultado": resultado
        }

    except Exception as error:

        ESTADO_BUSQUEDA = {
            "estado": "error",
            "error": str(error),
            "resultado": None
        }


# --------------------------------------------------------
# ESTADO DEL MÓDULO SEARCH Y SEARXNG
# --------------------------------------------------------

@app.route("/api/status")
def obtener_estado():

    try:

        respuesta_searxng = requests.get(
            SEARXNG_URL,
            timeout=5
        )

        respuesta_searxng.raise_for_status()

        return jsonify(
            {
                "ok": True,
                "search": True,
                "searxng": True
            }
        )

    except requests.RequestException as error:

        return jsonify(
            {
                "ok": False,
                "search": True,
                "searxng": False,
                "error": str(error)
            }
        ), 503


# --------------------------------------------------------
# RECIBIR JSON DEL TDR
# --------------------------------------------------------

@app.route(
    "/api/search",
    methods=["POST"]
)
def recibir_json_tdr():

    global ESTADO_BUSQUEDA

    try:

        tdr = request.get_json(
            force=False,
            silent=False
        )


        # ------------------------------------------------
        # COMPROBAR QUE SEA UN OBJETO JSON
        # ------------------------------------------------

        if not isinstance(tdr, dict):

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "El JSON recibido debe ser un objeto."
                }
            ), 400


        # ------------------------------------------------
        # COMPROBAR CAMPOS PRINCIPALES
        # ------------------------------------------------

        if "plazo_ejecucion" not in tdr:

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "El JSON no contiene el campo 'plazo_ejecucion'."
                }
            ), 400


        if "items" not in tdr:

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "El JSON no contiene el campo 'items'."
                }
            ), 400


        # ------------------------------------------------
        # COMPROBAR ITEMS
        # ------------------------------------------------

        items = tdr["items"]


        if not isinstance(items, list):

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "El campo 'items' debe ser una lista."
                }
            ), 400


        if len(items) == 0:

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "El JSON no contiene ítems."
                }
            ), 400


        # ------------------------------------------------
        # EVITAR DOS BÚSQUEDAS SIMULTÁNEAS
        # ------------------------------------------------

        if ESTADO_BUSQUEDA["estado"] == "procesando":

            return jsonify(
                {
                    "ok": False,
                    "error":
                        "Ya existe una búsqueda en ejecución."
                }
            ), 409


        # ------------------------------------------------
        # PREPARAR ESTADO
        # ------------------------------------------------

        ESTADO_BUSQUEDA = {
            "estado": "procesando",
            "error": None,
            "resultado": None
        }


        # ------------------------------------------------
        # INICIAR SEARCH EN SEGUNDO PLANO
        # ------------------------------------------------

        hilo_busqueda = Thread(
            target=ejecutar_busqueda_en_segundo_plano,
            args=(tdr,),
            daemon=True
        )

        hilo_busqueda.start()


        # ------------------------------------------------
        # RESPONDER INMEDIATAMENTE
        # ------------------------------------------------

        return jsonify(
            {
                "ok": True,
                "estado": "procesando",
                "items_recibidos": len(items)
            }
        ), 202


    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error)
            }
        ), 500


# --------------------------------------------------------
# CONSULTAR ESTADO DE LA BÚSQUEDA
# --------------------------------------------------------

@app.route("/api/search/status")
def obtener_estado_busqueda():

    respuesta = {
        "ok": True,
        "estado": ESTADO_BUSQUEDA["estado"]
    }


    # ----------------------------------------------------
    # SI OCURRIÓ UN ERROR
    # ----------------------------------------------------

    if ESTADO_BUSQUEDA["estado"] == "error":

        respuesta["error"] = (
            ESTADO_BUSQUEDA["error"]
        )


    # ----------------------------------------------------
    # SI TERMINÓ CORRECTAMENTE
    # ----------------------------------------------------

    if ESTADO_BUSQUEDA["estado"] == "completado":

        resultado = ESTADO_BUSQUEDA[
            "resultado"
        ]


        respuesta["items_procesados"] = (
            resultado["items_procesados"]
        )

        respuesta["consultas_realizadas"] = (
            resultado["consultas_realizadas"]
        )

        respuesta["tiempo_busqueda"] = (
            resultado["tiempo_busqueda"]
        )


    return jsonify(
        respuesta
    )

# --------------------------------------------------------
# OBTENER RESULTADOS DE LA BÚSQUEDA
# --------------------------------------------------------

@app.route("/api/search/resultados")
def obtener_resultados_busqueda():

    estado = ESTADO_BUSQUEDA["estado"]


    # ----------------------------------------------------
    # BÚSQUEDA TODAVÍA EN PROCESO
    # ----------------------------------------------------

    if estado == "procesando":

        return jsonify(
            {
                "ok": False,
                "estado": "procesando",
                "error":
                    "La búsqueda todavía está en ejecución."
            }
        ), 202


    # ----------------------------------------------------
    # LA BÚSQUEDA TERMINÓ CON ERROR
    # ----------------------------------------------------

    if estado == "error":

        return jsonify(
            {
                "ok": False,
                "estado": "error",
                "error": ESTADO_BUSQUEDA["error"]
            }
        ), 500


    # ----------------------------------------------------
    # TODAVÍA NO EXISTE UNA BÚSQUEDA
    # ----------------------------------------------------

    if estado != "completado":

        return jsonify(
            {
                "ok": False,
                "estado": estado,
                "error":
                    "No existen resultados disponibles."
            }
        ), 409


    resultado = ESTADO_BUSQUEDA["resultado"]


    # ----------------------------------------------------
    # DEVOLVER RESULTADOS
    # ----------------------------------------------------

    return jsonify(
        {
            "ok": True,
            "estado": "completado",

            "items_procesados":
                resultado["items_procesados"],

            "consultas_realizadas":
                resultado["consultas_realizadas"],

            "tiempo_busqueda":
                resultado["tiempo_busqueda"],

            "resultados":
                resultado["resultados"]
        }
    )
# --------------------------------------------------------
# EJECUTAR API
# --------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )