const TYPES = [
  { id: "polynomial", name: "多项式", blurb: "x 元 y 次，最高 6" },
  { id: "transcendental", name: "超越方程", blurb: "指数、对数、三角" },
  { id: "differential", name: "微分方程", blurb: "y′、y″ 或 dy/dx" },
  { id: "system", name: "方程组", blurb: "最多 6 条一起解" },
  { id: "recurrence", name: "递推方程", blurb: "求数列通项" },
];

const SAMPLES = {
  polynomial: [
    { label: "一元二次", maxVars: 1, maxDegree: 2, domain: "complex", equations: ["x^2 - 5*x + 6 = 0"] },
    { label: "二元一次方程组", maxVars: 2, maxDegree: 1, domain: "real", equations: ["x + y = 3", "x - y = 1"] },
    { label: "二元二次", maxVars: 2, maxDegree: 2, domain: "real", equations: ["x^2 + y^2 = 25", "x*y = 12"] },
    { label: "含参数", maxVars: 1, maxDegree: 2, domain: "complex", equations: ["a*x^2 + b*x + c = 0"] },
  ],
  transcendental: [
    { label: "三角", domain: "real", equations: ["sin(x) = 1/2"] },
    { label: "指数", domain: "real", equations: ["2^x = 8"] },
    { label: "对数", domain: "real", equations: ["ln(x) = 1"] },
    { label: "数值 cos x = x", domain: "real", guesses: "x=0.5", equations: ["cos(x) = x"] },
  ],
  differential: [
    { label: "指数增长", func: "y", ivar: "x", equations: ["y' = y"], ics: [{ order: "0", point: "0", value: "1" }] },
    { label: "简谐振动", func: "y", ivar: "x", equations: ["y'' + y = 0"], ics: [] },
    { label: "一阶线性", func: "y", ivar: "x", equations: ["y' + y = sin(x)"], ics: [] },
    { label: "方程组", func: "y", ivar: "x", equations: ["y' = z", "z' = -y"], ics: [] },
  ],
  system: [
    { label: "三元一次", domain: "real", equations: ["x + y + z = 6", "x - y + z = 2", "x + y - z = 0"] },
    { label: "和与积", domain: "real", equations: ["x + y = 5", "x*y = 6"] },
  ],
  recurrence: [
    { label: "等比数列", equations: ["a(n+1) - 2*a(n) = 0"], ics: [{ index: "0", value: "3" }] },
    { label: "斐波那契", equations: ["a(n+2) - a(n+1) - a(n) = 0"], ics: [{ index: "0", value: "0" }, { index: "1", value: "1" }] },
  ],
};

const HINTS = {
  polynomial: "未知数用 x、y、z、w、v、u，个数和次数都是上限。a、b、c 会当成已知参数。相乘可以写 2x，乘方用 ^。",
  transcendental: "ln 是自然对数，lg 是以 10 为底。e 和 π 是常数。未知数同样用 x 到 u。求不出公式解时，可填数值初值。",
  differential: "y' 表示 dy/dx，y'' 是二阶导数。初值可以写成单独一条 y(0) = 1，也可以填在下面的初值栏。",
  system: "每行一条方程，最多 6 条。未知数用 x、y、z、w、v、u，其他字母当成已知参数。",
  recurrence: "写成 a(n+1) - 2*a(n) = 0 这种形式。初值填在下面，例如 a(0) = 3。",
};

const TOKEN = {
  sin: { insert: "sin()", back: 1, cls: "fn" },
  cos: { insert: "cos()", back: 1, cls: "fn" },
  tan: { insert: "tan()", back: 1, cls: "fn" },
  asin: { insert: "asin()", back: 1, cls: "fn" },
  acos: { insert: "acos()", back: 1, cls: "fn" },
  atan: { insert: "atan()", back: 1, cls: "fn" },
  ln: { insert: "ln()", back: 1, cls: "fn" },
  lg: { insert: "lg()", back: 1, cls: "fn" },
  exp: { insert: "exp()", back: 1, cls: "fn" },
  abs: { insert: "abs()", back: 1, cls: "fn" },
  "√": { insert: "sqrt()", back: 1, cls: "fn" },
  "π": { insert: "pi", cls: "fn" },
  e: { insert: "e", cls: "fn" },
  i: { insert: "I", cls: "fn" },
  "^": { insert: "^", cls: "op" },
  "^2": { insert: "^2", cls: "op" },
  "+": { insert: "+", cls: "op" },
  "-": { insert: "-", cls: "op" },
  "*": { insert: "*", cls: "op" },
  "/": { insert: "/", cls: "op" },
  "=": { insert: " = ", cls: "op" },
  "⌫": { action: "backspace", cls: "muted" },
  "清空": { action: "clear", cls: "muted" },
};

