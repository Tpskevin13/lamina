"""Prepara una foto para rearmarla en PDF: la endereza, la limpia y la corta en franjas con reglas.

  python preparar.py ver FOTO                    grilla sobre la foto y esquinas sugeridas de la hoja
  python preparar.py preparar FOTO [opciones]    carpeta de trabajo: base.png, grilla, franjas e info.json
  python preparar.py zoom TRABAJO x0 y0 x1 y1    ampliación de una zona (en u) con reglas finas
  python preparar.py buscar                      últimas imágenes de Descargas, Escritorio, Imágenes...
"""
import argparse
import hashlib
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from comun import (ANCHO_U, MARGEN_IZQ, MARGEN_SUP, PAPELES_MM, abrir_imagen, con_reglas,
                   fuente_reglas, guardar_json, leer_json, limpiar, otsu, salida_utf8)

ANCHO_FRANJA = 1400   # px de cada franja, sin las reglas
ALTO_FRANJA_U = 180   # alto aproximado de cada franja
SOLAPE_U = 12         # cada franja repite el final de la anterior para no cortar renglones
ANCHO_BASE_MAX = 3000
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tif", ".tiff"}


def carpeta_trabajo(foto, trabajo=None):
    """Carpeta temporal propia de cada foto, para no llenar de archivos la carpeta del usuario."""
    if trabajo:
        d = Path(trabajo)
    else:
        marca = hashlib.md5(str(foto).lower().encode()).hexdigest()[:6]
        d = Path(tempfile.gettempdir()) / "foto-a-pdf" / f"{foto.stem}-{marca}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _recta(t, v):
    """Ajusta v = a·t + b descartando los puntos que se alejan (dedos, sombras sobre el borde)."""
    a, b = np.polyfit(t, v, 1)
    resto = np.abs(v - (a * t + b))
    bien = resto <= max(1.5, 2.5 * np.median(resto))
    return np.polyfit(t[bien], v[bien], 1) if bien.sum() >= 10 else (a, b)


def _bordes(hoja, esquinas):
    """Esquinas exactas: cruza las rectas ajustadas a los 4 bordes de la hoja (las puntas salen redondeadas)."""
    (si, sd, id_, ii), (H, W) = esquinas, hoja.shape

    def centro(p, q):  # 80 % central del tramo entre dos esquinas
        lo, hi = sorted((p, q))
        return int(lo + 0.1 * (hi - lo)), int(hi - 0.1 * (hi - lo))

    x0, x1 = centro(si[0], sd[0])
    a_s, b_s = _recta(np.arange(x0, x1), hoja[:, x0:x1].argmax(axis=0))
    x0, x1 = centro(ii[0], id_[0])
    a_i, b_i = _recta(np.arange(x0, x1), H - 1 - hoja[::-1, x0:x1].argmax(axis=0))
    y0, y1 = centro(si[1], ii[1])
    c_iz, d_iz = _recta(np.arange(y0, y1), hoja[y0:y1].argmax(axis=1))
    y0, y1 = centro(sd[1], id_[1])
    c_de, d_de = _recta(np.arange(y0, y1), W - 1 - hoja[y0:y1, ::-1].argmax(axis=1))

    def cruce(a, b, c, d):  # y = a·x + b  con  x = c·y + d
        y = (a * d + b) / (1 - a * c)
        return c * y + d, y

    return [cruce(a_s, b_s, c_iz, d_iz), cruce(a_s, b_s, c_de, d_de),
            cruce(a_i, b_i, c_de, d_de), cruce(a_i, b_i, c_iz, d_iz)]


def sugerir_esquinas(img):
    """Busca la hoja (zona clara conectada con el centro) y devuelve sus 4 esquinas en u, o None."""
    chica = img.convert("L")
    chica.thumbnail((1000, 1000))
    a = np.asarray(chica)
    m = Image.fromarray(np.where(a > otsu(a), 255, 0).astype(np.uint8))
    m = m.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))  # tapa el texto
    m = m.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))  # borra puntitos sueltos
    w, h = m.size
    for fx, fy in ((.5, .5), (.4, .5), (.6, .5), (.5, .4), (.5, .6), (.35, .35), (.65, .65)):
        semilla = (int(w * fx), int(h * fy))
        if m.getpixel(semilla) == 255:
            break
    else:
        return None
    ImageDraw.floodfill(m, semilla, 128)
    hoja = np.asarray(m) == 128
    ys, xs = np.nonzero(hoja)
    if len(xs) < 0.15 * w * h:
        return None
    suma, resta = xs + ys, xs - ys
    indices = (suma.argmin(), resta.argmax(), suma.argmax(), resta.argmin())  # sup-izq, sup-der, inf-der, inf-izq
    esquinas = [(float(xs[i]), float(ys[i])) for i in indices]
    try:
        finas = _bordes(hoja, esquinas)
        if max(math.dist(p, q) for p, q in zip(finas, esquinas)) < 0.03 * w:
            esquinas = finas
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError):
        pass  # bordes raros: quedan las aproximadas
    k = ANCHO_U / w
    return [(round(x * k, 1), round(y * k, 1)) for x, y in esquinas]


