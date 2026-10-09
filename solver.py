"""本地方程求解器，计算由 SymPy 完成。"""

from __future__ import annotations

import re
import time
import traceback

import sympy as sp
from sympy.core.function import AppliedUndef

from plotter import as_float as plot_float
from plotter import ode_plot, relation_plot, sequence_plot, system_plot
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

TRANSFORMS = standard_transformations + (
    convert_xor,
    implicit_multiplication_application,
)
VAR_ORDER = ["x", "y", "z", "w", "v", "u"]
CN = ["零", "一", "二", "三", "四", "五", "六"]
MODES = {"polynomial", "transcendental", "differential", "system", "recurrence"}
ODE_NAMES = {
    "separable": "可分离变量方程",
    "1st_exact": "一阶恰当方程",
    "1st_linear": "一阶线性方程",
    "Bernoulli": "伯努利方程",
    "1st_homogeneous_coeff_best": "齐次方程",
    "1st_homogeneous_coeff_subs_indep_div_dep": "齐次方程",
    "1st_homogeneous_coeff_subs_dep_div_indep": "齐次方程",
    "almost_linear": "近线性方程",
    "linear_coefficients": "线性系数方程",
    "nth_linear_constant_coeff_homogeneous": "常系数齐次线性方程",
    "nth_linear_constant_coeff_undetermined_coefficients": "常系数非齐次线性方程",
    "nth_linear_euler_eq_homogeneous": "欧拉方程",
    "nth_linear_euler_eq_nonhomogeneous_undetermined_coefficients": "非齐次欧拉方程",
    "Liouville": "刘维尔方程",
    "2nd_linear_airy": "艾里方程",
    "2nd_linear_bessel": "贝塞尔方程",
    "nth_algebraic": "可化为代数方程",
    "separable_reduced": "降阶后可分离的方程",
    "nth_order_reducible": "可降阶方程",
}
BLOCKED = re.compile(
    r"__|\\|lambda\b|import\b|exec\b|eval\b|open\s*\(|compile\s*\(|"
    r"globals\s*\(|locals\s*\(|getattr\s*\(|setattr\s*\(|subprocess\b|os\."
)


class UserError(Exception):
    pass


def log10(expr):
    return sp.log(expr, 10)


def L(expr) -> str:
    try:
        return sp.latex(expr)
    except Exception:
        return str(expr)


def require_int(value, lo: int, hi: int, label: str) -> int:
    if isinstance(value, bool):
        raise UserError(f"{label}要在 {lo} 到 {hi} 之间。")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise UserError(f"{label}必须是整数。") from None
    if isinstance(value, float) and not float(value).is_integer():
        raise UserError(f"{label}必须是整数。")
    if not lo <= number <= hi:
        raise UserError(f"{label}要在 {lo} 到 {hi} 之间。")
    return number


def one_letter(value, label: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z]", text):
        raise UserError(f"{label}请用一个英文字母。")
    return text


def normalize(text: str) -> str:
    if not isinstance(text, str):
        raise UserError("方程必须是文字。")
    raw = text.strip()
    if not raw:
        raise UserError("方程是空的。")
    if len(raw) > 2000:
        raise UserError("方程太长了，请化简后再试。")
    if BLOCKED.search(raw):
        raise UserError("表达式里有不支持的写法。")
    raw = raw.translate(
        str.maketrans(
            {
                "−": "-",
                "–": "-",
                "—": "-",
                "×": "*",
                "·": "*",
                "∙": "*",
                "÷": "/",
                "π": "pi",
                "（": "(",
                "）": ")",
                "，": ",",
                "＝": "=",
                "′": "'",
                "″": "''",
                "‴": "'''",
                "²": "^2",
                "³": "^3",
            }
        )
    )
    raw = raw.replace("∞", "oo")
    raw = re.sub(r"√\s*\(", "sqrt(", raw)
    raw = re.sub(r"√\s*([A-Za-z0-9.]+)", r"sqrt(\1)", raw)
    raw = re.sub(r"\blg\s*\(", "log10(", raw)
    raw = re.sub(r"([A-Za-z])\s*('{1,3})", r"\1\2", raw)
    return raw


def base_local() -> dict:
    local: dict = {}
    for name in list("abcdefghijklmnopqrstuvwxyz"):
        local[name] = sp.symbols(name)
    local.update(
        {
            "pi": sp.pi,
            "e": sp.E,
            "E": sp.E,
            "I": sp.I,
            "oo": sp.oo,
            "sin": sp.sin,
            "cos": sp.cos,
            "tan": sp.tan,
            "cot": sp.cot,
            "sec": sp.sec,
            "csc": sp.csc,
            "asin": sp.asin,
            "acos": sp.acos,
            "atan": sp.atan,
            "sinh": sp.sinh,
            "cosh": sp.cosh,
            "tanh": sp.tanh,
            "exp": sp.exp,
            "log": sp.log,
            "ln": sp.log,
            "log10": log10,
            "sqrt": sp.sqrt,
            "abs": sp.Abs,
            "Abs": sp.Abs,
            "diff": sp.diff,
            "Derivative": sp.Derivative,
            "Subs": sp.Subs,
        }
    )
    return local


def parse_side(text: str, local: dict):
    piece = text.strip()
    if not piece:
        raise UserError("等号两边都不能是空的。")
    try:
        return parse_expr(piece, local_dict=local, transformations=TRANSFORMS)
    except Exception as exc:
        raise UserError(f"无法识别「{piece}」。请检查括号、乘号和函数名。") from exc


def split_equation(text: str) -> tuple[str, str, bool]:
    if "==" in text or text.count("=") > 1:
        raise UserError("一条方程里只能有一个等号。初值请写在初值栏，或单独写成一条。")
    if "=" not in text:
        return text, "0", True
    lhs, rhs = text.split("=", 1)
    if not lhs.strip() or not rhs.strip():
        raise UserError("等号两边都不能是空的。")
    return lhs, rhs, False


def ode_function_names(texts: list[str], primary: str, ivar: str) -> set[str]:
    funcs = {primary}
    for text in texts:
        for match in re.finditer(r"\b([A-Za-z])'{1,3}", text):
            funcs.add(match.group(1))
        for match in re.finditer(r"d\^?\d*([A-Za-z])/d([A-Za-z])", text):
            funcs.add(match.group(1))
        for match in re.finditer(rf"\b([A-Za-z])\(\s*{re.escape(ivar)}\s*\)", text):
            funcs.add(match.group(1))
    funcs.discard(ivar)
    funcs.discard("e")
    funcs.discard("d")
    return funcs


def apply_ode(text: str, funcs: set[str], ivar: str) -> str:
    def deriv(name: str, order: int) -> str:
        if order <= 1:
            return f"Derivative({name}({ivar}), {ivar})"
        return f"Derivative({name}({ivar}), {ivar}, {order})"

    def subs_or_deriv(name: str, order: int, arg: str) -> str:
        if arg.strip() == ivar:
            return deriv(name, order)
        return f"Subs({deriv(name, order)}, {ivar}, {arg.strip()})"

    s = text
    for order, ticks in ((3, "'''"), (2, "''"), (1, "'")):
        s = re.sub(
            rf"\b([A-Za-z]){ticks}\(([^()]*)\)",
            lambda m, order=order: subs_or_deriv(m.group(1), order, m.group(2)),
            s,
        )
        s = re.sub(
            rf"\b([A-Za-z]){ticks}(?!')",
            lambda m, order=order: deriv(m.group(1), order),
            s,
        )
    s = re.sub(
        r"d\^([2-9])([A-Za-z])/d([A-Za-z])\^\1",
        lambda m: f"Derivative({m.group(2)}({m.group(3)}), {m.group(3)}, {m.group(1)})",
        s,
    )
    s = re.sub(
        r"d([A-Za-z])/d([A-Za-z])",
        lambda m: f"Derivative({m.group(1)}({m.group(2)}), {m.group(2)})",
        s,
    )
    if funcs:
        pattern = r"\b(" + "|".join(sorted(funcs, key=len, reverse=True)) + r")\b(?!\s*\()"
        s = re.sub(pattern, lambda m: f"{m.group(1)}({ivar})", s)
    s = re.sub(r"(\d)\s*(Derivative|Subs)\b", r"\1*\2", s)
    s = re.sub(r"\)\s*(Derivative|Subs)\b", r")*\1", s)
    return s


