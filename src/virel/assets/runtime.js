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

let disposers = [];

// Register cleanup that runs when the page unmounts (client navigation).
export function onDispose(fn) {
  disposers.push(fn);
}

// Everything a page module binds belongs to its mount scope. Client
// navigation disposes the scope before mounting the next page, so effects
// from a previous page never fire against a swapped-out DOM.
export function disposeMount() {
  for (const run of mountScope) run.disposed = true;
  mountScope = [];
  for (const fn of disposers) {
    try { fn(); } catch {}
  }
  disposers = [];
  for (const key in resourceRegistry) delete resourceRegistry[key];
}

// Run a callback when any dependency changes. Dependencies are read
// tracked; the body runs untracked so its own reads and writes never
// re-subscribe the watcher.
export function watch(deps, run, immediate) {
  let first = true;
  effect(() => {
    for (const dep of deps) dep();
    if (first) {
      first = false;
      if (!immediate) return;
    }
    const previous = activeEffect;
    activeEffect = null;
    try {
      run();
    } finally {
      activeEffect = previous;
    }
  });
}

// Persist a signal to localStorage under a namespaced key.
export function persist(sig, key) {
  const storageKey = "virel:" + key;
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored !== null) sig.set(JSON.parse(stored));
  } catch {}
  watch([() => sig.get()], () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(sig.get()));
    } catch {}
  }, false);
}

// Keep a signal synchronized with a URL query parameter.
export function urlSync(sig, param) {
  const initial = sig.get();
  const params = new URLSearchParams(location.search);
  if (params.has(param)) {
    const raw = params.get(param);
    sig.set(typeof initial === "number" ? Number(raw) : raw);
  }
  watch([() => sig.get()], () => {
    const value = sig.get();
    const next = new URLSearchParams(location.search);
    if (value === initial || value === "" || value == null) next.delete(param);
    else next.set(param, String(value));
    const query = next.toString();
    history.replaceState(history.state, "",
                         location.pathname + (query ? "?" + query : ""));
  }, false);
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
    if (prop === "value") {
      if (node.type === "range") paintRange(node);
      if (node.__virelSync) node.__virelSync();
    }
  });
  if (prop === "value" && node.type === "range") {
    node.addEventListener("input", () => paintRange(node));
  }
}

