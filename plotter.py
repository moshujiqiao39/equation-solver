"""Sample equations and return an adaptive plot description."""

from __future__ import annotations

import math
import re

import sympy as sp
from sympy.core.function import AppliedUndef


def _num(value: float | None):
    if value is None:
        return None
    if value != value or abs(value) == float("inf"):
        return None
    return float(f"{value:.8g}")


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 10000 or abs(value) < 0.001:
        return f"{value:.3g}"
    text = f"{value:.4g}"
    return text


def as_float(expr):
    if expr is None:
        return None
    if getattr(expr, "free_symbols", None):
        return None
    try:
        if getattr(expr, "is_real", None) is False:
            return None
        value = complex(sp.N(expr, 16))
    except Exception:
        return None
    if abs(value.imag) > 1e-7:
        return None
    if value.real != value.real or abs(value.real) > 1e9:
        return None
    return float(value.real)


def _lambdify(expr, symbols):
    expr = sp.sympify(expr)
    return sp.lambdify(
        symbols,
        expr,
        modules=[{"Abs": abs, "log": math.log, "log10": math.log10, "Heaviside": lambda z: 1.0 if z > 0 else 0.0}, "math"],
    )


def _eval1(func, x):
    try:
        value = func(float(x))
    except Exception:
        return None
    if isinstance(value, complex):
        if abs(value.imag) > 1e-7:
            return None
        value = value.real
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value or abs(value) > 1e8:
        return None
    return value


def _eval2(func, x, y):
    try:
        value = func(float(x), float(y))
    except Exception:
        return None
    if isinstance(value, complex):
        if abs(value.imag) > 1e-6:
            return None
        value = value.real
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value or abs(value) > 1e12:
        return None
    return value


def _pad(lo: float, hi: float, ratio: float = 0.14, minimum: float = 0.8):
    if not math.isfinite(lo) or not math.isfinite(hi):
        return -6.0, 6.0
    if hi < lo:
        lo, hi = hi, lo
    span = hi - lo
    if span < 1e-6:
        lo -= minimum / 2
        hi += minimum / 2
        span = hi - lo
    extra = max(span * ratio, minimum * 0.08)
    return lo - extra, hi + extra


def _window_from_xs(xs: list[float]) -> tuple[float, float]:
    usable = [x for x in xs if math.isfinite(x) and abs(x) < 200]
    if not usable:
        return -6.0, 6.0
    if len(usable) >= 4 and max(usable) - min(usable) > 12:
        usable = sorted(usable, key=lambda value: abs(value))[:4]
    lo, hi = min(usable), max(usable)
    pad = 3.2 if hi - lo < 1e-6 else max(1.4, 0.45 * (hi - lo))
    return lo - pad, hi + pad


def _sample(func, xmin: float, xmax: float):
    count = 72
    xs = [xmin + (xmax - xmin) * i / (count - 1) for i in range(count)]
    ys = [_eval1(func, x) for x in xs]
    finite = sorted(abs(y) for y in ys if y is not None)
    scale = finite[int(len(finite) * 0.86)] if finite else 1.0
    scale = max(scale, 1e-4)
    samples = [(xs[0], ys[0])]

    def refine(x0, y0, x1, y1, depth):
        if depth <= 0 or x1 - x0 < (xmax - xmin) / 1800:
            return
        mid = (x0 + x1) / 2
        ym = _eval1(func, mid)
        interesting = False
        if y0 is None or y1 is None or ym is None:
            interesting = True
        else:
            chord = (y0 + y1) / 2
            if abs(ym - chord) > 0.018 * scale:
                interesting = True
            if y0 == 0 or y1 == 0 or ym == 0 or y0 * y1 < 0 or y0 * ym < 0 or ym * y1 < 0:
                interesting = True
        if interesting:
            refine(x0, y0, mid, ym, depth - 1)
            samples.append((mid, ym))
            refine(mid, ym, x1, y1, depth - 1)

    for i in range(count - 1):
        refine(xs[i], ys[i], xs[i + 1], ys[i + 1], 6)
        samples.append((xs[i + 1], ys[i + 1]))
    samples.sort(key=lambda item: item[0])
    deduped = []
    for point in samples:
        if deduped and abs(point[0] - deduped[-1][0]) < (xmax - xmin) * 1e-6:
            continue
        deduped.append(point)
    return deduped, scale