def equation_latex(lhs, rhs) -> str:
    return L(sp.Eq(lhs, rhs))


def read_mode(payload: dict) -> str:
    mode = payload.get("type")
    if mode not in MODES:
        raise UserError("不认识这个方程类型。")
    return mode


def meta_from(payload: dict) -> dict:
    mode = read_mode(payload)
    meta = {
        "mode": mode,
        "func": "y",
        "ivar": "x",
        "rec_func": "a",
        "rec_index": "n",
        "max_vars": 6,
        "max_degree": None,
        "domain": "real",
        "numerical": True if payload.get("numerical", True) else False,
        "guesses": str(payload.get("guesses") or ""),
        "ics": payload.get("ics") if isinstance(payload.get("ics"), list) else [],
    }
    if mode == "polynomial":
        meta["max_vars"] = require_int(payload.get("maxVars", 1), 1, 6, "未知数个数")
        meta["max_degree"] = require_int(payload.get("maxDegree", 1), 1, 6, "最高次数")
        meta["domain"] = "complex"
    if payload.get("domain") in {"real", "complex"}:
        meta["domain"] = payload["domain"]
    if mode == "differential":
        meta["func"] = one_letter(payload.get("func") or "y", "函数名")
        meta["ivar"] = one_letter(payload.get("ivar") or "x", "自变量")
        if meta["func"] == meta["ivar"]:
            raise UserError("函数名和自变量要是两个不同的字母。")
        if meta["func"] in {"e", "E", "d"}:
            raise UserError("函数名不要用 e 或 d。")
    if mode == "recurrence":
        meta["rec_func"] = one_letter(payload.get("recFunc") or "a", "数列名")
        meta["rec_index"] = one_letter(payload.get("recIndex") or "n", "下标")
        if meta["rec_func"] == meta["rec_index"]:
            raise UserError("数列名和下标要是两个不同的字母。")
        if meta["rec_func"] in {"e", "E", "d"}:
            raise UserError("数列名不要用 e 或 d。")
    return meta


def parse_prepared(raw: str, text: str, meta: dict, funcs: set[str]) -> dict:
    if meta["mode"] == "differential":
        text = apply_ode(text, funcs, meta["ivar"])
    lhs_s, rhs_s, implicit = split_equation(text)
    local = base_local()
    if meta["mode"] == "differential":
        for name in funcs:
            local[name] = sp.Function(name)
        local[meta["ivar"]] = sp.symbols(meta["ivar"])
    if meta["mode"] == "recurrence":
        local[meta["rec_func"]] = sp.Function(meta["rec_func"])
        local[meta["rec_index"]] = sp.symbols(
            meta["rec_index"], integer=True, nonnegative=True
        )
    lhs = parse_side(lhs_s, local)
    rhs = parse_side(rhs_s, local)
    return {
        "raw": raw.strip(),
        "lhs": lhs,
        "rhs": rhs,
        "expr": lhs - rhs,
        "implicit": implicit,
        "latex": equation_latex(lhs, rhs),
        "funcs": funcs,
    }


def parse_rows(rows: list, meta: dict, soft: bool = False):
    """Parse every row. soft=True keeps per-row errors for the live preview."""
    prepared = []
    for raw in rows:
        if not isinstance(raw, str) or not raw.strip():
            prepared.append({"empty": True})
            continue
        try:
            prepared.append({"raw": raw, "text": normalize(raw)})
        except UserError as exc:
            if not soft:
                raise
            prepared.append({"error": str(exc)})
    funcs: set[str] = set()
    if meta["mode"] == "differential":
        funcs = ode_function_names(
            [item["text"] for item in prepared if "text" in item],
            meta["func"],
            meta["ivar"],
        )
    items = []
    parsed = []
    for item in prepared:
        if item.get("empty"):
            items.append({"empty": True})
            continue
        if item.get("error"):
            items.append({"ok": False, "error": item["error"]})
            continue
        try:
            eq = parse_prepared(item["raw"], item["text"], meta, funcs)
            parsed.append(eq)
            items.append({"ok": True, "latex": eq["latex"]})
        except UserError as exc:
            if not soft:
                raise
            items.append({"ok": False, "error": str(exc)})
    return items, parsed


def sort_syms(symbols: list):
    rank = {name: i for i, name in enumerate(VAR_ORDER)}
    return sorted(symbols, key=lambda s: rank.get(s.name, 99))


def is_identically_zero(expr) -> bool:
    if expr == 0:
        return True
    expanded = sp.expand(expr)
    if expanded == 0:
        return True
    if expr.has(sp.sin, sp.cos, sp.tan, sp.exp, sp.log):
        try:
            if sp.simplify(expr) == 0 or sp.trigsimp(expr) == 0:
                return True
        except Exception:
            return False
    return False


def negative_bases(expr) -> list:
    bases = []
    for node in sp.preorder_traversal(expr):
        if isinstance(node, sp.Pow) and node.exp.is_number and node.exp.is_real and node.exp < 0:
            bases.append(node.base)
    return bases


def has_denominator(expr) -> bool:
    return bool(negative_bases(expr))


def safe_is_zero(expr) -> bool | None:
    try:
        if expr == 0:
            return True
        expanded = sp.expand(expr)
        if expanded == 0:
            return True
        if expanded.has(sp.RootOf):
            val = expanded.evalf(20)
            if getattr(val, "is_number", False):
                return abs(complex(val)) < 1e-5
            return None
        if expanded.free_symbols:
            simplified = sp.simplify(expanded)
            if simplified == 0 or sp.expand(simplified) == 0:
                return True
            return None
        simplified = sp.simplify(expanded)
        if simplified == 0:
            return True
        return abs(complex(simplified.evalf(20))) < 1e-7
    except Exception:
        return None


def hits_pole(lhs, rhs, subs: dict) -> bool:
    for side in (lhs, rhs):
        for base in negative_bases(side):
            try:
                val = sp.simplify(base.subs(subs))
            except Exception:
                continue
            if val == 0:
                return True
            if not val.free_symbols:
                try:
                    if abs(complex(val.evalf(16))) < 1e-10:
                        return True
                except Exception:
                    pass
    return False


def real_flag(expr):
    if getattr(expr, "free_symbols", None):
        return None
    if getattr(expr, "is_real", None) is True:
        return True
    if getattr(expr, "is_real", None) is False:
        return False
    try:
        return abs(complex(sp.N(expr, 20)).imag) < 1e-9
    except Exception:
        return None


def approx_text(expr):
    if getattr(expr, "free_symbols", None):
        return None
    if expr.is_Integer or expr.is_Rational or expr.is_Float:
        return None
    try:
        val = expr.evalf(10)
        if not getattr(val, "is_number", False):
            return None
        text = str(val).replace("*I", "i").replace("I", "i")
        return text
    except Exception:
        return None


def difficulty_warning(n_unknown: int, degree: int, n_eq: int) -> str | None:
    if n_unknown >= 5 and degree >= 3:
        return "未知数不少于 5 个且次数不低于 3 时，常常要算很久，也可能超时。"
    if n_unknown >= 4 and degree >= 4:
        return "未知数和次数都比较高，求解可能超过时间限制。"
    if n_unknown >= 3 and degree >= 6 and n_eq >= 1:
        return "三元六次的一般方程往往很难得到公式解。"
    return None


