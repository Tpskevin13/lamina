---
description: 'Foto a PDF con el diseño a medida · solo horizontales y verticales (0° y 90°): planos, formularios, tablas'
argument-hint: "[ruta de la foto] [papel: a4|carta|oficio|297x210]"
---

Pasá a PDF la foto que indica el usuario siguiendo la skill `pdf` del plugin lamina (cargala con la herramienta Skill: `lamina:pdf`; si se copió a mano, `pdf`).

Modo de ángulos elegido: **orto** (solo horizontales y verticales (0° y 90°): planos, formularios, tablas). En `layout.json` poné en la raíz `"angulos": "orto"`.

Foto y papel: $ARGUMENTS

Si no vino ninguna ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es antes de seguir.
