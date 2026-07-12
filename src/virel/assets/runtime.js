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

/* Enter/exit animation (SPEC 10.8): a class carrying a CSS animation
 * is applied for one run. Real CSS animations mean the browser's
 * Animations devtools panel inspects every timeline. A run counter
 * guards against rapid toggles: a stale animation's completion never
 * applies an outdated end state. */
let motionRun = 0;
function animateClass(node, cls, done) {
  const token = ++motionRun;
  node.__vmRun = token;
  node.classList.remove(cls);
  void node.offsetWidth; // restart the animation if it was mid-flight
  node.classList.add(cls);
  const style = getComputedStyle(node);
  if (style.animationName === "none" || style.display === "none") {
    node.classList.remove(cls);
    if (done) done();
    return;
  }
  const finish = (ev) => {
    if (ev.target !== node) return;
    node.removeEventListener("animationend", finish);
    node.removeEventListener("animationcancel", finish);
    node.classList.remove(cls);
    if (done && node.__vmRun === token) done();
  };
  node.addEventListener("animationend", finish);
  node.addEventListener("animationcancel", finish);
}

export function bindShow(id, fn, motion) {
  const node = el(id);
  if (!node) return;
  let first = true;
  effect(() => {
    const show = !!fn();
    if (!motion || first) {
      node.style.display = show ? "" : "none";
      first = false;
      return;
    }
    const visible = node.style.display !== "none";
    if (show && !visible) {
      node.style.display = "";
      if (motion.enter) animateClass(node, motion.enter);
      else node.__vmRun = ++motionRun; // cancel a pending exit hide
    } else if (!show && visible) {
      if (motion.exit) {
        animateClass(node, motion.exit, () => {
          node.style.display = "none";
        });
      } else {
        node.style.display = "none";
      }
    }
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

export function bindList(id, items, renderItem, keyFn, handlers, motion,
                          reorder) {
  const node = el(id);
  if (!node) return;
  let current = [];
  let hydrated = false;
  const reordering = reorder
    ? makeReorderable(node, () => current)
    : null;

  // Item events are delegated from the list container, so handlers
  // survive re-renders and cost one listener per event type.
  if (handlers) {
    const eventNames = new Set();
    for (const hid in handlers) {
      for (const eventName in handlers[hid]) eventNames.add(eventName);
    }
    for (const eventName of eventNames) {
      node.addEventListener(eventName, (ev) => {
        if (ev.target.closest(".v-drag-handle")) return;
        const target = ev.target.closest("[data-vh]");
        if (!target || !node.contains(target)) return;
        const wrap = target.closest("[data-vi]");
        if (!wrap || wrap.dataset.vexit) return;
        const item = current[Number(wrap.dataset.vi)];
        const group = handlers[target.dataset.vh];
        const fn = group && group[ev.type];
        if (fn && item !== undefined) fn(ev, item);
      });
    }
  }

  // Keyed reconciliation: unchanged items keep their DOM nodes (and
  // therefore focus and selection); changed items re-render in place.
  // With motion, new items animate in, removed items freeze in place
  // (absolutely positioned) while animating out so the layout collapses
  // smoothly, and layout animation FLIPs survivors to new positions.
  const keyed = new Map();
  effect(() => {
    const list = items() || [];
    current = list;

    let flipRects = null;
    if (motion && motion.flip && hydrated) {
      flipRects = new Map();
      for (const [key, entry] of keyed) {
        const child = entry.el.firstElementChild;
        if (child) flipRects.set(key, child.getBoundingClientRect());
      }
    }

    const liveKeys = new Set();
    const ordered = [];
    const entered = [];
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
        if (hydrated && motion && motion.enter) entered.push(entry);
      }
      if (entry.html !== html) {
        entry.el.innerHTML = html;
        entry.html = html;
      }
      entry.el.dataset.vi = String(index);
      ordered.push(entry.el);
    });

    for (const [key, entry] of keyed) {
      if (liveKeys.has(key)) continue;
      keyed.delete(key);
      const child = entry.el.firstElementChild;
      if (hydrated && motion && motion.exit && child) {
        const listRect = node.getBoundingClientRect();
        const rect = child.getBoundingClientRect();
        entry.el.dataset.vexit = "1";
        child.style.position = "absolute";
        child.style.left = rect.left - listRect.left + "px";
        child.style.top = rect.top - listRect.top + "px";
        child.style.width = rect.width + "px";
        child.style.height = rect.height + "px";
        child.style.margin = "0";
        animateClass(child, motion.exit, () => entry.el.remove());
      } else {
        entry.el.remove();
      }
    }

    // Position live wrappers among the children, flowing around any
    // still-exiting ones; then drop leftovers (initial server-rendered
    // markup on hydration).
    let cursor = node.firstElementChild;
    const advance = () => {
      while (cursor && cursor.dataset.vexit) {
        cursor = cursor.nextElementSibling;
      }
    };
    for (const wrap of ordered) {
      advance();
      if (cursor === wrap) {
        cursor = cursor.nextElementSibling;
        continue;
      }
      node.insertBefore(wrap, cursor);
    }
    const keep = new Set(ordered);
    for (const extra of Array.from(node.children)) {
      if (!keep.has(extra) && !extra.dataset.vexit) extra.remove();
    }

    if (flipRects) {
      for (const [key, entry] of keyed) {
        const child = entry.el.firstElementChild;
        const was = flipRects.get(key);
        if (!child || !was) continue;
        const now = child.getBoundingClientRect();
        const dx = was.left - now.left;
        const dy = was.top - now.top;
        if (!dx && !dy) continue;
        child.style.transition = "none";
        child.style.transform = `translate(${dx}px, ${dy}px)`;
        requestAnimationFrame(() => {
          child.style.transition =
            `transform ${motion.flipDuration}ms ${motion.flipEasing}`;
          child.style.transform = "";
          child.addEventListener("transitionend", () => {
            child.style.transition = "";
          }, { once: true });
        });
      }
    }

    for (const entry of entered) {
      const child = entry.el.firstElementChild;
      if (child) animateClass(child, motion.enter);
    }

    if (reordering) reordering.prepare();
    hydrated = true;
  });
}

