# foto-a-pdf

- **Objetivo**: skill de Claude Code que pasa la foto de un documento a un PDF con el diseño a medida y texto real.
- **Stack**: Python 3.10+ (Pillow, numpy, ReportLab, pypdfium2). Se distribuye como plugin de Claude Code (`.claude-plugin/`).
- **Estructura**: `skills/foto-a-pdf/SKILL.md` (instrucciones para Claude) y `scripts/` (preparar → layout.json escrito por Claude → construir, que encaja, rectifica los ángulos, dibuja y compara).
- **Probar**: `python ejemplos/generar_prueba.py CARPETA` crea una foto sintética; después seguir los pasos de SKILL.md. `ejemplos/presupuesto/` tiene un caso resuelto.
- **Validar el plugin**: `claude plugin validate .`