const state = {
  type: "polynomial",
  maxVars: 1,
  maxDegree: 2,
  domains: { polynomial: "complex", transcendental: "real", system: "real" },
  numerical: true,
  guesses: "",
  func: "y",
  ivar: "x",
  recFunc: "a",
  recIndex: "n",
  equations: ["x^2 - 5*x + 6 = 0"],
  ics: [],
  coeffs: ["", "", "1"],
};

const memory = {};
let activeEl = null;
let previewToken = 0;
let lastResult = null;

const typeNav = document.getElementById("typeNav");
const settings = document.getElementById("settings");
const samples = document.getElementById("samples");
const coeffBox = document.getElementById("coeffBox");
const eqList = document.getElementById("eqList");
const icBlock = document.getElementById("icBlock");
const keypad = document.getElementById("keypad");
const summary = document.getElementById("summary");
const formNote = document.getElementById("formNote");
const solveBtn = document.getElementById("solveBtn");
const result = document.getElementById("result");

function h(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value == null) return;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  });
  [].concat(children).forEach((child) => {
    if (child == null) return;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  });
  return node;
}

function snapshot() {
  return {
    equations: state.equations.slice(),
    maxVars: state.maxVars,
    maxDegree: state.maxDegree,
    numerical: state.numerical,
    guesses: state.guesses,
    func: state.func,
    ivar: state.ivar,
    recFunc: state.recFunc,
    recIndex: state.recIndex,
    ics: state.ics.map((ic) => ({ ...ic })),
    domain: state.domains[state.type] || "real",
    coeffs: state.coeffs.slice(),
  };
}

function loadSnapshot(saved) {
  state.equations = saved.equations.slice();
  state.maxVars = saved.maxVars;
  state.maxDegree = saved.maxDegree;
  state.numerical = saved.numerical;
  state.guesses = saved.guesses;
  state.func = saved.func;
  state.ivar = saved.ivar;
  state.recFunc = saved.recFunc;
  state.recIndex = saved.recIndex;
  state.ics = saved.ics.map((ic) => ({ ...ic }));
  state.coeffs = saved.coeffs.slice();
  if (state.domains[state.type] !== undefined) state.domains[state.type] = saved.domain;
}

function domain() {
  return state.domains[state.type] || "real";
}

function renderNav() {
  typeNav.replaceChildren(
    ...TYPES.map((type) => {
      const btn = h("button", { class: "type-btn" + (type.id === state.type ? " active" : ""), type: "button" }, [
        h("strong", { text: type.name }),
        h("span", { text: type.blurb }),
      ]);
      btn.addEventListener("click", () => switchType(type.id));
      return btn;
    })
  );
}

function option(value, label, selected) {
  const node = h("option", { value, text: label });
  if (selected) node.selected = true;
  return node;
}

function renderSettings() {
  const fields = [];
  if (state.type === "polynomial") {
    const vars = h("select");
    const deg = h("select");
    for (let i = 1; i <= 6; i += 1) {
      vars.append(option(String(i), `${i} 元`, i === state.maxVars));
      deg.append(option(String(i), `最高 ${i} 次`, i === state.maxDegree));
    }
    vars.addEventListener("change", () => {
      state.maxVars = Number(vars.value);
      renderCoeffs();
      schedulePreview();
    });
    deg.addEventListener("change", () => {
      state.maxDegree = Number(deg.value);
      while (state.coeffs.length <= state.maxDegree) state.coeffs.push("");
      renderCoeffs();
      schedulePreview();
    });
    fields.push(h("div", { class: "field" }, [h("label", { text: "未知数个数" }), vars]));
    fields.push(h("div", { class: "field" }, [h("label", { text: "最高次数" }), deg]));
  }
  if (["polynomial", "transcendental", "system"].includes(state.type)) {
    const dom = h("select");
    dom.append(option("real", "只看实数解", domain() === "real"));
    dom.append(option("complex", "全部解，含复数", domain() === "complex"));
    dom.addEventListener("change", () => {
      state.domains[state.type] = dom.value;
      schedulePreview();
    });
    fields.push(h("div", { class: "field" }, [h("label", { text: "解的范围" }), dom]));
    const guess = h("input", { type: "text", value: state.guesses, placeholder: "x=0.5 或 x=1, y=0", class: "mathish" });
    guess.addEventListener("input", () => {
      state.guesses = guess.value;
      scheduleSolve();
    });
    fields.push(h("div", { class: "field grow" }, [h("label", { text: "数值初值（可选）" }), guess]));
    const box = h("input", { type: "checkbox" });
    box.checked = state.numerical;
    box.addEventListener("change", () => {
      state.numerical = box.checked;
      scheduleSolve();
    });
    fields.push(h("label", { class: "check" }, [box, "求不出公式解时尝试数值解"]));
  }
  if (state.type === "differential") {
    fields.push(letterField("函数名", state.func, (value) => {
      state.func = value || "y";
      renderKeypad();
      renderIcs();
      schedulePreview();
    }));
    fields.push(letterField("自变量", state.ivar, (value) => {
      state.ivar = value || "x";
      renderKeypad();
      renderIcs();
      schedulePreview();
    }));
  }
  if (state.type === "recurrence") {
    fields.push(letterField("数列名", state.recFunc, (value) => {
      state.recFunc = value || "a";
      renderKeypad();
      renderIcs();
      schedulePreview();
    }));
    fields.push(letterField("下标", state.recIndex, (value) => {
      state.recIndex = value || "n";
      renderKeypad();
      renderIcs();
      schedulePreview();
    }));
  }
  settings.replaceChildren(
    h("div", { class: "settings" }, fields),
    h("p", { class: "hint", text: HINTS[state.type] })
  );
}

