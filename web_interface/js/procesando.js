async function comprobarEstado() {

    const apiBaseUrl =
        window.SIGO_CONFIG.API_BASE_URL;


    try {

        const respuesta = await fetch(
            `${apiBaseUrl}/api/search/status`
        );

        const datos =
            await respuesta.json();


        // ------------------------------------------------
        // SEARCH SIGUE TRABAJANDO
        // ------------------------------------------------

        if (datos.estado === "procesando") {

            setTimeout(
                comprobarEstado,
                1000
            );

            return;
        }


        // ------------------------------------------------
        // SEARCH TERMINÓ CORRECTAMENTE
        // ------------------------------------------------

        if (datos.estado === "completado") {

            window.location.href =
                "resultados.html";

            return;
        }


        // ------------------------------------------------
        // SEARCH TERMINÓ CON ERROR
        // ------------------------------------------------

        if (datos.estado === "error") {

            const mensaje =
                encodeURIComponent(
                    datos.error ||
                    "Ocurrió un error durante la búsqueda."
                );

            window.location.href =
                `error.html?mensaje=${mensaje}`;

            return;
        }


        // ------------------------------------------------
        // ESTADO INESPERADO
        // ------------------------------------------------

        setTimeout(
            comprobarEstado,
            1000
        );

    }

    catch (error) {

        const mensaje =
            encodeURIComponent(
                `No fue posible consultar el estado de Search: ${error.message}`
            );

        window.location.href =
            `error.html?mensaje=${mensaje}`;
    }
}


comprobarEstado();