def _polylines(samples, scale: float):
    lines = []
    current = []
    previous = None
    limit = max(scale * 18, 40)
    for x, y in samples:
        if y is None or abs(y) > limit:
            if len(current) > 1:
                lines.append(current)
            current = []
            previous = None
            continue
        if previous is not None and abs(y - previous) > max(scale * 8, 12):
            if len(current) > 1:
                lines.append(current)
            current = [[_num(x), _num(y)]]
        else:
            current.append([_num(x), _num(y)])
        previous = y
    if len(current) > 1:
        lines.append(current)
    return [line for line in lines if len(line) > 1]


def _critical_markers(expr, symbol, xmin, xmax):
    try:
        deriv = sp.diff(expr, symbol)
        if deriv == 0:
            return []
        second = sp.diff(deriv, symbol)
        sol = sp.solveset(deriv, symbol, domain=sp.S.Reals)
    except Exception:
        return []
    found = []
    for x in _xs_from_solution(sol, symbol):
        if x < xmin - 0.05 or x > xmax + 0.05:
            continue
        y = as_float(expr.subs(symbol, x))
        if y is None:
            continue
        curvature = as_float(second.subs(symbol, x))
        if curvature is None or abs(curvature) < 1e-8:
            name = "驻点"
        else:
            name = "极小" if curvature > 0 else "极大"
        if any(abs(x - old[0]) < 0.05 for old in found):
            continue
        found.append((x, y, name))
        if len(found) >= 6:
            break
    return found


def _extrema(samples, scale: float):
    found = []
    for index in range(1, len(samples) - 1):
        x0, y0 = samples[index - 1]
        x1, y1 = samples[index]
        x2, y2 = samples[index + 1]
        if None in (y0, y1, y2) or x2 == x0:
            continue
        left = y1 - y0
        right = y2 - y1
        if left * right > 0:
            continue
        if abs(left) + abs(right) < max(scale * 1e-4, 1e-6):
            continue
        if left >= 0 and right <= 0:
            found.append((x1, y1, "极大"))
        elif left <= 0 and right >= 0:
            found.append((x1, y1, "极小"))
    thinned = []
    for point in found:
        if any(abs(point[0] - old[0]) < 0.15 for old in thinned):
            continue
        thinned.append(point)
    if len(thinned) > 6:
        step = len(thinned) / 6
        thinned = [thinned[int(i * step)] for i in range(6)]
    return thinned


def _xs_from_solution(solution, symbol) -> list[float]:
    if solution is None:
        return []
    parts = []
    if isinstance(solution, sp.Union):
        parts.extend(solution.args)
    else:
        parts.append(solution)
    found = []
    for part in parts:
        if isinstance(part, sp.FiniteSet):
            for value in part:
                number = as_float(value)
                if number is not None:
                    found.append(number)
        elif isinstance(part, sp.ImageSet):
            try:
                var = part.lamda.variables[0]
                expr = part.lamda.expr
                func = _lambdify(expr, (var,))
            except Exception:
                continue
            for n in range(-16, 17):
                value = _eval1(func, n)
                if value is not None and abs(value) < 80:
                    found.append(value)
    return found


def _marker(x, y, label, kind):
    return {"x": _num(x), "y": _num(y), "label": label, "kind": kind}


