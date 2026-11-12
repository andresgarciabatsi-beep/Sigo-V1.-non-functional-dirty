const contenedorResultados =
    document.getElementById(
        "contenedor-resultados"
    );

const resumen =
    document.getElementById(
        "resumen"
    );

const botonNuevoJson =
    document.getElementById(
        "boton-nuevo-json"
    );


// --------------------------------------------------------
// ESCAPAR TEXTO PARA HTML
// --------------------------------------------------------

function escaparHtml(texto) {

    const elemento =
        document.createElement("div");

    elemento.textContent =
        texto ?? "";

    return elemento.innerHTML;
}


// --------------------------------------------------------
// AGRUPAR RESULTADOS
// --------------------------------------------------------

function agruparResultados(consultas) {

    const items = {};


    for (const consulta of consultas) {

        const numeroItem =
            consulta.numero_item;


        if (!items[numeroItem]) {

            items[numeroItem] = {
                numero_item: numeroItem,
                nombre_item:
                    consulta.nombre_item,
                mercados: {}
            };
        }


        const mercado =
            consulta.mercado;


        if (!items[numeroItem].mercados[mercado]) {

            items[numeroItem].mercados[mercado] = {
                prioridad:
                    consulta.prioridad,
                resultados: []
            };
        }


        for (const resultado of consulta.resultados) {

            items[numeroItem]
                .mercados[mercado]
                .resultados
                .push(
                    {
                        tienda:
                            consulta.tienda,

                        ...resultado
                    }
                );
        }
    }


    return Object.values(items);
}


// --------------------------------------------------------
// CREAR TABLA DE MERCADO
// --------------------------------------------------------

function crearMercado(
    nombreMercado,
    datosMercado
) {

    const resultados =
        datosMercado.resultados;


    // Ordenar por posición BM25 regional.

    resultados.sort(
        (a, b) =>
            (a.posicion_region ?? 999999)
            -
            (b.posicion_region ?? 999999)
    );


    let html = `
        <section class="mercado">

            <h3 class="mercado-titulo">
                ${escaparHtml(nombreMercado)}
            </h3>
    `;


    if (resultados.length === 0) {

        html += `
            <p class="sin-resultados">
                No se encontraron resultados.
            </p>
        `;

    }

    else {

        html += `
            <div class="tabla-contenedor">

                <table>

                    <thead>

                        <tr>

                            <th class="columna-posicion">
                                Pos.
                            </th>

                            <th class="columna-tienda">
                                Tienda
                            </th>

                            <th>
                                Resultado
                            </th>

                            <th>
                                Descripción
                            </th>

                            <th class="columna-bm25">
                                BM25
                            </th>

                            <th>
                                Enlace
                            </th>

                        </tr>

                    </thead>

                    <tbody>
        `;


        for (const resultado of resultados) {

            const posicion =
                resultado.posicion_region ?? "";

            const puntaje =
                resultado.puntaje_bm25;

            const bm25 =
                typeof puntaje === "number"
                    ? puntaje.toFixed(3)
                    : "";


            html += `
                <tr>

                    <td class="columna-posicion">
                        ${posicion}
                    </td>

                    <td>
                        ${escaparHtml(resultado.tienda)}
                    </td>

                    <td>
                        ${escaparHtml(resultado.title)}
                    </td>

                    <td>
                        ${escaparHtml(resultado.content)}
                    </td>

                    <td class="columna-bm25">
                        ${bm25}
                    </td>

                    <td>

                        <a
                            href="${escaparHtml(resultado.url)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            Abrir producto
                        </a>

                    </td>

                </tr>
            `;
        }


        html += `
                    </tbody>

                </table>

            </div>
        `;
    }


    html += `
        </section>
    `;


    return html;
}


// --------------------------------------------------------
// MOSTRAR RESULTADOS
// --------------------------------------------------------

function mostrarResultados(consultas) {

    const items =
        agruparResultados(
            consultas
        );


    items.sort(
        (a, b) =>
            a.numero_item
            -
            b.numero_item
    );


    let html = "";


    for (const item of items) {

        html += `
            <section class="item">

                <h2 class="item-titulo">
                    Ítem ${item.numero_item}:
                    ${escaparHtml(item.nombre_item)}
                </h2>
        `;


        const mercados =
            Object.entries(
                item.mercados
            );


        mercados.sort(
            (a, b) =>
                a[1].prioridad
                -
                b[1].prioridad
        );


        for (
            const [
                nombreMercado,
                datosMercado
            ]
            of mercados
        ) {

            html += crearMercado(
                nombreMercado,
                datosMercado
            );
        }


        html += `
            </section>
        `;
    }


    contenedorResultados.innerHTML =
        html;
}


// --------------------------------------------------------
// CARGAR RESULTADOS DESDE SEARCH
// --------------------------------------------------------

async function cargarResultados() {

    const apiBaseUrl =
        window.SIGO_CONFIG.API_BASE_URL;


    try {

        const respuesta = await fetch(
            `${apiBaseUrl}/api/search/resultados`
        );


        const datos =
            await respuesta.json();


        if (!respuesta.ok || !datos.ok) {

            const mensaje =
                encodeURIComponent(
                    datos.error ||
                    "No fue posible obtener los resultados."
                );

            window.location.href =
                `error.html?mensaje=${mensaje}`;

            return;
        }


        resumen.textContent =
            `${datos.items_procesados} ítems · ` +
            `${datos.consultas_realizadas} consultas · ` +
            `${datos.tiempo_busqueda.toFixed(2)} s`;


        mostrarResultados(
            datos.resultados
        );

    }

    catch (error) {

        const mensaje =
            encodeURIComponent(
                `No fue posible cargar los resultados: ${error.message}`
            );

        window.location.href =
            `error.html?mensaje=${mensaje}`;
    }
}


// --------------------------------------------------------
// USAR OTRO JSON
// --------------------------------------------------------

botonNuevoJson.addEventListener(
    "click",
    function () {

        window.location.href =
            "index.html";
    }
);


// --------------------------------------------------------
// INICIAR
// --------------------------------------------------------

cargarResultados(); 