def aligned(items: list[dict]) -> str:
    lines = [f"{L(item['lhs'])} &= {L(item['rhs'])}" for item in items]
    return "\\begin{aligned}" + " \\\\ ".join(lines) + "\\end{aligned}"


def original_steps(items: list[dict], expanded: bool = True) -> list[dict]:
    steps = []
    if len(items) == 1:
        steps.append({"title": "原方程", "latex": items[0]["latex"]})
        if items[0]["implicit"]:
            steps.append({"title": "说明", "text": "没有写等号，已按等于 0 处理。"})
        expr = sp.expand(items[0]["expr"]) if expanded else items[0]["expr"]
        steps.append({"title": "整理", "latex": L(sp.Eq(expr, 0))})
    else:
        steps.append({"title": "原方程组", "latex": aligned(items)})
        if any(item["implicit"] for item in items):
            steps.append({"title": "说明", "text": "没有写等号的式子，已按等于 0 处理。"})
    return steps


def poly_title(n_unknown: int, degree: int, n_eq: int) -> str:
    v = CN[n_unknown] if 1 <= n_unknown <= 6 else str(n_unknown)
    d = CN[degree] if 1 <= degree <= 6 else str(degree)
    if n_eq > 1:
        return f"{v}元{d}次方程组"
    return f"{v}元{d}次方程"


def analyze_algebraic(items: list[dict], meta: dict) -> dict:
    polynomial = meta["mode"] == "polynomial"
    allowed = VAR_ORDER[: meta["max_vars"]]
    allowed_set = set(allowed)
    found: list = []
    seen = set()
    params = []
    seen_p = set()
    for item in items:
        for sym in item["expr"].free_symbols:
            if sym.name in VAR_ORDER and sym.name not in allowed_set:
                raise UserError(
                    f"未知数 {sym.name} 超出了当前的 {meta['max_vars']} 元范围。"
                    f"当前可以使用 {'、'.join(allowed)}。"
                )
            if sym.name in allowed_set:
                if sym.name not in seen:
                    seen.add(sym.name)
                    found.append(sym)
            elif sym.name not in seen_p:
                seen_p.add(sym.name)
                params.append(sym)
    gens = sort_syms(found)
    if not gens:
        names = "、".join(allowed)
        raise UserError(f"没有找到未知数。请使用 {names}，其他字母会当成已知参数。")

    kept = []
    zeros = 0
    degree = 0
    for item in items:
        expanded = sp.expand(item["expr"])
        gens_in = [g for g in gens if g in expanded.free_symbols]
        if not gens_in:
            if is_identically_zero(expanded):
                zeros += 1
                continue
            if not expanded.free_symbols:
                return {
                    "kind": "empty",
                    "items": items,
                    "gens": gens,
                    "params": params,
                    "degree": 0,
                    "summary": [f"未知数 {'、'.join(g.name for g in gens)}"],
                    "warning": None,
                    "notes": ["整理后出现了一个不为 0 的常数，所以无解。"],
                }
            raise UserError(
                "有一条方程不含未知数。未知数请用 "
                + "、".join(VAR_ORDER)
                + "，其他字母会当成已知参数。"
            )
        if polynomial:
            if not expanded.is_polynomial(*gens):
                raise UserError(
                    "多项式模式只接受多项式。分式、根式、指数、对数或三角函数"
                    "请改用「超越方程」或「方程组」。"
                )
            if expanded == 0:
                zeros += 1
                continue
            deg = int(sp.Poly(expanded, *gens).total_degree())
            if deg > meta["max_degree"]:
                raise UserError(
                    f"这个方程的总次数是 {deg}，超过了所选的最高次数 {meta['max_degree']}。"
                    "次数按每一项里未知数指数之和计算，例如 x·y² 是 3 次。"
                )
            degree = max(degree, deg)
        elif is_identically_zero(item["expr"]):
            zeros += 1
            continue
        kept.append(item)

    if not kept:
        summary = [f"未知数 {'、'.join(g.name for g in gens)}"]
        return {
            "kind": "identity",
            "items": items,
            "gens": gens,
            "params": params,
            "degree": 0,
            "summary": summary,
            "warning": None,
            "notes": [],
        }

    summary = [f"未知数 {'、'.join(g.name for g in gens)}"]
    if polynomial:
        summary.append(f"次数 {degree}")
    if params:
        summary.append("参数 " + "、".join(p.name for p in params))
    summary.append(f"{len(kept)} 条方程")
    notes = []
    if zeros:
        notes.append("已去掉整理后恒为 0 的方程。")
    if polynomial and meta["max_vars"] > len(gens):
        notes.append(
            f"未知数个数选的是 {meta['max_vars']}，方程里实际出现的是 {'、'.join(g.name for g in gens)}。"
        )
    if polynomial and degree != meta["max_degree"]:
        notes.append(f"最高次数设为 {meta['max_degree']}，这个方程实际是 {degree} 次。")
    warning = difficulty_warning(len(gens), degree, len(kept)) if polynomial else None
    return {
        "kind": "solve",
        "items": kept,
        "gens": gens,
        "params": params,
        "degree": degree,
        "summary": summary,
        "warning": warning,
        "notes": notes,
        "all_items": items,
    }


def disc_text(disc) -> str:
    if disc.free_symbols or not disc.is_number:
        return "判别式含有参数，根的情况取决于参数。"
    try:
        if disc == 0:
            return "判别式等于 0，有两个相等的实数根。"
        if disc.is_real is False:
            return "判别式不是实数。"
        if disc > 0:
            return "判别式大于 0，有两个不相等的实数根。"
        if disc < 0:
            return "判别式小于 0，有一对共轭复数根。"
    except Exception:
        pass
    return "已算出判别式。"


def value_card(sym, val, index: int, mult: int, verified) -> dict:
    title = f"解 {index}"
    if 2 <= mult <= 6:
        title += f"（{CN[mult]}重根）"
    elif mult > 6:
        title += f"（{mult} 重根）"
    badges = []
    if val.free_symbols:
        badges.append("参数形式")
    else:
        flag = real_flag(val)
        if flag is True:
            badges.append("实数")
        elif flag is False:
            badges.append("复数")
    number = plot_float(val)
    return {
        "title": title,
        "latex": f"{L(sym)} = {L(val)}",
        "plain": f"{sym} = {val}",
        "approx": approx_text(val),
        "badges": badges,
        "verified": verified,
        "kind": "value",
        "real": real_flag(val) if not val.free_symbols else None,
        "coords": {sym.name: number} if number is not None else None,
    }


def verify_value(items: list[dict], sym, val):
    subs = {sym: val}
    if any(hits_pole(item["lhs"], item["rhs"], subs) for item in items):
        return False
    verdicts = []
    for item in items:
        try:
            verdicts.append(safe_is_zero(item["expr"].subs(subs)))
        except Exception:
            return None
    if any(v is False for v in verdicts):
        return False
    if verdicts and all(v is True for v in verdicts):
        return True
    return None


def verify_dict(items: list[dict], subs: dict):
    if any(hits_pole(item["lhs"], item["rhs"], subs) for item in items):
        return False
    verdicts = []
    for item in items:
        try:
            verdicts.append(safe_is_zero(item["expr"].subs(subs)))
        except Exception:
            return None
    if any(v is False for v in verdicts):
        return False
    if verdicts and all(v is True for v in verdicts):
        return True
    return None


def route_card(card: dict, domain: str, real_cards: list, complex_cards: list):
    if domain == "real" and card.get("real") is False:
        complex_cards.append(card)
    else:
        real_cards.append(card)


