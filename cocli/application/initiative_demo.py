"""Record a form-fill demo for one campaign initiative scenario.

The shot list is ``<initiative>/demo-form.yaml``. The typed values are
``<initiative>/scenarios/<slug>/inputs.yaml``. Output lands in
``<initiative>/scenarios/<slug>/demo/``. Tabbing out of State of Residence
lets the page partial-save and enable the rest of the form. The closing
shot clicks Save & Continue and waits for the Retirement Goal Overview subtab.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)

_FRAME_JS = """
async (opts) => {
  const root = document.documentElement;
  const body = document.body;
  root.style.scrollBehavior = "auto";
  window.scrollTo(0, 0);

  const scaleOf = () => {
    const parsed = parseFloat(body.dataset.demoScale || "1");
    return parsed > 0 ? parsed : 1;
  };

  const docRect = (el) => {
    const previous = body.style.transform;
    body.style.transform = "none";
    const rect = el.getBoundingClientRect();
    body.style.transform = previous;
    return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
  };

  const must = (selector) => {
    const el = document.querySelector(selector);
    if (!el) {
      throw new Error("Missing frame element: " + selector);
    }
    return el;
  };

  const headingEl = (text) => {
    if (!text) return null;
    const nodes = document.querySelectorAll("h2, h3, h4");
    for (const node of nodes) {
      if ((node.textContent || "").includes(text)) return node;
    }
    throw new Error("Missing heading: " + text);
  };

  if (opts.reset) {
    body.style.transform = "none";
    body.dataset.demoScale = "1";
    body.dataset.demoTx = "0";
    body.dataset.demoTy = "0";
    window.scrollTo(0, 0);
    return { zoom: 1, scrollX: 0, scrollY: 0 };
  }

  const elements = [];
  if (opts.selector) elements.push(must(opts.selector));
  if (opts.start) elements.push(must(opts.start));
  if (opts.end) elements.push(must(opts.end));
  const heading = headingEl(opts.heading || "");
  if (heading) elements.push(heading);
  if (!elements.length) {
    throw new Error("Frame has no selector, start/end, or heading");
  }

  const boxOf = (el) => {
    const rect = docRect(el);
    if (rect.right - rect.left > 1 && rect.bottom - rect.top > 1) return rect;
    if (el.id) {
      const label = document.querySelector("label[for='" + CSS.escape(el.id) + "']");
      if (label) {
        const labelRect = docRect(label);
        if (labelRect.right - labelRect.left > 1 && labelRect.bottom - labelRect.top > 1) {
          return labelRect;
        }
      }
    }
    return null;
  };

  let top = Infinity;
  let left = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const el of elements) {
    const rect = boxOf(el);
    if (!rect) continue;
    top = Math.min(top, rect.top);
    left = Math.min(left, rect.left);
    right = Math.max(right, rect.right);
    bottom = Math.max(bottom, rect.bottom);
  }
  if (!Number.isFinite(top)) {
    throw new Error("Frame elements have no visible box");
  }
  if (opts.column) {
    const column = docRect(must(opts.column));
    left = column.left;
    right = column.right;
  }

  const pad = opts.pad;
  top -= pad;
  left -= pad;
  right += pad;
  bottom += pad;

  const boxWidth = Math.max(right - left, 1);
  const boxHeight = Math.max(bottom - top, 1);
  let targetZoom = Math.min(window.innerWidth / boxWidth, window.innerHeight / boxHeight);
  targetZoom = Math.max(opts.minZoom, Math.min(opts.maxZoom, targetZoom));
  const focalX = (left + right) / 2;
  const focalY = (top + bottom) / 2;

  const startZoom = scaleOf();
  const startTx = parseFloat(body.dataset.demoTx || "0");
  const startTy = parseFloat(body.dataset.demoTy || "0");
  const startFocalX = (window.innerWidth / 2 - startTx) / startZoom;
  const startFocalY = (window.innerHeight / 2 - startTy) / startZoom;

  const apply = (zoom, focusX, focusY) => {
    const tx = window.innerWidth / 2 - focusX * zoom;
    const ty = window.innerHeight / 2 - focusY * zoom;
    body.style.transformOrigin = "0 0";
    body.style.transform = `translate(${tx}px, ${ty}px) scale(${zoom})`;
    body.dataset.demoScale = String(zoom);
    body.dataset.demoTx = String(tx);
    body.dataset.demoTy = String(ty);
  };

  const duration = opts.duration;
  if (duration <= 0) {
    apply(targetZoom, focalX, focalY);
    return { zoom: targetZoom, scrollX: window.scrollX, scrollY: window.scrollY };
  }

  const started = performance.now();
  await new Promise((resolve) => {
    const step = (now) => {
      const t = Math.min(1, (now - started) / duration);
      const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      apply(
        startZoom + (targetZoom - startZoom) * eased,
        startFocalX + (focalX - startFocalX) * eased,
        startFocalY + (focalY - startFocalY) * eased,
      );
      if (t < 1) requestAnimationFrame(step);
      else resolve();
    };
    requestAnimationFrame(step);
  });
  return { zoom: scaleOf(), scrollX: window.scrollX, scrollY: window.scrollY };
}
"""

_INSTALL_JS = """
(() => {
  const install = () => {
    if (!document.documentElement || document.getElementById("rta-demo-style")) return;
    const style = document.createElement("style");
    style.id = "rta-demo-style";
    style.textContent = [
      ".client-container { display: none !important; }",
      "input:focus, select:focus { outline: 3px solid #1d4ed8; outline-offset: 2px; }",
    ].join("\\n");
    document.documentElement.appendChild(style);
    // Field clicks call scrollIntoView and shove the zoomed section off screen.
    const nativeScrollTo = window.scrollTo.bind(window);
    const keepTop = () => {
      if (window.scrollX !== 0 || window.scrollY !== 0) nativeScrollTo(0, 0);
    };
    window.scrollTo = (x, y) => {
      const left = typeof x === "object" ? (x.left || 0) : (x || 0);
      const top = typeof x === "object" ? (x.top || 0) : (y || 0);
      if (left === 0 && top === 0) nativeScrollTo(0, 0);
    };
    Element.prototype.scrollIntoView = () => {};
    window.addEventListener("scroll", keepTop, true);
  };
  install();
  document.addEventListener("DOMContentLoaded", install);
})();
"""


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    return loaded


def lookup(data: dict[str, Any], dotted: str) -> Any:
    """Resolve a dotted key such as goal.gogo.begin_age."""
    current: Any = data
    for part in dotted.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise KeyError(dotted)
            current = current[index]
            continue
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted)
        current = current[part]
    return current


def format_value(raw: Any, kind: str) -> str:
    """Render an inputs.yaml value the way a person would type it."""
    if kind == "text":
        return str(raw)
    if kind == "yes_no":
        if isinstance(raw, str):
            return "yes" if raw.strip().lower() in {"yes", "true", "y", "1"} else "no"
        return "yes" if raw else "no"
    number = float(raw)
    if kind in {"money", "integer"}:
        return str(int(round(number)))
    if kind == "decimal":
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
    raise ValueError(f"Unknown format {kind!r}")


def resolve_steps(form: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach typed text to each step, failing before the browser opens."""
    sections = form.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("demo-form.yaml needs a non-empty sections list")
    resolved: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict) or "name" not in section:
            raise ValueError(f"Section is missing a name: {section!r}")
        frame = section.get("frame")
        if not isinstance(frame, dict):
            raise ValueError(f"Section {section['name']} is missing a frame")
        steps_out: list[dict[str, Any]] = []
        for step in section.get("steps", []):
            if not isinstance(step, dict) or "action" not in step:
                raise ValueError(f"Bad step in {section['name']}: {step!r}")
            prepared = dict(step)
            if "value_from" in step:
                raw = lookup(inputs, str(step["value_from"]))
                kind = str(step.get("format", "text"))
                prepared["text"] = format_value(raw, kind)
            elif "value" in step:
                prepared["text"] = str(step["value"])
            elif step["action"] == "wait":
                if step.get("until") not in {"enabled", "visible", "detached"} or "selector" not in step:
                    raise ValueError(
                        "Wait in "
                        f"{section['name']} needs until: enabled, visible, or detached, "
                        f"and a selector: {step!r}"
                    )
            elif step["action"] not in {"pause", "click", "check"}:
                raise ValueError(f"Step in {section['name']} has no value: {step!r}")
            follow = step.get("then")
            if follow not in {None, "tab", "stay"}:
                raise ValueError(f"Step in {section['name']} has unknown then {follow!r}")
            steps_out.append(prepared)
        copied = dict(section)
        copied["steps"] = steps_out
        resolved.append(copied)
    return resolved


