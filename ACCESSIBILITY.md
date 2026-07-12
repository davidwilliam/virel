# Accessibility

Accessibility in Virel is a correctness property, enforced in three
layers: the typed API makes many failures inexpressible, the compiler
audits every page, and each interactive component ships a documented
keyboard and ARIA contract, tested in pytest and in a real browser.

## Enforced by construction

- `Image` requires alt text; `alt=""` is reserved for decorative images.
- Every input (`TextField`, `Select`, `DateField`, `Listbox`, and the
  rest) requires a label, rendered as a real `<label>` association.
- `Icon` is `aria-hidden` unless given `label=`, which becomes an
  `aria-label` on the SVG.
- Event handlers only exist on interactive components; a click handler
  on a plain container cannot be expressed.
- URLs are scheme-checked everywhere they appear, including chart data
  and command palette targets.

## Compiler audit

Every page compile runs the audit (`virel check` prints results):

- Errors: an interactive element with no accessible name; focusable
  content inside an `aria-hidden` subtree.
- Warnings: heading-progression skips, multiple `h1` elements, vague
  link text. `ui.use_accessibility(strict=True)` promotes warnings to
  errors. `Heading(level=, size=)` fixes outline problems without
  changing visual scale.

## Component contracts

Every interactive component documents its keyboard interaction, focus
behavior, and semantics. Reduced motion collapses animation globally
(`essential=True` exempts status motion), touch targets grow to 44px on
coarse pointers, and high contrast strengthens borders, muted text, and
focus rings; those apply to every component below.

| Component | Keyboard | Focus and semantics |
|---|---|---|
| `Button` | Enter/Space activate | Native button; `aria_label=` for icon-only |
| `Link`, `LinkButton` | Enter activates | Native anchors; router keeps `aria-current` on the active nav link |
| `TextField`, `Textarea`, `NumberField`, `DateField` | Native editing | Label association; errors render as field-scoped text |
| `Select` | Arrows move, Enter selects, Escape closes, type-ahead | Enhanced combobox over a native select that remains the source of truth |
| `Listbox` | Arrows move the active option, Home/End jump, Enter/Space select (toggle when multiselectable) | `role="listbox"`, `aria-activedescendant`, `aria-selected` per option |
| `Checkbox`, `Switch`, `RadioGroup`, `Slider` | Native interaction | Native inputs styled with CSS only |
| `FilterChips` | Tab between chips, Enter/Space toggle | `role="group"`; each chip carries `aria-pressed` |
| `Tabs` | Arrows move between tabs | `role="tablist"`; panels stay in the document |
| `Dialog` | Escape closes; focus is trapped | Native `<dialog>`: focus trapping and restoration come from the browser |
| `Menu` | Arrows move, Enter activates, Escape closes and refocuses the trigger | `role="menu"`; flips upward when space runs out |
| `Popover` | Escape closes and refocuses the trigger | `aria-expanded`/`aria-haspopup` on the trigger; focus moves to the first focusable on open |
| `Tooltip` | Appears on focus as well as hover | CSS-only |
| `Accordion` | Enter/Space toggle | Native `<details>`/`<summary>` |
| `Tree` | Arrows move, Right/Left expand and collapse, Home/End jump, Enter selects | `role="tree"` pattern with roving tabindex and `aria-expanded` |
| `CommandPalette` | Ctrl/Cmd+letter opens, typing filters, arrows move, Enter runs, Escape closes | Combobox over a listbox inside a native dialog; `aria-activedescendant` tracks the active option |
| `Pagination` | Tab between pages, Enter activates | `<nav>` with `aria-label`; `aria-current="page"` on the active page; edges disabled |
| `DataGrid` | Sort buttons and checkboxes are native controls; arrow keys move cell focus (roving tabindex), Enter edits an editable cell, Escape cancels | `aria-sort` tracks each sortable column; select-all is tri-state; group toggles carry `aria-expanded`; row count is a `role="status"` region |
| `Splitter` | Arrows move the divider, Home/End snap to the limits | `role="separator"` with `aria-valuenow`/min/max and orientation |
| `Swipeable` | Delete/Backspace dismiss | Focusable group with usage named in its label |
| `Each(reorderable=True)` | Space grabs the handle, arrows move, Space drops, Escape cancels | Per-item handle buttons; every move announced through a visually hidden `role="status"` region |
| `Tour` | Escape closes; Back/Next are buttons; focus moves to the card and returns on close | `role="dialog"`; spotlight is decorative (`pointer-events: none`) |
| `Toast` (`ui.notify`) | Dismiss button is labeled | `aria-live="polite"` region announces without stealing focus |
| `Chart` | Static content | `role="img"` with a text summary; every point carries a `<title>` |
| `Video`, `Audio` | Native player controls | Required `label=`; captions track supported; no autoplay |

## Testing

The pytest API queries by role and accessible name
(`view.get_by_role("button", name=...)`, `get_by_label`), so tests fail
when semantics regress. The browser suite drives components with the
keyboard (tree navigation, splitter arrows, reorder grab and move,
palette filtering) and verifies reduced-motion behavior in Chromium.