/* ------------------------------------------------------------------ *
 * List drag-and-drop (SPEC 11.1). Every item gets a drag handle: it
 * works with a pointer (drag; siblings FLIP out of the way) and from
 * the keyboard (Space grabs, arrows move, Space drops, Escape
 * cancels), with changes announced through a status region. On drop
 * the container dispatches virel-reorder with the reordered items in
 * detail.items, which the compiled handler writes back into state.
 * ------------------------------------------------------------------ */

const GRIP_SVG =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" ' +
  'aria-hidden="true"><circle cx="9" cy="6" r="1.6"/>' +
  '<circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/>' +
  '<circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/>' +
  '<circle cx="15" cy="18" r="1.6"/></svg>';

function makeReorderable(node, currentItems) {
  const status = document.createElement("div");
  status.className = "v-sr-only";
  status.setAttribute("role", "status");
  node.insertAdjacentElement("afterend", status);
  const announce = (text) => { status.textContent = text; };

  const wrappers = () =>
    Array.from(node.querySelectorAll(":scope > [data-vi]"))
      .filter((wrap) => !wrap.dataset.vexit);
  const orderedItems = () => {
    const list = currentItems();
    return wrappers().map((wrap) => list[Number(wrap.dataset.vi)]);
  };
  const dispatch = () => {
    node.dispatchEvent(new CustomEvent("virel-reorder", {
      detail: { items: orderedItems() },
    }));
  };
  const flip = (child, fromTop) => {
    const dy = fromTop - child.getBoundingClientRect().top;
    if (!dy) return;
    child.style.transition = "none";
    child.style.transform = `translateY(${dy}px)`;
    requestAnimationFrame(() => {
      child.style.transition = "transform 160ms cubic-bezier(0.16, 1, 0.3, 1)";
      child.style.transform = "";
      child.addEventListener("transitionend", () => {
        child.style.transition = "";
      }, { once: true });
    });
  };

  // Pointer drag from the handle. The wrapper reslots live while the
  // lifted element follows the pointer; displaced siblings FLIP.
  node.addEventListener("pointerdown", (down) => {
    const handle = down.target.closest(".v-drag-handle");
    if (!handle || down.button !== 0) return;
    down.preventDefault();
    const wrap = handle.closest("[data-vi]");
    const lifted = wrap.firstElementChild;
    const grabOffset = down.clientY - lifted.getBoundingClientRect().top;
    try {
      handle.setPointerCapture(down.pointerId);
    } catch {}
    lifted.classList.add("v-drag-lift");

    const track = (ev) => {
      const rect = lifted.getBoundingClientRect();
      const base = rect.top - currentShift();
      lifted.style.transform =
        `translateY(${ev.clientY - grabOffset - base}px)`;
      for (const other of wrappers()) {
        if (other === wrap) continue;
        const otherChild = other.firstElementChild;
        if (!otherChild) continue;
        const box = otherChild.getBoundingClientRect();
        const middle = box.top + box.height / 2;
        const before = wrap.compareDocumentPosition(other)
          & Node.DOCUMENT_POSITION_FOLLOWING;
        if (before && ev.clientY > middle) {
          const from = box.top;
          node.insertBefore(other, wrap);
          flip(otherChild, from);
          retarget(ev);
          break;
        }
        if (!before && ev.clientY < middle) {
          const from = box.top;
          node.insertBefore(other, wrap.nextElementSibling);
          flip(otherChild, from);
          retarget(ev);
          break;
        }
      }
    };
    const currentShift = () => {
      const match = /translateY\(([-0-9.]+)px\)/.exec(lifted.style.transform);
      return match ? Number(match[1]) : 0;
    };
    const retarget = (ev) => {
      lifted.style.transform = "";
      const rect = lifted.getBoundingClientRect();
      lifted.style.transform =
        `translateY(${ev.clientY - grabOffset - rect.top}px)`;
    };
    const drop = () => {
      document.removeEventListener("pointermove", track);
      document.removeEventListener("pointerup", drop);
      document.removeEventListener("pointercancel", drop);
      lifted.classList.remove("v-drag-lift");
      lifted.style.transition =
        "transform 160ms cubic-bezier(0.16, 1, 0.3, 1)";
      lifted.style.transform = "";
      lifted.addEventListener("transitionend", () => {
        lifted.style.transition = "";
      }, { once: true });
      dispatch();
    };
    // Document-level tracking survives fast pointers leaving the
    // handle and environments where pointer capture is unavailable.
    document.addEventListener("pointermove", track);
    document.addEventListener("pointerup", drop);
    document.addEventListener("pointercancel", drop);
  });

  // Keyboard: the handle is a button. Space grabs, arrows move,
  // Space drops, Escape restores the original order.
  let grabbed = null;
  let originalOrder = null;
  const release = (drop) => {
    if (!grabbed) return;
    grabbed.firstElementChild.classList.remove("v-drag-grabbed");
    if (drop) {
      dispatch();
      announce("Dropped.");
    } else if (originalOrder) {
      for (const wrap of originalOrder) node.appendChild(wrap);
      announce("Reorder cancelled.");
    }
    grabbed = null;
    originalOrder = null;
  };
  node.addEventListener("keydown", (ev) => {
    const handle = ev.target.closest(".v-drag-handle");
    if (!handle) return;
    const wrap = handle.closest("[data-vi]");
    if (ev.key === " " || ev.key === "Enter") {
      if (grabbed === wrap) {
        release(true);
      } else {
        release(false);
        grabbed = wrap;
        originalOrder = wrappers();
        wrap.firstElementChild.classList.add("v-drag-grabbed");
        announce("Grabbed. Use the arrow keys to move, space to drop, "
                 + "escape to cancel.");
      }
    } else if (grabbed === wrap
               && (ev.key === "ArrowUp" || ev.key === "ArrowDown")) {
      const list = wrappers();
      const index = list.indexOf(wrap);
      const target = ev.key === "ArrowUp"
        ? list[index - 1] : list[index + 1];
      if (target) {
        const child = target.firstElementChild;
        const from = child.getBoundingClientRect().top;
        if (ev.key === "ArrowUp") node.insertBefore(wrap, target);
        else node.insertBefore(target, wrap);
        flip(child, from);
        handle.focus();
        announce(`Moved to position ${wrappers().indexOf(wrap) + 1} `
                 + `of ${list.length}.`);
      }
    } else if (grabbed === wrap && ev.key === "Escape") {
      release(false);
      handle.focus();
    } else {
      return;
    }
    ev.preventDefault();
  });

  return {
    // Re-runs after every reconcile: re-rendered items get their
    // handle back, new items get one for the first time.
    prepare() {
      for (const wrap of wrappers()) {
        const root = wrap.firstElementChild;
        if (!root || root.querySelector(":scope > .v-drag-handle")) continue;
        root.classList.add("v-reorderable-item");
        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = "v-drag-handle";
        handle.setAttribute("aria-label", "Reorder item");
        handle.innerHTML = GRIP_SVG;
        root.prepend(handle);
      }
    },
  };
}