def _frame_options(form: dict[str, Any], frame: dict[str, Any], duration: int) -> dict[str, Any]:
    return {
        "selector": frame.get("selector", ""),
        "start": frame.get("start", ""),
        "end": frame.get("end", ""),
        "heading": frame.get("heading", ""),
        "column": frame.get("column", ""),
        "duration": duration,
        "pad": int(form.get("pad_px", 32)),
        "minZoom": float(frame.get("min_zoom", form.get("min_zoom", 0.72))),
        "maxZoom": float(frame.get("max_zoom", form.get("max_zoom", 2.25))),
        "reset": False,
    }


def move_camera(page: Page, form: dict[str, Any], frame: dict[str, Any], duration: int) -> float:
    """Animate zoom and scroll so the frame fills the viewport. Returns the zoom."""
    placed: dict[str, float] = page.evaluate(_FRAME_JS, _frame_options(form, frame, duration))
    return float(placed["zoom"])


def reset_camera(page: Page) -> None:
    """Return to the unzoomed top of the page."""
    page.evaluate(_FRAME_JS, {"reset": True, "duration": 0, "pad": 0, "minZoom": 1, "maxZoom": 1})


def element_in_view(page: Page, selector: str) -> bool:
    """Return whether the element's box sits inside the viewport."""
    return bool(
        page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (!el) return false;
                const slack = 2;
                const inside = (rect) => rect.width > 0 && rect.height > 0
                    && rect.top >= -slack && rect.left >= -slack
                    && rect.bottom <= window.innerHeight + slack
                    && rect.right <= window.innerWidth + slack;
                if (inside(el.getBoundingClientRect())) return true;
                if (!el.id) return false;
                const label = document.querySelector("label[for='" + CSS.escape(el.id) + "']");
                return !!label && inside(label.getBoundingClientRect());
            }""",
            selector,
        )
    )


def clear_field(page: Page, selector: str) -> None:
    """Empty a field, including autoNumeric money and percent masks."""
    locator = page.locator(selector).first
    locator.click()
    locator.press("Control+A")
    locator.press("Backspace")
    leftover = "".join(ch for ch in locator.input_value() if ch.isdigit())
    if leftover:
        locator.evaluate(
            """(el) => {
                const jq = window.jQuery;
                if (jq && jq(el).data("autoNumeric")) {
                    jq(el).autoNumeric("set", "");
                    return;
                }
                el.value = "";
            }"""
        )


def commit_field(page: Page, selector: str) -> None:
    """Blur and fire change so updateAges and the money mask run."""
    page.locator(selector).first.evaluate(
        """(el) => {
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.blur();
        }"""
    )


def _press_tab(page: Page) -> None:
    page.keyboard.press("Tab")


def _finish_control(page: Page, step: dict[str, Any], selector: str) -> None:
    """Leave a control the way the shot list asked.

    ``then: tab`` is a real Tab, so the page's own focusout handler runs.
    ``then: stay`` keeps focus. A synthetic blur has a null relatedTarget,
    which makes this form validate too early and paint red borders.
    """
    follow = step.get("then")
    if follow == "tab":
        _press_tab(page)
        return
    if follow == "stay":
        return
    if step.get("commit", True):
        commit_field(page, selector)


def _choose_radio(page: Page, name: str, value: str, *, then_tab: bool) -> None:
    """Choose a radio, from the keyboard when Tab already landed on it.

    Gender radios are display:none, so they are not a tab stop. The visible
    label is clicked while the previous field still holds focus, and the
    following Tab moves to the next real control.
    """
    on_radio = bool(
        page.evaluate(
            """(name) => {
                const el = document.activeElement;
                return !!(el && el.type === "radio" && el.name === name);
            }""",
            name,
        )
    )
    if on_radio:
        for _ in range(12):
            current = str(
                page.evaluate("() => (document.activeElement && document.activeElement.value) || ''")
            )
            if current == value:
                break
            page.keyboard.press("ArrowDown")
        page.keyboard.press("Space")
    else:
        selector = f"input[name='{name}'][value='{value}']"
        control = page.locator(selector).first
        control_id = control.get_attribute("id") or ""
        label = page.locator(f"label[for='{control_id}']") if control_id else None
        if label is not None and label.count() > 0:
            label.first.click()
        else:
            control.click(force=True)
    if then_tab:
        _press_tab(page)


def _wait_across_navigation(page: Page, selector: str, timeout_ms: int, attempt: Any) -> None:
    """Retry a wait when a partial save or Save & Continue reloads the page."""
    deadline = time.monotonic() + timeout_ms / 1000
    last_error: PlaywrightError | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        try:
            attempt(remaining)
            return
        except PlaywrightError as exc:
            last_error = exc
            message = str(exc).lower()
            if "destroyed" not in message and "navigation" not in message and "detached" not in message:
                break
            page.wait_for_timeout(250)
    raise RuntimeError(f"Timed out waiting for {selector}") from last_error


def wait_until_enabled(page: Page, selector: str, timeout_ms: int) -> None:
    """Wait until a section loses the disabled class.

    Tabbing out of State of Residence partial-saves and reloads the profile.
    """
    expression = """(selector) => {
        const el = document.querySelector(selector);
        return !!el && !el.classList.contains("disabled");
    }"""

    def attempt(remaining: int) -> None:
        page.wait_for_function(expression, arg=selector, timeout=remaining)

    _wait_across_navigation(page, selector, timeout_ms, attempt)


def wait_until_visible(page: Page, selector: str, timeout_ms: int) -> None:
    """Wait until a selector is on screen, including after Save & Continue."""

    def attempt(remaining: int) -> None:
        page.wait_for_selector(selector, state="visible", timeout=remaining)

    _wait_across_navigation(page, selector, timeout_ms, attempt)


def wait_until_detached(page: Page, selector: str, timeout_ms: int) -> None:
    """Wait until a selector is gone. An already-absent element returns at once."""

    def attempt(remaining: int) -> None:
        page.wait_for_selector(selector, state="detached", timeout=remaining)

    _wait_across_navigation(page, selector, timeout_ms, attempt)


def run_step(page: Page, step: dict[str, Any], char_delay: int, pause_ms: int) -> None:
    """Type, click, or choose one control, then pause."""
    action = str(step["action"])
    if action == "pause":
        page.wait_for_timeout(int(step.get("ms", pause_ms)))
        return
    if action == "wait":
        selector = str(step["selector"])
        until = str(step.get("until", ""))
        timeout_ms = int(step.get("timeout_ms", 30000))
        logger.info("Waiting until %s is %s", selector, until)
        if until == "enabled":
            wait_until_enabled(page, selector, timeout_ms)
        elif until == "visible":
            wait_until_visible(page, selector, timeout_ms)
        elif until == "detached":
            wait_until_detached(page, selector, timeout_ms)
        else:
            raise ValueError(f"Unknown wait {until!r}")
    elif action == "type":
        selector = str(step["selector"])
        clear_field(page, selector)
        page.locator(selector).first.press_sequentially(str(step["text"]), delay=char_delay)
        # Blur saves a passive-income row. Leave those fields focused until the row is complete.
        _finish_control(page, step, selector)
    elif action == "click":
        selector = str(step["selector"])
        # A new profile has no roadmap id, so the template omits Add Item
        # until the profile is saved. Put the same button on the table so
        # the row can be typed without saving.
        if page.locator(selector).count() == 0 and selector.endswith("#add-asset"):
            page.evaluate(
                """() => {
                    const body = document.querySelector("#passive-income-items tbody");
                    if (!body || document.getElementById("add-asset")) return;
                    const row = document.createElement("tr");
                    row.id = "total-row";
                    row.innerHTML = [
                        "<td>Total</td>",
                        '<td class="number currency highlighted"></td>',
                        "<td></td><td></td><td></td><td></td>",
                        '<td><button type="button" id="add-asset">Add Item</button></td>',
                    ].join("");
                    body.appendChild(row);
                    const button = document.getElementById("add-asset");
                    button.addEventListener("click", (event) => addPassiveIncomeItem(event));
                }"""
            )
        page.locator(selector).first.click(timeout=int(step.get("timeout_ms", 30000)))
    elif action == "check":
        box = page.locator(str(step["selector"])).first
        if not box.is_checked():
            box.click()
    elif action == "radio":
        _choose_radio(page, str(step["name"]), str(step["text"]), then_tab=step.get("then") == "tab")
    elif action == "select":
        selector = str(step["selector"])
        locator = page.locator(selector).first
        if step.get("then") == "tab":
            locator.focus()
        locator.select_option(str(step["text"]))
        if step.get("then") == "tab":
            _press_tab(page)
        else:
            page.keyboard.press("Escape")
    else:
        raise ValueError(f"Unknown action {action!r}")
    if pause_ms:
        page.wait_for_timeout(pause_ms)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit() or ch == ".")


def _same_typed_value(expected: str, actual: str) -> bool:
    """Match a typed number to a masked field such as 4.0% or $120,000."""
    if actual == expected:
        return True
    exp = _digits(expected)
    act = _digits(actual)
    if exp == act:
        return True
    try:
        return float(exp) == float(act)
    except ValueError:
        return False


def _quoted_name(selector: str) -> str:
    marker = "[name='"
    start = selector.find(marker)
    if start < 0:
        return ""
    rest = selector[start + len(marker) :]
    end = rest.find("']")
    return rest[:end] if end >= 0 else ""


def passive_saved_selector(selector: str) -> str | None:
    """Where a passive-income new row lands after the page saves it.

    Leaving the row posts it and replaces the inputs with text cells, so the
    ``tr.new-row`` selector is gone by the time the shot list is checked.
    """
    if "passive-income-items" not in selector or "tr.new-row" not in selector:
        return None
    name = _quoted_name(selector)
    if not name:
        return None
    if name == "is-continue-until-death":
        return (
            "#passive-income-items tr.passive-income-item "
            "input[name='is-continue-until-death']"
        )
    cell = "age-to-begin" if name == "year-to-begin" else name
    return f"#passive-income-items tr.passive-income-item td[name='{cell}']"


def verify_steps(page: Page, sections: list[dict[str, Any]]) -> list[str]:
    """Check the controls hold the values just entered."""
    problems: list[str] = []
    for section in sections:
        for step in section["steps"]:
            action = step["action"]
            expected = str(step.get("text", ""))
            if action == "type":
                selector = str(step["selector"])
                locator = page.locator(selector)
                if locator.count() == 0:
                    saved = passive_saved_selector(selector)
                    actual = ""
                    if saved is not None and page.locator(saved).count() > 0:
                        actual = page.locator(saved).first.inner_text()
                    if actual and _same_typed_value(expected, actual):
                        continue
                    problems.append(f"{selector} expected {expected!r} but has {actual!r}")
                    continue
                actual = locator.first.input_value()
                if _same_typed_value(expected, actual):
                    continue
                problems.append(f"{selector} expected {expected!r} but has {actual!r}")
            elif action == "radio":
                selector = f"input[name='{step['name']}'][value='{expected}']"
                locator = page.locator(selector)
                if locator.count() == 0 or not locator.first.is_checked():
                    problems.append(f"{selector} is not selected")
            elif action == "check":
                selector = str(step["selector"])
                locator = page.locator(selector)
                if locator.count() == 0:
                    saved = passive_saved_selector(selector)
                    if saved is not None and page.locator(saved).count() > 0:
                        if page.locator(saved).first.is_checked():
                            continue
                    problems.append(f"{selector} is not checked")
                    continue
                if not locator.first.is_checked():
                    problems.append(f"{selector} is not checked")
            elif action == "select":
                selector = str(step["selector"])
                locator = page.locator(selector)
                if locator.count() == 0:
                    problems.append(f"{selector} expected {expected!r} but has ''")
                    continue
                actual = locator.first.input_value()
                if actual != expected:
                    problems.append(f"{selector} expected {expected!r} but has {actual!r}")
    return problems


def shot(page: Page, frames_dir: Path, index: int, name: str) -> None:
    """Save the current viewport."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    path = frames_dir / f"{index:02d}-{name}.jpeg"
    page.screenshot(path=str(path), type="jpeg", quality=90)
    logger.info("Saved frame %s", path.name)


