"""Arma el PDF desde layout.json (una carpeta de trabajo por página) y lo compara con la foto.

  python construir.py TRABAJO [TRABAJO2 ...] [--pdf salida.pdf] [--sin-encajar] [--sin-comparar]
"""
import argparse
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont
from reportlab.lib.colors import toColor
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from comun import ANCHO_U, abrir_imagen, leer_json, salida_utf8
from encajar import caja, encajar_todo
from rectificar import rectificar

CARPETAS_FUENTES = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "~")).expanduser() / "Microsoft" / "Windows" / "Fonts",
    Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
    Path("/Library/Fonts"), Path("/System/Library/Fonts"),
]
# familia -> juegos de archivos (normal, negrita, cursiva, negrita cursiva); se usa el primero que exista
FAMILIAS = {
    "sans": [("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
             ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf", "Arial Bold Italic.ttf"),
             ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf",
              "LiberationSans-BoldItalic.ttf"),
             ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf")],
    "serif": [("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
              ("Times New Roman.ttf", "Times New Roman Bold.ttf", "Times New Roman Italic.ttf",
               "Times New Roman Bold Italic.ttf"),
              ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf",
               "LiberationSerif-BoldItalic.ttf"),
              ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf")],
    "mono": [("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
             ("Courier New.ttf", "Courier New Bold.ttf", "Courier New Italic.ttf", "Courier New Bold Italic.ttf"),
             ("LiberationMono-Regular.ttf", "LiberationMono-Bold.ttf", "LiberationMono-Italic.ttf",
              "LiberationMono-BoldItalic.ttf"),
             ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf", "DejaVuSansMono-Oblique.ttf",
              "DejaVuSansMono-BoldOblique.ttf")],
    "angosta": [("ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF", "ARIALNBI.TTF"),
                ("LiberationSansNarrow-Regular.ttf", "LiberationSansNarrow-Bold.ttf",
                 "LiberationSansNarrow-Italic.ttf", "LiberationSansNarrow-BoldItalic.ttf")],
    "manuscrita": [("Inkfree.ttf",) * 4, ("segoepr.ttf", "segoeprb.ttf", "segoepr.ttf", "segoeprb.ttf")],
    "calibri": [("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
                ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf")],
    "segoe": [("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf")],
    "verdana": [("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf")],
    "georgia": [("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf")],
    "tahoma": [("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf")],
    "trebuchet": [("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf")],
    "comic": [("comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf")],
}
PARECIDA = {"georgia": "serif", "serif": "serif", "mono": "mono"}  # el resto cae en sans
# Si no hay ningún .ttf, las 14 fuentes estándar del PDF (solo alfabeto latino).
ESTANDAR = {"sans": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
            "serif": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
            "mono": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique")}
ALTURA_MAYUS = {"Helvetica": 0.718, "Times": 0.662, "Courier": 0.571}
SIMBOLOS = ("seguisym.ttf", "segoeui.ttf", "ARIALUNI.ttf", "DejaVuSans.ttf", "Apple Symbols.ttf")


def color(valor, defecto="#000000"):
    try:
        return toColor(valor or defecto)
    except ValueError:
        return toColor(defecto)


class Fuentes:
    """Busca y registra las fuentes; si a una le falta un carácter, lo toma de una de símbolos."""

    def __init__(self):
        self._indice = None
        self._elegidas = {}
        self._simbolos = None
        self._rutas = {}       # nombre registrado -> archivo .ttf
        self._medidoras = {}   # archivo -> fuente de Pillow para medir la tinta
        self.sin_glifo = set()

    def _archivo(self, nombre):
        if self._indice is None:
            self._indice = {}
            for d in CARPETAS_FUENTES:
                if d.is_dir():
                    for p in d.rglob("*"):
                        if p.suffix.lower() in (".ttf", ".ttc"):
                            self._indice.setdefault(p.name.lower(), p)
        return self._indice.get(nombre.lower())

    def _registrar(self, ruta):
        nombre = "F-" + Path(ruta).stem
        if nombre not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(nombre, str(ruta)))
        self._rutas[nombre] = Path(ruta)
        return nombre

    def alto(self, nombre, texto, cap):
        """Alto de la tinta sobre la línea base, en tamaños de letra, para este texto.

        En muchas fuentes (Calibri, por ejemplo) las letras altas como b, d, f o l superan a
        las mayúsculas; medir el texto real evita que salga más grande que en la foto.
        Los acentos y los puntos de la i no cuentan, igual que al medir la foto.
        """
        ruta = self._rutas.get(nombre)
        limpio = "".join(ch for ch in unicodedata.normalize("NFD", texto) if not unicodedata.combining(ch))
        limpio = limpio.replace("i", "ı").strip()
        if not ruta or not limpio:
            return cap
        try:
            if ruta not in self._medidoras:
                self._medidoras[ruta] = ImageFont.truetype(str(ruta), 200)
            arriba = -self._medidoras[ruta].getbbox(limpio, anchor="ls")[1] / 200
        except (OSError, ValueError):
            return cap
        return arriba if 0.3 < arriba < 1.5 else cap

    def elegir(self, familia, negrita=False, cursiva=False):
        """(nombre registrado, altura de mayúscula / tamaño de letra)."""
        familia = familia or "sans"
        clave = (familia, bool(negrita), bool(cursiva))
        if clave in self._elegidas:
            return self._elegidas[clave]
        i = bool(negrita) + 2 * bool(cursiva)
        parecida = PARECIDA.get(familia.lower(), "sans")
        if familia.lower().endswith((".ttf", ".ttc")):
            rutas = [Path(familia)]
        else:
            rutas = [self._archivo(j[i]) for j in FAMILIAS.get(familia.lower(), []) + FAMILIAS[parecida]]
        elegida = None
        for ruta in rutas:
            if not ruta or not ruta.exists():
                continue
            try:
                nombre = self._registrar(ruta)
            except Exception:  # fuente rota o que no permite incrustarse: probar la siguiente
                continue
            cap = getattr(pdfmetrics.getFont(nombre).face, "capHeight", 0) / 1000
            elegida = (nombre, cap if 0.45 < cap < 0.95 else 0.7)
            break
        if elegida is None:
            nombre = ESTANDAR[parecida][i]
            elegida = (nombre, ALTURA_MAYUS[nombre.split("-")[0]])
        self._elegidas[clave] = elegida
        return elegida

    @staticmethod
    def cubre(nombre, ch):
        mapa = getattr(pdfmetrics.getFont(nombre).face, "charToGlyph", None)
        if mapa is not None:
            return ord(ch) in mapa
        try:
            ch.encode("cp1252")  # fuentes estándar del PDF
            return True
        except UnicodeEncodeError:
            return False

    def _de_simbolos(self):
        if self._simbolos is None:
            self._simbolos = []
            for archivo in SIMBOLOS:
                ruta = self._archivo(archivo)
                if ruta:
                    try:
                        self._simbolos.append(self._registrar(ruta))
                    except Exception:
                        pass
        return self._simbolos

    def tramos(self, texto, nombre):
        """Parte el texto en tramos [texto, fuente] según qué fuente tiene cada carácter."""
        res = []
        for ch in texto:
            f = nombre
            if not ch.isspace() and not self.cubre(nombre, ch):
                f = next((s for s in self._de_simbolos() if self.cubre(s, ch)), None)
                if f is None:
                    self.sin_glifo.add(ch)
                    ch, f = "?", nombre
            if res and res[-1][1] == f:
                res[-1][0] += ch
            else:
                res.append([ch, f])
        return res


def ajustar_ancho(natural, objetivo, huecos, tam):
    """Cómo llevar un renglón al ancho que tiene en la foto: (escala de las letras, espacio extra).

    Si la diferencia es chica, es la tipografía: se estiran o comprimen las letras.
    Si es grande y hay espacios, es texto justificado: crecen o se achican los espacios.
    """
    r = objetivo / natural
    if abs(r - 1) <= 0.15 or not huecos:
        return min(max(r, 0.7), 1.4), 0.0
    sx = 1.0 if r > 1 else 0.9
    extra = min(max((objetivo - natural * sx) / huecos, -0.15 * tam), 1.5 * tam)
    if abs(objetivo - natural * sx - extra * huecos) > 0.5:  # con los espacios no alcanzó
        sx = min(max((objetivo - extra * huecos) / natural, 0.7), 1.4)
    return sx, extra


def sin_papel(im):
    """Vuelve transparente el papel de un recorte, para que firmas y sellos no tapen lo de abajo."""
    claro = np.asarray(im.convert("RGB"), dtype=np.float32).min(axis=2)  # el canal más oscuro: el amarillo cuenta
    papel = float(np.percentile(claro, 95))
    if papel < 120:  # recorte oscuro sin papel a la vista: queda como está
        return im
    rgba = im.convert("RGBA")
    rgba.putalpha(Image.fromarray(np.clip((papel - 12 - claro) / 45 * 255, 0, 255).astype(np.uint8)))
    return rgba


class Pagina:
    """Dibuja los elementos de una página: recibe coordenadas en u y las pasa a puntos del PDF."""

    def __init__(self, c, ancho_pt, alto_pt, base, fuentes, defecto):
        self.c, self.alto, self.base, self.fuentes = c, alto_pt, base, fuentes
        self.s = ancho_pt / ANCHO_U
        self.defecto = defecto
        self.avisos = []

    def x(self, u):
        return u * self.s

    def y(self, u):
        return self.alto - u * self.s

    def _grosor(self, el):
        return max(float(el.get("grosor", 1)), 0.1) * self.s

    def texto(self, el, n):
        giro = float(el.get("giro", 0)) % 360
        if not giro:
            return self._texto(el, n, *caja(el))
        if giro not in (90, 270):
            # Giro libre (rótulos de isométrica, texto al revés): `centro` en la hoja, `largo` y
            # `alto` del renglón sin girar. Sin `centro`, la caja es el renglón sin girar.
            if "centro" in el:
                cx, cy = (float(v) for v in el["centro"])
                largo, alto = float(el["largo"]), float(el["alto"])
            else:
                x0, y0, x1, y1 = caja(el)
                cx, cy, largo, alto = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
            self.c.saveState()
            self.c.translate(self.x(cx), self.y(cy))
            self.c.rotate(giro)
            base = self.alto / self.s + alto / 2
            self._texto(el, n, -largo / 2, base - alto, largo / 2, base)
            self.c.restoreState()
            return
        # Texto vertical (cotas de planos, lomos): se gira el lienzo y se dibuja como un renglón
        # horizontal de largo = alto de la caja. 90: se lee de abajo hacia arriba; 270: al revés.
        x0, y0, x1, y1 = caja(el)
        self.c.saveState()
        if giro == 90:
            self.c.translate(self.x(x1), self.y(y1))
        else:
            self.c.translate(self.x(x0), self.y(y0))
        self.c.rotate(giro if giro == 90 else -90)
        base = self.alto / self.s  # con el origen movido, esta "y" cae en la línea base
        self._texto(el, n, 0, base - (x1 - x0), y1 - y0, base)
        self.c.restoreState()

    def _texto(self, el, n, x0, y0, x1, y1):
        fuente, cap = self.fuentes.elegir(el.get("fuente") or self.defecto.get("fuente"),
                                          el.get("negrita"), el.get("cursiva"))
        txt = str(el.get("texto", ""))
        tam_u = float(el.get("tam") or max(y1 - y0, 1.0) / self.fuentes.alto(fuente, txt, cap))
        if not el.get("tam") and not el.get("_palabras"):
            # En texto chico y borroso la tinta se ve más alta de lo que es; si a este tamaño
            # no entra en el ancho medido, manda el ancho (es la medida más confiable).
            natural = sum(pdfmetrics.stringWidth(t, f, 1) for t, f in self.fuentes.tramos(txt.strip(), fuente))
            if natural > 0 and natural * tam_u > 1.15 * (x1 - x0):
                tam_u = (x1 - x0) / natural
        self._renglon(txt, fuente, tam_u, x0, x1, y1, el, n)

    def _renglon(self, texto, fuente, tam_u, x0, x1, base_u, op, n):
        """Dibuja un renglón de texto real entre x0 y x1 (en u), apoyado en la línea base."""
        c, tam = self.c, tam_u * self.s
        piezas = [(p, self.fuentes.tramos(p, fuente)) for p in re.findall(r"\S+|\s+", texto.strip())]
        anchos = [sum(pdfmetrics.stringWidth(t, f, tam) for t, f in tr) for _, tr in piezas]
        natural = sum(anchos)
        if natural <= 0:
            return
        es_palabra = [not p.isspace() for p, _ in piezas]
        medidas = op.get("_palabras")  # inicio y fin de cada palabra, medidos en la foto por el encaje
        modo = op.get("ajuste", "auto")
        objetivo = (x1 - x0) * self.s
        if modo != "no" and medidas and len(medidas) == sum(es_palabra):
            letras = sum(w for w, p in zip(anchos, es_palabra) if p)
            sx = min(max(sum(b - a for a, b in medidas) * self.s / letras, 0.7), 1.4)
            inicios = [self.x(a) for a, _ in medidas]
            # en fotos borrosas la tinta se ensancha: que ninguna palabra pise el espacio hasta la siguiente
            espacio = 0.6 * pdfmetrics.stringWidth(" ", piezas[0][1][0][1], tam)
            w_pal = [w for w, p in zip(anchos, es_palabra) if p]
            for w, a, b in zip(w_pal, inicios, inicios[1:]):
                if w > 0:
                    sx = min(sx, max((b - a - espacio) / w, 0.7))
        else:
            huecos = len(es_palabra) - sum(es_palabra)
            if modo == "no":
                sx, extra = (min(1.0, objetivo / natural) if objetivo > 0 else 1.0), 0.0
            else:
                sx, extra = ajustar_ancho(natural, objetivo, huecos, tam)
            x = self.x(x0)
            alinear = op.get("alinear", "izq") if modo == "no" else "izq"
            sobra = objetivo - (natural * sx + extra * huecos)
            x += sobra / 2 if alinear == "centro" else (sobra if alinear == "der" else 0)
            inicios = []
            for w, p in zip(anchos, es_palabra):
                if p:
                    inicios.append(x)
                x += w * sx + (0 if p else extra)
        if modo != "no" and abs(sx - 1) > 0.15:
            self.avisos.append(f"#{n} «{texto[:30]}»: letras estiradas {sx - 1:+.0%}; "
                               "revisá la caja, tam o la fuente")
        base = self.y(base_u)
        tinta = color(op.get("color") or self.defecto.get("color"))
        t = c.beginText(inicios[0], base)
        t.setHorizScale(sx * 100)
        t.setFillColor(tinta)
        k, origen = 0, inicios[0]
        for (_, tr), p in zip(piezas, es_palabra):
            if p:  # cada palabra arranca donde le toca; los espacios igual se escriben (copiar y pegar)
                if k:
                    t.moveCursor(inicios[k] - origen, 0)
                    origen = inicios[k]
                k += 1
            for s, f in tr:
                t.setFont(f, tam)
                t.textOut(s)
        c.drawText(t)
        if op.get("subrayado") or op.get("tachado"):
            fin = inicios[-1] + anchos[max(i for i, p in enumerate(es_palabra) if p)] * sx
            c.saveState()
            c.setStrokeColor(tinta)
            c.setLineWidth(0.06 * tam)
            for activo, dy in ((op.get("subrayado"), -0.12), (op.get("tachado"), 0.3)):
                if activo:
                    c.line(inicios[0], base + dy * tam, fin, base + dy * tam)
            c.restoreState()

    def linea(self, el, n):
        (xa, ya), (xb, yb) = el["de"], el["a"]
        c = self.c
        c.saveState()
        g = self._grosor(el)
        c.setStrokeColor(color(el.get("color")))
        c.setLineWidth(g)
        trazo = el.get("trazo", "solido")
        if trazo == "guiones":
            c.setDash(4 * g + 2 * self.s, 3 * g + 2 * self.s)
        elif trazo == "puntos":
            c.setLineCap(1)
            c.setDash([0.01, 2.5 * g + self.s])
        c.line(self.x(xa), self.y(ya), self.x(xb), self.y(yb))
        flechas = el.get("flechas")  # "inicio", "fin" o "ambas": puntas llenas (cotas de planos)
        if flechas:
            c.setDash([])
            c.setFillColor(color(el.get("color")))
            largo = float(el.get("flecha", 4)) * self.s
            pa, pb = (self.x(xa), self.y(ya)), (self.x(xb), self.y(yb))
            for activo, punta, cola in ((flechas in ("inicio", "ambas"), pa, pb),
                                        (flechas in ("fin", "ambas"), pb, pa)):
                d = math.hypot(cola[0] - punta[0], cola[1] - punta[1])
                if activo and d > 0:
                    ux, uy = (cola[0] - punta[0]) / d, (cola[1] - punta[1]) / d
                    bx, by = punta[0] + ux * largo, punta[1] + uy * largo
                    ancho = 0.3 * largo
                    p = c.beginPath()
                    p.moveTo(*punta)
                    p.lineTo(bx - uy * ancho, by + ux * ancho)
                    p.lineTo(bx + uy * ancho, by - ux * ancho)
                    p.close()
                    c.drawPath(p, stroke=0, fill=1)
        c.restoreState()

    def arco(self, el, n):
        """Arco de circunferencia: `centro` [x, y], `radio`, `desde` y `hasta` en grados
        (0 = derecha, 90 = arriba, en sentido antihorario como se ve en la hoja).
        Con `radio_y` es un arco de elipse, y con `giro` la elipse se gira (isométrica)."""
        cx, cy = (float(v) for v in el["centro"])
        r = float(el["radio"])
        ry = float(el.get("radio_y", r))
        a, b = float(el.get("desde", 0)), float(el.get("hasta", 360))
        c = self.c
        c.saveState()
        c.setStrokeColor(color(el.get("color")))
        c.setLineWidth(self._grosor(el))
        if el.get("trazo", "solido") == "guiones":
            g = self._grosor(el)
            c.setDash(4 * g + 2 * self.s, 3 * g + 2 * self.s)
        c.translate(self.x(cx), self.y(cy))
        c.rotate(float(el.get("giro", 0)))
        c.arc(-r * self.s, -ry * self.s, r * self.s, ry * self.s, a, (b - a) % 360 or 360)
        c.restoreState()

    def _forma(self, el, dibujar):
        x0, y0, x1, y1 = caja(el)
        c = self.c
        c.saveState()
        borde, relleno = el.get("borde", "#000000"), el.get("relleno")
        if borde:
            c.setStrokeColor(color(borde))
            c.setLineWidth(self._grosor(el))
        if relleno:
            c.setFillColor(color(relleno))
        dibujar(self.x(x0), self.y(y1), (x1 - x0) * self.s, (y1 - y0) * self.s,
                int(bool(borde)), int(bool(relleno)))
        c.restoreState()

    def rect(self, el, n):
        radio = float(el.get("radio", 0)) * self.s
        if radio:
            self._forma(el, lambda x, y, w, h, s, f: self.c.roundRect(x, y, w, h, radio, stroke=s, fill=f))
        else:
            self._forma(el, lambda x, y, w, h, s, f: self.c.rect(x, y, w, h, stroke=s, fill=f))

    def elipse(self, el, n):
        giro = float(el.get("giro", 0)) % 360
        if not giro:
            return self._forma(el, lambda x, y, w, h, s, f: self.c.ellipse(x, y, x + w, y + h, stroke=s, fill=f))
        # elipse girada (círculos en isométrica): la caja es la elipse sin girar; gira sobre su centro
        x0, y0, x1, y1 = caja(el)
        self.c.saveState()
        self.c.translate(self.x((x0 + x1) / 2), self.y((y0 + y1) / 2))
        self.c.rotate(giro)
        w, h = (x1 - x0) * self.s, (y1 - y0) * self.s
        self._forma({**el, "caja": [0, 0, 0, 0]},
                    lambda x, y, _w, _h, s, f: self.c.ellipse(-w / 2, -h / 2, w / 2, h / 2, stroke=s, fill=f))
        self.c.restoreState()

    def casilla(self, el, n):
        self.rect({**el, "relleno": None}, n)
        marca = el.get("marca")
        if not marca:
            return
        x0, y0, x1, y1 = caja(el)
        w, h = x1 - x0, y1 - y0
        c = self.c
        c.saveState()
        tinta = color(el.get("color"))
        c.setStrokeColor(tinta)
        c.setFillColor(tinta)
        c.setLineWidth(self._grosor(el) * 1.6)
        c.setLineCap(1)
        c.setLineJoin(1)

        def p(fx, fy):
            return self.x(x0 + fx * w), self.y(y0 + fy * h)

        if marca == "x":
            c.line(*p(.2, .2), *p(.8, .8))
            c.line(*p(.8, .2), *p(.2, .8))
        elif marca == "v":
            trazo = c.beginPath()
            trazo.moveTo(*p(.18, .55))
            trazo.lineTo(*p(.42, .78))
            trazo.lineTo(*p(.84, .22))
            c.drawPath(trazo, stroke=1, fill=0)
        elif marca == "relleno":
            c.rect(*p(.22, .78), .56 * w * self.s, .56 * h * self.s, stroke=0, fill=1)
        c.restoreState()

    def imagen(self, el, n):
        x0, y0, x1, y1 = caja(el)
        if el.get("archivo"):
            im = abrir_imagen(el["archivo"])
        else:
            k = self.base.width / ANCHO_U
            im = self.base.crop((round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k)))
        if el.get("transparente", True):
            im = sin_papel(im)
        self.c.drawImage(ImageReader(im), self.x(x0), self.y(y1), (x1 - x0) * self.s, (y1 - y0) * self.s,
                         mask="auto")

    def tabla(self, el, n):
        xs, ys = [float(v) for v in el["columnas"]], [float(v) for v in el["filas"]]
        c = self.c
        for fila, relleno in (el.get("relleno_filas") or {}).items():
            i = int(fila)
            if 0 <= i < len(ys) - 1:
                self.rect({"caja": [xs[0], ys[i], xs[-1], ys[i + 1]], "borde": None, "relleno": relleno}, n)
        c.saveState()
        c.setStrokeColor(color(el.get("color_borde")))
        c.setLineWidth(self._grosor(el))
        bordes = el.get("bordes", "todos")
        if bordes in ("todos", "horizontales"):
            for y in ys:
                c.line(self.x(xs[0]), self.y(y), self.x(xs[-1]), self.y(y))
        if bordes == "todos":
            for x in xs:
                c.line(self.x(x), self.y(ys[0]), self.x(x), self.y(ys[-1]))
        if bordes == "externos":
            c.rect(self.x(xs[0]), self.y(ys[-1]), (xs[-1] - xs[0]) * self.s, (ys[-1] - ys[0]) * self.s,
                   stroke=1, fill=0)
        c.restoreState()
        alturas = sorted(b - a for a, b in zip(ys, ys[1:]))
        tam_u = float(el.get("tam") or 0.5 * alturas[len(alturas) // 2])
        alinear = el.get("alinear", "izq")
        negritas = set(el.get("negrita_filas", []))
        familia = el.get("fuente") or self.defecto.get("fuente")
        for i, fila in enumerate(el.get("celdas", [])):
            for j, txt in enumerate(fila):
                if txt in (None, ""):
                    continue
                if i + 1 >= len(ys) or j + 1 >= len(xs):
                    self.avisos.append(f"#{n}: la celda ({i}, {j}) cae fuera de la grilla de la tabla")
                    continue
                fuente, cap = self.fuentes.elegir(familia, i in negritas, False)
                renglones = str(txt).split("\n")
                interlinea = tam_u * 1.15
                bloque = cap * tam_u + interlinea * (len(renglones) - 1)
                base = (ys[i] + ys[i + 1]) / 2 - bloque / 2 + cap * tam_u
                al = (alinear[j] if j < len(alinear) else "izq") if isinstance(alinear, list) else alinear
                pad = 0.35 * tam_u
                for k, r in enumerate(renglones):
                    self._renglon(r, fuente, tam_u, xs[j] + pad, xs[j + 1] - pad, base + k * interlinea,
                                  {"ajuste": "no", "alinear": al, "color": el.get("color")}, n)


TIPOS = ("texto", "linea", "arco", "rect", "elipse", "casilla", "imagen", "tabla")


def construir(trabajos, salida, encajar=True):
    fuentes = Fuentes()
    c = Canvas(str(salida))
    c.setCreator("foto-a-pdf")
    for numero, d in enumerate(trabajos, 1):
        info, layout = leer_json(d / "info.json"), leer_json(d / "layout.json")
        if numero == 1:
            c.setTitle(Path(info["foto"]).stem)
        pag = layout.get("pagina", {})
        ancho = float(pag.get("ancho_mm", info["ancho_mm"])) * mm
        alto = float(pag.get("alto_mm", info["alto_mm"])) * mm
        c.setPageSize((ancho, alto))
        base = Image.open(d / "base.png").convert("RGB")
        elementos = layout.get("elementos", [])
        resumen = "sin encaje"
        if encajar:
            elementos, resumen = encajar_todo(elementos, base)
        try:
            resumen += " · " + rectificar(elementos, layout.get("angulos"), layout.get("tolerancia_angulo", 4))
        except ValueError as e:
            sys.exit(str(e))
        p = Pagina(c, ancho, alto, base, fuentes, layout.get("defecto", {}))
        fondo = pag.get("fondo")
        if fondo and str(fondo).lower() not in ("#fff", "#ffffff", "white", "blanco"):
            c.setFillColor(color(fondo))
            c.rect(0, 0, ancho, alto, stroke=0, fill=1)
        for n, el in enumerate(elementos, 1):
            tipo = el.get("tipo")
            if tipo not in TIPOS:
                p.avisos.append(f"#{n}: tipo desconocido {tipo!r} (válidos: {', '.join(TIPOS)})")
                continue
            try:
                getattr(p, tipo)(el, n)
            except (KeyError, ValueError, TypeError, IndexError, OSError) as e:
                p.avisos.append(f"#{n} ({tipo}): {type(e).__name__}: {e}")
        c.showPage()
        print(f"Página {numero}: {len(elementos)} elementos · encaje: {resumen}")
        for a in p.avisos:
            print(f"  Aviso {a}")
    if fuentes.sin_glifo:
        print("Sin glifo en ninguna fuente (salieron como ?): " + " ".join(sorted(fuentes.sin_glifo)))
    try:
        c.save()
    except PermissionError:
        sys.exit(f"No pude escribir {salida}: ¿está abierto en otro programa? Cerralo y volvé a correr.")
    print(f"PDF: {salida}")


def main():
    salida_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trabajos", nargs="+", help="carpetas de trabajo, una por página y en orden")
    ap.add_argument("--pdf", help="ruta del PDF (por defecto, al lado de la primera foto)")
    ap.add_argument("--sin-encajar", action="store_true", help="no ajustar las cajas a la tinta de la foto")
    ap.add_argument("--sin-comparar", action="store_true", help="no generar la comparación con la foto")
    a = ap.parse_args()
    trabajos = [Path(t) for t in a.trabajos]
    for t in trabajos:
        if not (t / "layout.json").exists():
            sys.exit(f"No encuentro {t / 'layout.json'}: corré antes preparar.py.")
    salida = Path(a.pdf) if a.pdf else Path(leer_json(trabajos[0] / "info.json")["pdf"])
    salida.parent.mkdir(parents=True, exist_ok=True)
    construir(trabajos, salida, encajar=not a.sin_encajar)
    if not a.sin_comparar:
        from comparar import comparar, imprimir
        for i, t in enumerate(trabajos):
            imprimir(comparar(t, salida, i), i + 1)


if __name__ == "__main__":
    main()
