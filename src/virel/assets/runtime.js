/* Virel browser runtime — fine-grained signals, no virtual DOM.
 *
 * Compiled pages import this module and register bindings against
 * data-v element ids. State updates touch only the DOM nodes whose
 * expressions read the changed signal (SPEC 9.3). Server communication
 * is plain HTTP: JSON actions and streamed fetch responses. No WebSocket.
 */

let activeEffect = null;
let mountScope = [];

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
      for (const fn of [...subscribers]) {
        if (fn.disposed) subscribers.delete(fn);
        else fn();
      }
    },
  };
}

export function effect(fn) {
  const run = () => {
    if (run.disposed) return;
    const previous = activeEffect;
    activeEffect = run;
    try {
      fn();
    } finally {
      activeEffect = previous;
    }
  };
  mountScope.push(run);
  run();
}

// Everything a page module binds belongs to its mount scope. Client
// navigation disposes the scope before mounting the next page, so effects
// from a previous page never fire against a swapped-out DOM.
export function disposeMount() {
  for (const run of mountScope) run.disposed = true;
  mountScope = [];
  for (const key in resourceRegistry) delete resourceRegistry[key];
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

export function safeUrl(value) {
  const url = String(value ?? "").trim();
  const match = url.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
  if (!match) return url;
  const scheme = match[1].toLowerCase();
  return ["http", "https", "mailto", "tel"].includes(scheme) ? url : "#";
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;",
  })[c]);
}

export function bindList(id, items, renderItem, keyFn, handlers) {
  const node = el(id);
  if (!node) return;
  let current = [];

  // Item events are delegated from the list container, so handlers
  // survive re-renders and cost one listener per event type.
  if (handlers) {
    const eventNames = new Set();
    for (const hid in handlers) {
      for (const eventName in handlers[hid]) eventNames.add(eventName);
    }
    for (const eventName of eventNames) {
      node.addEventListener(eventName, (ev) => {
        const target = ev.target.closest("[data-vh]");
        if (!target || !node.contains(target)) return;
        const wrap = target.closest("[data-vi]");
        if (!wrap) return;
        const item = current[Number(wrap.dataset.vi)];
        const group = handlers[target.dataset.vh];
        const fn = group && group[ev.type];
        if (fn && item !== undefined) fn(ev, item);
      });
    }
  }

  // Keyed reconciliation: unchanged items keep their DOM nodes (and
  // therefore focus and selection); changed items re-render in place.
  const keyed = new Map();
  effect(() => {
    const list = items() || [];
    current = list;
    const liveKeys = new Set();
    const ordered = [];
    list.forEach((item, index) => {
      let key = keyFn ? String(keyFn(item)) : String(index);
      while (liveKeys.has(key)) key += ":" + index;
      liveKeys.add(key);
      const html = renderItem(item);
      let entry = keyed.get(key);
      if (!entry) {
        const wrap = document.createElement("div");
        wrap.className = "v-each-item";
        wrap.style.display = "contents";
        entry = { el: wrap, html: null };
        keyed.set(key, entry);
      }
      if (entry.html !== html) {
        entry.el.innerHTML = html;
        entry.html = html;
      }
      entry.el.dataset.vi = String(index);
      ordered.push(entry.el);
    });
    for (const [key, entry] of keyed) {
      if (!liveKeys.has(key)) {
        keyed.delete(key);
        entry.el.remove();
      }
    }
    ordered.forEach((child, index) => {
      if (node.children[index] !== child) {
        node.insertBefore(child, node.children[index] || null);
      }
    });
    while (node.children.length > ordered.length) node.lastChild.remove();
  });
}

/* ------------------------------------------------------------------ *
 * Resources: async data with loading/value/error states (SPEC 8.7).
 * Fetches on load (unless server-rendered), refetches when reactive
 * parameters change, deduplicates identical in-flight requests.
 * ------------------------------------------------------------------ */

const resourceRegistry = {};
// Fetched values persist across navigations, keyed by action plus
// arguments, so returning to a page shows data instantly. staleFor
// controls revalidation: fresh entries skip the network, stale entries
// render immediately and revalidate in the background.
const resourceCache = new Map();

