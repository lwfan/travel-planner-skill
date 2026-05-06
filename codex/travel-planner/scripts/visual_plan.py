#!/usr/bin/env python3
"""Build a visual travel-plan HTML page from structured JSON."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def escape(value: Any) -> str:
    return html.escape(text(value), quote=True)


def image_src(image: Any) -> str:
    if isinstance(image, str):
        return image
    if isinstance(image, dict):
        return text(image.get("src"))
    return ""


def image_credit(image: Any) -> str:
    if isinstance(image, dict):
        parts = [text(image.get("caption")).strip(), text(image.get("credit")).strip()]
        return " · ".join(part for part in parts if part)
    return ""


def image_credit_html(image: Any) -> str:
    credit = image_credit(image)
    if not credit:
        return ""
    if isinstance(image, dict):
        source_url = text(image.get("source_url") or image.get("url")).strip()
        if source_url:
            return f'<a href="{escape(source_url)}">{escape(credit)}</a>'
    return escape(credit)


def render_meta(items: list[Any]) -> str:
    blocks = []
    for item in items:
        if isinstance(item, dict):
            label = escape(item.get("label"))
            value = escape(item.get("value"))
        else:
            label = ""
            value = escape(item)
        blocks.append(
            f'<div class="meta-card"><span>{label}</span><strong>{value}</strong></div>'
        )
    return "\n".join(blocks)


def render_route(route: list[Any]) -> str:
    if not route:
        return ""
    stops = "\n".join(f'<li>{escape(stop)}</li>' for stop in route)
    return f"""
    <section class="route">
      <h2>Route</h2>
      <ol>{stops}</ol>
    </section>
    """


def render_day(day: dict[str, Any], index: int) -> str:
    image = day.get("image") or day.get("photo")
    src = image_src(image)
    credit = image_credit_html(image)
    image_html = ""
    if src:
        image_html = f"""
        <figure>
          <img src="{escape(src)}" alt="{escape(day.get('area') or day.get('title') or day.get('day') or 'Travel day')}" loading="lazy">
          {f'<figcaption>{credit}</figcaption>' if credit else ''}
        </figure>
        """

    slots = []
    for key, label in (
        ("morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("evening", "Evening"),
    ):
        value = text(day.get(key)).strip()
        if value:
            slots.append(
                f'<div class="slot"><span>{label}</span><p>{escape(value)}</p></div>'
            )

    notes = []
    for key in ("transport", "food", "backup", "note"):
        value = text(day.get(key)).strip()
        if value:
            notes.append(f"<li>{escape(value)}</li>")
    for item in as_list(day.get("notes")):
        if text(item).strip():
            notes.append(f"<li>{escape(item)}</li>")
    notes_html = f'<ul class="notes">{"".join(notes)}</ul>' if notes else ""

    day_label = escape(day.get("day") or f"Day {index}")
    area = escape(day.get("area") or day.get("title") or "")
    date = escape(day.get("date") or "")

    return f"""
    <article class="day-card">
      {image_html}
      <div class="day-body">
        <div class="day-kicker">{day_label}{f' · {date}' if date else ''}</div>
        <h3>{area}</h3>
        <div class="slots">{"".join(slots)}</div>
        {notes_html}
      </div>
    </article>
    """


def render_budget(items: list[Any]) -> str:
    if not items:
        return ""
    blocks = []
    for item in items:
        if isinstance(item, dict):
            label = escape(item.get("label"))
            value = escape(item.get("value"))
        else:
            label = "Budget"
            value = escape(item)
        blocks.append(f"<li><span>{label}</span><strong>{value}</strong></li>")
    return f"""
    <section class="budget">
      <h2>Budget</h2>
      <ul>{"".join(blocks)}</ul>
    </section>
    """


def render_checklist(items: list[Any]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"""
    <section class="checklist">
      <h2>Checklist</h2>
      <ul>{rows}</ul>
    </section>
    """


def render_sources(items: list[Any]) -> str:
    if not items:
        return ""
    links = []
    for item in items:
        if isinstance(item, dict):
            title = escape(item.get("title") or item.get("url"))
            url = escape(item.get("url"))
            links.append(f'<li><a href="{url}">{title}</a></li>' if url else f"<li>{title}</li>")
        else:
            links.append(f"<li>{escape(item)}</li>")
    return f"""
    <footer>
      <h2>Sources</h2>
      <ul>{"".join(links)}</ul>
    </footer>
    """


def build_html(data: dict[str, Any]) -> str:
    title = escape(data.get("title") or "Travel Plan")
    subtitle = escape(data.get("subtitle") or "")
    hero = data.get("hero_image") or data.get("hero")
    hero_src = image_src(hero)
    hero_credit = image_credit_html(hero)
    hero_style = (
        f' style="background-image: linear-gradient(90deg, rgba(17, 24, 39, .78), rgba(17, 24, 39, .2)), url(\'{escape(hero_src)}\')"'
        if hero_src
        else ""
    )
    meta = render_meta(as_list(data.get("meta")))
    days = "\n".join(
        render_day(day, index)
        for index, day in enumerate(as_list(data.get("days")), start=1)
        if isinstance(day, dict)
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9e2df;
      --paper: #f7f4ee;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-2: #b45309;
      --deep: #102a43;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    .page {{
      width: min(1180px, 100%);
      margin: 0 auto;
      background: var(--paper);
    }}
    .hero {{
      min-height: 440px;
      display: flex;
      align-items: flex-end;
      padding: 56px;
      color: white;
      background: linear-gradient(135deg, #102a43, #0f766e);
      background-size: cover;
      background-position: center;
    }}
    .hero h1 {{
      max-width: 820px;
      margin: 0;
      font-size: clamp(44px, 7vw, 84px);
      line-height: .98;
      letter-spacing: 0;
    }}
    .hero p {{
      max-width: 760px;
      margin: 18px 0 0;
      font-size: 22px;
      line-height: 1.45;
    }}
    .hero .credit {{
      margin-top: 22px;
      font-size: 12px;
      opacity: .78;
    }}
    .content {{ padding: 34px; }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 26px;
    }}
    .meta-card {{
      min-height: 92px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .meta-card span, .slot span, .budget li span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .meta-card strong {{
      display: block;
      margin-top: 10px;
      font-size: 22px;
      line-height: 1.15;
    }}
    section h2 {{
      margin: 0 0 14px;
      font-size: 22px;
      letter-spacing: 0;
    }}
    .route, .budget, .checklist, footer {{
      margin: 26px 0;
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, .72);
    }}
    .route ol {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0;
      margin: 0;
      list-style: none;
    }}
    .route li {{
      padding: 10px 14px;
      border-radius: 999px;
      background: #e5f3ef;
      color: var(--deep);
      font-weight: 700;
    }}
    .days {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
      gap: 18px;
      align-items: stretch;
    }}
    .day-card {{
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    figure {{ margin: 0; position: relative; }}
    figure img {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      background: #d7dedb;
    }}
    figcaption {{
      position: absolute;
      left: 10px;
      bottom: 8px;
      max-width: calc(100% - 20px);
      padding: 5px 8px;
      border-radius: 6px;
      color: white;
      background: rgba(0, 0, 0, .48);
      font-size: 11px;
    }}
    .day-body {{ padding: 20px; }}
    .day-kicker {{
      color: var(--accent-2);
      font-weight: 800;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .day-card h3 {{
      margin: 8px 0 16px;
      font-size: 26px;
      line-height: 1.12;
      letter-spacing: 0;
    }}
    .slots {{
      display: grid;
      gap: 12px;
    }}
    .slot {{
      padding-left: 12px;
      border-left: 3px solid var(--accent);
    }}
    .slot p {{
      margin: 4px 0 0;
      line-height: 1.5;
    }}
    .notes {{
      margin: 16px 0 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .budget ul, .checklist ul, footer ul {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .budget ul {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .budget li, .checklist li {{
      padding: 14px;
      border-radius: 8px;
      background: white;
      border: 1px solid var(--line);
    }}
    .budget strong {{
      display: block;
      margin-top: 8px;
      font-size: 18px;
      line-height: 1.25;
    }}
    footer {{
      color: var(--muted);
      font-size: 12px;
    }}
    footer a {{ color: var(--accent); }}
    figcaption a, .hero .credit a {{ color: inherit; }}
    @media (max-width: 720px) {{
      .hero {{ min-height: 360px; padding: 30px; }}
      .hero p {{ font-size: 18px; }}
      .content {{ padding: 18px; }}
      .days {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero"{hero_style}>
      <div>
        <h1>{title}</h1>
        {f'<p>{subtitle}</p>' if subtitle else ''}
        {f'<div class="credit">{hero_credit}</div>' if hero_credit else ''}
      </div>
    </header>
    <div class="content">
      {f'<section class="meta-grid">{meta}</section>' if meta else ''}
      {render_route(as_list(data.get("route")))}
      <section class="days">{days}</section>
      {render_budget(as_list(data.get("budget")))}
      {render_checklist(as_list(data.get("checklist")))}
      {render_sources(as_list(data.get("sources")))}
    </div>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a visual travel-plan HTML page from JSON."
    )
    parser.add_argument("spec", help="Path to a travel-plan JSON spec.")
    parser.add_argument(
        "--output",
        "-o",
        default="travel-plan.html",
        help="Output HTML path. Defaults to travel-plan.html.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    output_path = Path(args.output)
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Top-level JSON value must be an object.")
    output_path.write_text(build_html(data), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
