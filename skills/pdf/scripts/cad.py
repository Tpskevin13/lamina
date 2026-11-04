"""Pasa a CAD (DXF y, si hay con qué, DWG) lo mismo que construir.py dibujó en el PDF.

  python cad.py TRABAJO [--dxf salida.dxf] [--dwg salida.dwg]

Lee TRABAJO/final.json, que deja construir.py: los elementos ya encajados y enderezados. Por eso
hay que correr antes construir.py. Unidades: milímetros de la hoja (1:1 con el papel), origen
abajo a la izquierda. Cada cosa va en su capa: CONTORNO, FINAS, EJES, COTAS, TEXTO, RELLENOS,
IMAGENES y HOJA (el borde del papel, que no se imprime).

El DWG lo escribe AutoCAD (accoreconsole, sin abrir ventana) o, si no está, el ODA File Converter
(gratis). Si no hay ninguno de los dos, queda el DXF, que AutoCAD abre igual.
"""
import argparse
import glob
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from comun import ANCHO_U, leer_json, salida_utf8

CAPAS = {  # nombre: (color AutoCAD, tipo de línea, grosor de línea en centésimas de mm)
    "CONTORNO": (7, "Continuous", 50),
    "FINAS": (7, "Continuous", 18),
    "EJES": (1, "CENTER", 18),
    "OCULTAS": (2, "DASHED", 25),
    "COTAS": (3, "Continuous", 18),
    "TEXTO": (7, "Continuous", 18),
    "RELLENOS": (8, "Continuous", 0),
    "IMAGENES": (7, "Continuous", 0),
    "HOJA": (9, "Continuous", 0),
}
GROSORES = [5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]
FUENTES = {"serif": "times.ttf", "georgia": "georgia.ttf", "mono": "cour.ttf", "angosta": "arialn.ttf",
           "calibri": "calibri.ttf", "segoe": "segoeui.ttf", "verdana": "verdana.ttf", "tahoma": "tahoma.ttf",
           "trebuchet": "trebuc.ttf", "comic": "comic.ttf", "manuscrita": "segoepr.ttf"}


def _rgb(hexa):
    if not hexa or not str(hexa).startswith("#") or len(str(hexa)) != 7:
        return None
    v = str(hexa)[1:]
    rgb = tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return None if rgb == (0, 0, 0) else rgb


