"""Genera un presupuesto ficticio y lo convierte en una 'foto de celular' para probar la skill.

  python ejemplos/generar_prueba.py CARPETA

Deja en CARPETA original.pdf (el documento) y foto_presupuesto.jpg (la foto simulada).
Usa fuentes de Windows (Calibri, Ink Free).
"""
import sys
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "foto-a-pdf" / "scripts"))
from preparar import coeficientes  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
F = "C:/Windows/Fonts/"
for n, f in (("Cal", "calibri.ttf"), ("CalB", "calibrib.ttf"), ("Ink", "Inkfree.ttf")):
    pdfmetrics.registerFont(TTFont(n, F + f))

pdf = out / "original.pdf"
c = Canvas(str(pdf), pagesize=A4)
W, H = A4
gris, verde = HexColor("#555555"), HexColor("#2e6b3a")

# logo: arbolito
c.setFillColor(HexColor("#6b4a2b")); c.rect(60, 760, 8, 16, stroke=0, fill=1)
c.setFillColor(verde); c.circle(64, 790, 20, stroke=0, fill=1)
c.setFillColor(HexColor("#4f9a5c")); c.circle(56, 796, 9, stroke=0, fill=1)

c.setFillColor(HexColor("#000000"))
c.setFont("CalB", 20); c.drawString(100, 792, "TALLER LOS ÁLAMOS")
c.setFillColor(gris)
c.setFont("Cal", 10); c.drawString(100, 777, "Muebles a medida · Restauración · Diseño")
c.setFont("Cal", 9); c.drawString(100, 764, "Belgrano 1450, Rosario · Tel. 341 555-0192")
c.setFillColor(HexColor("#000000"))
c.setFont("CalB", 15); c.drawRightString(555, 792, "PRESUPUESTO")
c.setFont("Cal", 11); c.drawRightString(555, 777, "N° 0158")
c.setFont("Cal", 10); c.drawRightString(555, 764, "Fecha: 03/11/2026")
c.setStrokeColor(verde); c.setLineWidth(1.2); c.line(40, 748, 555, 748)

for y, et, val in ((728, "Cliente:", "María Fernández"), (714, "Dirección:", "Av. Pellegrini 2210, Rosario"),
                   (700, "Teléfono:", "341 555-0147")):
    c.setFont("CalB", 10.5); c.drawString(40, y, et)
    c.setFont("Cal", 10.5); c.drawString(95, y, val)

xs = [40, 90, 380, 470, 555]
filas = [("Cant.", "Descripción", "Precio unit.", "Subtotal"),
         ("1", "Mesa de roble macizo 1,80 x 0,90 m", "$ 285.000", "$ 285.000"),
         ("6", "Sillas tapizadas en pana gris", "$ 32.000", "$ 192.000"),
         ("1", "Lustre y protección UV", "$ 35.000", "$ 35.000"),
         ("1", "Flete y armado en domicilio", "$ 18.000", "$ 18.000")]
top, alto = 680, 18
c.setFillColor(HexColor("#e8efe9")); c.rect(40, top - alto, 515, alto, stroke=0, fill=1)
c.setStrokeColor(HexColor("#000000")); c.setLineWidth(0.8)
for i in range(len(filas) + 1):
    c.line(40, top - i * alto, 555, top - i * alto)
for x in xs:
    c.line(x, top, x, top - len(filas) * alto)
c.setFillColor(HexColor("#000000"))
for i, fila in enumerate(filas):
    yb = top - i * alto - 12.5
    c.setFont("CalB" if i == 0 else "Cal", 10)
    c.drawCentredString((xs[0] + xs[1]) / 2, yb, fila[0])
    c.drawString(xs[1] + 5, yb, fila[1])
    c.drawRightString(xs[3] - 5, yb, fila[2])
    c.drawRightString(xs[4] - 5, yb, fila[3])

for y, et, val, f, t in ((572, "Subtotal", "$ 530.000", "Cal", 10), (558, "IVA 21 %", "$ 111.300", "Cal", 10),
                         (540, "TOTAL", "$ 641.300", "CalB", 12)):
    c.setFont(f, t); c.drawRightString(465, y, et); c.drawRightString(555, y, val)
c.setLineWidth(0.8); c.line(380, 551, 555, 551)

c.setFont("CalB", 10.5); c.drawString(40, 508, "Forma de pago:")
for x, txt, marcada in ((125, "Efectivo", True), (205, "Transferencia", False), (310, "Tarjeta", False)):
    c.setLineWidth(0.8); c.rect(x, 507, 9, 9, stroke=1, fill=0)
    if marcada:
        c.setLineWidth(1.2); c.line(x + 2, 509, x + 7, 514); c.line(x + 7, 509, x + 2, 514)
    c.setFont("Cal", 10.5); c.drawString(x + 14, 508, txt)