/* ------------------------------------------------------------------ *
 * Swipe gesture (SPEC 10.8): content follows the pointer and either
 * springs back or slides away and fires virel-dismiss. Delete and
 * Backspace dismiss from the keyboard. Reduced motion collapses the
 * inline transitions through the global rule.
 * ------------------------------------------------------------------ */

export function swipeable(id) {
  const node = el(id);
  if (!node) return;
  const direction = node.dataset.direction || "x";
  const threshold = Number(node.dataset.threshold || 0.35);
  const allowed = (dx) =>
    direction === "x" ? true : direction === "left" ? dx < 0 : dx > 0;
  let startX = null;
  let startTime = 0;
  let lastDx = 0;
  let dragging = false;

  const dismiss = (dx) => {
    const width = node.offsetWidth || 300;
    const target = (dx < 0 ? -1 : 1) * width * 1.2;
    node.style.transition =
      "transform 200ms cubic-bezier(0.16, 1, 0.3, 1), opacity 200ms linear";
    node.style.transform = `translateX(${target}px)`;
    node.style.opacity = "0";
    setTimeout(() => {
      node.dispatchEvent(new CustomEvent("virel-dismiss", { bubbles: true }));
      // The handler normally removes the item; if it did not, restore.
      setTimeout(() => {
        if (node.isConnected) {
          node.style.transition = "";
          node.style.transform = "";
          node.style.opacity = "";
        }
      }, 250);
    }, 200);
  };
  const snapBack = () => {
    node.style.transition = "transform 300ms cubic-bezier(0.16, 1, 0.3, 1)";
    node.style.transform = "";
    node.addEventListener("transitionend", () => {
      node.style.transition = "";
    }, { once: true });
  };

  node.addEventListener("pointerdown", (down) => {
    if (down.button !== 0) return;
    startX = down.clientX;
    startTime = performance.now();
    lastDx = 0;
    dragging = false;
  });
  node.addEventListener("pointermove", (ev) => {
    if (startX === null) return;
    let dx = ev.clientX - startX;
    if (!dragging) {
      if (Math.abs(dx) < 6) return;
      dragging = true;
      node.setPointerCapture(ev.pointerId);
    }
    if (!allowed(dx)) dx *= 0.25; // resistance against the blocked way
    lastDx = dx;
    node.style.transition = "none";
    node.style.transform = `translateX(${dx}px)`;
  });
  const release = () => {
    if (startX === null) return;
    const dx = lastDx;
    const wasDragging = dragging;
    startX = null;
    dragging = false;
    if (!wasDragging) return;
    const width = node.offsetWidth || 300;
    const elapsed = Math.max(1, performance.now() - startTime);
    const velocity = Math.abs(dx) / elapsed;
    if (allowed(dx) && (Math.abs(dx) > width * threshold
                        || (velocity > 0.6 && Math.abs(dx) > 24))) {
      dismiss(dx);
    } else {
      snapBack();
    }
  };
  node.addEventListener("pointerup", release);
  node.addEventListener("pointercancel", release);
  node.addEventListener("keydown", (ev) => {
    if (ev.key === "Delete" || ev.key === "Backspace") {
      ev.preventDefault();
      dismiss(direction === "right" ? 1 : -1);
    }
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

  // Stream-mode SSR: the data arrived as an inline JSON block after the
  // shell; read it at mount instead of fetching.
  if (spec.ssr === "streamed") {
    const block = document.querySelector(
      `script[type="application/json"][data-virel-stream="${id}"]`);
    if (block) {
      try {
        const payload = JSON.parse(block.textContent);
        if (payload.error) spec.error.set(payload.error);
        else spec.value.set(payload.value);
        spec.loading.set(false);
        hydrated = true;
      } catch {}
    }
  }

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

// Drag-and-drop file selection for a ui.FileField: dropping files
// assigns them to the input, and the summary line lists what's queued.
export function dropzone(id) {
  const zone = el(id);
  if (!zone) return;
  const input = zone.querySelector('input[type="file"]');
  const summary = zone.querySelector("[data-file-summary]");
  if (!input) return;

  const describe = () => {
    if (!summary) return;
    const files = [...(input.files || [])];
    summary.textContent = files.length
      ? files.map((f) => f.name).join(", ")
      : "";
  };
  input.addEventListener("change", describe);
  zone.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    zone.classList.add("v-dropzone-over");
  });
  zone.addEventListener("dragleave", () => {
    zone.classList.remove("v-dropzone-over");
  });
  zone.addEventListener("drop", (ev) => {
    ev.preventDefault();
    zone.classList.remove("v-dropzone-over");
    if (!ev.dataTransfer?.files?.length) return;
    if (input.multiple) {
      input.files = ev.dataTransfer.files;
    } else {
      const single = new DataTransfer();
      single.items.add(ev.dataTransfer.files[0]);
      input.files = single.files;
    }
    describe();
  });
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

/* ------------------------------------------------------------------ *
 * Splitter (SPEC 10.3): a draggable, keyboard-operable divider between
 * two panes. The position lives in the --v-split custom property; all
 * listeners sit on the splitter's own nodes, so navigation disposal is
 * automatic with the DOM.
 * ------------------------------------------------------------------ */

export function splitter(id) {
  const root = el(id);
  if (!root) return;
  const handle = root.querySelector(":scope > .v-splitter-handle");
  if (!handle) return;
  const vertical = root.classList.contains("v-splitter-col");
  const min = Number(root.dataset.min || 20);
  const max = Number(root.dataset.max || 80);
  const initial = Number(root.dataset.initial || 50);
  let value = initial;
  const apply = (next) => {
    value = Math.min(max, Math.max(min, next));
    root.style.setProperty("--v-split", value + "%");
    handle.setAttribute("aria-valuenow", String(Math.round(value)));
  };
  handle.addEventListener("pointerdown", (down) => {
    down.preventDefault();
    handle.setPointerCapture(down.pointerId);
    const move = (ev) => {
      const rect = root.getBoundingClientRect();
      const ratio = vertical
        ? (ev.clientY - rect.top) / rect.height
        : (ev.clientX - rect.left) / rect.width;
      apply(ratio * 100);
    };
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
  });
  handle.addEventListener("keydown", (ev) => {
    const back = vertical ? "ArrowUp" : "ArrowLeft";
    const forward = vertical ? "ArrowDown" : "ArrowRight";
    if (ev.key === back) apply(value - 2);
    else if (ev.key === forward) apply(value + 2);
    else if (ev.key === "Home") apply(min);
    else if (ev.key === "End") apply(max);
    else return;
    ev.preventDefault();
  });
  handle.addEventListener("dblclick", () => apply(initial));
}

/* ------------------------------------------------------------------ *
 * Data grid (SPEC 11.1): the rows are all server-rendered; sorting
 * reorders the real DOM, filtering hides rows, selection tracks
 * checkboxes and dispatches virel-selection, paging shows a window.
 * ------------------------------------------------------------------ */

export function datagrid(id) {
  const root = el(id);
  if (!root) return;
  const body = root.querySelector("tbody");
  const rows = Array.from(body.querySelectorAll(":scope > tr"));
  const count = root.querySelector(".v-grid-count");
  const pageSize = Number(root.dataset.pageSize) || 0;
  let page = 0;
  let sortKey = null;
  let sortDir = 0; // 1 ascending, -1 descending, 0 original order
  let query = "";

  const matches = (row) =>
    query === "" || row.textContent.toLowerCase().includes(query);

  const refresh = () => {
    let live = rows.filter(matches);
    if (sortDir !== 0 && sortKey !== null) {
      const heads = Array.from(root.querySelectorAll("th[data-key]"));
      const columnIndex = heads.findIndex(
        (th) => th.dataset.key === sortKey);
      const offset = root.querySelector(".v-grid-selcol") ? 1 : 0;
      const kind = heads[columnIndex].dataset.kind;
      const valueOf = (row) => {
        const cell = row.children[columnIndex + offset];
        return cell ? cell.dataset.value : "";
      };
      live = live.slice().sort((a, b) => {
        const va = valueOf(a);
        const vb = valueOf(b);
        const order = kind === "number"
          ? Number(va || "-Infinity") - Number(vb || "-Infinity")
          : va < vb ? -1 : va > vb ? 1 : 0;
        return order * sortDir;
      });
    } else {
      live = live.slice().sort(
        (a, b) => Number(a.dataset.index) - Number(b.dataset.index));
    }
    const pages = pageSize
      ? Math.max(1, Math.ceil(live.length / pageSize)) : 1;
    page = Math.min(page, pages - 1);
    const start = pageSize ? page * pageSize : 0;
    const shown = pageSize ? live.slice(start, start + pageSize) : live;

    for (const row of rows) row.hidden = true;
    // Reordering happens in the real DOM so the table stays a table.
    for (const row of shown) {
      body.appendChild(row);
      row.hidden = false;
    }
    if (count) {
      count.textContent = live.length === rows.length
        ? `${rows.length} rows` : `${live.length} of ${rows.length} rows`;
    }
    const pager = root.querySelector(".v-grid-pages");
    if (pager) pager.textContent = `Page ${page + 1} of ${pages}`;
    const previous = root.querySelector(".v-grid-prev");
    const next = root.querySelector(".v-grid-next");
    if (previous) previous.disabled = page === 0;
    if (next) next.disabled = page >= pages - 1;
    syncSelectAll();
  };

  // Sorting cycles ascending, descending, back to the original order.
  root.querySelectorAll("th[data-key]").forEach((th) => {
    const button = th.querySelector(".v-grid-sort");
    if (!button) return;
    button.addEventListener("click", () => {
      if (sortKey !== th.dataset.key) {
        sortKey = th.dataset.key;
        sortDir = 1;
      } else {
        sortDir = sortDir === 1 ? -1 : sortDir === -1 ? 0 : 1;
      }
      root.querySelectorAll("th[data-key]").forEach((other) => {
        if (other.getAttribute("aria-sort") !== null) {
          other.setAttribute("aria-sort",
            other === th && sortDir !== 0
              ? (sortDir === 1 ? "ascending" : "descending") : "none");
        }
      });
      refresh();
    });
  });

  const filter = root.querySelector(".v-grid-filter");
  if (filter) {
    filter.addEventListener("input", () => {
      query = filter.value.trim().toLowerCase();
      page = 0;
      refresh();
    });
  }
  const previous = root.querySelector(".v-grid-prev");
  const next = root.querySelector(".v-grid-next");
  if (previous) {
    previous.addEventListener("click", () => { page--; refresh(); });
  }
  if (next) {
    next.addEventListener("click", () => { page++; refresh(); });
  }

  // Selection: per-row checkboxes plus a tri-state select-all over the
  // currently visible rows.
  const selectAll = root.querySelector(".v-grid-check-all");
  const rowChecks = () => rows
    .filter((row) => !row.hidden)
    .map((row) => row.querySelector(".v-grid-check-row"))
    .filter(Boolean);
  const selectedKeys = () => rows
    .filter((row) => {
      const check = row.querySelector(".v-grid-check-row");
      return check && check.checked;
    })
    .map((row) => row.dataset.key);
  const announceSelection = () => {
    root.dispatchEvent(new CustomEvent("virel-selection", {
      detail: { keys: selectedKeys() },
    }));
    syncSelectAll();
  };
  function syncSelectAll() {
    if (!selectAll) return;
    const checks = rowChecks();
    const checked = checks.filter((check) => check.checked).length;
    selectAll.checked = checks.length > 0 && checked === checks.length;
    selectAll.indeterminate = checked > 0 && checked < checks.length;
  }
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      for (const check of rowChecks()) check.checked = selectAll.checked;
      announceSelection();
    });
    body.addEventListener("change", (ev) => {
      if (ev.target.classList.contains("v-grid-check-row")) {
        announceSelection();
      }
    });
  }

  refresh();
}