function letterField(label, value, oninput) {
  const input = h("input", { type: "text", value, maxlength: "1", class: "mathish" });
  input.addEventListener("input", () => oninput(input.value.trim()));
  return h("div", { class: "field" }, [h("label", { text: label }), input]);
}

function renderSamples() {
  samples.replaceChildren(
    ...SAMPLES[state.type].map((sample) => {
      const btn = h("button", { class: "chip", type: "button", text: sample.label });
      btn.addEventListener("click", () => applySample(sample));
      return btn;
    })
  );
}

function renderCoeffs() {
  if (state.type !== "polynomial" || state.maxVars !== 1) {
    coeffBox.replaceChildren();
    return;
  }
  while (state.coeffs.length <= state.maxDegree) state.coeffs.push("");
  const grid = h("div", { class: "coeff-grid" });
  for (let power = state.maxDegree; power >= 0; power -= 1) {
    const input = h("input", {
      type: "text",
      value: state.coeffs[power] || "",
      placeholder: "0",
      class: "mathish",
    });
    input.addEventListener("input", () => {
      state.coeffs[power] = input.value;
    });
    const mark = power === 0 ? "常数" : power === 1 ? "x" : `x^${power}`;
    grid.append(h("label", {}, [mark, input]));
  }
  const fill = h("button", { class: "text-btn", type: "button", text: "用这些系数填入方程" });
  fill.addEventListener("click", () => {
    const terms = [];
    for (let power = state.maxDegree; power >= 0; power -= 1) {
      const coeff = (state.coeffs[power] || "").trim();
      if (!coeff || coeff === "0") continue;
      if (power === 0) terms.push(`(${coeff})`);
      else if (power === 1) terms.push(`(${coeff})*x`);
      else terms.push(`(${coeff})*x^${power}`);
    }
    state.equations[0] = (terms.length ? terms.join(" + ") : "0") + " = 0";
    renderEquations();
    schedulePreview();
  });
  coeffBox.replaceChildren(h("div", { class: "coeff" }, [h("div", { class: "block-label", text: "一元时可以用系数填写" }), grid, fill]));
}

function renderEquations() {
  if (!state.equations.length) state.equations = [""];
  eqList.replaceChildren(
    ...state.equations.map((value, index) => {
      const area = h("textarea", { class: "equation mathish", "data-i": String(index), spellcheck: "false" });
      area.value = value;
      const remove = h("button", { class: "icon-btn", type: "button", "data-remove": String(index), text: "删除" });
      if (state.equations.length === 1) remove.hidden = true;
      return h("div", { class: "eq" }, [
        h("div", { class: "eq-top" }, [h("span", { text: `方程 ${index + 1}` }), remove]),
        area,
        h("div", { class: "preview", "data-preview": String(index) }),
      ]);
    })
  );
}

