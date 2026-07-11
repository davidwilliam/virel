/* A deliberately plain third-party custom element — no Virel code here.
 * It communicates through standard web platform contracts only:
 * attributes in, DOM events out. */

class StarRating extends HTMLElement {
  static get observedAttributes() {
    return ["value", "max"];
  }

  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.render();
  }

  attributeChangedCallback() {
    if (this.shadowRoot) this.render();
  }

  get value() {
    return Number(this.getAttribute("value") || 0);
  }

  get max() {
    return Number(this.getAttribute("max") || 5);
  }

  render() {
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>
        :host { display: inline-flex; gap: 4px; }
        button {
          line-height: 0; border: 0; background: none;
          cursor: pointer; padding: 2px; color: #c9c9d1;
        }
        button.on { color: #f59e0b; }
        button:focus-visible { outline: 2px solid #4f46e5; border-radius: 4px; }
        svg { width: 24px; height: 24px; fill: currentColor; }
      </style>
    `;
    const starPath =
      "M12 2l2.9 6.26 6.6.7-4.9 4.5 1.35 6.54L12 16.7 6.05 20l1.35-6.54-4.9-4.5 6.6-.7z";
    for (let i = 1; i <= this.max; i++) {
      const star = document.createElement("button");
      star.type = "button";
      star.innerHTML =
        `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${starPath}"/></svg>`;
      star.setAttribute("aria-label", `${i} star${i > 1 ? "s" : ""}`);
      if (i <= this.value) star.classList.add("on");
      star.addEventListener("click", () => {
        this.dispatchEvent(
          new CustomEvent("rating-changed", {
            detail: { value: i },
            bubbles: true,
          })
        );
      });
      root.appendChild(star);
    }
  }
}

if (!customElements.get("star-rating")) {
  customElements.define("star-rating", StarRating);
}
