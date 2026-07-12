# third-party-widgets

This directory plays the role of an external JavaScript package. It contains
no Virel code, on purpose: the demo application uses it to show how Virel
binds typed Python components to web components it did not generate.

Everything here follows standard web platform contracts only:

- `star-rating.js` — an interactive rating input; attributes in, a
  `rating-changed` custom event out.
- `widgets.js` — `spark-line`, an SVG sparkline that re-renders when its
  `values` attribute changes, and `relative-time`, a self-updating
  timestamp display.
- `*.manifest.json` — [custom elements manifests](https://github.com/webcomponents/custom-elements-manifest)
  describing the elements, as a real package would publish them.

The demo mounts this directory with `ui.use_static("/vendor/widgets", ...)`
and generates its typed bindings from the manifests:

```bash
cd ../demo
virel bind ../third-party-widgets/star-rating.manifest.json \
    --module /vendor/widgets/star-rating.js --out app/bindings.py
virel bind ../third-party-widgets/widgets.manifest.json \
    --module /vendor/widgets/widgets.js --out app/widgets_bindings.py
```

The demo application itself contains no hand-written JavaScript, CSS, or
HTML; this package exists so it has something foreign to integrate with.