function renderIcs() {
  if (!["differential", "recurrence"].includes(state.type)) {
    icBlock.replaceChildren();
    return;
  }
  const rows = state.ics.map((ic, index) => {
    if (state.type === "recurrence") {
      const at = h("input", { type: "text", value: ic.index || "0", placeholder: "下标", class: "mathish", "data-ic": String(index), "data-key": "index" });
      const val = h("input", { type: "text", value: ic.value || "", placeholder: "项的值", class: "mathish", "data-ic": String(index), "data-key": "value" });
      const del = h("button", { class: "icon-btn", type: "button", "data-del-ic": String(index), text: "删除" });
      return h("div", { class: "ic-row" }, [
        h("span", { text: `${state.recFunc || "a"}( )` }),
        at,
        val,
        del,
      ]);
    }
    const order = h("select", { "data-ic": String(index), "data-key": "order" });
    const fname = state.func || "y";
    ["函数值 " + fname, fname + "′", fname + "″", fname + "‴"].forEach((label, n) => {
      order.append(option(String(n), label, String(ic.order || "0") === String(n)));
    });
    const point = h("input", { type: "text", value: ic.point || "0", placeholder: "自变量取值", class: "mathish", "data-ic": String(index), "data-key": "point" });
    const val = h("input", { type: "text", value: ic.value || "", placeholder: "等于", class: "mathish", "data-ic": String(index), "data-key": "value" });
    const del = h("button", { class: "icon-btn", type: "button", "data-del-ic": String(index), text: "删除" });
    return h("div", { class: "ic-row" }, [order, point, val, del]);
  });
  const add = h("button", { class: "text-btn", type: "button", text: "添加初值" });
  add.addEventListener("click", () => {
    if (state.type === "recurrence") state.ics.push({ index: String(state.ics.length), value: "" });
    else state.ics.push({ order: "0", point: "0", value: "" });
    renderIcs();
  });
  const title = state.type === "recurrence" ? "初值：下标和对应的项" : `初值：在自变量 ${state.ivar || "x"} 处`;
  icBlock.replaceChildren(h("div", { class: "ic" }, [h("div", { class: "block-label", text: title }), ...rows, add]));
}

function extraKeys() {
  if (state.type === "differential") {
    const f = state.func || "y";
    const x = state.ivar || "x";
    return [
      { label: `${f}′`, insert: `${f}'`, cls: "fn" },
      { label: `${f}″`, insert: `${f}''`, cls: "fn" },
      { label: `${f}‴`, insert: `${f}'''`, cls: "fn" },
      { label: `d${f}/d${x}`, insert: `d${f}/d${x}`, cls: "fn" },
      { label: `d²${f}/d${x}²`, insert: `d^2${f}/d${x}^2`, cls: "fn" },
      { label: `${f}(0)`, insert: `${f}(0)`, cls: "fn" },
      { label: "z′", insert: "z'", cls: "fn" },
    ];
  }
  if (state.type === "recurrence") {
    const a = state.recFunc || "a";
    const n = state.recIndex || "n";
    return [
      { label: `${a}(${n})`, insert: `${a}(${n})`, cls: "fn" },
      { label: `${a}(${n}+1)`, insert: `${a}(${n}+1)`, cls: "fn" },
      { label: `${a}(${n}+2)`, insert: `${a}(${n}+2)`, cls: "fn" },
      { label: n, insert: n, cls: "fn" },
    ];
  }
  if (state.type === "transcendental") {
    return [
      { label: "sinh", insert: "sinh()", back: 1, cls: "fn" },
      { label: "cosh", insert: "cosh()", back: 1, cls: "fn" },
      { label: "tanh", insert: "tanh()", back: 1, cls: "fn" },
    ];
  }
  return [];
}

function renderKeypad() {
  const labels = ["x", "y", "z", "^", "(", ")", "⌫", "7", "8", "9", "+", "sin", "cos", "tan", "4", "5", "6", "-", "ln", "lg", "exp", "1", "2", "3", "*", "√", "π", "e", "0", ".", "=", "/", "abs", "i", "清空", "w", "v", "u", "^2", "asin", "acos", "atan"];
  const keys = labels.map((label) => ({ label, ...(TOKEN[label] || { insert: label }) }));
  extraKeys().forEach((key) => keys.push(key));
  keypad.replaceChildren(
    ...keys.map((key) => {
      const btn = h("button", { class: "key " + (key.cls || ""), type: "button", text: key.label });
      btn.addEventListener("click", () => useKey(key));
      return btn;
    })
  );
}

function targetField() {
  if (activeEl && document.body.contains(activeEl)) return activeEl;
  return eqList.querySelector("textarea.equation");
}