def transcode(webm: Path, mp4: Path, lead_s: float) -> None:
    """Write an H.264 MP4, skipping the login navigation before the opening hold."""
    if shutil.which("ffmpeg") is None:
        logger.info("ffmpeg is not installed; left %s", webm.name)
        return
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(0.0, lead_s):.3f}",
        "-i",
        str(webm),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(mp4),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.warning("ffmpeg failed: %s", result.stderr[-500:])
        return
    logger.info("Saved %s", mp4.name)


def _section_leaves_profile(section: dict[str, Any]) -> bool:
    """True when the section clicks Save & Continue and leaves the profile."""
    return any(
        step["action"] == "click" and "SAVE" in str(step.get("selector", ""))
        for step in section["steps"]
    )


def record(
    page: Page,
    form: dict[str, Any],
    sections: list[dict[str, Any]],
    out_dir: Path,
    *,
    char_delay: int,
    pause_ms: int,
    pan_ms: int,
) -> list[str]:
    """Play the shot list into an already-open profile page."""
    frames_dir = out_dir / "frames"
    settle_ms = int(form.get("settle_ms", 300))
    opening_hold = int(form.get("opening_hold_ms", 1000))
    offscreen: list[str] = []

    reset_camera(page)
    if opening_hold:
        page.wait_for_timeout(opening_hold)
    shot(page, frames_dir, 0, str(form.get("opening", {}).get("name", "whole-page")))

    checked: list[str] | None = None
    for index, section in enumerate(sections, start=1):
        name = str(section["name"])
        logger.info("Section %s", name)
        frame = section["frame"]
        # Save & Continue leaves the profile. Check the typed values first,
        # while those controls are still on the page.
        if checked is None and _section_leaves_profile(section):
            checked = verify_steps(page, sections[:index])
        start = str(frame.get("start") or frame.get("selector") or "")
        if not start or page.locator(start).count() > 0:
            zoom = move_camera(page, form, frame, pan_ms)
            logger.info("Framed %s at zoom %.2f", name, zoom)
            if settle_ms:
                page.wait_for_timeout(settle_ms)
            for edge in (frame.get("start"), frame.get("end"), frame.get("selector")):
                if edge and not element_in_view(page, str(edge)):
                    message = f"{name}: {edge} is outside the viewport"
                    logger.warning(message)
                    offscreen.append(message)
        else:
            logger.info("Holding the current frame until %s is on screen", name)
        for step in section["steps"]:
            logger.info("  %s %s", step["action"], step.get("text", step.get("selector", "")))
            run_step(page, step, char_delay, pause_ms)
            # A reload or a new page drops the camera transform.
            # A detached wait stays on the current page, so the frame stays put.
            if step["action"] == "wait" and step.get("until") != "detached":
                zoom = move_camera(page, form, frame, pan_ms)
                logger.info("Reframed %s at zoom %.2f", name, zoom)
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
        shot(page, frames_dir, index, name)
    if checked is None:
        checked = verify_steps(page, sections)
    return offscreen + checked


