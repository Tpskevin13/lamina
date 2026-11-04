---
name: foto-a-pdf
description: 'Convierte una foto de un documento (factura, presupuesto, formulario, carta, apunte, recibo, cartel, tabla, plano o lámina de dibujo técnico, página impresa o escrita a mano) en un PDF que respeta el diseño a medida: misma posición y tamaño de cada renglón, tablas, líneas, casillas, logos y firmas, con texto real seleccionable. Analiza la foto de arriba a abajo, línea por línea, y verifica el resultado superponiéndolo con la foto. Usala siempre que el usuario pase una foto o captura y pida pasarla a PDF, digitalizarla, "escanearla", rehacerla, transcribirla manteniendo el formato o recrear el documento, aunque no diga "layout" ni "PDF".'
argument-hint: "[ruta de la foto] [papel: a4|carta|oficio]"
---

# Foto a PDF con el diseño a medida

El objetivo es un PDF que, puesto encima de la foto, coincida: cada renglón en su lugar, del mismo tamaño, con la misma tipografía aproximada, y con el texto real (se puede seleccionar, copiar y buscar). No es una foto pegada en un PDF.

Vos (Claude) hacés la parte de entender la imagen: leer cada renglón y decir qué es y dónde está. Los scripts hacen lo que exige precisión: enderezar la foto, medir la tinta, dibujar el PDF y compararlo con la foto.

Los scripts están en `scripts/` dentro de esta skill. En los comandos, `S` es esa carpeta (ruta absoluta).

## 0. Dependencias

```bash
python -c "import PIL, numpy, reportlab, pypdfium2"
```

Si falla: `python -m pip install pillow numpy reportlab pypdfium2` (para fotos `.heic` de iPhone, además `pillow-heif`). Avisale al usuario antes de instalar.

## 1. Conseguir la foto como archivo

Si el usuario dio una ruta, usala. Si pegó la imagen en el chat, el archivo no queda en disco: buscá las últimas imágenes del equipo y confirmá cuál es (decí nombre y fecha):

```bash
python S/preparar.py buscar
```

Si no aparece, pedile que la guarde y te pase la ruta.

## 2. Enderezar y preparar

```bash
python S/preparar.py ver FOTO
```

Genera `vista.png` con una grilla y las esquinas de la hoja sugeridas en rojo, y muestra el `--esquinas "..."` correspondiente. Mirá `vista.png`:

- Si las esquinas rojas caen en las puntas de la hoja, usá `--esquinas auto`.
- Si no, leé las coordenadas correctas en la grilla y pasalas a mano en el orden arriba-izq, arriba-der, abajo-der, abajo-izq.
- Si la foto ya es una captura o un escaneo recto (no hay fondo alrededor de la hoja), no pases `--esquinas`.

```bash
python S/preparar.py preparar FOTO --esquinas auto --papel a4 --limpiar
```

- `--papel`: `a4` (lo más común en Argentina y Europa), `carta`, `oficio`, `legal`, `a5`, `auto` o `AxB` en mm. Si no sabés, `auto` elige el más parecido a la proporción medida (corrige la perspectiva). Si dice "a medida", la hoja no es estándar (un ticket, por ejemplo) y está bien.
- `--limpiar`: empareja la luz y deja el papel blanco. Usalo con fotos de papel; no con capturas de pantalla.
- `--esquinas`: `auto` o las cuatro esquinas entre comillas. Sin esta opción, la imagen se usa tal cual.
- `--rotar 90|180|270`: si en `vista.png` la hoja está de costado o al revés, girala esos grados en sentido horario (corré `ver` de nuevo con el mismo `--rotar` para confirmar).
- Enderezado fino: `preparar` mide si el contenido quedó torcido (hasta 5°) y lo deja a 0°/90°; lo informa con "Enderecé el contenido …". `--sin-enderezar` lo apaga (por ejemplo, si el documento tiene a propósito todo inclinado).

El comando crea una carpeta de trabajo (la muestra al final) con:

- `base.png`: la hoja enderezada. De ahí salen los recortes de imágenes.
- `grilla.png`: la página completa con reglas en u.
- `franja_01.png`, `franja_02.png`…: la página cortada en franjas horizontales ampliadas, con reglas. Cada franja repite un poco de la anterior.
- `info.json`: papel, tamaño en u, franjas y ruta del PDF de salida.

### Coordenadas

Todo se mide en **u**: el ancho de la página es 1000 u, el origen está arriba a la izquierda y la y crece hacia abajo. El alto en u depende del papel (A4 ≈ 1414). Las reglas de las imágenes están en u.

## 3. Analizar la foto de arriba a abajo

1. Mirá `grilla.png` para entender la estructura: encabezado, bloques, tablas, columnas, pie.
2. Recorré **todas** las franjas en orden, de la primera a la última, sin saltear ninguna. En cada una, anotá cada cosa visible de arriba a abajo y de izquierda a derecha: cada renglón de texto, línea, recuadro, casilla, tabla, logo, sello, firma.
3. Si algo se ve chico o dudoso, ampliá la zona (en u):

   ```bash
   python S/preparar.py zoom TRABAJO x0 y0 x1 y1
   ```

4. Escribí `TRABAJO/layout.json` directamente con la herramienta de escritura (no hay plantilla que leer).

Reglas de transcripción:

- **Literal**: copiá el texto tal cual, con su ortografía, mayúsculas, acentos y signos. No corrijas ni completes.
- Lo que no se lee: `[?]` en la letra o palabra dudosa; `[ilegible]` si es un fragmento entero.
- **Un elemento `texto` por renglón visual.** Un párrafo de 5 renglones son 5 textos. Así cada renglón queda en su lugar exacto, aunque el párrafo esté justificado.
- Texto en columnas o separado por espacios grandes (por ejemplo "Total" a la izquierda y "$ 1.500" a la derecha): un texto por cada bloque.
- No inventes contenido que no está en la foto.

### La caja de un texto

`"caja": [x0, y0, x1, y1]`:

- `x0`, `x1`: donde empieza la primera letra y termina la última.
- `y0`: el borde de arriba de las mayúsculas y letras altas (b, d, l), **sin contar acentos**.
- `y1`: la **línea base**, donde se apoyan las letras; no cuentes lo que baja (g, p, q, y).

El tamaño de letra sale de esa caja, así que no hace falta poner `tam`. No hace falta que sea exacta: el encaje (abajo) la ajusta a la tinta real. Sí tiene que estar sobre el renglón correcto (error de hasta medio renglón).

## 4. layout.json

```json
{
  "pagina": {"ancho_mm": 210, "alto_mm": 297, "fondo": "#ffffff"},
  "defecto": {"fuente": "sans", "color": "#000000"},
  "elementos": [
    {"tipo": "imagen", "caja": [60, 40, 150, 130]},
    {"tipo": "texto", "caja": [170, 60, 460, 84], "texto": "EMPRESA S.A.", "negrita": true},
    {"tipo": "linea", "de": [60, 150], "a": [940, 150], "grosor": 2, "color": "#1f4e79"},
    {"tipo": "casilla", "caja": [60, 600, 74, 614], "marca": "x"},
    {"tipo": "tabla", "columnas": [60, 150, 640, 940], "filas": [270, 300, 330],
     "celdas": [["Cant.", "Descripción", "Importe"], ["2", "Sillas", "$ 40.000"]],
     "negrita_filas": [0], "relleno_filas": {"0": "#e7eef7"}, "alinear": ["centro", "izq", "der"]}
  ]
}
```

`pagina` es opcional (por defecto, lo de `info.json`). El orden de `elementos` es el orden de dibujo (lo de abajo tapa lo de arriba: poné los rellenos antes que el texto) y el orden de lectura del PDF: seguí el orden de la foto, de arriba a abajo.

