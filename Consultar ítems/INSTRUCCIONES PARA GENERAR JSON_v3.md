# VOLTIX ECUADOR S.A.S.

**PROVEEDOR, CONSULTORÍA, ESTUDIOS Y EJECUTOR DE PROYECTOS ELÉCTRICOS, ELECTRÓNICOS, TELECOMUNICACIONES Y SOFTWARE**  
Cuenca, Loja, Ecuador

Este es un tutorial que debes seguir para registrar los ítems del documento donde se hallan los ítems, denominado TDR.

## Campos para el registro de ítems del TDR

Lea la siguiente tabla e infórmese sobre el significado de cada campo:

| Campo | Significado | Ejemplo |
|---|---|---|
| **Proceso (NIC)** | Identifica el proceso de contratación al que pertenecen los ítems. | NIC-123456789 |
| **Subsección: Plazo de ejecución** | | |
| Valor | Número que define el plazo de ejecución. | 5 |
| Unidad | Unidades del plazo de ejecución: días, semanas, meses, etc. | Días |
| Tipo | Distinción del plazo, por ejemplo, calendario o laborables. | Calendario |
| **Subsección: Ítems / Ítem \<n\>** | | |
| Número de ítem dentro del TDR | Identificador del ítem dentro del proceso, es decir dentro del TDR. | 1 |
| Nombre | Denominación del producto que debe buscarse en el módulo Search. | Pantalla interactiva táctil de 86 pulgadas |
| Cantidad | Número de unidades requeridas. | 1 |
| Unidad de medida | Unidad, juego, kit, paquete, metro, etc. | UNIDAD |
| **Subsubsección: Especificaciones técnicas** | | |
| Grupos | Agrupaciones de requisitos técnicos por categoría. A veces se dan los requisitos agrupados según los subcomponentes del ítem. | Audio y micrófono, cámara integrada |
| Requisitos | Condiciones específicas de cada subgrupo. | Salida de audio: 1 estéreo mini Jack, Resolución mínima de cámara: 4K |
| **Subsubsección: Accesorios necesarios (correspondiente a cada ítem)** | | |
| Nombre | Nombre del accesorio. | Control remoto |
| Cantidad → Valor | Número que define la cantidad de accesorios. | 2 |
| Cantidad → Tipo | Define las unidades para la cantidad. | Unidades |
| Requisitos | Requisitos técnicos del accesorio. | Con puntero |

## Reglas de extracción

A la hora de extraer la información para cada campo de la tabla anterior, siga las siguientes reglas:

| Código | Regla | Instrucción |
|---|---|---|
| E01 | Información ausente | No inventar información que no esté presente en el TDR. Si un dato no puede identificarse, dejarlo sin determinar para su posterior representación según las reglas de formato. |
| E02 | Información ambigua | No asumir valores, características o condiciones cuando existan varias interpretaciones posibles. Conservar únicamente la información que pueda determinarse con certeza. |
| E03 | Identificación de ítems | Identificar todos los ítems solicitados en el TDR y conservar su numeración original, incluso cuando los números no sean consecutivos. |
| E05 | Cantidades y unidades | Identificar las cantidades y unidades de medida correspondientes a cada ítem y accesorio, respetando su significado original. No asumir unidades que no estén especificadas. |
| E06 | Grupos existentes | Respetar las agrupaciones de especificaciones técnicas establecidas explícitamente en el TDR, conservando los requisitos correspondientes a cada grupo. |
| E07 | Ausencia de grupos | Si las especificaciones técnicas de un ítem no están organizadas en grupos, colocar todos sus requisitos dentro de un único grupo cuyo nombre sea `null`. No crear agrupaciones artificiales. |
| E08 | Separación de requisitos | Cuando una descripción contenga varias características técnicas independientes, separarlas en requisitos individuales, conservando su significado y las relaciones necesarias entre ellas. Cada requisito deberá incorporarse al grupo técnico correspondiente. Si el TDR no establece grupos, se utilizará un único grupo cuyo nombre sea `null`, conforme a la regla E07. |
| E09 | Conservación de requisitos | Preservar íntegramente los valores, unidades, rangos, tolerancias, límites mínimos y máximos, condiciones de funcionamiento y demás características técnicas exigidas. No omitir condiciones que puedan influir en el cumplimiento del producto. |
| E10 | Accesorios obligatorios | Identificar los accesorios exigidos en el TDR y asociarlos con el ítem principal correspondiente. Extraer el nombre, la cantidad, la unidad de medida y los requisitos técnicos particulares de cada accesorio. No convertir los accesorios en ítems independientes. |
| E12 | Requisitos contradictorios | Cuando se identifiquen requisitos técnicos incompatibles dentro de un mismo ítem, conservar ambos sin seleccionar arbitrariamente uno de ellos. La contradicción deberá comunicarse mediante el log correspondiente, definido en la sección 4. Una contradicción existe únicamente cuando dos condiciones no pueden cumplirse simultáneamente. Dos requisitos de diferente exigencia no deben considerarse contradictorios si ambos pueden satisfacerse. |
| E13 | Información ajena al producto | No incorporar condiciones administrativas o contractuales como especificaciones técnicas del producto. El plazo de ejecución deberá extraerse en su apartado correspondiente. |
| E14 | Fidelidad documental | No inventar, añadir, sustituir ni modificar características técnicas, cantidades, compatibilidades, funcionalidades o equivalencias que no estén respaldadas por el TDR. Se permite reorganizar y separar información siempre que se conserve su significado original. |