def select_or_create_client(page: Page, client_name: str) -> str:
    """Select an existing client, or click Add New when the name is absent."""
    selector = "select[name='client.id']"
    if page.locator(selector).count() == 0:
        logger.warning("Client dropdown %s not found on page.", selector)
        return ""
    options: list[dict[str, str]] = page.evaluate(
        """(selector) => {
            const select = document.querySelector(selector);
            if (!select) return [];
            return Array.from(select.options).map(o => ({ value: o.value, text: o.text.trim() }));
        }""",
        selector,
    )
    normalized_target = client_name.lower().strip()
    matched = next(
        (
            opt
            for opt in options
            if opt["text"].lower().strip() == normalized_target
            or normalized_target in opt["text"].lower().strip()
        ),
        None,
    )
    if matched:
        logger.info("Selecting existing client %s", matched["text"])
        page.select_option(selector, value=matched["value"])
        if page.locator("input[name='selectClient'], input[value='Select']").count() > 0:
            page.click("input[name='selectClient'], input[value='Select']")
            page.wait_for_load_state("networkidle")
        return str(matched["value"])
    logger.info("Client %s not found. Clicking Add New.", client_name)
    if page.locator("input[name='add_new'], input[value='+ Add New']").count() > 0:
        page.click("input[name='add_new'], input[value='+ Add New']")
        page.wait_for_load_state("networkidle")
    return "new"


