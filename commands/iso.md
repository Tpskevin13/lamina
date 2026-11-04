---
description: 'Foto a PDF con el diseño a medida · perspectiva isométrica (0°, 30°, 90° y 150°), con círculos como elipses giradas'
argument-hint: "[ruta de la foto] [papel: a4|carta|oficio|297x210]"
---

Pasá a PDF la foto que indica el usuario siguiendo la skill `foto-a-pdf` (cargala con la herramienta Skill: `foto-a-pdf:foto-a-pdf`; si no está como plugin, `foto-a-pdf`).

Modo de ángulos elegido: **iso** (perspectiva isométrica (0°, 30°, 90° y 150°), con círculos como elipses giradas). En `layout.json` poné en la raíz `"angulos": "iso"`.

Anotá cada arista de vértice a vértice. Círculos de las caras: `elipse` de proporción 1 : 0,58 (arriba `giro: 0`, cara derecha `giro: 60`, izquierda `giro: 120`); arcos con `radio_y` = 0,58 × `radio` y el mismo `giro`; rótulos sobre las caras con `giro: 30` o `150`.

Foto y papel: $ARGUMENTS

Si no vino ninguna ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es antes de seguir.