function useKey(key) {
  const el = targetField();
  if (!el) return;
  if (key.action === "clear") {
    el.value = "";
  } else if (key.action === "backspace") {
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    if (start !== end) el.value = el.value.slice(0, start) + el.value.slice(end);
    else if (start > 0) el.value = el.value.slice(0, start - 1) + el.value.slice(end);
    const pos = start === end ? Math.max(0, start - 1) : start;
    el.focus();
    el.setSelectionRange(pos, pos);
  } else {
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    el.value = el.value.slice(0, start) + key.insert + el.value.slice(end);
    const pos = start + key.insert.length - (key.back || 0);
    el.focus();
    el.setSelectionRange(pos, pos);
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function renderShell() {
  renderNav();
  renderSettings();
  renderSamples();
  renderCoeffs();
  renderEquations();
  renderIcs();
  renderKeypad();
}

function switchType(type) {
  if (type === state.type) return;
  memory[state.type] = snapshot();
  state.type = type;
  if (memory[type]) loadSnapshot(memory[type]);
  else applySample(SAMPLES[type][0], true);
  renderShell();
  schedulePreview();
}

function applySample(sample, silent) {
  state.equations = sample.equations.slice();
  if (sample.maxVars) state.maxVars = sample.maxVars;
  if (sample.maxDegree) state.maxDegree = sample.maxDegree;
  if (sample.domain) state.domains[state.type] = sample.domain;
  if (sample.guesses !== undefined) state.guesses = sample.guesses;
  if (sample.func) state.func = sample.func;
  if (sample.ivar) state.ivar = sample.ivar;
  if ("ics" in sample) state.ics = sample.ics.map((ic) => ({ ...ic }));
  if (!silent) {
    renderShell();
    schedulePreview();
  }
}

function buildPayload(keepEmpty) {
  const equations = keepEmpty ? state.equations.slice() : state.equations.map((eq) => eq.trim()).filter(Boolean);
  return {
    type: state.type,
    equations,
    maxVars: state.maxVars,
    maxDegree: state.maxDegree,
    domain: domain(),
    numerical: state.numerical,
    guesses: state.guesses,
    func: state.func || "y",
    ivar: state.ivar || "x",
    recFunc: state.recFunc || "a",
    recIndex: state.recIndex || "n",
    ics: state.ics.filter((ic) => String(ic.value || "").trim() !== ""),
  };
}

function renderMath(node, latex, display) {
  node.replaceChildren();
  if (!latex) return;
  if (window.katex) {
    try {
      node.innerHTML = katex.renderToString(latex, {
        displayMode: display !== false,
        throwOnError: false,
        strict: "ignore",
      });
      return;
    } catch (err) {
      node.textContent = latex;
      return;
    }
  }
  node.textContent = latex;
}

let previewTimer = 0;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(preview, 220);
}

function onGitHubPages() {
  return location.hostname.endsWith("github.io");
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("计算引擎没有加载成功。"));
    document.head.appendChild(script);
  });
}

let enginePromise = null;
function engine() {
  if (!enginePromise) enginePromise = startEngine();
  return enginePromise;
}

async function startEngine() {
  formNote.textContent = "正在加载计算引擎，第一次打开大约需要十几秒。";
  formNote.className = "note";
  await loadScript("https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js");
  const pyodide = await loadPyodide();
  await pyodide.loadPackage("sympy");
  const root = new URL(".", location.href);
  const plotter = await (await fetch(new URL("plotter.py", root))).text();
  const solver = await (await fetch(new URL("solver.py", root))).text();
  pyodide.FS.writeFile("plotter.py", plotter);
  pyodide.FS.writeFile("solver.py", solver);
  pyodide.runPython(`
import json
import solver as solver_mod

def run_preview(text):
    return json.dumps(solver_mod.preview_request(json.loads(text)), ensure_ascii=False)

def run_solve(text):
    return json.dumps(solver_mod.solve_request(json.loads(text)), ensure_ascii=False)
`);
  if (!formNote.classList.contains("warn") && !formNote.classList.contains("bad")) formNote.textContent = "";
  return pyodide;
}

async function callApi(path, payload) {
  if (!onGitHubPages()) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }
  const pyodide = await engine();
  const fn = pyodide.globals.get(path.endsWith("preview") ? "run_preview" : "run_solve");
  try {
    return JSON.parse(fn(JSON.stringify(payload)));
  } finally {
    fn.destroy();
  }
}

async function preview() {
  const token = ++previewToken;
  try {
    const data = await callApi("/api/preview", buildPayload(true));
    if (token !== previewToken) return;
    summary.replaceChildren(...(data.summary || []).map((text) => h("span", { text })));
    formNote.textContent = data.warning || data.error || "";
    formNote.className = "note" + (data.warning || data.error ? " warn" : "");
    (data.items || []).forEach((item, index) => {
      const box = eqList.querySelector(`[data-preview="${index}"]`);
      if (!box) return;
      if (item.empty) {
        box.className = "preview";
        box.replaceChildren();
        return;
      }
      if (!item.ok) {
        box.className = "preview bad";
        box.textContent = item.error;
        return;
      }
      box.className = "preview";
      renderMath(box, item.latex, false);
    });
    scheduleSolve();
  } catch (err) {
    if (token !== previewToken) return;
    formNote.textContent = onGitHubPages()
      ? "计算引擎没有加载成功。请刷新页面后再试。"
      : "连接不上求解服务。请关闭页面后重新运行 启动.bat。";
    formNote.className = "note bad";
  }
}