def finish_notes(notes: list[str], solutions: list[dict], params: list, dropped: int):
    explicit = [s for s in solutions if s.get("kind") == "value"]
    if explicit and all(s.get("verified") is True for s in explicit):
        notes.append("显式解已代回原方程，残差为 0。")
    elif any(s.get("verified") is None for s in explicit):
        notes.append("含参数或特殊函数的解，没有逐个做数值验算。")
    if dropped:
        notes.append(f"有 {dropped} 个结果不满足原方程，已舍去。")
    if params:
        notes.append("、".join(p.name for p in params) + " 是已知参数。")
    blob = " ".join(s.get("plain", "") for s in solutions)
    if "LambertW" in blob:
        notes.append("Lambert W 函数满足 W(z)·e^{W(z)} = z。")
    if "RootOf" in blob:
        notes.append("高次方程的根用 RootOf 精确表示，下面的小数是它的近似值。")
    if any(s.get("kind") == "set" for s in solutions):
        notes.append("带整数参数的解集里，每个整数都对应一个解。")
    return notes


def empty_message(domain: str, real_cards: list, complex_cards: list) -> str:
    if real_cards:
        return ""
    if domain == "real":
        return "实数范围内无解。"
    return "无解。"


def plot_for_items(items, gens, cards=None, solution=None):
    cards = cards or []
    try:
        if len(gens) == 1 and items:
            extra = []
            for card in cards:
                coords = card.get("coords") or {}
                if gens[0].name in coords:
                    extra.append(coords[gens[0].name])
            return relation_plot(items[0]["lhs"], items[0]["rhs"], gens[0], solution, extra)
        if len(gens) == 2 and items:
            points = [card["coords"] for card in cards if card.get("coords")]
            return system_plot(items, gens, points)
        if len(gens) > 2:
            return {"empty": True, "note": "三个及以上的未知数不再画成平面图像。"}
    except Exception:
        return {"empty": True, "note": "这张图暂时没有画出来。"}
    return {"empty": True, "note": "还没有可以绘制的实数曲线。"}


def _ode_plot_payload(sols, meta, ics):
    points = []
    for key, val in ics.items():
        if isinstance(key, AppliedUndef) and key.args:
            x = plot_float(key.args[0])
            y = plot_float(val)
            if x is not None and y is not None:
                points.append((str(key.func), x, y))
    return ode_plot(sols, meta["ivar"], points)


def pack(title, method, summary, steps, notes, warnings, real_cards, complex_cards, domain, plot=None):
    data = {
        "title": title,
        "method": method,
        "summary": summary,
        "steps": steps,
        "notes": notes,
        "warnings": [w for w in warnings if w],
        "solutions": real_cards,
        "complex_solutions": complex_cards if domain == "real" else [],
        "empty_message": empty_message(domain, real_cards, complex_cards),
    }
    if plot:
        data["plot"] = plot
    return data


def solve_univariate_poly(model: dict, meta: dict) -> dict:
    item = model["items"][0]
    sym = model["gens"][0]
    expanded = sp.expand(item["expr"])
    poly = sp.Poly(expanded, sym)
    degree = int(poly.degree())
    steps = original_steps([item])
    fac = sp.factor(expanded)
    if fac != expanded:
        steps.append({"title": "因式分解", "latex": L(sp.Eq(fac, 0))})
    if degree == 2:
        a, b, c = poly.all_coeffs()
        disc = sp.together(sp.simplify(b**2 - 4 * a * c))
        steps.append({"title": "判别式", "latex": "\\Delta = " + L(disc), "text": disc_text(disc)})
    try:
        root_map = sp.roots(poly)
    except Exception:
        root_map = {}
    kind = "exact"
    pairs: list[tuple] = []
    if root_map and sum(root_map.values()) == degree:
        pairs = list(root_map.items())
    else:
        try:
            solved = sp.solve(expanded, sym)
        except Exception:
            solved = []
        seen = []
        for root in solved:
            if any(root == old for old in seen):
                continue
            seen.append(root)
            try:
                mult = int(poly.multiplicity(root))
            except Exception:
                mult = 1
            pairs.append((root, mult))
        if not pairs:
            kind = "numeric"
            try:
                pairs = [(root, 1) for root in poly.nroots(n=12)]
            except Exception:
                pairs = []
    real_cards, complex_cards = [], []
    dropped = 0
    number = 1
    complex_number = 1
    for root, mult in pairs:
        verdict = verify_value([item], sym, root)
        if verdict is False:
            dropped += 1
            continue
        hidden = meta["domain"] == "real" and not root.free_symbols and real_flag(root) is False
        card = value_card(sym, root, complex_number if hidden else number, int(mult), verdict)
        if kind == "numeric":
            card["kind"] = "numeric"
            card["title"] = f"数值解 {complex_number if hidden else number}"
            card["badges"] = ["数值近似"] + [b for b in card["badges"] if b in {"实数", "复数"}]
            shown = sp.N(root, 10)
            card["latex"] = f"{L(sym)} \\approx {L(shown)}"
            card["plain"] = f"{sym} ≈ {shown}"
            card["approx"] = None
        if hidden:
            card["title"] = card["title"].replace("解 ", "复数解 ")
            complex_cards.append(card)
            complex_number += 1
        else:
            real_cards.append(card)
            number += 1
    methods = {1: "移项求解", 2: "求根公式", 3: "三次方程求根", 4: "四次方程求根"}
    method = "数值求根" if kind == "numeric" else methods.get(degree, "高次多项式求根")
    notes = list(model["notes"])
    if poly.LC().free_symbols:
        notes.append("最高次项系数含有参数，求根结果默认该系数不为 0。")
    notes = finish_notes(notes, real_cards + complex_cards, model["params"], dropped)
    warnings = [model.get("warning")]
    if kind == "numeric":
        warnings.append("没有得到根式解，下面是全部复根的小数近似。")
    return pack(
        poly_title(1, degree, 1),
        method,
        model["summary"],
        steps,
        notes,
        warnings,
        real_cards,
        complex_cards,
        meta["domain"],
        plot_for_items(model["items"], model["gens"], real_cards),
    )


def present_dict(raw: dict, gens: list):
    shown = {}
    free = []
    for gen in gens:
        val = raw.get(gen, gen)
        if val == gen:
            free.append(gen.name)
        else:
            shown[gen] = val
    return shown, free


def dict_card(shown: dict, free: list[str], index: int, verified, numeric: bool = False) -> dict:
    if not shown:
        return {
            "title": f"解 {index}",
            "latex": "",
            "plain": "未知数可以任意取值",
            "approx": None,
            "badges": ["通解"],
            "verified": verified,
            "kind": "set",
            "text": "、".join(free) + " 可以任意取值。" if free else "",
            "real": True,
        }
    lines = []
    plains = []
    approx_parts = []
    flags = []
    parametric = False
    for sym, val in shown.items():
        if numeric:
            shown_val = sp.N(val, 10)
            lines.append(f"{L(sym)} &\\approx {L(shown_val)}")
            plains.append(f"{sym} ≈ {shown_val}")
        else:
            lines.append(f"{L(sym)} &= {L(val)}")
            plains.append(f"{sym} = {val}")
            approx = approx_text(val)
            if approx:
                approx_parts.append(f"{sym} ≈ {approx}")
        if getattr(val, "free_symbols", None):
            parametric = True
        else:
            flags.append(real_flag(val))
    badges = ["数值近似"] if numeric else []
    if parametric:
        badges.append("参数形式")
    elif flags and all(flag is True for flag in flags):
        badges.append("实数")
    elif any(flag is False for flag in flags):
        badges.append("复数")
    real = False if any(flag is False for flag in flags) else True if flags and all(f is True for f in flags) else None
    text = "、".join(free) + " 可以任意取值。" if free else ""
    coords = {}
    coord_ok = True
    for sym, val in shown.items():
        number = plot_float(val)
        if number is None:
            coord_ok = False
            break
        coords[sym.name] = number
    return {
        "title": f"数值解 {index}" if numeric else f"解 {index}",
        "latex": "\\begin{aligned}" + " \\\\ ".join(lines) + "\\end{aligned}",
        "plain": ", ".join(plains),
        "approx": "，".join(approx_parts) if approx_parts else None,
        "badges": badges,
        "verified": verified,
        "kind": "numeric" if numeric else "value",
        "text": text,
        "real": real,
        "coords": coords if coord_ok and coords else None,
    }


