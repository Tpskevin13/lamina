---
description: 'Foto a PDF con el diseño a medida · perspectiva dimétrica normalizada (0°, 7°, 42°, 90°, 138° y 173°)'
argument-hint: "[ruta de la foto] [papel: a4|carta|oficio|297x210]"
---

Pasá a PDF la foto que indica el usuario siguiendo la skill `foto-a-pdf` (cargala con la herramienta Skill: `foto-a-pdf:foto-a-pdf`; si no está como plugin, `foto-a-pdf`).

Modo de ángulos elegido: **dimetrica** (perspectiva dimétrica normalizada (0°, 7°, 42°, 90°, 138° y 173°)). En `layout.json` poné en la raíz `"angulos": "dimetrica"`.

Foto y papel: $ARGUMENTS

Si no vino ninguna ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es antes de seguir.
