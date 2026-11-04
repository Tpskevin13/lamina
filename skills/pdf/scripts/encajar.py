"""Ajusta las cajas estimadas a ojo contra la tinta real de la foto.

Claude ubica cada elemento con unas pocas u de error; acá se mide sobre la imagen:
línea base, alto y bordes de cada renglón, y posición y grosor de líneas, recuadros
y bordes de tabla. No modifica layout.json: el ajuste se rehace en cada armado.
"""
import copy

import numpy as np
from PIL import Image

from comun import ANCHO_U, mascara_tinta

PPU = 2  # se mide a 2 px por u


def mascara(base):
    alto = round(ANCHO_U * PPU * base.height / base.width)
    return mascara_tinta(base.convert("L").resize((ANCHO_U * PPU, alto), Image.Resampling.BILINEAR))


def caja(el):
    x0, y0, x1, y1 = (float(v) for v in el["caja"])
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def corridas(v):
    """[(inicio, fin)) de cada tramo True consecutivo de un vector."""
    d = np.diff(np.concatenate(([0], np.asarray(v, dtype=np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _ventana(m, x0, y0, x1, y1):
    H, W = m.shape
    X0, X1 = max(0, int(x0 * PPU)), min(W, int(np.ceil(x1 * PPU)))
    Y0, Y1 = max(0, int(y0 * PPU)), min(H, int(np.ceil(y1 * PPU)))
    return m[Y0:Y1, X0:X1], X0, Y0


def _agrupar(tramos, hueco):
    """Une los tramos separados por menos de `hueco` px."""
    grupos = []
    for a, b in tramos:
        if grupos and a - grupos[-1][1] < hueco:
            grupos[-1][1] = b
        else:
            grupos.append([a, b])
    return grupos


def perfil_vertical(filas, base_est, tolerancia, alto_est=None):
    """(tope, base) de un renglón a partir de la tinta por fila, o None.

    base: borde de abajo del cuerpo del renglón (las filas densas) más cercano a base_est.
    tope: se sube mientras siga habiendo tinta pegada (mayúsculas y letras altas).
    """
    if filas.max() < 3:
        return None
    a, base = min(corridas(filas > 0.35 * filas.max()), key=lambda t: abs(t[1] - base_est))
    if abs(base - base_est) > tolerancia:
        return None
    piso = max(1.0, 0.04 * filas[a:base].max())
    tope = a
    while tope > 0 and filas[tope - 1] >= piso:
        tope -= 1
    if alto_est and not 0.8 * alto_est <= base - tope <= 1.25 * alto_est:
        tope = max(0, int(round(base - alto_est)))  # sin letras altas o pegado a otro renglón: el estimado
    return tope, base


def _filas(win):
    filas = win.sum(axis=1).astype(float)
    filas[filas > 0.6 * win.shape[1]] = 0  # filas que son reglas o subrayados
    return filas


def texto(m, cj, palabras=0):
    """Mide un renglón sobre la tinta.

    Devuelve (caja [x0, tope de mayúsculas, x1, línea base], palabras) o (None, None).
    `palabras` es [[x0, x1], ...] de cada palabra si en la foto se distinguen tantas
    como tiene el texto; así el PDF las pone donde están (sirve para justificado y tabulados).
    """
    x0, y0, x1, y1 = cj
    h = max(y1 - y0, 2.0)
    my, mx = max(5.0, 0.6 * h), 12.0
    win, X0, Y0 = _ventana(m, x0 - mx, y0 - my, x1 + mx, y1 + my)
    if win.shape[0] < 4 or win.shape[1] < 4:
        return None, None
    win = win & ~(win.mean(axis=0) > 0.8)[None, :]  # columnas que son reglas verticales
    base_est = y1 * PPU - Y0
    r = perfil_vertical(_filas(win), base_est, my * PPU, h * PPU)
    if not r:
        return None, None
    tope, base = r
    # bordes: grupos de tinta de esas filas; quedan los que caen mayormente dentro de la caja
    # (así no se suma el borde de una casilla o una palabra vecina)
    xa, xb = x0 * PPU - X0, x1 * PPU - X0
    dentro = [g for g in _agrupar(corridas(win[tope:base].any(axis=0)), 0.45 * h * PPU)
              if min(g[1], xb) - max(g[0], xa) > 0.5 * (g[1] - g[0])]
    if not dentro:
        return None, None
    c0, c1 = dentro[0][0], dentro[-1][1]
    # segunda pasada, solo con las columnas del renglón: lo de al lado ya no tira el tope ni la base
    r = perfil_vertical(_filas(win[:, c0:c1]), base_est, my * PPU, h * PPU)
    if r:
        tope, base = r
    tinta = win[tope:base].any(axis=0)
    nueva = [round((X0 + c0) / PPU, 1), round((Y0 + tope) / PPU, 1),
             round((X0 + c1) / PPU, 1), round((Y0 + base) / PPU, 1)]
    # 4) palabras: huecos de más de 0,22 del alto de letra (entre letras casi nunca hay tanto)
    pal = _agrupar(corridas(tinta[c0:c1]), 0.22 * h * PPU)
    if palabras < 2 or len(pal) != palabras:
        return nueva, None
    return nueva, [[round((X0 + c0 + p0) / PPU, 1), round((X0 + c0 + p1) / PPU, 1)] for p0, p1 in pal]


def linea_h(m, y, xa, xb, umbral=0.5, r=6.0):
    """(y del centro, grosor) de la línea horizontal más marcada cerca de y, o None.

    Para verticales se usa con la máscara transpuesta (m.T) y los ejes cambiados.
    """
    win, _, Y0 = _ventana(m, min(xa, xb), y - r, max(xa, xb), y + r)
    if win.shape[0] < 2 or win.shape[1] < 4:
        return None
    frac = win.mean(axis=1)
    k = int(frac.argmax())
    if frac[k] < umbral:
        return None
    a, b = k, k + 1
    while a > 0 and frac[a - 1] >= umbral:
        a -= 1
    while b < len(frac) and frac[b] >= umbral:
        b += 1
    return (Y0 + (a + b) / 2) / PPU, (b - a) / PPU


def extremos_h(m, y, grosor, xa, xb, r=10.0):
    """Dónde empieza y termina de verdad una línea horizontal continua, o None."""
    g = max(grosor, 1.0) / 2
    win, X0, _ = _ventana(m, min(xa, xb) - r, y - g, max(xa, xb) + r, y + g)
    if win.size == 0:
        return None
    tramos = []
    for c0, c1 in corridas(win.any(axis=0)):
        if tramos and c0 - tramos[-1][1] <= 2 * PPU:  # une cortes chicos
            tramos[-1][1] = c1
        else:
            tramos.append([c0, c1])
    a, b = min(xa, xb) * PPU - X0, max(xa, xb) * PPU - X0
    mejor = max(tramos, key=lambda t: min(t[1], b) - max(t[0], a), default=None)
    if mejor is None or min(mejor[1], b) - max(mejor[0], a) < 0.5 * (b - a):
        return None
    # cada punta se corrige solo si cae cerca de la estimada: una línea algo inclinada en la foto
    # se sale de la franja medida y parecería más corta (o se pegaría a otra línea y más larga)
    tol = max(4.0, 0.05 * abs(xb - xa))
    e0, e1 = (X0 + mejor[0]) / PPU, (X0 + mejor[1]) / PPU
    lo, hi = min(xa, xb), max(xa, xb)
    return (e0 if abs(e0 - lo) <= tol else lo), (e1 if abs(e1 - hi) <= tol else hi)


def _linea(m, el):
    (xa, ya), (xb, yb) = el["de"], el["a"]
    punteada = el.get("trazo", "solido") != "solido"
    umbral = 0.25 if punteada else 0.5
    if abs(yb - ya) <= 0.05 * abs(xb - xa):      # horizontal
        r = linea_h(m, (ya + yb) / 2, xa, xb, umbral)
        if not r:
            return False
        y, g = r
        e = None if punteada else extremos_h(m, y, g, xa, xb)
        if e:
            xa, xb = e if xa <= xb else e[::-1]
        el["de"], el["a"] = [round(xa, 1), round(y, 1)], [round(xb, 1), round(y, 1)]
    elif abs(xb - xa) <= 0.05 * abs(yb - ya):    # vertical
        r = linea_h(m.T, (xa + xb) / 2, ya, yb, umbral)
        if not r:
            return False
        x, g = r
        e = None if punteada else extremos_h(m.T, x, g, ya, yb)
        if e:
            ya, yb = e if ya <= yb else e[::-1]
        el["de"], el["a"] = [round(x, 1), round(ya, 1)], [round(x, 1), round(yb, 1)]
    else:
        return False
    if "grosor" not in el and 0.4 <= g <= 8:
        el["grosor"] = round(g * 0.8, 2)  # la foto engrosa un poco las líneas
    return True


def _recuadro(m, el):
    x0, y0, x1, y1 = caja(el)
    r = min(6.0, 0.3 * min(x1 - x0, y1 - y0))
    lados = [linea_h(m, y0, x0, x1, r=r), linea_h(m, y1, x0, x1, r=r),
             linea_h(m.T, x0, y0, y1, r=r), linea_h(m.T, x1, y0, y1, r=r)]
    if lados[0]: y0 = lados[0][0]
    if lados[1]: y1 = lados[1][0]
    if lados[2]: x0 = lados[2][0]
    if lados[3]: x1 = lados[3][0]
    el["caja"] = [round(v, 1) for v in (x0, y0, x1, y1)]
    return any(lados)


def _tabla(m, el):
    xs, ys = [float(v) for v in el["columnas"]], [float(v) for v in el["filas"]]
    bordes = el.get("bordes", "todos")
    ry = min(6.0, 0.3 * min(b - a for a, b in zip(ys, ys[1:])))  # no saltar a la línea vecina
    rx = min(6.0, 0.3 * min(b - a for a, b in zip(xs, xs[1:])))
    externos = bordes == "externos"
    filas = range(len(ys)) if bordes in ("todos", "horizontales") else ((0, len(ys) - 1) if externos else ())
    columnas = range(len(xs)) if bordes == "todos" else ((0, len(xs) - 1) if externos else ())
    hechos = 0
    for i in filas:
        r = linea_h(m, ys[i], xs[0], xs[-1], r=ry)
        if r:
            ys[i], hechos = round(r[0], 1), hechos + 1
    for j in columnas:
        r = linea_h(m.T, xs[j], ys[0], ys[-1], r=rx)
        if r:
            xs[j], hechos = round(r[0], 1), hechos + 1
    el["columnas"], el["filas"] = xs, ys
    return hechos > 0


def encajar_todo(elementos, base):
    """Devuelve (copia ajustada de los elementos, resumen en texto)."""
    m = mascara(base)
    nuevos = copy.deepcopy(elementos)
    cuenta = {"textos": [0, 0], "palabras ubicadas": [0, 0], "líneas": [0, 0], "bordes": [0, 0]}
    movidos = []
    for n, el in enumerate(nuevos, 1):
        if not el.get("encajar", True):
            continue
        tipo = el.get("tipo")
        try:
            if tipo == "texto" and "caja" in el and not int(el.get("giro", 0)) % 360:
                cuenta["textos"][1] += 1
                nueva, palabras = texto(m, caja(el), len(str(el.get("texto", "")).split()))
                if nueva:
                    cuenta["textos"][0] += 1
                    d = max(abs(p - q) for p, q in zip(nueva, caja(el)))
                    if d > 3:
                        movidos.append(f"#{n} ({d:.0f} u)")
                    el["caja"] = nueva
                    if palabras:
                        el["_palabras"] = palabras
                        cuenta["palabras ubicadas"][0] += 1
            elif tipo == "linea":
                cuenta["líneas"][1] += 1
                cuenta["líneas"][0] += _linea(m, el)
            elif tipo in ("rect", "casilla") and el.get("borde", "#000000"):
                cuenta["bordes"][1] += 1
                cuenta["bordes"][0] += _recuadro(m, el)
            elif tipo == "tabla" and el.get("bordes", "todos") != "ninguno":
                cuenta["bordes"][1] += 1
                cuenta["bordes"][0] += _tabla(m, el)
        except (KeyError, TypeError, ValueError):
            pass  # elemento mal formado: lo reporta construir.py al dibujarlo
    cuenta["palabras ubicadas"][1] = cuenta["textos"][1]
    resumen = ", ".join(f"{k} {a}/{t}" for k, (a, t) in cuenta.items() if t)
    if movidos:
        resumen += " · movidos más de 3 u: " + ", ".join(movidos[:20]) + (" …" if len(movidos) > 20 else "")
    return nuevos, resumen or "nada para ajustar"