function paintRange(node) {
  const min = Number(node.min || 0);
  const max = Number(node.max || 100);
  const value = Number(node.value || 0);
  const percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
  node.style.setProperty("--v-fill", percent.toFixed(2) + "%");
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
  const state = { key: null, inflight: false, controller: null };
  let hydrated = spec.initial;
  const cacheKey = (key) => spec.action + "|" + key;

  const runStream = (args) => {
    state.controller?.abort();
    const controller = new AbortController();
    state.controller = controller;
    spec.value.set("");
    spec.loading.set(true);
    spec.error.set(null);
    stream(spec.action, args,
           (chunk) => spec.value.set((spec.value.get() || "") + chunk),
           () => spec.loading.set(false),
           { signal: controller.signal })
      .catch((err) => {
        if (err.name !== "AbortError") {
          spec.error.set(String(err.message || err));
          spec.loading.set(false);
        }
      });
  };

  const run = (args, force) => {
    if (spec.stream) return runStream(args);
    const key = JSON.stringify(args);
    if (!force && state.inflight && state.key === key) return;
    // Cancel the superseded request instead of letting it race.
    state.controller?.abort();
    const controller = new AbortController();
    state.controller = controller;
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
    const attempt = (remaining) => {
      action(spec.action, args, { signal: controller.signal })
        .then((result) => {
          resourceCache.set(cacheKey(key), { value: result, time: Date.now() });
          if (state.key === key) {
            spec.value.set(result);
            spec.error.set(null);
            state.inflight = false;
            spec.loading.set(false);
          }
        })
        .catch((err) => {
          if (err.name === "AbortError") return;
          if (remaining > 0) {
            setTimeout(() => attempt(remaining - 1),
                       300 * ((spec.retry ?? 0) - remaining + 1));
            return;
          }
          if (state.key === key) {
            spec.error.set(String(err.message || err));
            state.inflight = false;
            spec.loading.set(false);
          }
        });
    };
    attempt(spec.retry ?? 0);
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

  resourceRegistry[id] = {
    action: spec.action,
    refresh: () => run(currentArgs(), true),
  };
}

export function refreshResource(id) {
  const entry = resourceRegistry[id];
  if (entry) entry.refresh();
  else console.warn(`virel: unknown resource ${id}`);
}

// Drop every cached value for an action and refetch the live resources
// bound to it.
export function invalidate(actionName) {
  for (const key of [...resourceCache.keys()]) {
    if (key.startsWith(actionName + "|")) resourceCache.delete(key);
  }
  for (const id in resourceRegistry) {
    if (resourceRegistry[id].action === actionName) {
      resourceRegistry[id].refresh();
    }
  }
}

// Send the files from a ui.FileField to an upload action as multipart,
// reporting byte-level progress (0-100) into a signal.
export function upload(name, fileRef, args, opts) {
  const input = document.querySelector(`[data-vf="${fileRef}"]`);
  const files = input?.files;
  if (!files || files.length === 0) {
    opts.error?.set("no file selected");
    return;
  }
  const form = new FormData();
  form.append("__args", JSON.stringify(args || {}));
  for (const file of files) form.append(opts.fileParam, file, file.name);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/_virel/action/${name}`);
  xhr.responseType = "json";
  if (opts.progress) {
    opts.progress.set(0);
    xhr.upload.addEventListener("progress", (ev) => {
      if (ev.lengthComputable) {
        opts.progress.set(Math.round((ev.loaded / ev.total) * 100));
      }
    });
  }
  xhr.addEventListener("load", () => {
    const payload = xhr.response || {};
    if (xhr.status >= 200 && xhr.status < 300) {
      opts.progress?.set(100);
      opts.into?.set(payload.result);
    } else {
      opts.error?.set(payload.error || `upload failed (${xhr.status})`);
    }
  });
  xhr.addEventListener("error", () => {
    opts.error?.set("upload failed");
  });
  xhr.send(form);
}

/* ------------------------------------------------------------------ *
 * Custom select: a styled combobox enhancing a native <select>. The
 * native element stays as the source of truth (form semantics, tests,
 * bindings); the runtime renders the button and listbox, handles
 * keyboard interaction, and flips the menu upward when the space below
 * is not sufficient.
 * ------------------------------------------------------------------ */

const CHEVRON =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
  'stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';

export function select(id) {
  const wrap = el(id);
  if (!wrap || wrap.classList.contains("v-select-enhanced")) return;
  const native = wrap.querySelector("select");
  if (!native) return;
  const options = [...native.options];

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "v-input v-select-btn";
  btn.setAttribute("role", "combobox");
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");
  const labelSpan = wrap.closest("label")?.querySelector(".v-label");
  if (labelSpan) btn.setAttribute("aria-label", labelSpan.textContent);
  const valueSpan = document.createElement("span");
  valueSpan.className = "v-select-value";
  btn.appendChild(valueSpan);
  btn.insertAdjacentHTML("beforeend", CHEVRON);

  const list = document.createElement("ul");
  list.className = "v-select-list";
  list.setAttribute("role", "listbox");
  options.forEach((option, index) => {
    const item = document.createElement("li");
    item.className = "v-select-option";
    item.setAttribute("role", "option");
    item.id = `v-${id}-opt-${index}`;
    item.textContent = option.textContent;
    item.addEventListener("click", () => choose(index));
    list.appendChild(item);
  });

  let active = Math.max(0, native.selectedIndex);
  const isOpen = () => wrap.classList.contains("v-select-open");

  const sync = () => {
    const index = native.selectedIndex;
    valueSpan.textContent = index >= 0 ? options[index].textContent : "";
    [...list.children].forEach((item, i) =>
      item.setAttribute("aria-selected", String(i === index)));
  };
  native.__virelSync = sync;

  const highlight = () => {
    [...list.children].forEach((item, i) =>
      item.classList.toggle("v-active", i === active));
    btn.setAttribute("aria-activedescendant", `v-${id}-opt-${active}`);
    list.children[active]?.scrollIntoView({ block: "nearest" });
  };

  const openList = () => {
    wrap.classList.add("v-select-open");
    btn.setAttribute("aria-expanded", "true");
    active = Math.max(0, native.selectedIndex);
    highlight();
    // Flip upward when the menu does not fit below the control.
    const rect = btn.getBoundingClientRect();
    const height = list.offsetHeight;
    const fitsBelow = window.innerHeight - rect.bottom >= height + 12;
    const fitsAbove = rect.top >= height + 12;
    wrap.classList.toggle("v-select-up", !fitsBelow && fitsAbove);
  };

  const closeList = () => {
    wrap.classList.remove("v-select-open", "v-select-up");
    btn.setAttribute("aria-expanded", "false");
    btn.removeAttribute("aria-activedescendant");
  };

  const choose = (index) => {
    native.value = options[index].value;
    native.dispatchEvent(new Event("change"));
    sync();
    closeList();
    btn.focus();
  };

  btn.addEventListener("click", () => (isOpen() ? closeList() : openList()));
  btn.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (!isOpen()) return openList();
      const step = ev.key === "ArrowDown" ? 1 : -1;
      active = Math.min(Math.max(active + step, 0), options.length - 1);
      highlight();
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      isOpen() ? choose(active) : openList();
    } else if (ev.key === "Escape" && isOpen()) {
      ev.preventDefault();
      closeList();
    } else if (ev.key === "Home" && isOpen()) {
      active = 0;
      highlight();
    } else if (ev.key === "End" && isOpen()) {
      active = options.length - 1;
      highlight();
    } else if (ev.key === "Tab") {
      closeList();
    }
  });
  document.addEventListener("click", (ev) => {
    if (isOpen() && !wrap.contains(ev.target)) closeList();
  });

  native.setAttribute("aria-hidden", "true");
  native.tabIndex = -1;
  wrap.classList.add("v-select-enhanced");
  wrap.appendChild(btn);
  wrap.appendChild(list);
  sync();
}

/* ------------------------------------------------------------------ *
 * Dropdown menu: trigger plus popup panel. Items are ordinary anchors
 * and buttons whose handlers bind normally; this helper manages open
 * state, keyboard interaction, click-outside, and flip-up placement.
 * ------------------------------------------------------------------ */

export function menu(id) {
  const wrap = el(id);
  if (!wrap || wrap.__virelMenu) return;
  wrap.__virelMenu = true;
  const trigger = wrap.firstElementChild;
  const panel = wrap.querySelector(".v-menu-list");
  if (!trigger || !panel) return;
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");

  const items = () => [...panel.querySelectorAll('[role="menuitem"]')];
  const isOpen = () => wrap.classList.contains("v-menu-open");

  const openMenu = (focusFirst) => {
    wrap.classList.add("v-menu-open");
    trigger.setAttribute("aria-expanded", "true");
    const rect = trigger.getBoundingClientRect();
    const height = panel.offsetHeight;
    const fitsBelow = window.innerHeight - rect.bottom >= height + 12;
    const fitsAbove = rect.top >= height + 12;
    wrap.classList.toggle("v-menu-up", !fitsBelow && fitsAbove);
    if (focusFirst) items()[0]?.focus();
  };

  const closeMenu = (refocus) => {
    wrap.classList.remove("v-menu-open", "v-menu-up");
    trigger.setAttribute("aria-expanded", "false");
    if (refocus) trigger.focus();
  };

  trigger.addEventListener("click", () => {
    isOpen() ? closeMenu(false) : openMenu(false);
  });
  trigger.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      openMenu(true);
    }
  });
  panel.addEventListener("keydown", (ev) => {
    const list = items();
    const index = list.indexOf(document.activeElement);
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      list[Math.min(index + 1, list.length - 1)]?.focus();
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      list[Math.max(index - 1, 0)]?.focus();
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      closeMenu(true);
    } else if (ev.key === "Tab") {
      closeMenu(false);
    }
  });
  panel.addEventListener("click", (ev) => {
    if (ev.target.closest('[role="menuitem"]')) closeMenu(false);
  });
  document.addEventListener("click", (ev) => {
    if (isOpen() && !wrap.contains(ev.target)) closeMenu(false);
  });
}

/* ------------------------------------------------------------------ *
 * Error boundaries: if binding a subtree throws, show its fallback
 * with the error message and a retry that re-binds the content.
 * ------------------------------------------------------------------ */

export function boundary(id, bind) {
  const wrap = el(id);
  if (!wrap) return;
  const content = wrap.querySelector(":scope > .v-boundary-content");
  const fallback = wrap.querySelector(":scope > .v-boundary-fallback");

  const attempt = () => {
    try {
      bind();
      content.style.display = "contents";
      fallback.style.display = "none";
    } catch (err) {
      console.error("virel boundary:", err);
      content.style.display = "none";
      fallback.style.display = "contents";
      const slot = fallback.querySelector("[data-error-message]");
      if (slot) slot.textContent = String(err.message || err);
    }
  };
  fallback.querySelector("[data-retry]")
    ?.addEventListener("click", attempt);
  attempt();
}

/* ------------------------------------------------------------------ *
 * Islands: deferred hydration boundaries (SPEC 9.7). The HTML is
 * already server-rendered; bind() activates the subtree's reactivity
 * according to the load strategy.
 * ------------------------------------------------------------------ */

export function island(id, strategy, bind, media) {
  const node = el(id);
  if (!node) return;
  // The island wrapper uses display:contents and has no box of its own;
  // intersection and interaction need a real element.
  const target = node.firstElementChild || node;
  if (strategy === "media") {
    const query = window.matchMedia(media);
    if (query.matches) {
      bind();
      return;
    }
    const listener = (ev) => {
      if (ev.matches) {
        query.removeEventListener("change", listener);
        bind();
      }
    };
    query.addEventListener("change", listener);
    return;
  }
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
    observer.observe(target);
    return;
  }
  if (strategy === "interaction") {
    let bound = false;
    const activate = () => {
      if (bound) return;
      bound = true;
      bind();
    };
    target.addEventListener("pointerenter", activate, { once: true });
    target.addEventListener("focusin", activate, { once: true });
    target.addEventListener("touchstart", activate, { once: true, passive: true });
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

let progressBar = null;

function showProgress() {
  progressBar?.remove();
  progressBar = document.createElement("div");
  progressBar.setAttribute("aria-hidden", "true");
  progressBar.style.cssText =
    "position:fixed;top:0;left:0;height:2px;width:0;z-index:99999;" +
    "background:var(--v-accent, #4f46e5);transition:width 400ms ease;" +
    "border-radius:0 2px 2px 0";
  document.body.appendChild(progressBar);
  requestAnimationFrame(() => { if (progressBar) progressBar.style.width = "70%"; });
}

function hideProgress() {
  if (!progressBar) return;
  const bar = progressBar;
  progressBar = null;
  bar.style.width = "100%";
  setTimeout(() => bar.remove(), 180);
}

async function navigate(url, push) {
  showProgress();
  let doc;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      hideProgress();
      location.href = url;
      return;
    }
    doc = new DOMParser().parseFromString(await response.text(), "text/html");
  } catch {
    hideProgress();
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

  for (const script of doc.querySelectorAll(
      'head script[type="module"][src]')) {
    const src = script.getAttribute("src");
    if (!src.startsWith("/_virel/")) import(src); // e.g. web components
  }
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
  hideProgress();
  window.scrollTo(0, 0);
  markCurrentPage();
  document.body.setAttribute("tabindex", "-1");
  document.body.focus({ preventScroll: true });
  window.dispatchEvent(new CustomEvent("virel:navigate"));
}

function markCurrentPage() {
  for (const anchor of document.querySelectorAll("nav a[href]")) {
    const url = new URL(anchor.href, location.href);
    // A link with its own query string is current only when the query
    // matches too (sidebar tabs); plain links match on pathname alone.
    const current = url.pathname === location.pathname &&
      (url.search === "" ? true : url.search === location.search);
    if (current) anchor.setAttribute("aria-current", "page");
    else anchor.removeAttribute("aria-current");
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

let transport = (url, options) => fetch(url, options);

// Replace the HTTP transport (testing, custom auth headers, tunnels).
export function setTransport(fn) {
  transport = fn;
}

export async function action(name, args, options) {
  const headers = { "Content-Type": "application/json" };
  if (options?.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  const response = await transport(`/_virel/action/${name}`, {
    method: "POST",
    headers,
    body: JSON.stringify(args || {}),
    signal: options?.signal,
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || `action ${name} failed (${response.status})`);
    if (payload.field_errors) error.fieldErrors = payload.field_errors;
    throw error;
  }
  return payload.result;
}

// Live one-way updates over server-sent events. The browser reconnects
// automatically; changing reactive parameters reopens the stream, and
// client navigation closes it.
export function sse(name, argsFn, opts) {
  let source = null;
  const open = (args) => {
    source?.close();
    const query = new URLSearchParams();
    for (const key in args) query.set(key, String(args[key]));
    const suffix = query.toString() ? "?" + query.toString() : "";
    source = new EventSource(`/_virel/action/${name}${suffix}`);
    source.onmessage = (ev) => {
      if (opts.events) {
        try {
          opts.events.set([...(opts.events.get() || []), JSON.parse(ev.data)]);
        } catch {}
      } else if (opts.into) {
        opts.into.set((opts.into.get() || "") + ev.data + "\n");
      }
    };
  };
  effect(() => {
    const args = argsFn ? argsFn() : {};
    const previous = activeEffect;
    activeEffect = null;
    try {
      open(args);
    } finally {
      activeEffect = previous;
    }
  });
  onDispose(() => source?.close());
}

// Structured streams: the server emits JSON lines; parsed events append
// into a list signal so ui.Each renders them as they arrive.
export async function streamEvents(name, args, listSignal, onDone) {
  let buffer = "";
  await stream(name, args, (chunk) => {
    buffer += chunk;
    const lines = buffer.split("\n");
    buffer = lines.pop();
    const parsed = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        parsed.push(JSON.parse(line));
      } catch {}
    }
    if (parsed.length) listSignal.set([...(listSignal.get() || []), ...parsed]);
  }, onDone);
}

export async function stream(name, args, onChunk, onDone, options) {
  const response = await transport(`/_virel/action/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args || {}),
    signal: options?.signal,
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