def _finish(title, xlabel, ylabel, series, markers, xmin, xmax, ymin, ymax, note=""):
    xs = []
    ys = []
    for marker in markers:
        xs.append(marker["x"])
        ys.append(marker["y"])
    for item in series:
        for line in item["polylines"]:
            for x, y in line:
                xs.append(x)
                ys.append(y)
    finite_y = [y for y in ys if y is not None and math.isfinite(y)]
    finite_x = [x for x in xs if x is not None and math.isfinite(x)]
    if not finite_x or not finite_y:
        return {"empty": True, "note": note or "这个方程画不出实数图像。"}
    y_values = sorted(abs(y) for y in finite_y)
    cap = y_values[int(len(y_values) * 0.94)] if y_values else 1
    cap = max(cap * 1.8, 1)
    kept_y = [y for y in finite_y if abs(y) <= cap]
    if not kept_y:
        kept_y = finite_y
    ymin, ymax = min(kept_y), max(kept_y)
    if ymin > 0 and ymin < 0.45 * ymax:
        ymin = 0
    if ymax < 0 and abs(ymax) < 0.45 * abs(ymin):
        ymax = 0
    xmin, xmax = _pad(min(finite_x), max(finite_x), 0.08, 0.6)
    ymin, ymax = _pad(ymin, ymax, 0.16, 0.6)
    return {
        "empty": False,
        "title": title,
        "xLabel": xlabel,
        "yLabel": ylabel,
        "xMin": _num(xmin),
        "xMax": _num(xmax),
        "yMin": _num(ymin),
        "yMax": _num(ymax),
        "series": series,
        "markers": markers,
        "note": note,
    }


def relation_plot(lhs, rhs, symbol, solution=None, extra_xs=None):
    try:
        return _relation_plot(lhs, rhs, symbol, solution, extra_xs or [])
    except Exception:
        return {"empty": True, "note": "这张图暂时没有画出来。"}


def _relation_plot(lhs, rhs, symbol, solution, extra_xs):
    exprs = [lhs, rhs]
    if any((expr.free_symbols - {symbol}) for expr in exprs):
        return {"empty": True, "note": "方程里还有未定参数，给定参数的数值后才能画出函数。"}
    xs = list(extra_xs) + _xs_from_solution(solution, symbol)
    xmin, xmax = _window_from_xs(xs)
    rhs_const = as_float(rhs)
    lhs_const = as_float(lhs)
    series = []
    samples = []
    scale = 1.0
    if lhs_const is None:
        func = _lambdify(lhs, (symbol,))
        samples, scale = _sample(func, xmin, xmax)
        lines = _polylines(samples, scale)
        if lines:
            series.append({"name": f"y = {_short(lhs)}", "polylines": lines})
    else:
        series.append({"name": f"y = {_fmt(lhs_const)}", "polylines": [[[_num(xmin), _num(lhs_const)], [_num(xmax), _num(lhs_const)]]]})
    show_rhs = rhs_const != 0
    if show_rhs:
        if rhs_const is None:
            func_r = _lambdify(rhs, (symbol,))
            samples_r, scale_r = _sample(func_r, xmin, xmax)
            lines_r = _polylines(samples_r, max(scale, scale_r))
            if lines_r:
                series.append({"name": f"y = {_short(rhs)}", "polylines": lines_r})
            scale = max(scale, scale_r)
        else:
            series.append(
                {
                    "name": f"y = {_fmt(rhs_const)}",
                    "polylines": [[[_num(xmin), _num(rhs_const)], [_num(xmax), _num(rhs_const)]]],
                }
            )
    markers = []
    seen = set()
    lhs_func = None if lhs_const is not None else _lambdify(lhs, (symbol,))
    for x in xs:
        if not (xmin - 1 <= x <= xmax + 1):
            continue
        key = round(x, 5)
        if key in seen:
            continue
        seen.add(key)
        if lhs_const is not None:
            y = lhs_const
        else:
            y = _eval1(lhs_func, x)
        if y is None and rhs_const is not None:
            y = rhs_const
        if y is None:
            continue
        label = "交点" if show_rhs else "根"
        markers.append(_marker(x, y, f"{label} ({_fmt(x)}, {_fmt(y)})", "intersection" if show_rhs else "root"))
    if lhs_const is None and samples:
        analytic = _critical_markers(lhs, symbol, xmin, xmax)
        spots = analytic or _extrema(samples, scale)
        for x, y, name in spots:
            if any(abs(x - marker["x"]) < 0.2 and abs(y - marker["y"]) < 0.2 * max(scale, 1) for marker in markers):
                continue
            markers.append(_marker(x, y, f"{name} ({_fmt(x)}, {_fmt(y)})", "extremum"))
        if xmin <= 0 <= xmax:
            y0 = _eval1(lhs_func, 0)
            if y0 is not None and not any(abs(marker["x"]) < 0.25 and abs(marker["y"] - y0) < 0.2 * max(scale, 1) for marker in markers):
                markers.append(_marker(0, y0, f"截距 (0, {_fmt(y0)})", "intercept"))
    title = f"{_short(lhs)} = {_short(rhs)}"
    return _finish(title, symbol.name, "y", series, markers, xmin, xmax, -1, 1)