def leer_esquinas(texto):
    try:
        puntos = [tuple(float(v) for v in p.split(",")) for p in texto.replace(";", " ").split()]
    except ValueError:
        puntos = []
    if len(puntos) != 4 or any(len(p) != 2 for p in puntos):
        sys.exit('--esquinas espera "x,y x,y x,y x,y" (sup-izq, sup-der, inf-der, inf-izq) o "auto".')
    return puntos


def coeficientes(destino, origen):
    """Coeficientes de Image.transform(PERSPECTIVE): llevan cada punto de destino a su origen."""
    filas, b = [], []
    for (x, y), (u, v) in zip(destino, origen):
        filas += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    return np.linalg.solve(np.array(filas, dtype=float), np.array(b, dtype=float)).tolist()


def proporcion_real(p, centro, lado_foto):
    """Alto/ancho real de la hoja a partir de sus esquinas en la foto (Zhang y He, 2007).

    La perspectiva achica lo que está lejos, así que medir los lados en la foto engaña.
    Supone el centro óptico en el centro de la foto (fotos sin recortar); si no hay
    perspectiva o la cuenta no da una distancia focal razonable, promedia los lados.
    """
    sup_izq, sup_der, inf_der, inf_izq = p
    simple = ((math.dist(sup_izq, inf_izq) + math.dist(sup_der, inf_der))
              / (math.dist(sup_izq, sup_der) + math.dist(inf_izq, inf_der)))
    m1, m2, m3, m4 = (np.array([x, y, 1.0]) for x, y in (sup_izq, sup_der, inf_izq, inf_der))
    k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
    k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
    n2, n3 = k2 * m2 - m1, k3 * m3 - m1
    u0, v0 = centro
    den = n2[2] * n3[2]
    if abs(den) < 1e-12:
        return simple
    f2 = -((n2[0] * n3[0] - (n2[0] * n3[2] + n2[2] * n3[0]) * u0 + den * u0 ** 2)
           + (n2[1] * n3[1] - (n2[1] * n3[2] + n2[2] * n3[1]) * v0 + den * v0 ** 2)) / den
    if not 0.3 * lado_foto < math.sqrt(max(f2, 0)) < 10 * lado_foto:
        return simple
    a_inv = np.linalg.inv(np.array([[math.sqrt(f2), 0, u0], [0, math.sqrt(f2), v0], [0, 0, 1]]))
    b = a_inv.T @ a_inv
    real = math.sqrt((n3 @ b @ n3) / (n2 @ b @ n2))
    return real if abs(real - simple) / simple < 0.35 else simple  # muy lejos: foto recortada, no confiar


def elegir_papel(papel, proporcion, tolerancia):
    """(ancho_mm, alto_mm, nombre) para una proporción alto/ancho."""
    if papel and papel != "auto":
        clave = papel.lower()
        if clave in PAPELES_MM:
            an, al = PAPELES_MM[clave]
            return (al, an, clave) if proporcion < 1 else (an, al, clave)
        try:
            an, al = (float(v) for v in clave.split("x"))
            return an, al, clave
        except ValueError:
            sys.exit(f"--papel no reconocido: {papel} (a4, carta, oficio, legal, a5, auto o ANCHOxALTO en mm)")
    dif, an, al, nombre = min((abs(b / a - proporcion) / proporcion, a, b, n)
                              for n, (x, y) in PAPELES_MM.items() for a, b in ((x, y), (y, x)))
    if dif < tolerancia:
        return an, al, nombre
    return 210.0, round(210 * proporcion, 1), "a medida"