/* ------------------------------------------------------------------ *
 * Tree view (SPEC 11.1): the ARIA tree pattern. Roving tabindex, arrow
 * navigation, Right/Left expand and collapse, Enter selects.
 * ------------------------------------------------------------------ */

export function tree(id) {
  const root = el(id);
  if (!root) return;
  const items = () => Array.from(root.querySelectorAll('[role="treeitem"]'));
  const visible = () => items().filter((item) => {
    let parent = item.parentElement;
    while (parent && parent !== root) {
      if (parent.getAttribute("role") === "group" &&
          parent.parentElement.getAttribute("aria-expanded") === "false") {
        return false;
      }
      parent = parent.parentElement;
    }
    return true;
  });
  const focusItem = (item) => {
    items().forEach((other) => other.setAttribute("tabindex", "-1"));
    item.setAttribute("tabindex", "0");
    item.focus();
  };
  const first = items()[0];
  if (first) first.setAttribute("tabindex", "0");

  root.addEventListener("click", (ev) => {
    const twist = ev.target.closest(".v-tree-twist");
    if (twist) {
      const item = twist.closest('[role="treeitem"]');
      const expanded = item.getAttribute("aria-expanded");
      if (expanded !== null) {
        item.setAttribute("aria-expanded",
                          expanded === "true" ? "false" : "true");
      }
      ev.stopPropagation();
      return;
    }
    const row = ev.target.closest(".v-tree-row");
    if (row) focusItem(row.closest('[role="treeitem"]'));
  });

  root.addEventListener("keydown", (ev) => {
    const item = ev.target.closest('[role="treeitem"]');
    if (!item) return;
    const list = visible();
    const index = list.indexOf(item);
    const expanded = item.getAttribute("aria-expanded");
    if (ev.key === "ArrowDown" && index < list.length - 1) {
      focusItem(list[index + 1]);
    } else if (ev.key === "ArrowUp" && index > 0) {
      focusItem(list[index - 1]);
    } else if (ev.key === "ArrowRight" && expanded !== null) {
      if (expanded === "false") item.setAttribute("aria-expanded", "true");
      else {
        const child = item.querySelector('[role="treeitem"]');
        if (child) focusItem(child);
      }
    } else if (ev.key === "ArrowLeft") {
      if (expanded === "true") item.setAttribute("aria-expanded", "false");
      else {
        const parent = item.parentElement.closest('[role="treeitem"]');
        if (parent) focusItem(parent);
      }
    } else if (ev.key === "Home" && list.length) {
      focusItem(list[0]);
    } else if (ev.key === "End" && list.length) {
      focusItem(list[list.length - 1]);
    } else if (ev.key === "Enter" || ev.key === " ") {
      const target = item.querySelector(":scope > .v-tree-row .v-tree-label");
      if (target) target.click();
    } else {
      return;
    }
    ev.preventDefault();
  });
}