function badgeClass(text) {
  if (text === "实数" || text === "特解" || text === "通项") return "badge real";
  if (text === "复数" || text === "数值近似") return "badge complex";
  return "badge";
}

function solutionNode(card) {
  const badges = h("div", { class: "badges" }, (card.badges || []).map((text) => h("span", { class: badgeClass(text), text })));
  const body = [h("header", {}, [h("h3", { text: card.title || "解" }), badges])];
  if (card.latex) {
    const math = h("div", { class: "math" });
    renderMath(math, card.latex, true);
    body.push(math);
  }
  if (card.approx) body.push(h("p", { class: "approx", text: "约 " + card.approx }));
  if (card.text) body.push(h("p", { text: card.text }));
  return h("article", { class: "card" }, body);
}

function renderResult(data) {
  lastResult = data;
  result.replaceChildren();
  if (!data) {
    result.append(
      h("div", { class: "placeholder" }, [
        h("h2", { text: "解会显示在这里" }),
        h("p", { text: "输入方程后，这里给出公式解或数值近似。" }),
      ])
    );
    return;
  }
  if (!data.ok) {
    result.append(h("div", { class: "callout error", text: data.error || "求解失败" }));
    drawPlot(null);
    return;
  }
  const copy = h("button", { class: "copy", type: "button", text: "复制" });
  copy.addEventListener("click", async () => {
    const lines = [];
    (data.solutions || []).concat(data.complex_solutions || []).forEach((card) => {
      lines.push(card.approx ? `${card.plain}    约 ${card.approx}` : card.plain);
    });
    if (!lines.length) lines.push(data.empty_message || "无解");
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      copy.textContent = "已复制";
    } catch (err) {
      copy.textContent = "复制失败";
    }
  });
  const steps = h("ol", { class: "steps" });
  (data.steps || []).forEach((step) => {
    const li = h("li", {}, [h("strong", { text: step.title || "" })]);
    if (step.text) li.append(h("p", { text: step.text }));
    if (step.latex) {
      const math = h("div", { class: "math" });
      renderMath(math, step.latex, true);
      li.append(math);
    }
    steps.append(li);
  });
  const cards = h("div", { class: "cards" });
  if ((data.solutions || []).length) data.solutions.forEach((card) => cards.append(solutionNode(card)));
  else cards.append(h("div", { class: "callout", text: data.empty_message || "无解。" }));
  const chunks = [
    h("div", { class: "result-head" }, [
      h("div", {}, [
        h("h2", { text: data.title || "结果" }),
        h("p", { class: "meta", text: [data.method, data.elapsed].filter(Boolean).join(" · ") }),
      ]),
      copy,
    ]),
    h("div", { class: "summary" }, (data.summary || []).map((text) => h("span", { text }))),
    cards,
  ];
  if ((data.steps || []).length) {
    chunks.push(h("details", { class: "fold" }, [h("summary", { text: "整理过程" }), steps]));
  }
  (data.warnings || []).forEach((text) => chunks.push(h("div", { class: "callout warn", text })));
  if ((data.complex_solutions || []).length) {
    const fold = h("details", { class: "fold" }, [
      h("summary", { text: `复数解（${data.complex_solutions.length} 个）` }),
      h("div", { class: "cards" }, data.complex_solutions.map(solutionNode)),
    ]);
    chunks.push(fold);
  }
  if ((data.notes || []).length) {
    chunks.push(h("ul", { class: "notes" }, data.notes.map((text) => h("li", { text }))));
  }
  result.append(...chunks);
  drawPlot(data.plot || null);
}

let solveToken = 0;
async function solve(options = {}) {
  const auto = options.auto === true;
  const payload = buildPayload(false);
  if (!payload.equations.length) {
    if (!auto) renderResult({ ok: false, error: "请先输入方程。" });
    return;
  }
  const token = ++solveToken;
  if (!auto) {
    solveBtn.disabled = true;
    solveBtn.textContent = "正在求解…";
  }
  try {
    const data = await callApi("/api/solve", payload);
    if (token !== solveToken) return;
    renderResult(data);
  } catch (err) {
    if (token !== solveToken) return;
    renderResult({
      ok: false,
      error: onGitHubPages()
        ? "计算引擎没有加载成功。请刷新页面后再试。"
        : "连接不上求解服务。请关闭页面后重新运行 启动.bat。",
    });
  } finally {
    if (!auto) {
      solveBtn.disabled = false;
      solveBtn.replaceChildren("求解 ", h("kbd", { text: "Ctrl" }), h("kbd", { text: "Enter" }));
    }
  }
}