def open_live_page(
    page: Page,
    inputs: dict[str, Any],
    *,
    url: str,
    username: str,
    password: str,
    client_name: str,
) -> None:
    """Log in and select the scenario client without submitting the profile."""
    logger.info("Opening %s", url)
    page.goto(url, wait_until="domcontentloaded")
    login = page.locator("form#login")
    if login.count() > 0:
        if not password:
            raise RuntimeError(
                f"Login page {page.url} has a password field and no password was provided. "
                "Sign in to 1Password or pass --password."
            )
        logger.info("Logging in as %s", username)
        # The header also has a Login submit that posts to action="login".
        # Only the #login form reaches j_spring_security_check.
        login.locator("input[name='username']").fill(username)
        login.locator("input[name='password']").fill(password)
        with page.expect_navigation(wait_until="domcontentloaded"):
            login.locator("input[type='submit']").click()
        if page.locator("form#login").count() > 0:
            raise RuntimeError(
                f"Login as {username} did not leave {page.url}. "
                "The account rejected the password from 1Password."
            )
    if page.locator("select[name='client.id']").count() == 0:
        profile_url = urljoin(page.url, "clientProfile.html")
        logger.info("Client picker is not on %s. Opening %s", page.url, profile_url)
        page.goto(profile_url, wait_until="domcontentloaded")
    chosen = client_name or f"{inputs['client']['first_name']} {inputs['client']['last_name']}"
    select_or_create_client(page, chosen)
    try:
        page.locator("input[name='client.firstName']").first.wait_for(state="visible")
    except PlaywrightError as exc:
        raise RuntimeError(
            f"Profile form did not open. The page is still {page.url}."
        ) from exc


