"""Segunda puerta: clasifica la respuesta de Fetch sin escribir archivos."""


def evaluar_respuesta(respuesta_fetch: dict) -> dict:
    """Devuelve acción y motivo para que el conductor registre la decisión.

    `error` se conserva como diagnóstico; su texto no determina la acción.
    Los códigos específicos se evalúan antes del indicador `exito`.
    """
    if not isinstance(respuesta_fetch, dict):
        return {
            "accion": "revision",
            "motivo": "respuesta_fetch_invalida",
            "status_code": None,
            "error": None,
        }

    codigo = respuesta_fetch.get("status_code")
    diagnostico = {
        "accion": "revision",
        "motivo": "codigo_ausente_o_invalido",
        "status_code": codigo,
        "error": respuesta_fetch.get("error"),
    }

    # bool es subclase de int, pero no representa un código HTTP.
    if not isinstance(codigo, int) or isinstance(codigo, bool) or not 100 <= codigo <= 599:
        return diagnostico

    if codigo in {404, 410}:
        diagnostico.update(
            accion="descartar",
            motivo="pagina_no_encontrada" if codigo == 404 else "pagina_eliminada",
        )
    elif codigo == 403:
        diagnostico["motivo"] = "acceso_denegado"
    elif codigo == 429:
        diagnostico["motivo"] = "limite_de_solicitudes"
    elif codigo >= 500:
        diagnostico["motivo"] = "error_del_servidor"
    elif respuesta_fetch.get("exito") is not True:
        diagnostico["motivo"] = "fetch_no_exitoso"
    elif not 200 <= codigo < 300:
        diagnostico["motivo"] = "codigo_no_exitoso"
    else:
        html = respuesta_fetch.get("html")
        if not isinstance(html, str) or not html.strip():
            diagnostico["motivo"] = "html_ausente_vacio_o_no_textual"
        else:
            diagnostico.update(accion="continuar", motivo="respuesta_valida")

    return diagnostico


def is_response_code_valid(respuesta_fetch: dict) -> bool:
    """True permite pasar; False requiere consultar evaluar_respuesta()."""
    return evaluar_respuesta(respuesta_fetch)["accion"] == "continuar"