def _short(expr) -> str:
    text = str(expr)
    if len(text) > 42:
        return text[:39] + "..."
    return text


def system_plot(items, gens, points):
    try:
        return _system_plot(items, gens, points)
    except Exception:
        return {"empty": True, "note": "这张图暂时没有画出来。"}


def _system_plot(items, gens, points):
    if len(gens) != 2:
        return {"empty": True, "note": "图像只画一个或两个未知数。三个及以上的未知数不再投影成平面曲线。"}
    x_sym, y_sym = gens
    coords = []
    for point in points:
        if x_sym.name in point and y_sym.name in point:
            coords.append((point[x_sym.name], point[y_sym.name]))
    if coords:
        xmin, xmax = _window_from_xs([p[0] for p in coords])
        ymin, ymax = _window_from_xs([p[1] for p in coords])
    else:
        xmin, xmax, ymin, ymax = -6.0, 6.0, -6.0, 6.0
    series = []
    axis_points = []
    for index, item in enumerate(items[:4]):
        expr = item["expr"]
        if expr.free_symbols - set(gens):
            continue
        func = _lambdify(expr, (x_sym, y_sym))
        lines = []
        for _ in range(3):
            lines = _contour(func, xmin, xmax, ymin, ymax)
            hits_border = False
            for line in lines:
                for x, y in line:
                    if min(abs(x - xmin), abs(x - xmax), abs(y - ymin), abs(y - ymax)) < 1e-4:
                        hits_border = True
                        break
                if hits_border:
                    break
            if lines and not hits_border:
                break
            if coords and lines:
                break
            span_x = (xmax - xmin) * 0.4
            span_y = (ymax - ymin) * 0.4
            xmin -= span_x
            xmax += span_x
            ymin -= span_y
            ymax += span_y
        if lines:
            series.append({"name": f"方程 {index + 1}", "polylines": lines})
        for point in _axis_zeros(func, xmin, xmax, True) + _axis_zeros(func, ymin, ymax, False):
            axis_points.append(point)
    markers = []
    used = []
    for x, y in coords:
        if any(abs(x - ox) < 0.08 and abs(y - oy) < 0.08 for ox, oy in used):
            continue
        used.append((x, y))
        markers.append(_marker(x, y, f"交点 ({_fmt(x)}, {_fmt(y)})", "intersection"))
    for x, y in axis_points:
        if any(abs(x - ox) < 0.12 and abs(y - oy) < 0.12 for ox, oy in used):
            continue
        used.append((x, y))
        markers.append(_marker(x, y, f"截距 ({_fmt(x)}, {_fmt(y)})", "intercept"))
        if len(markers) >= 14:
            break
    data = _finish("平面曲线", x_sym.name, y_sym.name, series, markers, xmin, xmax, ymin, ymax)
    data["equal"] = True
    return data


