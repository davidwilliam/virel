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

export function on(id, event, handler) {
  const node = el(id);
  if (!node) return;
  node.addEventListener(event, handler);
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
    throw new Error(payload.error || `action ${name} failed (${response.status})`);
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