## Reglas de formato

| Código | Regla | Instrucción |
|---|---|---|
| F01 | Estructura obligatoria | Utilizar exactamente la estructura JSON establecida respetando la jerarquía de los campos y sus relaciones. |
| F02 | Nombres de campos | Utilizar exclusivamente los nombres de campos definidos en el esquema JSON. No añadir, eliminar, renombrar ni modificar claves. |
| F03 | Tipos de datos | Respetar los tipos de datos definidos para cada campo: números, cadenas de texto, objetos, listas o `null`, según corresponda. |
| F04 | Valores desconocidos | Representar mediante `null` los valores individuales que no puedan determinarse a partir del TDR. No utilizar cadenas como "Desconocido", "N/A" o "No especificado" en sustitución de `null`. |
| F05 | Colecciones vacías | Utilizar `[]` cuando se confirme que una colección no contiene elementos. No generar objetos vacíos artificiales para representar elementos inexistentes. |
| F06 | Organización de ítems | Representar cada ítem como un objeto independiente dentro de la lista `items`, conservando su número original y los campos correspondientes. |
| F07 | Organización de grupos | Representar los grupos técnicos dentro de `especificaciones_tecnicas.grupos`. Cada grupo debe contener los campos `grupo` y `requisitos`. Si el documento no establece grupos, utilizar un único grupo con `"grupo": null`. |
| F08 | Requisitos técnicos | Representar cada requisito técnico como una cadena de texto independiente dentro de la lista `requisitos` del grupo correspondiente. |
| F09 | Accesorios obligatorios | Representar los accesorios dentro de `especificaciones_tecnicas.accesorios_obligatorios` del ítem correspondiente. Cada accesorio debe constituir un objeto independiente. |
| F10 | Cantidad de accesorios | Representar la cantidad de cada accesorio mediante un objeto `cantidad` que contenga `valor` (cantidad numérica) y `tipo` (unidad de medida). Si alguno de estos datos es desconocido, utilizar `null` únicamente en el campo correspondiente. |
| F11 | Requisitos de accesorios | Representar las características técnicas de cada accesorio mediante una lista `requisitos`, donde cada elemento sea una cadena de texto. No utilizar el campo `detalle`. |
| F13 | Sintaxis JSON | Generar un JSON sintácticamente válido, utilizando comillas dobles para las claves y cadenas de texto, sin comentarios, comas finales ni elementos ajenos a la estructura definida. |

## 4. Logs y estructura de respuesta

Las siguientes instrucciones establecen el formato que se debe utilizar para presentar los resultados del análisis del documento.

La respuesta deberá contener tres secciones, en el siguiente orden:

1. Logs del documento: mensajes relacionados con anomalías detectadas en el documento.
2. Logs de los ítems: mensajes relacionados con anomalías detectadas en cada ítem.
3. JSONS de ítems: información extraída y estructurada en formato JSON.

### 4.1. Logs del documento

Esta sección deberá aparecer siempre al inicio de la respuesta.

Cuando se detecte alguna anomalía documental contemplada en las reglas de logs, deberá mostrarse su código y un mensaje descriptivo.

Si no existen anomalías, se escribirá “Sin logs”.

#### 4.1.1 Condiciones para generar logs del documento

| Código del log | Clasificación | Condición para generar el log |
|---|---|---|
| DOC-01 | Documento no correspondiente | Cuando el archivo proporcionado no corresponda a un TDR o documento que permita identificar los productos solicitados. |
| DOC-02 | Agrupación inconsistente de productos | Cuando el TDR identifique como un único producto o ítem a dos o más bienes diferentes que, en otras partes del documento, se describan como productos independientes. El mensaje debe identificar la agrupación y los bienes involucrados. No generar este log por la sola presencia de accesorios o componentes de un kit o conjunto expresamente definido como una unidad. La advertencia no autoriza a corregir la numeración, fusionar productos ni decidir automáticamente si deben registrarse como uno o varios ítems. |

### 4.2. Logs de los ítems

Los logs deberán organizarse individualmente según el número de ítem establecido en el TDR.

Cada ítem tendrá un encabezado con su número y nombre, seguido de los mensajes correspondientes.