def cards_from_dicts(dicts: list[dict], items, gens, domain: str):
    real_cards, complex_cards = [], []
    dropped = 0
    index = 1
    for raw in dicts:
        if any(getattr(v, "has", lambda *_: False)(sp.zoo, sp.nan) for v in raw.values()):
            dropped += 1
            continue
        verdict = verify_dict(items, {**{g: g for g in gens}, **raw})
        if verdict is False:
            dropped += 1
            continue
        shown, free = present_dict(raw, gens)
        card = dict_card(shown, free, index, verdict)
        before = len(real_cards)
        route_card(card, domain, real_cards, complex_cards)
        if len(real_cards) != before:
            index += 1
    return real_cards, complex_cards, dropped


def tuples_to_dicts(solset, gens: list) -> list[dict] | None:
    if solset is None or solset == sp.EmptySet:
        return []
    if not isinstance(solset, sp.FiniteSet):
        return None
    dicts = []
    for item in solset:
        if isinstance(item, dict):
            dicts.append(item)
            continue
        if isinstance(item, (tuple, sp.Tuple)) and len(item) == len(gens):
            if all(isinstance(val, sp.Expr) for val in item):
                dicts.append({gen: val for gen, val in zip(gens, item)})
                continue
        return None
    return dicts


def is_linear_expr(expr, gens: list) -> bool:
    try:
        expanded = sp.expand(expr)
        if not expanded.is_polynomial(*gens):
            return False
        return int(sp.Poly(expanded, *gens).total_degree()) <= 1
    except Exception:
        return False


def parse_guesses(text: str, gens: list):
    raw = (text or "").strip()
    if not raw:
        return {}
    local = base_local()
    if "=" not in raw:
        if len(gens) != 1:
            raise UserError("多个未知数的初值请写成 x=0.5, y=1。")
        return {gens[0]: parse_side(raw, local)}
    found = {}
    for part in re.split(r"[,，;；]", raw):
        if not part.strip():
            continue
        if "=" not in part:
            raise UserError("初值请写成 x=0.5, y=1。")
        name, value = part.split("=", 1)
        name = name.strip()
        gen = next((g for g in gens if g.name == name), None)
        if gen is None:
            raise UserError(f"初值里的 {name} 不是当前未知数。")
        found[gen] = parse_side(value, local)
    missing = [g.name for g in gens if g not in found]
    if missing:
        raise UserError("请为每个未知数都写上初值：" + "、".join(missing) + "。")
    return found


def numeric_key(values: list) -> tuple:
    parts = []
    for val in values:
        comp = complex(sp.N(val, 12))
        parts.append((round(comp.real, 6), round(comp.imag, 6)))
    return tuple(parts)


def numeric_solutions(exprs: list, gens: list, guesses: dict, domain: str):
    found = []
    seen = set()
    if len(gens) == 1:
        starts = [guesses[gens[0]]] if gens[0] in guesses else [0.5, 0, 1, 1.5, 2, -0.5, -1, 0.2, 3, -2]
        for start in starts:
            if len(found) >= 6:
                break
            try:
                val = sp.nsolve(exprs[0], gens[0], start, prec=30)
            except Exception:
                continue
            if verify_value_expr(exprs, gens[0], val) is False:
                continue
            comp = complex(sp.N(val, 12))
            if domain == "real" and abs(comp.imag) > 1e-7:
                continue
            key = numeric_key([val])
            if key in seen:
                continue
            seen.add(key)
            found.append({gens[0]: val})
        return found
    if guesses and all(g in guesses for g in gens):
        start_list = [[guesses[g] for g in gens]]
    else:
        start_list = [[0.5] * len(gens), [0] * len(gens), [1] * len(gens), [-0.5] * len(gens)]
    for start in start_list:
        try:
            ans = sp.nsolve(exprs, gens, start, prec=25)
        except Exception:
            continue
        if isinstance(ans, sp.MatrixBase):
            vals = list(ans)
        elif isinstance(ans, (tuple, list, sp.Tuple)):
            vals = list(ans)
        else:
            vals = [ans]
        if len(vals) != len(gens):
            continue
        mapping = {g: v for g, v in zip(gens, vals)}
        if verify_dict_expr(exprs, mapping) is False:
            continue
        if domain == "real":
            comps = [complex(sp.N(v, 12)) for v in vals]
            if any(abs(c.imag) > 1e-7 for c in comps):
                continue
        key = numeric_key(vals)
        if key in seen:
            continue
        seen.add(key)
        found.append(mapping)
    return found


def verify_value_expr(exprs, sym, val):
    verdicts = []
    for expr in exprs:
        try:
            verdicts.append(safe_is_zero(expr.subs(sym, val)))
        except Exception:
            return None
    if any(v is False for v in verdicts):
        return False
    if verdicts and all(v is True for v in verdicts):
        return True
    return None


def verify_dict_expr(exprs, mapping):
    verdicts = []
    for expr in exprs:
        try:
            verdicts.append(safe_is_zero(expr.subs(mapping)))
        except Exception:
            return None
    if any(v is False for v in verdicts):
        return False
    if verdicts and all(v is True for v in verdicts):
        return True
    return None


def is_useful(sol) -> bool:
    if sol is None or sol == sp.EmptySet:
        return False
    if isinstance(sol, sp.ConditionSet):
        return False
    if isinstance(sol, sp.FiniteSet) and len(sol) == 0:
        return False
    return True


def flatten_union(sol) -> list:
    if isinstance(sol, sp.Union):
        parts = []
        for arg in sol.args:
            parts.extend(flatten_union(arg))
        return parts
    return [sol]


def set_card(sym, part, index: int) -> dict:
    try:
        if isinstance(part, sp.ImageSet):
            var = part.lamda.variables[0]
            expr = part.lamda.expr
            latex = f"{L(sym)} = {L(expr)},\\ {L(var)} \\in {L(part.base_set)}"
            plain = f"{sym} = {expr}, {var} ∈ {part.base_set}"
        else:
            raise TypeError
    except Exception:
        latex = f"{L(sym)} \\in {L(part)}"
        plain = f"{sym} ∈ {part}"
    return {
        "title": "通解" if index == 1 else f"通解 {index}",
        "latex": latex,
        "plain": plain,
        "approx": None,
        "badges": ["通解"],
        "verified": None,
        "kind": "set",
        "real": True,
    }


