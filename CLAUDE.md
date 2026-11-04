# lamina

- **Objetivo**: plugin de Claude Code que pasa la foto de un documento o lámina a PDF con el diseño a medida y texto real, y a DXF/DWG.
- **Stack**: Python 3.10+ (Pillow, numpy, ReportLab, pypdfium2, ezdxf; AutoCAD u ODA File Converter para el DWG). Se distribuye como plugin de Claude Code (`.claude-plugin/`).
- **Estructura**: `skills/pdf/SKILL.md`, `commands/` (modos de ángulos, dxf, dwg) (instrucciones para Claude) y `scripts/` (preparar → layout.json escrito por Claude → construir, que encaja, rectifica los ángulos, dibuja y compara → cad.py, DXF/DWG).
- **Probar**: `python ejemplos/generar_prueba.py CARPETA` crea una foto sintética; después seguir los pasos de SKILL.md. `ejemplos/presupuesto/` tiene un caso resuelto.
- **Validar el plugin**: `claude plugin validate .`