/* ------------------------------------------------------------------ *
 * Command palette (SPEC 11.1): Ctrl/Cmd+letter opens a modal search
 * over static commands; typing filters, arrows move the active option,
 * Enter runs it. The native dialog supplies focus trapping and Escape.
 * ------------------------------------------------------------------ */

export function palette(id) {
  const dialog = el(id);
  if (!dialog) return;
  const input = dialog.querySelector(".v-palette-input");
  const empty = dialog.querySelector(".v-palette-empty");
  const options = Array.from(dialog.querySelectorAll(".v-palette-item"));
  options.forEach((option, index) => {
    option.id = `${id}-cmd-${index}`;
  });
  let active = -1;

  const shown = () => options.filter((option) => !option.hidden);
  const mark = (index) => {
    const list = shown();
    active = Math.max(0, Math.min(index, list.length - 1));
    options.forEach((option) => option.classList.remove("v-palette-active"));
    if (list.length) {
      list[active].classList.add("v-palette-active");
      list[active].scrollIntoView({ block: "nearest" });
      input.setAttribute("aria-activedescendant", list[active].id);
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  };
  const filter = () => {
    const query = input.value.trim().toLowerCase();
    for (const option of options) {
      option.hidden = query !== "" && !option.dataset.label.includes(query);
    }
    empty.hidden = shown().length > 0;
    mark(0);
  };
  const openPalette = () => {
    if (dialog.open) return;
    dialog.showModal();
    input.value = "";
    filter();
    input.focus();
  };

  const hotkey = (dialog.dataset.hotkey || "k").toLowerCase();
  const onGlobalKey = (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === hotkey) {
      ev.preventDefault();
      openPalette();
    }
  };
  document.addEventListener("keydown", onGlobalKey);
  onDispose(() => document.removeEventListener("keydown", onGlobalKey));

  input.addEventListener("input", filter);
  dialog.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") mark(active + 1);
    else if (ev.key === "ArrowUp") mark(active - 1);
    else if (ev.key === "Enter") {
      const list = shown();
      if (list[active]) list[active].click();
      dialog.close();
    } else {
      return;
    }
    ev.preventDefault();
  });
  dialog.addEventListener("click", (ev) => {
    if (ev.target.closest(".v-palette-item")) dialog.close();
    else if (ev.target === dialog) dialog.close(); // backdrop click
  });
}