def solve_single_general(model: dict, meta: dict) -> dict:
    item = model["items"][0]
    sym = model["gens"][0]
    expr = item["expr"]
    domain_obj = sp.S.Reals if meta["domain"] == "real" else sp.S.Complexes
    sol = None
    try:
        sol = sp.solveset(expr, sym, domain=domain_obj)
    except Exception:
        sol = None
    if not is_useful(sol):
        try:
            vals = sp.solve(expr, sym)
        except Exception:
            vals = []
        if vals:
            sol = sp.FiniteSet(*vals)
        elif meta["domain"] == "complex":
            try:
                real_sol = sp.solveset(expr, sym, domain=sp.S.Reals)
            except Exception:
                real_sol = None
            if is_useful(real_sol):
                sol = real_sol
    steps = original_steps([item], expanded=False)
    real_cards, complex_cards = [], []
    dropped = 0
    method = "符号求解"
    warnings = []
    if is_useful(sol):
        index = 1
        set_index = 1
        for part in flatten_union(sol):
            if part == sp.EmptySet:
                continue
            if isinstance(part, sp.FiniteSet):
                for val in sorted(list(part), key=lambda v: str(v)):
                    verdict = verify_value([item], sym, val)
                    if verdict is False:
                        dropped += 1
                        continue
                    card = value_card(sym, val, index, 1, verdict)
                    before = len(real_cards)
                    route_card(card, meta["domain"], real_cards, complex_cards)
                    if len(real_cards) != before:
                        index += 1
            else:
                real_cards.append(set_card(sym, part, set_index))
                set_index += 1
    elif meta["numerical"]:
        guesses = parse_guesses(meta["guesses"], model["gens"])
        nums = numeric_solutions([expr], [sym], guesses, meta["domain"])
        for i, mapping in enumerate(nums, 1):
            real_cards.append(dict_card(mapping, [], i, True, numeric=True))
        if real_cards:
            method = "数值近似"
            warnings.append("没有得到完整的公式解，下面是数值近似，可能不是全部解。")
        elif isinstance(sol, sp.ConditionSet):
            real_cards.append(set_card(sym, sol, 1))
            warnings.append("这个方程没有简洁的公式解，下面保留了 SymPy 给出的条件描述。")
    elif isinstance(sol, sp.ConditionSet):
        real_cards.append(set_card(sym, sol, 1))
    notes = finish_notes(list(model["notes"]), real_cards + complex_cards, model["params"], dropped)
    title = "超越方程" if meta["mode"] == "transcendental" else "方程"
    return pack(
        title,
        method,
        model["summary"],
        steps,
        notes,
        warnings,
        real_cards,
        complex_cards,
        meta["domain"],
        plot_for_items(model["items"], model["gens"], real_cards, sol),
    )


def solve_system(model: dict, meta: dict) -> dict:
    items = model["items"]
    gens = model["gens"]
    exprs = [item["expr"] for item in items]
    steps = original_steps(items, expanded=meta["mode"] == "polynomial")
    real_cards, complex_cards = [], []
    dropped = 0
    method = "符号求解"
    warnings = [model.get("warning")]
    handled = False
    if all(is_linear_expr(expr, gens) for expr in exprs):
        method = "线性方程组求解"
        try:
            solset = sp.linsolve(exprs, gens)
        except Exception:
            solset = None
        dicts = tuples_to_dicts(solset, gens)
        if dicts is not None:
            real_cards, complex_cards, dropped = cards_from_dicts(dicts, items, gens, meta["domain"])
            handled = True
    if not handled:
        dicts = []
        try:
            dicts = sp.solve(exprs, gens, dict=True)
        except Exception:
            dicts = []
        good = []
        if isinstance(dicts, list):
            for item in dicts:
                if isinstance(item, dict) and all(isinstance(v, sp.Expr) for v in item.values()):
                    good.append(item)
        if good:
            real_cards, complex_cards, dropped = cards_from_dicts(good, items, gens, meta["domain"])
            handled = True
        else:
            try:
                solset = sp.nonlinsolve(exprs, gens)
            except Exception:
                solset = None
            converted = tuples_to_dicts(solset, gens)
            if converted:
                real_cards, complex_cards, dropped = cards_from_dicts(converted, items, gens, meta["domain"])
                handled = True
            elif solset not in (None, sp.EmptySet) and not isinstance(solset, sp.FiniteSet):
                real_cards.append(
                    {
                        "title": "解集",
                        "latex": L(solset),
                        "plain": str(solset),
                        "approx": None,
                        "badges": ["通解"],
                        "verified": None,
                        "kind": "set",
                        "real": True,
                    }
                )
                handled = True
    proved_empty = handled and not real_cards and not complex_cards and method == "线性方程组求解"
    if (
        handled
        and not real_cards
        and not complex_cards
        and meta["numerical"]
        and meta["mode"] != "polynomial"
        and not proved_empty
    ):
        handled = False
    if not handled and meta["numerical"]:
        guesses = parse_guesses(meta["guesses"], gens)
        nums = numeric_solutions(exprs, gens, guesses, meta["domain"])
        for i, mapping in enumerate(nums, 1):
            real_cards.append(dict_card(mapping, [], i, True, numeric=True))
        if real_cards:
            method = "数值近似"
            warnings.append("没有得到完整的公式解，下面是数值近似，可能不是全部解。")
    if meta["mode"] == "polynomial":
        title = poly_title(len(gens), model["degree"] or 1, len(items))
    elif meta["mode"] == "transcendental":
        title = "超越方程组" if len(items) > 1 else "超越方程"
    else:
        title = "方程组" if len(items) > 1 else "方程"
    notes = finish_notes(list(model["notes"]), real_cards + complex_cards, model["params"], dropped)
    return pack(
        title,
        method,
        model["summary"],
        steps,
        notes,
        warnings,
        real_cards,
        complex_cards,
        meta["domain"],
        plot_for_items(items, gens, real_cards),
    )


def identity_result(model: dict, meta: dict) -> dict:
    notes = list(model["notes"])
    if any(has_denominator(item["lhs"]) or has_denominator(item["rhs"]) for item in model["items"]):
        notes.append("这是恒等式，分母为 0 的点仍要除外。")
    else:
        notes.append("整理后方程变成 0 = 0，未知数取任意允许的值都成立。")
    card = {
        "title": "任意解",
        "latex": L(sp.Eq(0, 0)),
        "plain": "恒成立",
        "approx": None,
        "badges": ["恒成立"],
        "verified": True,
        "kind": "set",
        "real": True,
    }
    steps = original_steps(model["items"], expanded=meta["mode"] == "polynomial")
    return pack(
        "恒等式",
        "化简",
        model["summary"],
        steps,
        notes,
        [],
        [card],
        [],
        meta["domain"],
        plot_for_items(model["items"], model.get("gens") or []),
    )


def empty_result(model: dict, meta: dict, title: str) -> dict:
    steps = original_steps(model["items"], expanded=meta["mode"] == "polynomial")
    return pack(
        title,
        "判定",
        model["summary"],
        steps,
        list(model["notes"]),
        [],
        [],
        [],
        meta["domain"],
        plot_for_items(model["items"], model.get("gens") or []),
    )


def algebraic_title(model, meta) -> str:
    if meta["mode"] == "polynomial":
        return poly_title(len(model["gens"]), max(model["degree"], 1), len(model["items"]))
    if meta["mode"] == "transcendental":
        return "超越方程"
    return "方程组"


def solve_algebraic(items: list[dict], meta: dict) -> dict:
    model = analyze_algebraic(items, meta)
    if model["kind"] == "identity":
        return identity_result(model, meta)
    if model["kind"] == "empty":
        return empty_result(model, meta, algebraic_title(model, meta))
    if (
        meta["mode"] == "polynomial"
        and len(model["gens"]) == 1
        and len(model["items"]) == 1
    ):
        return solve_univariate_poly(model, meta)
    if len(model["gens"]) == 1 and len(model["items"]) == 1 and meta["mode"] != "polynomial":
        return solve_single_general(model, meta)
    return solve_system(model, meta)


def as_initial(lhs, rhs, ivar=None, index=None):
    if rhs.has(sp.Derivative) or rhs.has(AppliedUndef) or rhs.has(sp.Subs):
        return None
    if isinstance(lhs, sp.Subs):
        return lhs, rhs
    if isinstance(lhs, AppliedUndef) and len(lhs.args) == 1:
        arg = lhs.args[0]
        if arg.free_symbols:
            return None
        if ivar is not None and arg == ivar:
            return None
        if index is not None and arg == index:
            return None
        return lhs, rhs
    return None


