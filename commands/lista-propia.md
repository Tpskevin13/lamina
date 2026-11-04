---
description: 'Foto a PDF con el diseño a medida, líneas enderezadas a los ángulos que elijas'
argument-hint: "[ruta de la foto] [ángulos, ej. 0 60 90 120] [papel]"
---

Pasá a PDF la foto que indica el usuario siguiendo la skill `pdf` del plugin lamina (cargala con la herramienta Skill: `lamina:pdf`; si se copió a mano, `pdf`).

Modo de ángulos: **lista propia**. De los argumentos, los números son los ángulos permitidos en grados (0 = horizontal, 90 = vertical, antihorario, entre 0 y 180); poné en la raíz de `layout.json` `"angulos": [esos números]`. Lo demás es la ruta de la foto y, si está, el papel.

Argumentos: $ARGUMENTS

Si no vino ningún ángulo, preguntale al usuario cuáles quiere antes de armar el PDF (ejemplo: `0 60 90 120`). Si no vino ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es.
