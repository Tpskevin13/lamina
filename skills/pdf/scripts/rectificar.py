"""Endereza las líneas de un dibujo: cada una se lleva al ángulo permitido más cercano y las puntas
que casi tocan otra línea se estiran o recortan hasta tocarla (esquinas cerradas, sin huecos).

Ángulos en grados como se ven en la hoja: 0 = horizontal, 90 = vertical, antihorario.
"""
import math

import numpy as np

PRESETS = {
    "orto": [0, 90],                      # planos, formularios, tablas
    "orto45": [0, 45, 90, 135],           # además chaflanes e inclinadas a 45° (por defecto)
    "iso": [0, 30, 90, 150],              # isométrica (ejes a 30°, 90° y 150°)
    "caballera": [0, 45, 90, 135],        # perspectiva caballera
    "dimetrica": [0, 7, 42, 90, 138, 173],  # dimétrica normalizada (7° y 42°)
    "libre": [],                          # no tocar los ángulos
}
UNION_U = 3.0  # distancia máxima (u) para considerar que una punta toca otra línea


def angulos_permitidos(valor):
    if valor is None:
        return PRESETS["orto45"]
    if isinstance(valor, str):
        if valor not in PRESETS:
            raise ValueError(f"angulos: {valor!r} no es {', '.join(PRESETS)} ni una lista de grados")
        return PRESETS[valor]
    return [float(v) for v in valor]


def _angulo(a, b):
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 180


def _dif(a, b):
    d = abs(a - b) % 180
    return min(d, 180 - d)


def _enderezar(el, permitidos, tol):
    a, b = [float(v) for v in el["de"]], [float(v) for v in el["a"]]
    if math.dist(a, b) < 1 or not permitidos:
        return False
    ang = _angulo(a, b)
    obj = min(permitidos, key=lambda p: _dif(ang, p))
    if _dif(ang, obj) > tol or _dif(ang, obj) < 1e-3:
        return False
    ux, uy = math.cos(math.radians(obj)), -math.sin(math.radians(obj))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    for k, p in (("de", a), ("a", b)):  # se proyecta cada punta sobre la recta que pasa por el medio
        t = (p[0] - mx) * ux + (p[1] - my) * uy
        el[k] = [round(mx + t * ux, 2), round(my + t * uy, 2)]
    return True


def _unir(lineas, originales):
    """Cierra esquinas y uniones sin cambiar el ángulo de ninguna línea.

    Las puntas que están a menos de UNION_U entre sí forman un vértice; una punta pegada al medio de
    otra línea (una T) también cuenta como apoyada en ella. Después se busca, por mínimos cuadrados,
    dónde poner cada vértice y cada recta (de ángulo fijo) para que todo vértice caiga sobre todas
    sus líneas moviéndose lo menos posible. Así tres aristas de un cubo isométrico salen del mismo punto.
    """
    if not lineas:
        return 0
    puntas = originales  # los vértices se arman con las puntas como estaban, antes de enderezar
    padre = list(range(len(puntas)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(len(puntas)):
        for j in range(i + 1, len(puntas)):
            if j != i ^ 1 and math.dist(puntas[i], puntas[j]) <= UNION_U:
                padre[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(len(puntas)):
        grupos.setdefault(raiz(i), []).append(i)
    nodos = list(grupos.values())
    nodo_de = {i: n for n, g in enumerate(nodos) for i in g}
    pos0 = np.array([np.mean([puntas[i] for i in g], axis=0) for g in nodos])
    normal = []
    for el in lineas:
        t = math.radians(_angulo(el["de"], el["a"]))
        normal.append((math.sin(t), math.cos(t)))  # perpendicular a (cos t, -sin t) en la hoja
    apoyos = {(i // 2, nodo_de[i]) for i in range(len(puntas))}
    for n, p in enumerate(pos0):  # T: un vértice suelto sobre el tramo de otra línea
        propias = {i // 2 for i in nodos[n]}
        for k, el in enumerate(lineas):
            if k in propias or any(_dif(_angulo(el["de"], el["a"]), _angulo(lineas[q]["de"], lineas[q]["a"])) < 15
                                   for q in propias):
                continue
            a, b = np.array(el["de"], float), np.array(el["a"], float)
            d = b - a
            u = float(np.dot(p - a, d) / max(np.dot(d, d), 1e-9))
            if abs(float(np.dot(p - a, normal[k]))) <= UNION_U and -0.02 <= u <= 1.02:
                apoyos.add((k, n))
    nn, nl = len(nodos), len(lineas)
    filas, lado = [], []
    for k, n in apoyos:  # n·p_n − c_k = 0
        f = np.zeros(2 * nn + nl)
        f[2 * n], f[2 * n + 1], f[2 * nn + k] = normal[k][0], normal[k][1], -1
        filas.append(f); lado.append(0.0)
    peso = 0.05  # quedarse cerca de lo medido
    for n, p in enumerate(pos0):
        for e in (0, 1):
            f = np.zeros(2 * nn + nl)
            f[2 * n + e] = peso
            filas.append(f); lado.append(peso * p[e])
    sol = np.linalg.lstsq(np.array(filas), np.array(lado), rcond=None)[0]
    movidas = 0
    for k, el in enumerate(lineas):
        nx, ny = normal[k]
        c = sol[2 * nn + k]
        for e, clave in ((2 * k, "de"), (2 * k + 1, "a")):
            p = sol[2 * nodo_de[e]:2 * nodo_de[e] + 2]
            q = p - (nx * p[0] + ny * p[1] - c) * np.array([nx, ny])  # sobre la recta de la línea
            if math.dist(q, el[clave]) > 0.05:
                movidas += 1
            el[clave] = [round(float(q[0]), 2), round(float(q[1]), 2)]
    return movidas


def rectificar(elementos, angulos=None, tolerancia=4.0):
    """Endereza en el lugar las líneas de `elementos`. Devuelve un resumen en texto."""
    permitidos = angulos_permitidos(angulos)
    lineas = [el for el in elementos if el.get("tipo") == "linea" and el.get("rectificar", True)
              and "de" in el and "a" in el]
    if not permitidos:
        return "ángulos libres"
    originales = [[float(v) for v in el[k]] for el in lineas for k in ("de", "a")]
    n = sum(_enderezar(el, permitidos, float(tolerancia)) for el in lineas)
    unidas = _unir(lineas, originales)
    return f"{n} líneas enderezadas a {', '.join(f'{p:g}°' for p in permitidos)}, {unidas} puntas unidas"