def collect_functions(expr, ivar_name: str) -> list:
    found = []
    seen = set()
    for node in sp.preorder_traversal(expr):
        target = None
        if isinstance(node, sp.Derivative) and isinstance(node.expr, AppliedUndef):
            target = node.expr.func
            for var in node.variables:
                if str(var) != ivar_name:
                    raise UserError("目前只求解常微分方程，导数都要对所选自变量来求。")
        elif isinstance(node, AppliedUndef):
            target = node.func
        if target is not None and target.name not in seen:
            seen.add(target.name)
            found.append(target)
    return found


def ode_kind(eq, func_app) -> str:
    try:
        hints = sp.classify_ode(eq, func_app)
    except Exception:
        return "常微分方程"
    for hint in hints:
        if hint in ODE_NAMES:
            return ODE_NAMES[hint]
    return "常微分方程"


def build_ui_ics(raw_ics: list, funcs: dict, ivar, local: dict) -> dict:
    mapping = {}
    for ic in raw_ics:
        if not isinstance(ic, dict):
            continue
        if not str(ic.get("value", "")).strip() and not str(ic.get("point", "")).strip():
            continue
        order = require_int(ic.get("order", 0), 0, 3, "导数阶数")
        point = parse_side(str(ic.get("point", "0")), local)
        value = parse_side(str(ic.get("value", "0")), local)
        name = str(ic.get("func") or "")
        func = funcs.get(name) or next(iter(funcs.values()))
        if order == 0:
            key = func(point)
        else:
            key = func(ivar).diff(ivar, order).subs(ivar, point)
        mapping[key] = value
    return mapping


def solve_ode(items: list[dict], meta: dict) -> dict:
    ivar = sp.symbols(meta["ivar"])
    recs = []
    peeled = []
    for item in items:
        ic = as_initial(item["lhs"], item["rhs"], ivar=ivar)
        if ic:
            peeled.append(ic)
        else:
            recs.append(item)
    if not recs:
        raise UserError("只看到初值，还没有微分方程。例如 y' + y = 0。")
    funcs = []
    seen = set()
    for item in recs:
        for func in collect_functions(item["expr"], meta["ivar"]):
            if func.name not in seen:
                seen.add(func.name)
                funcs.append(func)
    if not funcs:
        raise UserError("方程里没有导数。一阶导可以写成 y' 或 dy/dx。")
    apps = [func(ivar) for func in funcs]
    eqs = [item["expr"] for item in recs]
    local = base_local()
    for func in funcs:
        local[func.name] = func
    local[meta["ivar"]] = ivar
    ics = {}
    for lhs, rhs in peeled:
        ics[lhs] = rhs
    ui = []
    for ic in meta["ics"]:
        if isinstance(ic, dict):
            data = dict(ic)
            data.setdefault("func", meta["func"])
            ui.append(data)
    ics.update(build_ui_ics(ui, {func.name: func for func in funcs}, ivar, local))
    steps = original_steps(recs, expanded=False)
    try:
        if len(eqs) == 1 and len(apps) == 1:
            kind = ode_kind(eqs[0], apps[0])
            steps.append({"title": "方程类型", "text": kind})
            result = sp.dsolve(eqs[0], apps[0], ics=ics or None)
        else:
            kind = "常微分方程组"
            steps.append({"title": "方程类型", "text": kind})
            result = sp.dsolve(eqs, apps, ics=ics or None)
    except Exception as exc:
        raise UserError(
            "这个微分方程没有求出闭式解。常见的可分离、一阶线性和常系数线性方程都可以试。"
            f"（{exc}）"
        ) from exc
    sols = result if isinstance(result, list) else [result]
    cards = []
    plain_blob = " ".join(str(sol) for sol in sols)
    has_c = bool(re.search(r"\bC\d+\b", plain_blob))
    if ics and not has_c:
        label = "特解"
    elif ics and has_c:
        label = "部分定解"
    else:
        label = "通解"
    for i, sol in enumerate(sols, 1):
        title = label if len(sols) == 1 else f"{label} {i}"
        cards.append(
            {
                "title": title,
                "latex": L(sol) if isinstance(sol, sp.Eq) else L(sol),
                "plain": str(sol),
                "approx": None,
                "badges": ["特解" if label == "特解" else "通解"],
                "verified": None,
                "kind": "value",
                "real": True,
            }
        )
    notes = []
    consts = []
    for name in re.findall(r"\bC\d+\b", plain_blob):
        if name not in consts:
            consts.append(name)
    if consts:
        notes.append("、".join(consts) + " 是任意常数。")
    if not ics:
        notes.append("未填写初值，得到的是通解。")
    params = []
    for item in recs:
        for sym in item["expr"].free_symbols:
            if sym.name != meta["ivar"] and sym not in params:
                params.append(sym)
    if params:
        notes.append("、".join(sym.name for sym in params) + " 是已知参数。")
    warnings = []
    if ics and has_c:
        warnings.append("结果里还有任意常数，请检查初值是否写全。")
    summary = [f"未知函数 {'、'.join(func.name for func in funcs)}", f"自变量 {meta['ivar']}"]
    if ics:
        summary.append(f"{len(ics)} 个初值")
    return pack(
        "常微分方程组" if len(eqs) > 1 or len(apps) > 1 else kind,
        "微分方程求解" + ("，带初值" if ics else ""),
        summary,
        steps,
        notes,
        warnings,
        cards,
        [],
        "real",
        _ode_plot_payload(sols, meta, ics),
    )


def solve_recurrence(items: list[dict], meta: dict) -> dict:
    func = None
    index = None
    for item in items:
        for node in sp.preorder_traversal(item["expr"]):
            if isinstance(node, AppliedUndef) and node.func.name == meta["rec_func"]:
                func = node.func
                for sym in node.args[0].free_symbols if node.args else []:
                    if sym.name == meta["rec_index"]:
                        index = sym
            if isinstance(node, sp.Symbol) and node.name == meta["rec_index"]:
                index = node
    if func is None:
        raise UserError(
            f"没有看到数列 {meta['rec_func']}。请写成 {meta['rec_func']}({meta['rec_index']}+1) 这种形式。"
        )
    if index is None:
        index = sp.symbols(meta["rec_index"], integer=True, nonnegative=True)
    recs = []
    inits = {}
    for item in items:
        ic = as_initial(item["lhs"], item["rhs"], index=index)
        if ic and isinstance(ic[0], AppliedUndef) and ic[0].func == func:
            inits[ic[0]] = ic[1]
        else:
            recs.append(item)
    local = base_local()
    local[meta["rec_func"]] = func
    local[meta["rec_index"]] = index
    for ic in meta["ics"]:
        if not isinstance(ic, dict):
            continue
        if not str(ic.get("value", "")).strip():
            continue
        point = parse_side(str(ic.get("index", ic.get("point", "0"))), local)
        value = parse_side(str(ic.get("value", "0")), local)
        inits[func(point)] = value
    if len(recs) != 1:
        raise UserError(
            f"请写一条递推方程，例如 {meta['rec_func']}({meta['rec_index']}+1) - 2*{meta['rec_func']}({meta['rec_index']}) = 0。"
            "初值单独写。"
        )
    steps = original_steps(recs, expanded=False)
    try:
        result = sp.rsolve(recs[0]["expr"], func(index), inits or None)
    except Exception as exc:
        raise UserError(
            "没有求出通项。可以写成 a(n+1) - 2*a(n) = 0，并在初值栏填写 a(0)。"
            f"（{exc}）"
        ) from exc
    if result is None:
        raise UserError("没有求出通项。可以写成 a(n+1) - 2*a(n) = 0，并补上足够的初值。")
    if isinstance(result, sp.Eq):
        latex = L(result)
        plain = str(result)
    else:
        latex = L(sp.Eq(func(index), result))
        plain = f"{func(index)} = {result}"
    has_c = bool(re.search(r"\bC\d+\b", plain))
    label = "通项" if inits and not has_c else "通解"
    card = {
        "title": label,
        "latex": latex,
        "plain": plain,
        "approx": None,
        "badges": [label],
        "verified": None,
        "kind": "value",
        "real": True,
    }
    notes = []
    consts = []
    for name in re.findall(r"\bC\d+\b", plain):
        if name not in consts:
            consts.append(name)
    if consts:
        notes.append("、".join(consts) + " 是任意常数，由初值决定。")
    if not inits:
        notes.append("未填写初值，得到的是带任意常数的通解。")
    params = [s for s in recs[0]["expr"].free_symbols if s != index]
    if params:
        notes.append("、".join(s.name for s in params) + " 是已知参数。")
    summary = [f"数列 {meta['rec_func']}", f"下标 {meta['rec_index']}"]
    if inits:
        summary.append(f"{len(inits)} 个初值")
    expr = result.rhs if isinstance(result, sp.Eq) else result
    return pack(
        "递推方程",
        "递推求通项",
        summary,
        steps,
        notes,
        [],
        [card],
        [],
        "real",
        sequence_plot(expr, index, meta["rec_func"], meta["rec_index"]),
    )