def _contour(func, xmin, xmax, ymin, ymax, n: int = 96):
    grid = []
    for j in range(n):
        y = ymin + (ymax - ymin) * j / (n - 1)
        row = []
        for i in range(n):
            x = xmin + (xmax - xmin) * i / (n - 1)
            row.append(_eval2(func, x, y))
        grid.append(row)
    segments = []
    for j in range(n - 1):
        for i in range(n - 1):
            corners = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
            if any(value is None for value in corners):
                continue
            xs = [
                xmin + (xmax - xmin) * i / (n - 1),
                xmin + (xmax - xmin) * (i + 1) / (n - 1),
            ]
            ys = [
                ymin + (ymax - ymin) * j / (n - 1),
                ymin + (ymax - ymin) * (j + 1) / (n - 1),
            ]
            points = {
                0: (xs[0], ys[0]),
                1: (xs[1], ys[0]),
                2: (xs[1], ys[1]),
                3: (xs[0], ys[1]),
            }
            values = {0: corners[0], 1: corners[1], 2: corners[2], 3: corners[3]}
            mask = 0
            for bit, value in enumerate(corners):
                if value > 0:
                    mask |= 1 << bit
            if mask == 0 or mask == 15:
                continue
            edges = _SQUARE_EDGES.get(mask, [])
            if mask in (5, 10):
                center = corners[0] + corners[1] + corners[2] + corners[3]
                edges = _SQUARE_EDGES[mask][0 if center >= 0 else 1]
            for a, b in edges:
                p1 = _cross(points[a[0]], values[a[0]], points[a[1]], values[a[1]])
                p2 = _cross(points[b[0]], values[b[0]], points[b[1]], values[b[1]])
                segments.append((p1, p2))
    return _chain(segments, xmin, xmax, ymin, ymax)


_SQUARE_EDGES = {
    1: [((0, 1), (0, 3))],
    2: [((0, 1), (1, 2))],
    3: [((0, 3), (1, 2))],
    4: [((1, 2), (2, 3))],
    5: [[((0, 1), (1, 2)), ((0, 3), (2, 3))], [((0, 1), (0, 3)), ((1, 2), (2, 3))]],
    6: [((0, 1), (2, 3))],
    7: [((0, 3), (2, 3))],
    8: [((0, 3), (2, 3))],
    9: [((0, 1), (2, 3))],
    10: [[((0, 1), (0, 3)), ((1, 2), (2, 3))], [((0, 1), (1, 2)), ((0, 3), (2, 3))]],
    11: [((1, 2), (2, 3))],
    12: [((0, 3), (1, 2))],
    13: [((0, 1), (1, 2))],
    14: [((0, 1), (0, 3))],
}


def _cross(p1, v1, p2, v2):
    if abs(v1 - v2) < 1e-14:
        t = 0.5
    else:
        t = v1 / (v1 - v2)
    t = min(1.0, max(0.0, t))
    return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))


def _chain(segments, xmin, xmax, ymin, ymax):
    def key(point):
        return (round(point[0], 4), round(point[1], 4))

    coords = {}
    links = {}
    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        coords[ka] = a
        coords[kb] = b
        links.setdefault(ka, []).append(kb)
        links.setdefault(kb, []).append(ka)
    used = set()
    polylines = []

    def trace(start):
        path = [start]
        used.add(start)
        while True:
            nxts = [node for node in links.get(path[-1], []) if node not in used]
            if not nxts:
                break
            used.add(nxts[0])
            path.append(nxts[0])
        if len(path) > 2 and path[0] in links.get(path[-1], []):
            path.append(path[0])
        if len(path) > 1:
            polylines.append([[_num(coords[node][0]), _num(coords[node][1])] for node in path])

    for start, nodes in list(links.items()):
        if start not in used and len(nodes) == 1:
            trace(start)
    for start in list(links):
        if start not in used:
            trace(start)
    return polylines


def _axis_zeros(func, a, b, horizontal: bool):
    count = 80
    found = []
    previous_x = a
    previous = _eval2(func, a, 0) if horizontal else _eval2(func, 0, a)
    for i in range(1, count):
        pos = a + (b - a) * i / (count - 1)
        value = _eval2(func, pos, 0) if horizontal else _eval2(func, 0, pos)
        if previous is not None and value is not None and previous * value <= 0:
            lo, hi = previous_x, pos
            flo, fhi = previous, value
            for _ in range(18):
                mid = (lo + hi) / 2
                fmid = _eval2(func, mid, 0) if horizontal else _eval2(func, 0, mid)
                if fmid is None:
                    break
                if flo * fmid <= 0:
                    hi, fhi = mid, fmid
                else:
                    lo, flo = mid, fmid
            zero = (lo + hi) / 2
            found.append((zero, 0.0) if horizontal else (0.0, zero))
        previous_x, previous = pos, value
    return found