class Hoja:
    def __init__(self, doc, final, trabajo, carpeta_img):
        self.doc, self.msp = doc, doc.modelspace()
        self.k = float(final["ancho_mm"]) / ANCHO_U          # mm por u
        self.alto_mm = float(final["alto_mm"])
        self.trabajo, self.carpeta_img = trabajo, carpeta_img
        self.base = None
        self.estilos = {}
        self.n_img = 0

    def p(self, x, y):  # u (y hacia abajo) -> mm (y hacia arriba)
        return (round(float(x) * self.k, 4), round(self.alto_mm - float(y) * self.k, 4))

    def atrib(self, el, capa):
        a = {"layer": capa}
        rgb = _rgb(el.get("color") or el.get("borde"))
        if rgb:
            a["true_color"] = (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]
        if "grosor" in el:
            mm = float(el["grosor"]) * self.k * 100
            a["lineweight"] = min(GROSORES, key=lambda g: abs(g - mm))
        return a

    def estilo(self, el, defecto):
        familia = str(el.get("fuente") or defecto.get("fuente") or "sans").lower()
        ttf = familia if familia.endswith(".ttf") else FUENTES.get(familia, "arial.ttf")
        if el.get("negrita") and ttf == "arial.ttf":
            ttf = "arialbd.ttf"
        nombre = Path(ttf).stem.upper()
        if nombre not in self.estilos:
            if nombre not in self.doc.styles:
                self.doc.styles.new(nombre, dxfattribs={"font": Path(ttf).name})
            self.estilos[nombre] = True
        return nombre

    # ---- elementos ----
    def linea(self, el):
        trazo = el.get("trazo", "solido")
        if trazo == "guiones":
            capa = "EJES"
        elif trazo == "puntos":
            capa = "OCULTAS"
        elif el.get("flechas"):
            capa = "COTAS"
        else:
            capa = "CONTORNO" if float(el.get("grosor", 1)) >= 1 else "FINAS"
        a, b = self.p(*el["de"]), self.p(*el["a"])
        self.msp.add_line(a, b, dxfattribs=self.atrib(el, capa))
        flechas = el.get("flechas")
        if flechas:
            largo = float(el.get("flecha", 4)) * self.k
            for activo, punta, cola in ((flechas in ("inicio", "ambas"), a, b), (flechas in ("fin", "ambas"), b, a)):
                d = math.dist(punta, cola)
                if activo and d > 0:
                    ux, uy = (cola[0] - punta[0]) / d, (cola[1] - punta[1]) / d
                    bx, by = punta[0] + ux * largo, punta[1] + uy * largo
                    w = 0.3 * largo
                    self.msp.add_solid([punta, (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)],
                                       dxfattribs={"layer": "COTAS"})

    def arco(self, el):
        cx, cy = self.p(*el["centro"])
        r = float(el["radio"]) * self.k
        ry = float(el.get("radio_y", el["radio"])) * self.k
        a, b = float(el.get("desde", 0)), float(el.get("hasta", 360))
        giro = float(el.get("giro", 0))
        capa = "EJES" if el.get("trazo") == "guiones" else ("CONTORNO" if float(el.get("grosor", 1)) >= 1 else "FINAS")
        at = self.atrib(el, capa)
        if abs(ry - r) < 1e-6 and not giro:
            if (b - a) % 360 == 0:
                self.msp.add_circle((cx, cy), r, dxfattribs=at)
            else:
                self.msp.add_arc((cx, cy), r, a, b, dxfattribs=at)
            return
        mayor = max(r, ry)
        eje = giro if r >= ry else giro + 90
        ax = (mayor * math.cos(math.radians(eje)), mayor * math.sin(math.radians(eje)))
        desplazo = 0 if r >= ry else 90  # los parámetros se miden desde el eje mayor
        self.msp.add_ellipse((cx, cy), ax, min(r, ry) / mayor, math.radians(a - desplazo),
                             math.radians(b - desplazo), dxfattribs=at)

    def elipse(self, el):
        x0, y0, x1, y1 = (float(v) for v in el["caja"])
        rx, ry = abs(x1 - x0) / 2, abs(y1 - y0) / 2
        centro = [(x0 + x1) / 2, (y0 + y1) / 2]
        if el.get("relleno"):
            self._relleno_elipse(el, centro, rx, ry)
        if el.get("borde", "#000000"):
            self.arco({**el, "centro": centro, "radio": rx, "radio_y": ry, "desde": 0, "hasta": 360})

    def _relleno_elipse(self, el, centro, rx, ry):
        cx, cy = self.p(*centro)
        h = self.msp.add_hatch(dxfattribs={"layer": "RELLENOS"})
        rgb = _rgb(el["relleno"])
        if rgb:
            h.rgb = rgb
        giro = math.radians(float(el.get("giro", 0)))
        pts = [(cx + rx * self.k * math.cos(t) * math.cos(giro) - ry * self.k * math.sin(t) * math.sin(giro),
                cy + rx * self.k * math.cos(t) * math.sin(giro) + ry * self.k * math.sin(t) * math.cos(giro))
               for t in (i * 2 * math.pi / 72 for i in range(72))]
        h.paths.add_polyline_path(pts, is_closed=True)

    def rect(self, el):
        x0, y0, x1, y1 = (float(v) for v in el["caja"])
        pts = [self.p(x0, y0), self.p(x1, y0), self.p(x1, y1), self.p(x0, y1)]
        if el.get("relleno"):
            h = self.msp.add_hatch(dxfattribs={"layer": "RELLENOS"})
            rgb = _rgb(el["relleno"])
            if rgb:
                h.rgb = rgb
            h.paths.add_polyline_path(pts, is_closed=True)
        if el.get("borde", "#000000"):
            capa = "CONTORNO" if float(el.get("grosor", 1)) >= 1 else "FINAS"
            self.msp.add_lwpolyline(pts, close=True, dxfattribs=self.atrib(el, capa))

    def casilla(self, el):
        self.rect({**el, "relleno": None})
        x0, y0, x1, y1 = (float(v) for v in el["caja"])
        w, h = x1 - x0, y1 - y0
        q = lambda fx, fy: self.p(x0 + fx * w, y0 + fy * h)
        marca = el.get("marca")
        at = {"layer": "FINAS"}
        if marca == "x":
            self.msp.add_line(q(.2, .2), q(.8, .8), dxfattribs=at)
            self.msp.add_line(q(.8, .2), q(.2, .8), dxfattribs=at)
        elif marca == "v":
            self.msp.add_lwpolyline([q(.18, .55), q(.42, .78), q(.84, .22)], dxfattribs=at)
        elif marca == "relleno":
            h_ = self.msp.add_hatch(color=7, dxfattribs={"layer": "RELLENOS"})
            h_.paths.add_polyline_path([q(.22, .22), q(.78, .22), q(.78, .78), q(.22, .78)], is_closed=True)

    def _texto_en(self, txt, el, defecto, x0, x1, base_y, tam_u, cap, giro=0.0, alinear=None):
        """Un renglón: de (x0, base) a (x1, base) en el sistema ya girado del texto (u)."""
        from ezdxf.enums import TextEntityAlignment
        alto = max(tam_u * cap * self.k, 0.1)
        at = self.atrib({"color": el.get("color")}, "TEXTO")
        at.update({"style": self.estilo(el, defecto), "height": alto, "rotation": giro})
        t = self.msp.add_text(txt, dxfattribs=at)
        return t, alto, TextEntityAlignment

    def texto(self, el, defecto):
        txt = str(el.get("texto", "")).strip()
        if not txt:
            return
        tam, cap = float(el.get("_tam", 0)), float(el.get("_cap", 0.716))
        x0, y0, x1, y1 = (float(v) for v in el["caja"]) if "caja" in el else (0, 0, 0, 0)
        giro = float(el.get("giro", 0)) % 360
        if not tam:
            tam = max(y1 - y0, 1.0) / cap
        no_estirar = el.get("ajuste") == "no"
        alinear = el.get("alinear", "izq")
        if not giro:
            a, b = self.p(x0, y1), self.p(x1, y1)
        elif giro in (90, 270):
            if giro == 90:   # se lee de abajo hacia arriba, la base del renglón es el borde derecho
                a, b = self.p(x1, y1), self.p(x1, y0)
            else:
                a, b = self.p(x0, y0), self.p(x0, y1)
        else:
            if "centro" in el:
                cx, cy = (float(v) for v in el["centro"])
                largo, alto_r = float(el["largo"]), float(el["alto"])
            else:
                cx, cy, largo, alto_r = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
            c = self.p(cx, cy)
            ux, uy = math.cos(math.radians(giro)), math.sin(math.radians(giro))
            L, h = largo * self.k / 2, alto_r * self.k / 2
            # base del renglón: medio alto por debajo del centro, en la dirección girada
            bx, by = c[0] + uy * h, c[1] - ux * h
            a, b = (bx - ux * L, by - uy * L), (bx + ux * L, by + uy * L)
        t, alto, TEA = self._texto_en(txt, el, defecto, 0, 0, 0, tam, cap, giro)
        if no_estirar:
            medio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if alinear == "centro":
                t.set_placement(medio, align=TEA.BOTTOM_CENTER)
            elif alinear == "der":
                t.set_placement(b, align=TEA.BOTTOM_RIGHT)
            else:
                t.set_placement(a, align=TEA.BOTTOM_LEFT)
        else:
            t.set_placement(a, b, align=TEA.FIT)  # ocupa de la primera a la última letra, como en el PDF

    def tabla(self, el, defecto):
        from ezdxf.enums import TextEntityAlignment as TEA
        xs, ys = [float(v) for v in el["columnas"]], [float(v) for v in el["filas"]]
        bordes = el.get("bordes", "todos")
        for fila, relleno in (el.get("relleno_filas") or {}).items():
            i = int(fila)
            if 0 <= i < len(ys) - 1:
                self.rect({"caja": [xs[0], ys[i], xs[-1], ys[i + 1]], "borde": None, "relleno": relleno})
        at = self.atrib({"color": el.get("color_borde"), "grosor": el.get("grosor", 1)}, "FINAS")
        if bordes in ("todos", "horizontales"):
            for y in ys:
                self.msp.add_line(self.p(xs[0], y), self.p(xs[-1], y), dxfattribs=at)
        if bordes == "todos":
            for x in xs:
                self.msp.add_line(self.p(x, ys[0]), self.p(x, ys[-1]), dxfattribs=at)
        if bordes == "externos":
            self.rect({"caja": [xs[0], ys[0], xs[-1], ys[-1]], "grosor": el.get("grosor", 1)})
        alturas = sorted(b - a for a, b in zip(ys, ys[1:]))
        tam_u = float(el.get("tam") or 0.5 * alturas[len(alturas) // 2])
        alinear = el.get("alinear", "izq")
        negritas = set(el.get("negrita_filas", []))
        for i, fila in enumerate(el.get("celdas", [])):
            for j, txt in enumerate(fila):
                if txt in (None, "") or i + 1 >= len(ys) or j + 1 >= len(xs):
                    continue
                al = (alinear[j] if j < len(alinear) else "izq") if isinstance(alinear, list) else alinear
                renglones = str(txt).split("\n")
                inter = tam_u * 1.15
                cap = 0.716
                bloque = cap * tam_u + inter * (len(renglones) - 1)
                base = (ys[i] + ys[i + 1]) / 2 - bloque / 2 + cap * tam_u
                pad = 0.35 * tam_u
                celda = {"fuente": el.get("fuente"), "negrita": i in negritas, "color": el.get("color")}
                for k, r in enumerate(renglones):
                    t, _, _ = self._texto_en(r, celda, defecto, 0, 0, 0, tam_u, cap)
                    y = base + k * inter
                    if al == "centro":
                        t.set_placement(self.p((xs[j] + xs[j + 1]) / 2, y), align=TEA.BOTTOM_CENTER)
                    elif al == "der":
                        t.set_placement(self.p(xs[j + 1] - pad, y), align=TEA.BOTTOM_RIGHT)
                    else:
                        t.set_placement(self.p(xs[j] + pad, y), align=TEA.BOTTOM_LEFT)

    def imagen(self, el):
        x0, y0, x1, y1 = (float(v) for v in el["caja"])
        if el.get("archivo"):
            ruta = Path(el["archivo"]).resolve()
            im = Image.open(ruta)
        else:
            if self.base is None:
                self.base = Image.open(self.trabajo / "base.png").convert("RGB")
            k = self.base.width / ANCHO_U
            im = self.base.crop((round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k)))
            self.carpeta_img.mkdir(parents=True, exist_ok=True)
            self.n_img += 1
            ruta = self.carpeta_img / f"imagen_{self.n_img:02d}.png"
            im.save(ruta)
        definicion = self.doc.add_image_def(filename=str(ruta), size_in_pixel=im.size)
        w, h = (x1 - x0) * self.k, (y1 - y0) * self.k
        self.msp.add_image(definicion, insert=self.p(x0, y1), size_in_units=(w, h),
                           dxfattribs={"layer": "IMAGENES"})


def exportar_dxf(trabajo, salida):
    import ezdxf
    from ezdxf import units
    final_json = trabajo / "final.json"
    if not final_json.exists():
        sys.exit(f"No encuentro {final_json}: corré antes construir.py (deja ahí lo que dibujó).")
    final, layout = leer_json(final_json), leer_json(trabajo / "layout.json")
    doc = ezdxf.new("R2018", setup=True, units=units.MM)
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    doc.header["$LWDISPLAY"] = 1
    for nombre, (col, tl, lw) in CAPAS.items():
        capa = doc.layers.add(nombre, color=col, linetype=tl if tl in doc.linetypes else "Continuous")
        capa.dxf.lineweight = lw or -3
        if nombre == "HOJA":
            capa.dxf.plot = 0
    hoja = Hoja(doc, final, trabajo, salida.with_name(salida.stem + "_imagenes"))
    defecto = layout.get("defecto", {})
    avisos = []
    w, h = float(final["ancho_mm"]), float(final["alto_mm"])
    doc.modelspace().add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True, dxfattribs={"layer": "HOJA"})
    for n, el in enumerate(final["elementos"], 1):
        tipo = el.get("tipo")
        try:
            if tipo in ("texto", "tabla"):
                getattr(hoja, tipo)(el, defecto)
            elif tipo in ("linea", "arco", "elipse", "rect", "casilla", "imagen"):
                getattr(hoja, tipo)(el)
        except (KeyError, ValueError, TypeError, OSError) as e:
            avisos.append(f"#{n} ({tipo}): {type(e).__name__}: {e}")
    doc.set_modelspace_vport(height=h * 1.05, center=(w / 2, h / 2))
    doc.saveas(salida)
    print(f"DXF: {salida}  ({len(final['elementos'])} elementos, en mm, hoja {w:g} x {h:g})")
    if hoja.n_img:
        print(f"  Las {hoja.n_img} imágenes van como referencia externa en {hoja.carpeta_img}: "
              "si movés el DXF o el DWG, llevá esa carpeta con él.")
    for a in avisos:
        print(f"  Aviso {a}")