Cuando un ítem presente varias anomalías, estas se mostrarán en líneas independientes, cada una identificada mediante su código.

Si un ítem no presenta anomalías, se escribirá “Sin logs”.

#### 4.2.1 Condiciones para generar logs de los ítems

| Código | Clasificación | Condición para generar el log |
|---|---|---|
| ITEM-01 | Especificaciones contradictorias | Cuando dos o más requisitos técnicos del mismo ítem sean incompatibles entre sí. El mensaje debe identificar los requisitos involucrados. |
| ITEM-02 | Cantidades contradictorias | Cuando el TDR presente cantidades diferentes para un mismo ítem o accesorio, sin que exista una distinción que justifique la diferencia. |
| ITEM-03 | Cantidad o unidad ausente | Cuando no pueda determinarse la cantidad o unidad de medida de un ítem o accesorio. |

### 4.3 Formato obligatorio de respuesta

El LLM deberá utilizar exactamente la siguiente estructura:

```text
Logs del documento:
<Logs detectados o "Sin logs">

Logs de los ítems:

Ítem 1: <Nombre del ítem>
<Logs detectados o "Sin logs">

Ítem 2: <Nombre del ítem>
<Logs detectados o "Sin logs">

Ítem <número de ítem>: <Nombre del ítem>
<Logs detectados o "Sin logs">

==================================================

JSONS de ítems:
<JSON completo>
```

## 5. Instrucciones adicionales

- Mostrar siempre las tres secciones, incluso cuando no existan logs.
- Presentar los ítems en el mismo orden en que aparecen en el documento, utilizando su numeración original.
- Identificar cada mensaje de log mediante su código correspondiente.
- No incorporar los logs dentro del JSON.
- Mantener el separador `==================================================` entre los logs y el JSON.
- Generar un único objeto JSON que contenga el NIC, el plazo de ejecución y todos los ítems extraídos.
- No añadir explicaciones, conclusiones ni comentarios fuera de la estructura establecida.

## 6. Formato JSON a usar

El siguiente JSON representa una plantilla estructural. Los objetos incluidos dentro de las listas son ejemplos de su composición y no deben reproducirse automáticamente. Las listas contendrán únicamente los elementos identificados en el TDR, respetando las reglas de formato.

```json
{
  "nic": null,
  "plazo_ejecucion": {
    "valor": null,
    "unidad": null,
    "tipo": null
  },
  "items": [
    {
      "numero_item": null,
      "nombre": null,
      "cantidad": null,
      "unidad_medida": null,
      "especificaciones_tecnicas": {
        "grupos": [
          {
            "grupo": null,
            "requisitos": []
          }
        ],
        "accesorios_obligatorios": [
          {
            "nombre": null,
            "cantidad": {
              "valor": null,
              "tipo": null
            },
            "requisitos": []
          }
        ]
      }
    }
  ]
}
```

---


## 7. Enriquecimiento del nombre del ítem para búsqueda

Después de extraer toda la información del ítem y completar sus especificaciones técnicas, revisa el campo `nombre`.

Si el nombre original es demasiado general, ambiguo o poco útil para realizar una búsqueda web precisa, complétalo únicamente con los requisitos técnicos más representativos y discriminantes del producto.

El nombre resultante debe:

- Identificar claramente el tipo de producto.
- Reducir ambigüedades con otros productos o significados.
- Incorporar solo características que ayuden significativamente a encontrar el producto correcto.
- Priorizar características como capacidad, potencia, tamaño, categoría, voltaje, tecnología, tipo, estándar u otras propiedades esenciales, según corresponda al producto.
- Utilizar únicamente información explícitamente indicada en el documento.
- No inventar características.
- No incluir todas las especificaciones técnicas.
- No incluir requisitos secundarios, accesorios, garantía, certificaciones u otras características que hagan la búsqueda innecesariamente restrictiva.
- Mantener el nombre breve y adecuado para utilizarlo directamente como consulta en un buscador.

**Ejemplo:**

Nombre original:  
`UPS` Capacidad mínima: 750 VA / 360 W Voltaje: 110 V / 120 V Topología: Line-Interactive o Standby Mínimo 4 a 6 tomas Batería VRLA

Especificaciones extraídas:

- Capacidad mínima: 750 VA / 360 W
- Voltaje: 110 V / 120 V
- Topología: Line-Interactive o Standby
- Mínimo 4 a 6 tomas
- Batería VRLA

Nombre enriquecido:  
`UPS respaldo eléctrico 750VA 360W 120V`

No modificar el resto de las especificaciones técnicas para realizar este enriquecimiento. El campo `nombre` funciona como una descripción breve optimizada para la búsqueda del producto.

**Contactos:** Tlf: +593 963262851 · @VoltixEcuador · voltixecuador@gmail.com