def dispatch(payload: dict) -> dict:
    meta = meta_from(payload)
    rows = payload.get("equations")
    if not isinstance(rows, list) or not rows:
        raise UserError("请先输入方程。")
    if len(rows) > 6:
        raise UserError("最多同时求解 6 条方程。")
    _preview_items, items = parse_rows(rows, meta, soft=False)
    if not items:
        raise UserError("请先输入方程。")
    if meta["mode"] in {"polynomial", "transcendental", "system"}:
        return solve_algebraic(items, meta)
    if meta["mode"] == "differential":
        return solve_ode(items, meta)
    return solve_recurrence(items, meta)


def solve_request(payload: dict) -> dict:
    started = time.perf_counter()
    try:
        if not isinstance(payload, dict):
            raise UserError("请求格式不正确。")
        result = dispatch(payload)
        result["ok"] = True
        result["elapsed"] = f"{time.perf_counter() - started:.2f} 秒"
        return result
    except UserError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "error": f"求解时出错：{exc}"}


def preview_request(payload: dict) -> dict:
    try:
        if not isinstance(payload, dict):
            raise UserError("请求格式不正确。")
        meta = meta_from(payload)
        rows = payload.get("equations")
        if not isinstance(rows, list):
            raise UserError("请输入方程。")
        if len(rows) > 6:
            raise UserError("最多 6 条方程。")
        items, parsed = parse_rows(rows, meta, soft=True)
        summary = []
        warning = None
        if parsed and all(item.get("ok") for item in items if not item.get("empty")):
            if meta["mode"] in {"polynomial", "transcendental", "system"}:
                try:
                    model = analyze_algebraic(parsed, meta)
                    summary = model["summary"]
                    warning = model.get("warning")
                    if model["kind"] == "identity":
                        summary = summary + ["整理后恒成立"]
                    if model["kind"] == "empty":
                        warning = "整理后得到不为 0 的常数，方程无解。"
                except UserError as exc:
                    warning = str(exc)
            elif meta["mode"] == "differential":
                summary = [f"函数 {meta['func']}", f"自变量 {meta['ivar']}"]
            else:
                summary = [f"数列 {meta['rec_func']}", f"下标 {meta['rec_index']}"]
        return {"ok": True, "items": items, "summary": summary, "warning": warning}
    except UserError as exc:
        return {"ok": False, "error": str(exc), "items": [], "summary": []}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "error": f"暂时无法预览：{exc}", "items": [], "summary": []}


def mp_entry(payload, queue) -> None:
    try:
        queue.put(solve_request(payload))
    except Exception as exc:
        queue.put({"ok": False, "error": f"求解时出错：{exc}"})


def _blob(result: dict) -> str:
    import json

    return json.dumps(result, ensure_ascii=False)


def self_check() -> None:
    cases = []

    def check(name, payload, pred):
        result = solve_request(payload)
        try:
            ok = bool(pred(result, _blob(result)))
        except Exception as exc:
            ok = False
            result = {"ok": False, "error": str(exc)}
        cases.append((name, ok, None if ok else result))

    check(
        "quadratic",
        {"type": "polynomial", "equations": ["x^2 - 5*x + 6 = 0"], "maxVars": 1, "maxDegree": 2, "domain": "complex"},
        lambda r, b: "x = 2" in b and "x = 3" in b,
    )
    check(
        "degree limit",
        {"type": "polynomial", "equations": ["x^3 + 1 = 0"], "maxVars": 1, "maxDegree": 2},
        lambda r, b: r["ok"] is False,
    )
    check(
        "variable limit",
        {"type": "polynomial", "equations": ["z + 1 = 0"], "maxVars": 1, "maxDegree": 1},
        lambda r, b: r["ok"] is False,
    )
    check(
        "linear system",
        {"type": "polynomial", "equations": ["x + y = 3", "x - y = 1"], "maxVars": 2, "maxDegree": 1, "domain": "real"},
        lambda r, b: "x = 2" in b and "y = 1" in b,
    )
    check(
        "circle",
        {"type": "polynomial", "equations": ["x^2 + y^2 = 25", "x*y = 12"], "maxVars": 2, "maxDegree": 2, "domain": "real"},
        lambda r, b: "3" in b and "4" in b,
    )
    check(
        "power",
        {"type": "transcendental", "equations": ["2^x = 8"], "domain": "real"},
        lambda r, b: "x = 3" in b,
    )
    check(
        "trig",
        {"type": "transcendental", "equations": ["sin(x) = 1/2"], "domain": "real"},
        lambda r, b: "pi" in b and r["ok"],
    )
    check(
        "lambert",
        {"type": "transcendental", "equations": ["exp(x) + x = 0"], "domain": "real"},
        lambda r, b: "LambertW" in b,
    )
    check(
        "numeric",
        {"type": "transcendental", "equations": ["cos(x) = x"], "domain": "real", "numerical": True, "guesses": "x=0.5"},
        lambda r, b: "0.739" in b,
    )
    check(
        "ode ic",
        {"type": "differential", "equations": ["y' = y"], "func": "y", "ivar": "x", "ics": [{"order": 0, "point": "0", "value": "1"}]},
        lambda r, b: "exp(x)" in b,
    )
    check(
        "ode peel",
        {"type": "differential", "equations": ["y' = y", "y(0) = 1"], "func": "y", "ivar": "x"},
        lambda r, b: "exp(x)" in b,
    )
    check(
        "ode second",
        {"type": "differential", "equations": ["y'' + y = 0"], "func": "y", "ivar": "x"},
        lambda r, b: "sin" in b and "cos" in b,
    )
    check(
        "ode system",
        {"type": "differential", "equations": ["y' = z", "z' = -y"], "func": "y", "ivar": "x"},
        lambda r, b: "sin" in b and "z(x)" in b,
    )
    check(
        "recurrence",
        {"type": "recurrence", "equations": ["a(n+1) - 2*a(n) = 0"], "ics": [{"index": "0", "value": "3"}]},
        lambda r, b: "2**n" in b and "3" in b,
    )
    check(
        "fibonacci",
        {
            "type": "recurrence",
            "equations": ["a(n+2) - a(n+1) - a(n) = 0"],
            "ics": [{"index": "0", "value": "0"}, {"index": "1", "value": "1"}],
        },
        lambda r, b: "sqrt" in b,
    )
    failed = [item for item in cases if not item[1]]
    for name, ok, info in cases:
        print(("PASS " if ok else "FAIL ") + name)
        if info is not None:
            print(info.get("error") or info.get("title"), _blob(info)[:500])
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    self_check()