def buscar_convertidor():
    """('autocad' | 'oda', ruta del ejecutable) o None."""
    for patron in (r"C:\Program Files\Autodesk\AutoCAD *\accoreconsole.exe",
                   r"C:\Program Files\Autodesk\AutoCAD LT *\accoreconsole.exe"):
        hallados = sorted(glob.glob(patron))
        if hallados:
            return "autocad", hallados[-1]  # la versión más nueva
    for patron in (r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
                   r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
                   "/usr/bin/ODAFileConverter", "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"):
        hallados = sorted(glob.glob(patron))
        if hallados:
            return "oda", hallados[-1]
    return None


def dxf_a_dwg(dxf, dwg):
    conv = buscar_convertidor()
    if not conv:
        print("No encontré AutoCAD ni el ODA File Converter para escribir el DWG. Quedó el DXF, que AutoCAD "
              "abre igual (y con Guardar como… lo pasás a DWG). Para el DWG automático, instalá el ODA File "
              "Converter (gratis): https://www.opendesign.com/guestfiles/oda_file_converter")
        return False
    tipo, exe = conv
    dwg = Path(dwg).resolve()
    if dwg.exists():
        dwg.unlink()
    if tipo == "autocad":
        with tempfile.TemporaryDirectory() as tmp:
            guion = Path(tmp) / "guardar.scr"
            guion.write_text(f'FILEDIA 0\n_.SAVEAS 2018 "{dwg}"\n', encoding="utf-8")
            r = subprocess.run([exe, "/i", str(Path(dxf).resolve()), "/s", str(guion), "/l", "en-US"],
                               capture_output=True, timeout=300)
    else:
        with tempfile.TemporaryDirectory() as ent, tempfile.TemporaryDirectory() as sal:
            Path(ent, Path(dxf).name).write_bytes(Path(dxf).read_bytes())
            r = subprocess.run([exe, ent, sal, "ACAD2018", "DWG", "0", "1", Path(dxf).name],
                               capture_output=True, timeout=300)
            hecho = Path(sal, Path(dxf).stem + ".dwg")
            if hecho.exists():
                dwg.write_bytes(hecho.read_bytes())
    if not dwg.exists():
        salida = (r.stdout or b"").decode("utf-16-le" if tipo == "autocad" else "utf-8", "ignore")[-800:]
        print(f"No se pudo escribir el DWG con {exe}. Quedó el DXF.\n{salida}")
        return False
    print(f"DWG: {dwg}  (escrito con {'AutoCAD' if tipo == 'autocad' else 'ODA File Converter'}, formato 2018)")
    return True


def main():
    salida_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trabajo", help="carpeta de trabajo (después de construir.py)")
    ap.add_argument("--dxf", help="ruta del DXF (por defecto, al lado del PDF)")
    ap.add_argument("--dwg", nargs="?", const="", help="también escribir el DWG (opcionalmente, su ruta)")
    a = ap.parse_args()
    trabajo = Path(a.trabajo)
    try:
        import ezdxf  # noqa: F401
    except ImportError:
        sys.exit("Falta la librería ezdxf: python -m pip install ezdxf")
    pdf = Path(leer_json(trabajo / "info.json")["pdf"])
    dxf = Path(a.dxf) if a.dxf else pdf.with_suffix(".dxf")
    if a.dwg is not None and not a.dxf:
        # si solo se pidió DWG, el DXF intermedio va al lado del DWG pedido
        if a.dwg:
            dxf = Path(a.dwg).with_suffix(".dxf")
    dxf.parent.mkdir(parents=True, exist_ok=True)
    exportar_dxf(trabajo, dxf)
    if a.dwg is not None:
        dxf_a_dwg(dxf, Path(a.dwg) if a.dwg else dxf.with_suffix(".dwg"))


if __name__ == "__main__":
    main()
