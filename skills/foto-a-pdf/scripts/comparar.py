"""Compara el PDF armado con la foto: rojo = está en la foto y falta en el PDF, celeste = sobra en el PDF.

  python comparar.py TRABAJO PDF [número de página, desde 1]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from comun import ANCHO_U, con_reglas, fondo_papel, leer_json, mascara_tinta, salida_utf8

PPU = 2           # se compara a 2 px por u
UMBRAL = 0.85     # por debajo de esto, la franja se marca para revisar


def renderizar(pdf, pagina, ancho_px):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        hoja = doc[pagina]
        return hoja.render(scale=ancho_px / hoja.get_width()).to_pil().convert("RGB")
    finally:
        doc.close()


def dilatar(m, k=7):
    """Engrosa la tinta 1,5 u: tolera diferencias chicas de tipografía."""
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(k))) > 0


def normalizar(gris):
    """Papel blanco parejo, para que la superposición se lea bien aunque la foto no esté limpia."""
    a = np.asarray(gris, dtype=np.float32) / np.maximum(np.asarray(fondo_papel(gris), dtype=np.float32), 1)
    return Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))


def zonas(m, celda=8, maximo=10):
    """Agrupa los píxeles marcados en cajas [x0, y0, x1, y1] en u, de la más pesada a la más liviana."""
    c = celda * PPU
    H, W = m.shape
    fh, fw = -(-H // c), -(-W // c)
    p = np.zeros((fh * c, fw * c), dtype=bool)
    p[:H, :W] = m
    cuenta = p.reshape(fh, c, fw, c).sum(axis=(1, 3))
    marcada = cuenta >= max(6, 0.03 * c * c)
    visto = np.zeros_like(marcada)
    res = []
    for i, j in zip(*np.nonzero(marcada)):
        if visto[i, j]:
            continue
        visto[i, j] = True
        pila, celdas = [(i, j)], []
        while pila:
            a, b = pila.pop()
            celdas.append((a, b))
            for na in (a - 1, a, a + 1):
                for nb in (b - 1, b, b + 1):
                    if 0 <= na < fh and 0 <= nb < fw and marcada[na, nb] and not visto[na, nb]:
                        visto[na, nb] = True
                        pila.append((na, nb))
        if len(celdas) >= 2:
            ii, jj = zip(*celdas)
            peso = int(sum(cuenta[a, b] for a, b in celdas))
            res.append((peso, [int(min(jj)) * celda, int(min(ii)) * celda,
                               (int(max(jj)) + 1) * celda, (int(max(ii)) + 1) * celda]))
    res.sort(key=lambda t: -t[0])
    return [z for _, z in res[:maximo]]


def comparar(trabajo, pdf, pagina=0):
    trabajo = Path(trabajo)
    info = leer_json(trabajo / "info.json")
    base = Image.open(trabajo / "base.png").convert("L")
    W = ANCHO_U * PPU
    H = round(W * base.height / base.width)
    orig = normalizar(base.resize((W, H), Image.Resampling.BILINEAR))
    rend = renderizar(pdf, pagina, W).convert("L").resize((W, H), Image.Resampling.BILINEAR)
    mo, mp = mascara_tinta(orig, 0.8), mascara_tinta(rend)  # la foto es borrosa: se le acepta tinta más clara
    falta, sobra = mo & ~dilatar(mp), mp & ~dilatar(mo)

    # Foto en el verde y azul, PDF en el rojo: lo que está solo en la foto se ve rojo,
    # lo que está solo en el PDF se ve celeste y lo que coincide, oscuro.
    sup = Image.merge("RGB", (rend, orig, orig))
    alto_u = H / PPU
    vista = sup.resize((ANCHO_U, round(alto_u)), Image.Resampling.LANCZOS)
    con_reglas(vista, 0, 0, ANCHO_U, alto_u, menores=False).save(trabajo / "comparacion.png")
    rend.resize((ANCHO_U, round(alto_u)), Image.Resampling.LANCZOS).save(trabajo / "pdf.png")

    franjas = []
    for k, f in enumerate(info["franjas"], 1):
        a, b = int(f["y0"] * PPU), min(H, int(f["y1"] * PPU))
        vacia = mo[a:b].sum() < 150 and mp[a:b].sum() < 150
        franjas.append({"n": k, "y0": f["y0"], "y1": f["y1"], "vacia": bool(vacia),
                        "cobertura": 1 - falta[a:b].sum() / max(mo[a:b].sum(), 1),
                        "precision": 1 - sobra[a:b].sum() / max(mp[a:b].sum(), 1)})
        rec = sup.crop((0, a, W, b))
        rec = rec.resize((1400, max(1, round(1400 * rec.height / W))), Image.Resampling.LANCZOS)
        con_reglas(rec, 0, a / PPU, ANCHO_U, b / PPU).save(trabajo / f"comp_franja_{k:02d}.png")
    return {"trabajo": str(trabajo),
            "cobertura": 1 - falta.sum() / max(mo.sum(), 1),
            "precision": 1 - sobra.sum() / max(mp.sum(), 1),
            "franjas": franjas, "falta": zonas(falta), "sobra": zonas(sobra)}


def imprimir(r, numero):
    print(f"Página {numero}: cobertura {r['cobertura']:.0%} · precisión {r['precision']:.0%}  "
          "(cobertura = tinta de la foto que aparece en el PDF; precisión = tinta del PDF que está en la foto)")
    for f in r["franjas"]:
        rango = f"  franja {f['n']:02d} (y {f['y0']:.0f}-{f['y1']:.0f}): "
        if f["vacia"]:
            print(rango + "vacía en la foto y en el PDF")
            continue
        marca = "  <- revisar" if min(f["cobertura"], f["precision"]) < UMBRAL else ""
        print(rango + f"{f['cobertura']:.0%} / {f['precision']:.0%}{marca}")
    cajas = lambda zs: "  ".join("[" + " ".join(f"{v:g}" for v in z) + "]" for z in zs)
    if r["falta"]:
        print("  Falta en el PDF (rojo), x0 y0 x1 y1:", cajas(r["falta"]))
    if r["sobra"]:
        print("  Sobra en el PDF (celeste), x0 y0 x1 y1:", cajas(r["sobra"]))
    print(f"  Imágenes en {r['trabajo']}: comparacion.png, comp_franja_XX.png, pdf.png")


if __name__ == "__main__":
    salida_utf8()
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    num = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    imprimir(comparar(sys.argv[1], sys.argv[2], num - 1), num)