let solveTimer = 0;
function scheduleSolve() {
  clearTimeout(solveTimer);
  solveTimer = setTimeout(() => {
    if (eqList.querySelector(".preview.bad")) return;
    solve({ auto: true });
  }, 320);
}

document.addEventListener("focusin", (event) => {
  if (event.target.matches("textarea, input.mathish")) activeEl = event.target;
});

eqList.addEventListener("input", (event) => {
  const area = event.target.closest("textarea.equation");
  if (!area) return;
  state.equations[Number(area.dataset.i)] = area.value;
  schedulePreview();
});

eqList.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-remove]");
  if (!btn) return;
  state.equations.splice(Number(btn.dataset.remove), 1);
  renderEquations();
  schedulePreview();
});

icBlock.addEventListener("input", (event) => {
  const input = event.target.closest("[data-ic]");
  if (!input) return;
  const ic = state.ics[Number(input.dataset.ic)];
  if (!ic) return;
  ic[input.dataset.key] = input.value;
  scheduleSolve();
});

icBlock.addEventListener("change", (event) => {
  const input = event.target.closest("[data-ic]");
  if (!input) return;
  const ic = state.ics[Number(input.dataset.ic)];
  if (!ic) return;
  ic[input.dataset.key] = input.value;
  scheduleSolve();
});

icBlock.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-del-ic]");
  if (!btn) return;
  state.ics.splice(Number(btn.dataset.delIc), 1);
  renderIcs();
  scheduleSolve();
});

document.getElementById("addEq").addEventListener("click", () => {
  if (state.equations.length >= 6) return;
  state.equations.push("");
  renderEquations();
});

solveBtn.addEventListener("click", solve);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    solve();
  }
});

const SERIES_COLORS = ["#1e6b5c", "#c4492c", "#274c77", "#8a5a12"];
const MARKER_COLORS = {
  root: "#c4492c",
  extremum: "#8a5a12",
  intercept: "#274c77",
  intersection: "#c4492c",
  initial: "#1e6b5c",
  term: "#1e6b5c",
};
let plotData = null;

function drawPlot(plot) {
  plotData = plot && !plot.empty ? plot : null;
  const note = document.getElementById("graphNote");
  const empty = document.getElementById("graphEmpty");
  const stage = document.getElementById("graphStage");
  if (note) note.textContent = plot && plot.note && plotData ? plot.note : "";
  if (empty) {
    empty.textContent = plot && plot.empty && plot.note
      ? plot.note
      : "输入方程后，这里会按图像范围自动画出函数，并标出根、交点和极值。";
  }
  if (stage) stage.classList.toggle("has-plot", Boolean(plotData));
  paintPlot();
}

function niceStep(span, count) {
  const rough = span / Math.max(count, 1);
  const mag = 10 ** Math.floor(Math.log10(rough || 1));
  const err = rough / mag;
  const base = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  return base * mag;
}

function niceTicks(min, max, count) {
  if (!(max > min)) return [min];
  const step = niceStep(max - min, count);
  const start = Math.ceil((min - step * 1e-6) / step) * step;
  const ticks = [];
  for (let value = start; value <= max + step * 1e-6; value += step) {
    ticks.push(Math.abs(value) < step * 1e-6 ? 0 : value);
    if (ticks.length > 12) break;
  }
  return ticks;
}

function formatTick(value) {
  if (Object.is(value, -0) || Math.abs(value) < 1e-10) return "0";
  const abs = Math.abs(value);
  if (abs >= 10000 || (abs > 0 && abs < 0.001)) return value.toExponential(1);
  const text = abs >= 100 ? value.toFixed(0) : abs >= 1 ? value.toFixed(2) : value.toFixed(3);
  return text.replace(/\.?0+$/, "");
}