/* ------------------------------------------------------------------ *
 * Notifications (SPEC 11.1): toasts in a polite live region. Screen
 * readers announce them without focus moving; hover pauses the timer;
 * exits reuse the CSS animation pipeline.
 * ------------------------------------------------------------------ */

let toastRegion = null;

export function notify(message, opts = {}) {
  if (!toastRegion || !toastRegion.isConnected) {
    toastRegion = document.createElement("div");
    toastRegion.className = "v-toasts";
    toastRegion.setAttribute("role", "status");
    toastRegion.setAttribute("aria-live", "polite");
    document.body.appendChild(toastRegion);
  }
  const toast = document.createElement("div");
  toast.className = "v-toast v-toast-" + (opts.intent || "neutral");
  const text = document.createElement("span");
  text.className = "v-toast-text";
  text.textContent = String(message);
  toast.appendChild(text);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "v-toast-close";
  close.setAttribute("aria-label", "Dismiss notification");
  close.innerHTML =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
    'aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  toast.appendChild(close);

  let timer = null;
  const dismiss = () => {
    if (toast.__closing) return;
    toast.__closing = true;
    clearTimeout(timer);
    toast.classList.add("v-toast-exit");
    if (getComputedStyle(toast).animationName === "none") {
      toast.remove();
      return;
    }
    toast.addEventListener("animationend", () => toast.remove(),
                           { once: true });
  };
  close.addEventListener("click", dismiss);
  const duration = opts.duration == null ? 5000 : opts.duration;
  if (duration > 0) {
    timer = setTimeout(dismiss, duration);
    toast.addEventListener("mouseenter", () => clearTimeout(timer));
    toast.addEventListener("mouseleave", () => {
      if (!toast.__closing) timer = setTimeout(dismiss, duration);
    });
  }
  toastRegion.appendChild(toast);
}