| tipo | campos | notas |
|---|---|---|
| `texto` | `caja`, `texto`; opcionales `fuente`, `negrita`, `cursiva`, `color`, `tam`, `subrayado`, `tachado`, `ajuste`, `alinear`, `giro`, `encajar` | Un renglón. Con `ajuste: "no"` no se estira para llenar la caja, solo se achica si no entra, y se alinea con `alinear` (`izq`, `centro`, `der`). `giro: 90` = texto vertical que se lee de abajo hacia arriba (cotas de planos); `270`, de arriba hacia abajo: la caja es la que ocupa en la hoja. Cualquier otro giro (30, 150, 180…, antihorario): `centro [x, y]`, `largo` y `alto` del renglón sin girar (rótulos de isométrica). El texto girado no se encaja. |
| `linea` | `de [x, y]`, `a [x, y]`; `grosor` (u, por defecto 1), `color`, `trazo` (`solido`, `guiones`, `puntos`), `flechas` (`inicio`, `fin`, `ambas`), `flecha` (largo de la punta en u, por defecto 4) | Reglas, separadores, renglones para escribir, cotas y ejes de planos. |
| `arco` | `centro [x, y]`, `radio`, `desde`, `hasta` (grados: 0 = derecha, 90 = arriba, antihorario); `radio_y`, `giro`, `grosor`, `color`, `trazo` | Esquinas redondeadas, arcos de ángulos. Con `radio_y` es un arco de elipse, girado `giro` grados (arcos en isométrica). |
| `rect` | `caja`; `borde` (color o `null`), `relleno`, `grosor`, `radio` | Recuadros, fondos de color, bandas. |
| `elipse` | `caja`; `borde`, `relleno`, `grosor`, `giro` | Círculos y óvalos. Con `giro`, la caja es la elipse sin girar y gira sobre su centro (círculos en isométrica, ver abajo). |
| `casilla` | `caja`; `marca` (`x`, `v`, `relleno` o nada), `grosor`, `color` | Checkbox. Si está tildada, `marca`. |
| `tabla` | `columnas` (x de cada borde), `filas` (y de cada borde), `celdas` (lista de filas); `bordes` (`todos`, `horizontales`, `externos`, `ninguno`), `tam`, `fuente`, `alinear` (uno o lista por columna), `negrita_filas`, `relleno_filas`, `color`, `color_borde`, `grosor` | Para tablas con grilla regular. `"\n"` en una celda = varios renglones. Si la tabla es irregular, armala con `linea` y `texto`. |
| `imagen` | `caja`; `archivo` (opcional), `transparente` (por defecto `true`) | Sin `archivo`, recorta esa zona de la foto enderezada: usalo para logos, sellos, firmas, dibujos, fotos, códigos QR y de barras. `transparente` borra el papel del recorte para que no quede un parche gris. |

Colores: `"#rrggbb"`. Para texto gris, azul o rojo, poné el color que se ve; en textos negros no hace falta.

### Dibujos técnicos: líneas rectas y ángulos

En un dibujo, las líneas que en la foto salen casi horizontales, verticales o a 45° se dejan **exactas**, aunque la foto (o el dibujo a mano) las tenga un poco torcidas. Al armar, cada `linea` se lleva al ángulo permitido más cercano si está a menos de `tolerancia_angulo` grados (por defecto 4). Después se cierran las esquinas: las puntas que casi se tocan pasan a ser el mismo vértice, y una punta pegada a otra línea queda apoyada en ella. Los segmentos de una cota en cadena quedan alineados.

Elegí los ángulos con la clave `angulos` en la raíz de `layout.json`:

| `angulos` | ángulos | para |
|---|---|---|
| `"orto45"` (por defecto) | 0, 45, 90, 135 | planos, formularios, chaflanes |
| `"orto"` | 0, 90 | solo horizontales y verticales |
| `"iso"` | 0, 30, 90, 150 | perspectiva isométrica |
| `"caballera"` | 0, 45, 90, 135 | perspectiva caballera |
| `"dimetrica"` | 0, 7, 42, 90, 138, 173 | dimétrica normalizada |
| `[0, 60, 90, 120]` | los que pongas | otros sistemas |
| `"libre"` | — | no tocar los ángulos (gráficos, croquis) |

Si el usuario llamó a la skill desde un comando de modo (`/foto-a-pdf:iso`, `:orto`, `:libre`…), usá ese modo. Si no, elegilo vos según el dibujo, o preguntale si no está claro.