function paintPlot() {
  const canvas = document.getElementById("plotCanvas");
  const stage = document.getElementById("graphStage");
  if (!canvas || !stage) return;
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  if (width < 40 || height < 40) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!plotData) return;
  const pad = { left: 52, right: 16, top: plotData.series.length > 1 ? 28 : 14, bottom: 32 };
  const plotW = Math.max(width - pad.left - pad.right, 40);
  const plotH = Math.max(height - pad.top - pad.bottom, 40);
  const xMin = Number(plotData.xMin);
  const xMax = Number(plotData.xMax);
  const yMin = Number(plotData.yMin);
  const yMax = Number(plotData.yMax);
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  let originX = pad.left;
  let originY = pad.top;
  let usedW = plotW;
  let usedH = plotH;
  if (plotData.equal) {
    const unit = Math.min(plotW / xSpan, plotH / ySpan);
    usedW = unit * xSpan;
    usedH = unit * ySpan;
    originX = pad.left + (plotW - usedW) / 2;
    originY = pad.top + (plotH - usedH) / 2;
  }
  const X = (x) => originX + ((x - xMin) / xSpan) * usedW;
  const Y = (y) => originY + ((yMax - y) / ySpan) * usedH;

  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#efe6d6";
  ctx.lineWidth = 1;
  niceTicks(xMin, xMax, 6).forEach((tick) => {
    const x = X(tick);
    ctx.beginPath();
    ctx.moveTo(x, originY);
    ctx.lineTo(x, originY + usedH);
    ctx.stroke();
  });
  niceTicks(yMin, yMax, 5).forEach((tick) => {
    const y = Y(tick);
    ctx.beginPath();
    ctx.moveTo(originX, y);
    ctx.lineTo(originX + usedW, y);
    ctx.stroke();
  });

  ctx.save();
  ctx.beginPath();
  ctx.rect(originX, originY, usedW, usedH);
  ctx.clip();
  ctx.strokeStyle = "#c8bba6";
  ctx.lineWidth = 1.2;
  if (yMin <= 0 && yMax >= 0) {
    ctx.beginPath();
    ctx.moveTo(originX, Y(0));
    ctx.lineTo(originX + usedW, Y(0));
    ctx.stroke();
  }
  if (xMin <= 0 && xMax >= 0) {
    ctx.beginPath();
    ctx.moveTo(X(0), originY);
    ctx.lineTo(X(0), originY + usedH);
    ctx.stroke();
  }
  (plotData.series || []).forEach((series, index) => {
    ctx.strokeStyle = SERIES_COLORS[index % SERIES_COLORS.length];
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    (series.polylines || []).forEach((line) => {
      if (!line.length) return;
      ctx.beginPath();
      line.forEach((point, i) => {
        const px = X(point[0]);
        const py = Y(point[1]);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.stroke();
    });
  });
  ctx.restore();

  ctx.fillStyle = "#5e564c";
  ctx.font = "12px Noto Sans SC, Microsoft YaHei, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  niceTicks(xMin, xMax, 6).forEach((tick) => {
    ctx.fillText(formatTick(tick), X(tick), pad.top + plotH + 6);
  });
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  niceTicks(yMin, yMax, 5).forEach((tick) => {
    ctx.fillText(formatTick(tick), pad.left - 8, Y(tick));
  });
  ctx.textAlign = "center";
  ctx.fillText(plotData.xLabel || "x", pad.left + plotW / 2, height - 14);
  ctx.save();
  ctx.translate(14, pad.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(plotData.yLabel || "y", 0, 0);
  ctx.restore();

  const boxes = [];
  (plotData.markers || []).forEach((marker) => {
    const x = X(marker.x);
    const y = Y(marker.y);
    if (x < pad.left - 4 || x > pad.left + plotW + 4 || y < pad.top - 4 || y > pad.top + plotH + 4) return;
    ctx.beginPath();
    ctx.fillStyle = MARKER_COLORS[marker.kind] || "#1e6b5c";
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.arc(x, y, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    const label = marker.label || "";
    ctx.font = "12px Noto Sans SC, Microsoft YaHei, sans-serif";
    const boxW = ctx.measureText(label).width + 8;
    const boxH = 16;
    const spots = [[8, -18], [8, 8], [-boxW - 6, -18], [-boxW - 6, 8]];
    for (const [dx, dy] of spots) {
      const box = { x: x + dx, y: y + dy, w: boxW, h: boxH };
      const hits = boxes.some((old) => box.x < old.x + old.w && box.x + box.w > old.x && box.y < old.y + old.h && box.y + box.h > old.y);
      if (hits) continue;
      boxes.push(box);
      ctx.fillStyle = "#1c1915";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(label, box.x, box.y);
      break;
    }
  });

  if ((plotData.series || []).length > 1) {
    let cursor = pad.left;
    ctx.font = "12px Noto Sans SC, Microsoft YaHei, sans-serif";
    ctx.textBaseline = "middle";
    plotData.series.forEach((series, index) => {
      ctx.fillStyle = SERIES_COLORS[index % SERIES_COLORS.length];
      ctx.fillRect(cursor, 8, 14, 3);
      cursor += 18;
      ctx.fillStyle = "#1c1915";
      ctx.textAlign = "left";
      const name = series.name || "";
      ctx.fillText(name, cursor, 10);
      cursor += ctx.measureText(name).width + 14;
    });
  }
}

const plotStage = document.getElementById("graphStage");
if (plotStage && "ResizeObserver" in window) {
  new ResizeObserver(() => paintPlot()).observe(plotStage);
}
window.addEventListener("resize", paintPlot);

renderShell();
renderResult(null);
schedulePreview();
solve();
