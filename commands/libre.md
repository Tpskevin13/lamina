---
description: 'Foto a PDF con el diseño a medida · sin enderezar líneas: gráficos, croquis, dibujos a mano alzada'
argument-hint: "[ruta de la foto] [papel: a4|carta|oficio|297x210]"
---

Pasá a PDF la foto que indica el usuario siguiendo la skill `pdf` del plugin lamina (cargala con la herramienta Skill: `lamina:pdf`; si se copió a mano, `pdf`).

Modo de ángulos elegido: **libre** (sin enderezar líneas: gráficos, croquis, dibujos a mano alzada). En `layout.json` poné en la raíz `"angulos": "libre"`. Igual se corrige la inclinación general de la hoja al preparar, salvo que el usuario pida lo contrario (`--sin-enderezar`).

Foto y papel: $ARGUMENTS

Si no vino ninguna ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es antes de seguir.