/* ------------------------------------------------------------------ *
 * Popover (SPEC 11.1): an anchored non-modal panel. Click toggles,
 * Escape and outside clicks close, focus moves into the panel on open
 * and back to the trigger on close, and the panel flips upward when
 * space below runs out.
 * ------------------------------------------------------------------ */

export function popover(id) {
  const node = el(id);
  if (!node) return;
  const trigger = node.firstElementChild;
  const panel = node.querySelector(":scope > .v-popover-panel");
  if (!trigger || !panel) return;
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-expanded", "false");

  const close = (refocus) => {
    if (!node.classList.contains("v-popover-open")) return;
    node.classList.remove("v-popover-open", "v-popover-up");
    trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", onOutside, true);
    if (refocus) trigger.focus();
  };
  const onOutside = (ev) => {
    if (!node.contains(ev.target)) close(false);
  };
  const open = () => {
    node.classList.add("v-popover-open");
    trigger.setAttribute("aria-expanded", "true");
    const rect = trigger.getBoundingClientRect();
    const panelHeight = panel.offsetHeight || 240;
    if (rect.bottom + panelHeight + 16 > window.innerHeight
        && rect.top > panelHeight) {
      node.classList.add("v-popover-up");
    }
    document.addEventListener("pointerdown", onOutside, true);
    const focusable = panel.querySelector(
      "button, [href], input, select, textarea, [tabindex]");
    if (focusable) focusable.focus();
  };
  trigger.addEventListener("click", () => {
    if (node.classList.contains("v-popover-open")) close(true);
    else open();
  });
  node.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && node.classList.contains("v-popover-open")) {
      ev.stopPropagation();
      close(true);
    }
  });
  onDispose(() => close(false));
}

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
 * Design preferences (SPEC 10.1): theme, brand, density, contrast.
 * Each lives as data-<key> on the root element and persists to
 * localStorage; the inline bootstrap restores all of them before first
 * paint. A null value clears the preference back to the default.
 * ------------------------------------------------------------------ */