def cmd_ver(a):
    foto = Path(a.foto).resolve()
    img = abrir_imagen(foto)
    dt = carpeta_trabajo(foto, a.trabajo)
    alto_u = ANCHO_U * img.height / img.width
    vista = img.copy()
    vista.thumbnail((1100, 1100))
    lienzo = con_reglas(vista, 0, 0, ANCHO_U, alto_u, menores=False)
    print(f"Foto: {img.width}x{img.height} px (ya girada según EXIF) = {ANCHO_U} x {alto_u:.0f} u")
    esquinas = sugerir_esquinas(img)
    if esquinas:
        ppu = vista.width / ANCHO_U
        pts = [(MARGEN_IZQ + x * ppu, MARGEN_SUP + y * ppu) for x, y in esquinas]
        d = ImageDraw.Draw(lienzo)
        d.line(pts + pts[:1], fill=(230, 0, 0), width=3)
        for n, (px, py) in enumerate(pts, 1):
            d.ellipse([px - 7, py - 7, px + 7, py + 7], outline=(230, 0, 0), width=3)
            d.text((px + 10, py + 6), str(n), fill=(230, 0, 0), font=fuente_reglas(22))
        pares = zip(esquinas, esquinas[1:] + esquinas[:1])
        area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in pares)) / 2
        print("Esquinas sugeridas (1 sup-izq, 2 sup-der, 3 inf-der, 4 inf-izq), en rojo en vista.png:")
        print('  --esquinas "' + " ".join(f"{x:g},{y:g}" for x, y in esquinas) + '"')
        if area > 0.97 * ANCHO_U * alto_u:
            print("  La hoja ocupa casi toda la foto: si ya está derecha, no hace falta --esquinas.")
    else:
        print("No encontré la hoja (¿fondo claro o parecido al papel?): leé las 4 esquinas en la grilla.")
    lienzo.save(dt / "vista.png")
    print(f"Mirá: {dt / 'vista.png'}")


def cmd_preparar(a):
    foto = Path(a.foto).resolve()
    img = abrir_imagen(foto)
    dt = carpeta_trabajo(foto, a.trabajo)
    esquinas = None
    if a.esquinas:
        esquinas = sugerir_esquinas(img) if a.esquinas == "auto" else leer_esquinas(a.esquinas)
        if not esquinas:
            sys.exit("No encontré la hoja: corré 'ver' y pasá las esquinas a mano.")
        k = img.width / ANCHO_U
        p = [(x * k, y * k) for x, y in esquinas]
        ancho = max(math.dist(p[0], p[1]), math.dist(p[3], p[2]))
        prop = proporcion_real(p, (img.width / 2, img.height / 2), max(img.size))
        an, al, papel = elegir_papel(a.papel, prop, 0.06)
        print(f"Proporción estimada de la hoja (alto/ancho): {prop:.3f} -> {papel}"
              + ("  (si sabés el tamaño real, repetí con --papel)" if a.papel == "auto" else ""))
        W, H = round(ancho), round(ancho * al / an)
        img = img.transform((W, H), Image.Transform.PERSPECTIVE,
                            coeficientes([(0, 0), (W, 0), (W, H), (0, H)], p),
                            Image.Resampling.BICUBIC, fillcolor="white")
        # borde de 3 u en blanco: ahí suele colarse un hilo del fondo (la mesa) y no hay contenido
        ImageDraw.Draw(img).rectangle([0, 0, W - 1, H - 1], outline="white", width=max(2, round(3 * W / ANCHO_U)))
    else:
        prop = img.height / img.width
        an, al, papel = elegir_papel(a.papel, prop, 0.03)
        if abs(al / an - prop) / prop > 0.03:  # papel pedido con otra proporción: no deformar la imagen
            print(f"Aviso: la imagen no tiene proporción {papel}; uso {an:g} x {an * prop:.1f} mm.")
            al, papel = round(an * prop, 1), f"{papel} (solo el ancho)"
        alto_px = round(img.width * al / an)
        if alto_px != img.height:
            img = img.resize((img.width, alto_px), Image.Resampling.LANCZOS)  # estira 3 % como mucho
    if a.limpiar:
        img = limpiar(img)
    if img.width > ANCHO_BASE_MAX:
        img = img.resize((ANCHO_BASE_MAX, round(ANCHO_BASE_MAX * img.height / img.width)),
                         Image.Resampling.LANCZOS)
    img.save(dt / "base.png")
    alto_u = round(ANCHO_U * al / an, 1)
    ppu = img.width / ANCHO_U

    vista = img.resize((ANCHO_U, round(ANCHO_U * img.height / img.width)), Image.Resampling.LANCZOS)
    con_reglas(vista, 0, 0, ANCHO_U, alto_u, menores=False).save(dt / "grilla.png")
    n = a.franjas or max(1, math.ceil(alto_u / ALTO_FRANJA_U))
    paso = alto_u / n
    franjas = []
    for i in range(n):
        y0, y1 = max(0.0, i * paso - SOLAPE_U), min(alto_u, (i + 1) * paso + SOLAPE_U)
        rec = img.crop((0, round(y0 * ppu), img.width, round(y1 * ppu)))
        rec = rec.resize((ANCHO_FRANJA, max(1, round(ANCHO_FRANJA * rec.height / rec.width))),
                         Image.Resampling.LANCZOS)
        nombre = f"franja_{i + 1:02d}.png"
        con_reglas(rec, 0, y0, ANCHO_U, y1).save(dt / nombre)
        franjas.append({"archivo": nombre, "y0": round(y0, 1), "y1": round(y1, 1)})

    previo = leer_json(dt / "info.json") if (dt / "info.json").exists() else {}
    pdf = Path(previo["pdf"]) if previo.get("pdf") else foto.with_suffix(".pdf")
    numero = 1
    while not previo.get("pdf") and pdf.exists():  # no pisar un PDF que ya tenía el usuario
        pdf = foto.with_name(f"{foto.stem}-{numero}.pdf")
        numero += 1
    guardar_json(dt / "info.json", {
        "foto": str(foto), "pdf": str(pdf), "papel": papel, "ancho_mm": an, "alto_mm": al,
        "ancho_u": ANCHO_U, "alto_u": alto_u, "esquinas": esquinas, "limpiada": a.limpiar,
        "franjas": franjas})
    print(f"Trabajo: {dt}")
    print(f"Página: {papel}, {an:g} x {al:g} mm = {ANCHO_U} x {alto_u:g} u (1 u = {an / ANCHO_U:.2f} mm)")
    print(f"Mirá grilla.png y después, en orden, franja_01.png a franja_{n:02d}.png "
          f"(cada una repite {SOLAPE_U} u de la anterior).")
    if (dt / "layout.json").exists():
        print("Ojo: layout.json ya existía (de una vuelta anterior); si cambiaste esquinas o papel, rehacelo.")
    print(f"Escribí {dt / 'layout.json'} y armá el PDF con construir.py. Salida: {pdf}")