`"rectificar": false` en una línea la deja como está (una inclinada a propósito que cae cerca de un ángulo permitido).

Isométrica: anotá las aristas como `linea` (cada arista de una pieza, de vértice a vértice). Los círculos de las caras salen como elipses de proporción 1 : 0,58: en la cara de arriba, `elipse` con el eje largo horizontal (`giro: 0`); en la cara lateral derecha, `giro: 60`, y en la izquierda, `giro: 120` (el eje largo queda perpendicular a la arista que sale de esa cara). Los arcos, con `arco` y `radio_y` igual a 0,58 × `radio` y el mismo `giro`. Los rótulos sobre una cara llevan `giro: 30` o `giro: 150` (o -30).

### Fuentes

Elegí la más parecida a la de la foto: `sans` (Arial/Helvetica), `serif` (Times), `mono` (Courier, máquina de escribir, tickets), `angosta` (Arial Narrow), `calibri`, `segoe`, `verdana`, `georgia`, `tahoma`, `trebuchet`, `comic`, `manuscrita` (escrito a mano), o la ruta a un `.ttf`. Si falta en el equipo, se usa la más parecida. Las letras que la fuente no tiene (✓, →, ★) salen de una fuente de símbolos.

Para texto escrito a mano: si importa que se vea igual (una firma, una nota corta), usá `imagen`; si importa que se pueda leer y buscar, `texto` con `manuscrita`. Elegí uno de los dos, no los dos encimados.

### Encaje

Antes de dibujar, `construir.py` ajusta cada elemento a la tinta real de la foto:

- `texto`: la caja se pega a la tinta del renglón y se mide dónde empieza cada palabra, así el PDF las pone en el mismo lugar (sirve para texto justificado y tabulado).
- `linea`, `rect` y `casilla` con borde, `tabla`: se acomodan a las líneas medidas.

Si un elemento queda mal porque el encaje lo pegó a otra cosa, poné `"encajar": false` en ese elemento y corregí la caja a mano. `--sin-encajar` lo apaga para todo.

## 5. Armar y comparar

```bash
python S/construir.py TRABAJO
```

Arma el PDF (al lado de la foto, sin pisar uno existente) y lo compara con la foto:

- **cobertura**: cuánta tinta de la foto aparece en el PDF. Baja = falta algo.
- **precisión**: cuánta tinta del PDF está en la foto. Baja = algo sobra o está corrido o es más grande.
- Por franja, con `<- revisar` si alguna baja del 85 %.
- Cajas `x0 y0 x1 y1` de lo que más falta (rojo) y más sobra (celeste).
- Avisos: elementos con error, texto estirado más de 15 % (la caja, la fuente o la negrita no coinciden), elementos que el encaje movió mucho.

En la carpeta de trabajo quedan `comparacion.png` y `comp_franja_XX.png`: la foto y el PDF superpuestos. Oscuro = coincide; **rojo** = está en la foto y falta en el PDF; **celeste** = está en el PDF y no en la foto. Un par rojo y celeste juntos = algo corrido.

Repasá las franjas marcadas y las zonas listadas, corregí `layout.json` y volvé a correr. Hacé 2 o 3 vueltas; no persigas el 100 %: fotos borrosas o con sombras dejan diferencias que no son errores. Un 95 % o más en las dos medidas es muy bueno.

Más de una página: preparar cada foto por separado (cada una tiene su carpeta) y después `python S/construir.py TRABAJO1 TRABAJO2 ... --pdf SALIDA.pdf`.

## 6. Entregar

Decí dónde quedó el PDF, la cobertura y precisión finales, y listá lo que transcribiste con `[?]` o `[ilegible]` para que el usuario lo revise. Si lo pidió, ofrecé abrirlo.

## Límites

- El texto es una transcripción: revisá números, nombres y montos, que son lo más importante y lo más fácil de leer mal en una foto borrosa.
- La tipografía es la más parecida disponible, no la original.
- Fotos muy oblicuas, arrugadas o con poca luz dan peores resultados. Si la hoja está curvada (un libro abierto), el enderezado es solo aproximado.