def ode_plot(solutions, ivar_name: str, ic_points: list[tuple[str, float, float]]):
    try:
        return _ode_plot(solutions, ivar_name, ic_points)
    except Exception:
        return {"empty": True, "note": "这张图暂时没有画出来。"}


def _ode_plot(solutions, ivar_name, ic_points):
    xs = [point[1] for point in ic_points]
    xmin, xmax = _window_from_xs(xs or [0])
    if not xs:
        xmin, xmax = -2.0, 6.0
    series = []
    markers = []
    ivar = sp.symbols(ivar_name)
    for sol in solutions:
        if not isinstance(sol, sp.Eq):
            continue
        rhs = sol.rhs
        if rhs.free_symbols - {ivar} - {s for s in rhs.free_symbols if str(s).startswith("C")}:
            return {"empty": True, "note": "解里还有未定参数，给定参数后才能作图。"}
        consts = [s for s in rhs.free_symbols if str(s).startswith("C")]
        name = str(sol.lhs.func) if isinstance(sol.lhs, AppliedUndef) else "y"
        choices = [{}]
        if consts:
            choices = []
            for value in (-1, 0, 1):
                choices.append({const: value for const in consts})
        for choice in choices:
            expr = rhs.subs(choice)
            func = _lambdify(expr, (ivar,))
            samples, scale = _sample(func, xmin, xmax)
            lines = _polylines(samples, scale)
            if not lines:
                continue
            label = name + "(x)"
            if choice:
                label += "，" + ", ".join(f"{k}={v}" for k, v in choice.items())
            series.append({"name": label, "polylines": lines})
            if not choice:
                for x, y, kind in _extrema(samples, scale)[:4]:
                    markers.append(_marker(x, y, f"{kind} ({_fmt(x)}, {_fmt(y)})", "extremum"))
    for name, x, y in ic_points:
        markers.append(_marker(x, y, f"初值 {name}({_fmt(x)})={_fmt(y)}", "initial"))
    note = ""
    if any(re.search(r"\bC\d+\b", str(sol)) for sol in solutions):
        note = "未定初值时，任意常数取 -1、0、1 各画一条。"
    return _finish("解曲线", ivar_name, "y", series, markers, xmin, xmax, -1, 1, note)


def sequence_plot(expr, index, func_name: str, index_name: str):
    try:
        return _sequence_plot(expr, index, func_name, index_name)
    except Exception:
        return {"empty": True, "note": "这张图暂时没有画出来。"}


def _sequence_plot(expr, index, func_name, index_name):
    if isinstance(expr, sp.Eq):
        expr = expr.rhs
    consts = [s for s in expr.free_symbols if str(s).startswith("C") and s != index]
    others = [s for s in expr.free_symbols if s != index and s not in consts]
    if others:
        return {"empty": True, "note": "通项里还有未定参数，给定参数后才能画出数列。"}
    expr = expr.subs({const: 1 for const in consts})
    func = _lambdify(expr, (index,))
    points = []
    for n in range(0, 18):
        value = _eval1(func, n)
        if value is None or abs(value) > 1e6:
            break
        if points:
            early = max(abs(item[1]) for item in points[:3]) or 1.0
            if len(points) >= 4 and abs(value) > max(40.0, 18.0 * early):
                break
        points.append((n, value))
        if len(points) >= 14:
            break
    if len(points) < 2:
        return {"empty": True, "note": "通项在整数下标上没有足够的实数值可以作图。"}
    series = [{"name": f"{func_name}({index_name})", "polylines": [[[_num(n), _num(y)] for n, y in points]]}]
    markers = []
    for n, y in points:
        if len(points) <= 10 or n in (points[0][0], points[-1][0]) or y == max(p[1] for p in points) or y == min(p[1] for p in points):
            markers.append(_marker(n, y, f"{func_name}({n})={_fmt(y)}", "term"))
    note = "任意常数按 1 画出。" if consts else ""
    xmin, xmax = points[0][0], points[-1][0]
    ymin, ymax = min(y for _, y in points), max(y for _, y in points)
    return _finish(f"{func_name}({index_name}) 的图像", index_name, func_name, series, markers, xmin, xmax, ymin, ymax, note)
