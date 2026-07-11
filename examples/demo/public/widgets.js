/* More deliberately plain third-party custom elements — no Virel code.
 * They communicate through standard web platform contracts only. */

class SparkLine extends HTMLElement {
  static get observedAttributes() {
    return ["values", "stroke"];
  }

  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.render();
  }

  attributeChangedCallback() {
    if (this.shadowRoot) this.render();
  }

  render() {
    const values = (this.getAttribute("values") || "")
      .split(",").map(Number).filter((n) => !Number.isNaN(n));
    const stroke = this.getAttribute("stroke") || "#4f46e5";
    const width = 220, height = 48, pad = 4;
    let points = "";
    if (values.length > 1) {
      const min = Math.min(...values), max = Math.max(...values);
      const span = max - min || 1;
      points = values.map((v, i) => {
        const x = pad + (i / (values.length - 1)) * (width - pad * 2);
        const y = height - pad - ((v - min) / span) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
    }
    this.shadowRoot.innerHTML = `
      <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"
           role="img" aria-label="sparkline">
        <polyline points="${points}" fill="none" stroke="${stroke}"
                  stroke-width="2" stroke-linecap="round"
                  stroke-linejoin="round"/>
      </svg>`;
  }
}

class RelativeTime extends HTMLElement {
  static get observedAttributes() {
    return ["datetime"];
  }

  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.tick = setInterval(() => this.render(), 1000);
    this.render();
  }

  disconnectedCallback() {
    clearInterval(this.tick);
  }

  attributeChangedCallback() {
    if (this.shadowRoot) this.render();
  }

  render() {
    const then = new Date(this.getAttribute("datetime") || Date.now());
    const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    let text;
    if (seconds < 60) text = `${seconds}s ago`;
    else if (seconds < 3600) text = `${Math.floor(seconds / 60)}m ago`;
    else text = `${Math.floor(seconds / 3600)}h ago`;
    this.shadowRoot.innerHTML = `<span>${text}</span>`;
  }
}

if (!customElements.get("spark-line")) {
  customElements.define("spark-line", SparkLine);
}
if (!customElements.get("relative-time")) {
  customElements.define("relative-time", RelativeTime);
}
