---
description: 'Foto a DXF para AutoCAD (y a PDF): mismo análisis y diseño a medida, en capas y en mm'
argument-hint: "[ruta de la foto] [modo de ángulos: orto|orto45|iso|caballera|dimetrica|libre|lista] [papel]"
---

Pasá la foto que indica el usuario a **DXF**, con los mismos pasos que para el PDF: seguí la skill `pdf` del plugin lamina (cargala con la herramienta Skill: `lamina:pdf`; si se copió a mano, `pdf`) completa, hasta tener el PDF armado y comparado con la foto (pasos 1 a 5). Después hacé el paso de CAD de la skill:

```bash
python S/cad.py TRABAJO 
```

Argumentos: $ARGUMENTS

- Si entre los argumentos hay un modo de ángulos (`orto`, `orto45`, `iso`, `caballera`, `dimetrica`, `libre`) o una lista de ángulos, usalo en `"angulos"` de `layout.json`. Si no, elegilo según el dibujo (`orto45` en planos, `iso` en isométrica).
- Lo demás es la ruta de la foto y, si está, el papel. Si no vino ruta, buscá la foto como dice la skill (paso 1) y confirmá cuál es.
- Al entregar, decí dónde quedaron el PDF y el DXF, y si hay imágenes, que la carpeta `_imagenes` tiene que ir junto al DXF.