export function resource(id, spec) {
  const state = { key: null, inflight: false };
  let hydrated = spec.initial;
  const cacheKey = (key) => spec.action + "|" + key;

  const run = (args, force) => {
    const key = JSON.stringify(args);
    if (!force && state.inflight && state.key === key) return;
    state.key = key;

    let background = false;
    const cached = resourceCache.get(cacheKey(key));
    if (!force && cached !== undefined) {
      spec.value.set(cached.value);
      spec.error.set(null);
      spec.loading.set(false);
      const maxAge = (spec.staleFor ?? 0) * 1000;
      if (Date.now() - cached.time < maxAge) return; // fresh: no request
      background = true; // stale: revalidate without a loading flash
    }

    state.inflight = true;
    if (!background) {
      spec.loading.set(true);
      spec.error.set(null);
    }
    action(spec.action, args)
      .then((result) => {
        resourceCache.set(cacheKey(key), { value: result, time: Date.now() });
        if (state.key === key) {
          spec.value.set(result);
          spec.error.set(null);
        }
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
  // Seed the cache from server-rendered data outside the effect: reads
  // here must not subscribe, or setting the value would retrigger the
  // effect and loop.
  if (hydrated) {
    const key = JSON.stringify(currentArgs());
    state.key = key;
    resourceCache.set(cacheKey(key),
                      { value: spec.value.get(), time: Date.now() });
  }
  // The effect subscribes to every signal the params read, so a parameter
  // change triggers a refetch. The first run is the initial load, skipped
  // when the server already rendered the data.
  effect(() => {
    const args = currentArgs();
    if (hydrated) {
      hydrated = false;
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
 * Islands: deferred hydration boundaries (SPEC 9.7). The HTML is
 * already server-rendered; bind() activates the subtree's reactivity
 * according to the load strategy.
 * ------------------------------------------------------------------ */

export function island(id, strategy, bind) {
  const node = el(id);
  if (!node) return;
  if (strategy === "idle") {
    const schedule = window.requestIdleCallback || ((fn) => setTimeout(fn, 1));
    schedule(bind);
    return;
  }
  if (strategy === "visible") {
    if (!("IntersectionObserver" in window)) {
      bind();
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          observer.disconnect();
          bind();
          return;
        }
      }
    });
    observer.observe(node);
    return;
  }
  if (strategy === "interaction") {
    let bound = false;
    const activate = () => {
      if (bound) return;
      bound = true;
      bind();
    };
    node.addEventListener("pointerenter", activate, { once: true });
    node.addEventListener("focusin", activate, { once: true });
    node.addEventListener("touchstart", activate, { once: true, passive: true });
    return;
  }
  bind(); // immediate
}

/* ------------------------------------------------------------------ *
 * Client navigation: same-origin link clicks fetch the target page,
 * swap the document, and mount its page module, so navigation keeps
 * scroll-restoring history semantics without full reloads. Pages that
 * compile per request (inline modules) fall back to a full load.
 * ------------------------------------------------------------------ */

let routerInstalled = false;
const importedPages = new Set();

export function router() {
  if (routerInstalled) return;
  routerInstalled = true;
  const initial = document.querySelector(
    'head script[type="module"][src^="/_virel/page/"]');
  if (initial) importedPages.add(initial.getAttribute("src"));
  markCurrentPage();

  document.addEventListener("click", (ev) => {
    if (ev.defaultPrevented || ev.button !== 0) return;
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    const anchor = ev.target.closest("a");
    if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search) {
      return; // same page (or a fragment link): let the browser handle it
    }
    ev.preventDefault();
    navigate(url.pathname + url.search, true);
  });

  window.addEventListener("popstate", () => {
    navigate(location.pathname + location.search, false);
  });
}

async function navigate(url, push) {
  let doc;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      location.href = url;
      return;
    }
    doc = new DOMParser().parseFromString(await response.text(), "text/html");
  } catch {
    location.href = url;
    return;
  }
  // Per-request pages carry their module inline; run them with a full load
  // so the document and its CSP hashes stay consistent.
  if (doc.querySelector("head script[type=module]:not([src])")) {
    location.href = url;
    return;
  }
  disposeMount();
  document.title = doc.title;
  document.body.replaceWith(document.adoptNode(doc.body));
  if (push) history.pushState({}, "", url);

  const moduleScript = doc.querySelector(
    'head script[type="module"][src^="/_virel/page/"]');
  if (moduleScript) {
    const src = moduleScript.getAttribute("src");
    if (importedPages.has(src)) {
      (await import(src)).mount();
    } else {
      importedPages.add(src);
      await import(src); // fresh modules mount themselves
    }
  }
  window.scrollTo(0, 0);
  markCurrentPage();
  document.body.setAttribute("tabindex", "-1");
  document.body.focus({ preventScroll: true });
  window.dispatchEvent(new CustomEvent("virel:navigate"));
}

function markCurrentPage() {
  for (const anchor of document.querySelectorAll("nav a[href]")) {
    const url = new URL(anchor.href, location.href);
    if (url.pathname === location.pathname) {
      anchor.setAttribute("aria-current", "page");
    } else {
      anchor.removeAttribute("aria-current");
    }
  }
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
