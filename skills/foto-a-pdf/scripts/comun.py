"""Utilidades compartidas: coordenadas, imágenes, máscara de tinta y reglas.

Toda la skill mide en "u": el ancho de la página mide 1000 u, el origen está
arriba a la izquierda y la y crece hacia abajo.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ANCHO_U = 1000
MARGEN_IZQ, MARGEN_SUP = 50, 24  # lugar para las reglas en las imágenes de trabajo

PAPELES_MM = {
    "a4": (210, 297),
    "a5": (148, 210),
    "carta": (215.9, 279.4),
    "oficio": (216, 340),
    "legal": (215.9, 355.6),
}


def salida_utf8():
    """Evita errores con acentos al imprimir desde consolas de Windows."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def abrir_imagen(ruta):
    """Abre la imagen en RGB y girada según el EXIF (las fotos de celular suelen venir acostadas)."""
    try:
        from pillow_heif import register_heif_opener  # opcional: fotos .heic de iPhone
        register_heif_opener()
    except ImportError:
        pass
    img = ImageOps.exif_transpose(Image.open(ruta))
    if img.mode in ("RGBA", "LA", "P", "PA"):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, "white")
        fondo.paste(img, mask=img.getchannel("A"))
        return fondo
    return img.convert("RGB")


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def guardar_json(ruta, datos):
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def otsu(a):
    """Umbral que mejor separa claros de oscuros en un array uint8."""
    p = np.bincount(a.ravel(), minlength=256) / a.size
    w = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    return int(np.argmax((mu[-1] * w - mu) ** 2 / (w * (1 - w) + 1e-12)))


def fondo_papel(img):
    """Iluminación del papel sin la tinta: máximo local sobre la imagen achicada, suavizado."""
    chica = img.resize((max(1, img.width // 16), max(1, img.height // 16)), Image.Resampling.BILINEAR)
    a = np.asarray(chica.filter(ImageFilter.MaxFilter(9)), dtype=np.float32)
    # Una zona oscura grande (logo, foto) no es sombra: el papel nunca es más oscuro que esto.
    a = np.maximum(a, np.percentile(a, 90, axis=(0, 1)) * 0.6)
    chica = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
    return chica.resize(img.size, Image.Resampling.BILINEAR)


def limpiar(img):
    """Empareja la luz: el papel queda blanco parejo y la tinta conserva su color."""
    a = np.asarray(img, dtype=np.float32)
    f = np.asarray(fondo_papel(img), dtype=np.float32)
    return Image.fromarray(np.clip(a / np.maximum(f, 1) * 255 * 1.03, 0, 255).astype(np.uint8))


def mascara_tinta(gris, factor=0.72):
    """True donde hay tinta: más oscuro que `factor` veces el papel de alrededor. Con fondo oscuro, invierte."""
    if np.median(np.asarray(gris)) < 110:
        gris = ImageOps.invert(gris)
    a = np.asarray(gris, dtype=np.float32)
    return a < np.asarray(fondo_papel(gris), dtype=np.float32) * factor


def fuente_reglas(tam=13):
    for nombre in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default(size=tam)


def con_reglas(img, x0, y0, x1, y1, menores=True):
    """Devuelve img con reglas en u (arriba, izquierda y derecha) y guías azules tenues.

    img muestra la zona [x0, x1] x [y0, y1] de la página. Las etiquetas quedan a
    45 px o más entre sí; con menores=True suma guías horizontales finas entre ellas.
    """
    w, h = img.size
    ppu = w / (x1 - x0)
    paso = next((p for p in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if p * ppu >= 45), 1000)
    sub = paso / 5
    lienzo = Image.new("RGB", (w + 2 * MARGEN_IZQ, h + MARGEN_SUP + 6), "white")
    lienzo.paste(img, (MARGEN_IZQ, MARGEN_SUP))
    d = ImageDraw.Draw(lienzo, "RGBA")
    f = fuente_reglas()
    azul = (0, 120, 255)
    for k in range(math.ceil(x0 / sub - 1e-9), math.floor(x1 / sub + 1e-9) + 1):
        px = MARGEN_IZQ + (k * sub - x0) * ppu
        mayor = k % 5 == 0
        d.line([(px, MARGEN_SUP - (9 if mayor else 4)), (px, MARGEN_SUP - 1)], fill="black")
        if mayor:
            d.line([(px, MARGEN_SUP), (px, MARGEN_SUP + h)], fill=azul + (70,))
            d.text((px, MARGEN_SUP - 11), f"{k * sub:g}", fill="black", font=f, anchor="ms")
    for k in range(math.ceil(y0 / sub - 1e-9), math.floor(y1 / sub + 1e-9) + 1):
        py = MARGEN_SUP + (k * sub - y0) * ppu
        mayor = k % 5 == 0
        largo = 9 if mayor else 4
        d.line([(MARGEN_IZQ - largo, py), (MARGEN_IZQ - 1, py)], fill="black")
        d.line([(MARGEN_IZQ + w, py), (MARGEN_IZQ + w + largo, py)], fill="black")
        if mayor or menores:
            d.line([(MARGEN_IZQ, py), (MARGEN_IZQ + w, py)], fill=azul + (80 if mayor else 28,))
        if mayor:
            d.text((MARGEN_IZQ - 11, py), f"{k * sub:g}", fill="black", font=f, anchor="rm")
            d.text((MARGEN_IZQ + w + 11, py), f"{k * sub:g}", fill="black", font=f, anchor="lm")
    return lienzo