def cmd_zoom(a):
    dt = Path(a.trabajo)
    img = Image.open(dt / "base.png")
    ppu = img.width / ANCHO_U
    x0, y0, x1, y1 = a.caja
    rec = img.crop((round(x0 * ppu), round(y0 * ppu), round(x1 * ppu), round(y1 * ppu)))
    escala = min(1400 / rec.width, 1000 / rec.height)
    rec = rec.resize((max(1, round(rec.width * escala)), max(1, round(rec.height * escala))),
                     Image.Resampling.LANCZOS)
    salida = dt / f"zoom_{x0:g}_{y0:g}.png"
    con_reglas(rec, x0, y0, x1, y1).save(salida)
    print(salida)


def cmd_buscar(a):
    """Lista las imágenes más nuevas de las carpetas donde suelen caer fotos y capturas."""
    raices = [Path.home()] + ([Path(os.environ["OneDrive"])] if os.environ.get("OneDrive") else [])
    subcarpetas = ["Downloads", "Descargas", "Desktop", "Escritorio", "Pictures", "Imágenes",
                   "Pictures/Screenshots", "Pictures/Capturas de pantalla", "Imágenes/Capturas de pantalla",
                   "Documents", "Documentos"]
    vistas = {}
    for carpeta in [r / s for r in raices for s in subcarpetas] + [Path.cwd()]:
        if carpeta.is_dir():
            for p in carpeta.iterdir():
                if p.suffix.lower() in EXTENSIONES and p.is_file():
                    vistas[p.resolve()] = p.stat().st_mtime
    if not vistas:
        print("No encontré imágenes en Descargas, Escritorio, Imágenes ni Documentos.")
    for p, t in sorted(vistas.items(), key=lambda kv: -kv[1])[:a.cantidad]:
        print(f"{time.strftime('%d/%m %H:%M', time.localtime(t))}  {p}")


def main():
    salida_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("ver", help="grilla sobre la foto y esquinas sugeridas")
    v.add_argument("foto")
    v.add_argument("--trabajo", help="carpeta de trabajo (por defecto, una temporal por foto)")
    p = sub.add_parser("preparar", help="enderezar, limpiar y cortar en franjas")
    p.add_argument("foto")
    p.add_argument("--esquinas", help='"auto" o "x,y x,y x,y x,y" en u de la foto (sup-izq, sup-der, inf-der, inf-izq)')
    p.add_argument("--papel", default="auto", help="a4, carta, oficio, legal, a5, auto o ANCHOxALTO en mm")
    p.add_argument("--limpiar", action="store_true", help="papel blanco parejo (fotos de papel)")
    p.add_argument("--franjas", type=int, help="cantidad de franjas (por defecto, una cada ~180 u)")
    p.add_argument("--trabajo")
    z = sub.add_parser("zoom", help="ampliar una zona de base.png")
    z.add_argument("trabajo")
    z.add_argument("caja", nargs=4, type=float, metavar=("x0", "y0", "x1", "y1"))
    b = sub.add_parser("buscar", help="últimas imágenes en las carpetas habituales")
    b.add_argument("--cantidad", type=int, default=10)
    a = ap.parse_args()
    {"ver": cmd_ver, "preparar": cmd_preparar, "zoom": cmd_zoom, "buscar": cmd_buscar}[a.cmd](a)


if __name__ == "__main__":
    main()
