const jsonInput =
    document.getElementById("json-input");

const botonEnviar =
    document.getElementById("boton-enviar");

const mensajeError =
    document.getElementById("mensaje-error");


async function enviarJson() {

    mensajeError.textContent = "";

    const textoJson =
        jsonInput.value.trim();


    // ----------------------------------------------------
    // COMPROBAR QUE HAYA CONTENIDO
    // ----------------------------------------------------

    if (!textoJson) {

        mensajeError.textContent =
            "Debe ingresar un JSON.";

        return;
    }


    // ----------------------------------------------------
    // CONVERTIR TEXTO A JSON
    // ----------------------------------------------------

    let datosJson;

    try {

        datosJson = JSON.parse(
            textoJson
        );

    }

    catch (error) {

        mensajeError.textContent =
            `JSON no válido: ${error.message}`;

        return;
    }


    // ----------------------------------------------------
    // DESHABILITAR BOTÓN MIENTRAS SE ENVÍA
    // ----------------------------------------------------

    botonEnviar.disabled = true;
    botonEnviar.textContent = "ENVIANDO...";


    try {

        const apiBaseUrl =
            window.SIGO_CONFIG.API_BASE_URL;


        // ------------------------------------------------
        // ENVIAR JSON AL MÓDULO SEARCH
        // ------------------------------------------------

        const respuesta = await fetch(
            `${apiBaseUrl}/api/search`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify(
                    datosJson
                )
            }
        );


        const datos =
            await respuesta.json();


        // ------------------------------------------------
        // COMPROBAR RESPUESTA DEL BACKEND
        // ------------------------------------------------

        if (!respuesta.ok || !datos.ok) {

            mensajeError.textContent =
                datos.error ||
                "El Módulo Search rechazó el JSON.";

            return;
        }


        // ------------------------------------------------
        // SEARCH FUE INICIADO CORRECTAMENTE
        // ------------------------------------------------

        console.log(
            "Búsqueda iniciada:",
            datos
        );


        // ------------------------------------------------
        // IR A PANTALLA DE PROCESAMIENTO
        // ------------------------------------------------

        window.location.href =
            "procesando.html";

    }

    catch (error) {

        mensajeError.textContent =
            `No fue posible comunicarse con el Módulo Search: ${error.message}`;

    }

    finally {

        botonEnviar.disabled = false;
        botonEnviar.textContent = "ENVIAR";
    }
}


botonEnviar.addEventListener(
    "click",
    enviarJson
);