c.setFont("CalB", 10.5); c.drawString(40, 478, "Condiciones:")
parrafo = ["La seña del 50 % confirma el pedido y congela los precios. El saldo se abona contra",
           "entrega. Plazo de fabricación: 25 días hábiles desde la seña. Las medidas finales se",
           "verifican en el domicilio antes de cortar la madera. Validez del presupuesto: 15 días."]
for k, linea in enumerate(parrafo):
    palabras = linea.split()
    anchos = [pdfmetrics.stringWidth(p, "Cal", 9.5) for p in palabras]
    hueco = (515 - sum(anchos)) / (len(palabras) - 1)
    x = 40
    for p, a in zip(palabras, anchos):
        c.setFont("Cal", 9.5); c.drawString(x, 464 - k * 12, p); x += a + hueco

c.setFillColor(HexColor("#1f3f9a")); c.setFont("Ink", 13)
c.drawString(60, 405, "Entregar antes del 20/11 - llamar antes")

# sello girado
c.saveState(); c.translate(120, 345); c.rotate(12)
c.setStrokeColor(HexColor("#c0262d")); c.setFillColor(HexColor("#c0262d")); c.setLineWidth(2)
c.roundRect(0, 0, 120, 34, 4, stroke=1, fill=0)
c.setFont("CalB", 18); c.drawCentredString(60, 11, "APROBADO")
c.restoreState()

# firma
c.setStrokeColor(HexColor("#000000")); c.setLineWidth(0.8); c.line(360, 330, 540, 330)
c.setStrokeColor(HexColor("#1d2b6b")); c.setLineWidth(1.4)
p = c.beginPath(); p.moveTo(380, 340)
for x, y in ((395, 368), (402, 338), (418, 362), (425, 336), (445, 360), (452, 341), (470, 352),
             (490, 344), (520, 356)):
    p.lineTo(x, y)
c.drawPath(p, stroke=1, fill=0)
c.setFillColor(HexColor("#000000")); c.setFont("Cal", 9); c.drawCentredString(450, 318, "Firma y aclaración")

c.setFillColor(gris); c.setFont("Cal", 7.5)
c.drawCentredString(W / 2, 40, "Taller Los Álamos · tallerlosalamos@ejemplo.com · Página 1 de 1")
c.save()

# PDF -> imagen a 150 ppp
doc = pdfium.PdfDocument(str(pdf))
hoja = doc[0].render(scale=150 / 72).to_pil().convert("RGBA")
doc.close()
pw, ph = hoja.size

# "foto": fondo de madera, perspectiva, luz despareja, ruido y JPEG
FW, FH = 2200, 2900
rng = np.random.default_rng(7)
vetas = np.cumsum(rng.normal(0, 1, (FH, 1)), axis=0) % 40 / 40
madera = np.stack([120 + 30 * vetas, 82 + 20 * vetas, 52 + 12 * vetas], axis=2) * np.ones((1, FW, 1))
fondo = Image.fromarray(np.clip(madera + rng.normal(0, 6, (FH, FW, 3)), 0, 255).astype(np.uint8)).convert("RGBA")
def camara(ax, ay, az, f=2300, t=(8, 40, 330)):
    """Esquinas de una hoja A4 vista por una cámara real (centro óptico en el centro de la foto)."""
    cx, sx, cy, sy, cz, sz = np.cos(ax), np.sin(ax), np.cos(ay), np.sin(ay), np.cos(az), np.sin(az)
    R = (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
         @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))
    pts = []
    for X, Y in ((-105, -148.5), (105, -148.5), (105, 148.5), (-105, 148.5)):
        P = R @ np.array([X, Y, 0.0]) + np.array(t)
        pts.append((f * P[0] / P[2] + FW / 2, f * P[1] / P[2] + FH / 2))
    return pts


esq = camara(0.30, -0.10, 0.035)
print("esquinas reales (px):", [tuple(round(v) for v in p) for p in esq])
pagina = hoja.transform((FW, FH), Image.Transform.PERSPECTIVE,
                        coeficientes(esq, [(0, 0), (pw, 0), (pw, ph), (0, ph)]),
                        Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
foto = Image.alpha_composite(fondo, pagina).convert("RGB")
yy, xx = np.mgrid[0:FH, 0:FW]
luz = 1.0 - 0.22 * (xx / FW + yy / FH) / 2 - 0.12 * np.exp(-(((xx - 1500) / 500) ** 2 + ((yy - 2300) / 380) ** 2))
a = np.asarray(foto, dtype=np.float32) * luz[..., None] * np.array([1.0, 0.97, 0.9])
foto = Image.fromarray(np.clip(a + rng.normal(0, 4, a.shape), 0, 255).astype(np.uint8))
foto = foto.filter(ImageFilter.GaussianBlur(1.1))
exif = Image.Exif()
exif[0x0112] = 6  # el celular la guardó acostada
foto.rotate(90, expand=True).save(out / "foto_presupuesto.jpg", quality=82, exif=exif)
print(out / "foto_presupuesto.jpg")
