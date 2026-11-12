async function verificarConexion() {

    const apiBaseUrl =
        window.SIGO_CONFIG.API_BASE_URL;

    try {

        const respuesta = await fetch(
            `${apiBaseUrl}/api/status`
        );


        const datos = await respuesta.json();


        if (respuesta.ok && datos.ok) {

            window.location.href =
                "ingresar_json.html";

            return;
        }


        const mensaje =
            datos.error ||
            "No fue posible conectar con el Módulo Search o SearXNG.";


        window.location.href =
            `error.html?mensaje=${encodeURIComponent(mensaje)}`;

    }

    catch (error) {

        const mensaje =
            `No fue posible conectar con el Módulo Search. ${error.message}`;


        window.location.href =
            `error.html?mensaje=${encodeURIComponent(mensaje)}`;
    }
}


verificarConexion();