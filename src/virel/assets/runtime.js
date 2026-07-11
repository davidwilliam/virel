/* Virel browser runtime — fine-grained signals, no virtual DOM.
 *
 * Compiled pages import this module and register bindings against
 * data-v element ids. State updates touch only the DOM nodes whose
 * expressions read the changed signal (SPEC 9.3). Server communication
 * is plain HTTP: JSON actions and streamed fetch responses. No WebSocket.
 */

let activeEffect = null;

export function signal(value) {
  const subscribers = new Set();
  return {
    get() {
      if (activeEffect) subscribers.add(activeEffect);
      return value;
    },
    set(next) {
      if (next === value) return;
      value = next;
      for (const fn of [...subscribers]) fn();
    },
  };
}

export function effect(fn) {
  const run = () => {
    const previous = activeEffect;
    activeEffect = run;
    try {
      fn();
    } finally {
      activeEffect = previous;
    }
  };
  run();
}

export function computed(fn) {
  const inner = signal(undefined);
  effect(() => inner.set(fn()));
  return { get: inner.get };
}

function el(id) {
  const node = document.querySelector(`[data-v="${id}"]`);
  if (!node) console.warn(`virel: missing element for binding id ${id}`);
  return node;
}

export function bindText(id, fn) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    const value = fn();
    node.textContent = value == null ? "" : String(value);
  });
}

export function bindShow(id, fn) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    node.style.display = fn() ? "" : "none";
  });
}

export function bindAttr(id, attr, fn) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    const value = fn();
    if (value === false || value == null) node.removeAttribute(attr);
    else node.setAttribute(attr, value === true ? "" : String(value));
  });
}

export function bindProp(id, prop, fn) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    const value = fn();
    if (node[prop] !== value) node[prop] = value;
  });
}

export function bindDialog(id, fn) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    const open = fn();
    if (open && !node.open) node.showModal();
    else if (!open && node.open) node.close();
  });
}

export function on(id, event, handler) {
  const node = el(id);
  if (!node) return;
  node.addEventListener(event, handler);
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;",
  })[c]);
}

export function bindList(id, items, renderItem) {
  const node = el(id);
  if (!node) return;
  effect(() => {
    const list = items() || [];
    node.innerHTML = list.map(renderItem).join("");
  });
}

/* ------------------------------------------------------------------ *
 * Resources: async data with loading/value/error states (SPEC 8.7).
 * Fetches on load (unless server-rendered), refetches when reactive
 * parameters change, deduplicates identical in-flight requests.
 * ------------------------------------------------------------------ */

const resourceRegistry = {};

export function resource(id, spec) {
  const state = { key: null, inflight: false };
  let hydrated = spec.initial;

  const run = (args, force) => {
    const key = JSON.stringify(args);
    if (!force && state.inflight && state.key === key) return;
    state.key = key;
    state.inflight = true;
    spec.loading.set(true);
    spec.error.set(null);
    action(spec.action, args)
      .then((result) => {
        if (state.key === key) spec.value.set(result);
      })
      .catch((err) => {
        if (state.key === key) spec.error.set(String(err.message || err));
      })
      .finally(() => {
        if (state.key === key) {
          state.inflight = false;
          spec.loading.set(false);
        }
      });
  };

  const currentArgs = () => (spec.params ? spec.params() : {});
  // The effect subscribes to every signal the params read, so a parameter
  // change triggers a refetch. The first run is the initial load, skipped
  // when the server already rendered the data.
  effect(() => {
    const args = currentArgs();
    if (hydrated) {
      hydrated = false;
      state.key = JSON.stringify(args);
      return;
    }
    run(args, false);
  });

  resourceRegistry[id] = () => run(currentArgs(), true);
}

export function refreshResource(id) {
  const refresh = resourceRegistry[id];
  if (refresh) refresh();
  else console.warn(`virel: unknown resource ${id}`);
}

/* ------------------------------------------------------------------ *
 * Theme switching: system, light, dark. The stored preference is
 * applied before first paint by the inline bootstrap in the document
 * head; this binding just cycles and persists it.
 * ------------------------------------------------------------------ */

export function themeToggle(id) {
  const node = el(id);
  if (!node) return;
  const modes = ["system", "light", "dark"];
  const read = () => {
    try {
      const stored = localStorage.getItem("virel-theme");
      return modes.includes(stored) ? stored : "system";
    } catch {
      return "system";
    }
  };
  const apply = (mode) => {
    const root = document.documentElement;
    if (mode === "system") delete root.dataset.theme;
    else root.dataset.theme = mode;
    node.setAttribute("aria-label", `Color scheme: ${mode}`);
  };
  apply(read());
  node.addEventListener("click", () => {
    const next = modes[(modes.indexOf(read()) + 1) % modes.length];
    try {
      if (next === "system") localStorage.removeItem("virel-theme");
      else localStorage.setItem("virel-theme", next);
    } catch {}
    apply(next);
  });
}

/* ------------------------------------------------------------------ *
 * Server actions: typed HTTP RPC (SPEC 8.8). JSON in, JSON out.
 * ------------------------------------------------------------------ */

export async function action(name, args) {
  const response = await fetch(`/_virel/action/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args || {}),
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || `action ${name} failed (${response.status})`);
    if (payload.field_errors) error.fieldErrors = payload.field_errors;
    throw error;
  }
  return payload.result;
}

export async function stream(name, args, onChunk, onDone) {
  const response = await fetch(`/_virel/action/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args || {}),
  });
  if (!response.ok) {
    let message = `stream ${name} failed (${response.status})`;
    try {
      message = (await response.json()).error || message;
    } catch {}
    throw new Error(message);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
  const tail = decoder.decode();
  if (tail) onChunk(tail);
  if (onDone) onDone();
}