export function setPreference(key, value) {
  if (!["theme", "brand", "density", "contrast"].includes(key)) return;
  const root = document.documentElement;
  try {
    if (value == null) {
      delete root.dataset[key];
      localStorage.removeItem("virel-" + key);
    } else {
      root.dataset[key] = value;
      localStorage.setItem("virel-" + key, value);
    }
  } catch {}
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
// on network failures; a finished stream sends a done event and closes
// cleanly (no endless reconnect). Changing reactive parameters reopens
// the stream, client navigation closes it, and $.sseRestart reopens a
// finished subscription.
const sseRegistry = {};

export function sse(id, name, argsFn, opts) {
  let source = null;
  const open = (args) => {
    source?.close();
    const query = new URLSearchParams();
    for (const key in args) query.set(key, String(args[key]));
    const suffix = query.toString() ? "?" + query.toString() : "";
    source = new EventSource(`/_virel/action/${name}${suffix}`);
    opts.status?.set("live");
    source.onmessage = (ev) => {
      if (opts.events) {
        try {
          opts.events.set([...(opts.events.get() || []), JSON.parse(ev.data)]);
        } catch {}
      } else if (opts.into) {
        opts.into.set((opts.into.get() || "") + ev.data + "\n");
      }
    };
    source.addEventListener("done", () => {
      source.close();
      opts.status?.set("done");
    });
    source.addEventListener("error", (ev) => {
      if (ev.data) opts.status?.set("error");
    });
  };
  const reopen = () => {
    const args = argsFn ? argsFn() : {};
    const previous = activeEffect;
    activeEffect = null;
    try {
      open(args);
    } finally {
      activeEffect = previous;
    }
  };
  effect(() => {
    if (argsFn) argsFn(); // subscribe to reactive params
    reopen();
  });
  sseRegistry[id] = reopen;
  onDispose(() => {
    source?.close();
    delete sseRegistry[id];
  });
}

export function sseRestart(id) {
  sseRegistry[id]?.();
}

/* ------------------------------------------------------------------ *
 * WebSocket channels: bidirectional real-time messaging, opened only
 * when a page connects to a declared channel (SPEC 9.5). Incoming JSON
 * messages append into a list state; sends queue until the socket is
 * open; reconnection backs off and navigation closes the socket.
 * ------------------------------------------------------------------ */

const channels = {};

export function channel(name, opts) {
  const entry = { socket: null, queue: [], attempts: 0, disposed: false };
  channels[name] = entry;

  const open = () => {
    if (entry.disposed) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(
      `${scheme}://${location.host}/_virel/channel/${name}`);
    entry.socket = socket;
    socket.addEventListener("open", () => {
      entry.attempts = 0;
      opts.status?.set("open");
      for (const payload of entry.queue.splice(0)) socket.send(payload);
    });
    socket.addEventListener("message", (ev) => {
      try {
        const data = JSON.parse(ev.data);
        opts.events.set([...(opts.events.get() || []), data]);
      } catch {}
    });
    socket.addEventListener("close", () => {
      opts.status?.set("closed");
      if (entry.disposed || entry.attempts >= 5) return;
      entry.attempts += 1;
      setTimeout(open, Math.min(500 * 2 ** entry.attempts, 8000));
    });
  };
  open();
  onDispose(() => {
    entry.disposed = true;
    entry.socket?.close();
    delete channels[name];
  });
}

export function channelSend(name, data) {
  const entry = channels[name];
  if (!entry) {
    console.warn(`virel: no connection to channel ${name}`);
    return;
  }
  const payload = JSON.stringify(data);
  if (entry.socket && entry.socket.readyState === WebSocket.OPEN) {
    entry.socket.send(payload);
  } else {
    entry.queue.push(payload);
  }
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