def record_initiative_demo(
    initiative_dir: Path,
    scenario: str,
    *,
    form_path: Path | None = None,
    fixture: Path | None = None,
    out_dir: Path | None = None,
    url: str = "https://roadmappartners.net/roadmap/login.html",
    username: str = "appdev",
    password: str = "",
    password_op: str = "op://Private/Roadmappartners/password",
    client_name: str = "",
    headed: bool = False,
    char_delay: int | None = None,
    pause_ms: int | None = None,
    pan_ms: int | None = None,
) -> Path:
    """Record one scenario. Returns the directory that holds demo.webm."""
    form = load_yaml(form_path or (initiative_dir / "demo-form.yaml"))
    scenario_dir = initiative_dir / "scenarios" / scenario
    inputs = load_yaml(scenario_dir / "inputs.yaml")
    sections = resolve_steps(form, inputs)
    destination = out_dir or (scenario_dir / "demo")
    destination.mkdir(parents=True, exist_ok=True)
    video_tmp = destination / "_video"
    if video_tmp.exists():
        shutil.rmtree(video_tmp)
    video_tmp.mkdir()

    typed_delay = char_delay if char_delay is not None else int(form.get("char_delay_ms", 50))
    typed_pause = pause_ms if pause_ms is not None else int(form.get("pause_between_fields_ms", 500))
    typed_pan = pan_ms if pan_ms is not None else int(form.get("pan_ms", 700))
    viewport = form.get("viewport", {})
    width = int(viewport.get("width", 1920))
    height = int(viewport.get("height", 1080))
    secret = password
    if fixture is None and not secret:
        fetched = get_op_secret(password_op)
        if not fetched:
            raise RuntimeError(
                f"Could not read {password_op}. "
                "The Linux 1Password CLI has no session, and the desktop fallback did not return a value. "
                "Run `op signin`, unlock 1Password, or pass --password."
            )
        secret = fetched

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        if fixture:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=str(video_tmp),
                record_video_size={"width": width, "height": height},
            )
            if form.get("hide_client_picker", True):
                context.add_init_script(_INSTALL_JS)
            page = context.new_page()
            started = time.perf_counter()
            page.goto(fixture.resolve().as_uri(), wait_until="domcontentloaded")
            lead_s = time.perf_counter() - started
        else:
            setup = browser.new_context(viewport={"width": width, "height": height})
            setup_page = setup.new_page()
            open_live_page(
                setup_page,
                inputs,
                url=url,
                username=username,
                password=secret,
                client_name=client_name,
            )
            storage = setup.storage_state()
            profile_url = setup_page.url
            setup.close()

            context = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=str(video_tmp),
                record_video_size={"width": width, "height": height},
                storage_state=storage,
            )
            if form.get("hide_client_picker", True):
                context.add_init_script(_INSTALL_JS)
            page = context.new_page()
            started = time.perf_counter()
            logger.info("Recording from %s", profile_url)
            page.goto(profile_url, wait_until="domcontentloaded")
            page.locator("input[name='client.firstName']").first.wait_for(state="visible")
            lead_s = time.perf_counter() - started

        video = page.video
        problems: list[str] = []
        try:
            problems = record(
                page,
                form,
                sections,
                destination,
                char_delay=typed_delay,
                pause_ms=typed_pause,
                pan_ms=typed_pan,
            )
        finally:
            context.close()
            browser.close()
        if video is None:
            raise RuntimeError("Playwright did not attach a video to the page")
        webm = destination / "demo.webm"
        if webm.exists():
            webm.unlink()
        shutil.move(str(video.path()), webm)
    shutil.rmtree(video_tmp, ignore_errors=True)
    transcode(webm, destination / "demo.mp4", lead_s)
    if problems:
        for problem in problems:
            logger.error("%s", problem)
        raise RuntimeError(f"{len(problems)} demo check(s) failed")
    logger.info("Demo written to %s", destination)
    return destination
