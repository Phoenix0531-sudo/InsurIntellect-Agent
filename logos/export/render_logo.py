#!/usr/bin/env python3
"""Render InsurIntellect logo.svg to standard PNG sizes (RGBA, transparent)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

SIZES = (16, 32, 48, 192, 512, 1024, 2048)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def parse_length(raw: str | None, default: float = 0.0) -> float:
    if raw is None:
        return default
    return float(re.sub(r"[a-zA-Z%]+$", "", raw.strip()))


def parse_opacity(raw: str | None) -> float:
    if raw is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 1.0


def _alpha(opacity: float) -> int:
    return int(round(255 * opacity))


def _resolve_color(fill: str | None, opacity: float) -> tuple[int, int, int, int]:
    """fill may be None / 'none' / hex. Returns RGBA."""
    a = _alpha(opacity)
    if not fill or fill == "none":
        return (0, 0, 0, 0)
    return (*hex_to_rgb(fill), a)


def collect_shapes(root: ET.Element) -> list[dict]:
    """Flatten SVG into ordered draw ops: rect / circle / line, honoring opacity + stroke."""
    shapes: list[dict] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        op = el.get("fill")
        stroke = el.get("stroke")
        stroke_w = parse_length(el.get("stroke-width"), 0.0)
        opacity = parse_opacity(el.get("opacity"))

        if tag == "rect":
            x = parse_length(el.get("x"))
            y = parse_length(el.get("y"))
            w = parse_length(el.get("width"), 1.0)
            h = parse_length(el.get("height"), 1.0)
            rx = parse_length(el.get("rx"))
            shapes.append(
                {
                    "kind": "rect",
                    "x": x, "y": y, "w": w, "h": h, "rx": rx,
                    "fill": op, "fill_opacity": opacity,
                    "stroke": stroke, "stroke_w": stroke_w,
                }
            )
        elif tag == "circle":
            shapes.append(
                {
                    "kind": "circle",
                    "cx": parse_length(el.get("cx")),
                    "cy": parse_length(el.get("cy")),
                    "r": parse_length(el.get("r"), 0.0),
                    "fill": op, "fill_opacity": opacity,
                    "stroke": stroke, "stroke_w": stroke_w,
                }
            )
        elif tag == "line":
            shapes.append(
                {
                    "kind": "line",
                    "x1": parse_length(el.get("x1")),
                    "y1": parse_length(el.get("y1")),
                    "x2": parse_length(el.get("x2")),
                    "y2": parse_length(el.get("y2")),
                    "stroke": stroke if stroke else op,  # line uses stroke (fallback to fill attr as color)
                    "stroke_w": stroke_w if stroke_w > 0 else 1.0,
                    "stroke_opacity": opacity,
                }
            )
    return shapes


def render(svg_path: Path, out_path: Path, size: int) -> None:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = (root.get("viewBox") or "0 0 512 512").split()
    vw, vh = float(vb[2]), float(vb[3])
    scale = size / max(vw, vh)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for s in collect_shapes(root):
        if s["kind"] == "rect":
            x0 = s["x"] * scale
            y0 = s["y"] * scale
            x1 = (s["x"] + s["w"]) * scale
            y1 = (s["y"] + s["h"]) * scale
            rx = s["rx"] * scale
            fill_rgba = _resolve_color(s["fill"], s["fill_opacity"])
            stroke_rgba = _resolve_color(s["stroke"], s["fill_opacity"])
            sw = s["stroke_w"] * scale
            # PIL rounded_rectangle supports width & outline since Pillow 8.0
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=max(0, int(round(rx))) if rx > 0 else 0,
                fill=fill_rgba if fill_rgba[3] > 0 else None,
                outline=stroke_rgba if (stroke_rgba[3] > 0 and sw > 0) else None,
                width=int(round(sw)) if sw > 0 else 1,
            )
        elif s["kind"] == "circle":
            cx = s["cx"] * scale
            cy = s["cy"] * scale
            r = s["r"] * scale
            fill_rgba = _resolve_color(s["fill"], s["fill_opacity"])
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=fill_rgba if fill_rgba[3] > 0 else None,
            )
        elif s["kind"] == "line":
            x1 = s["x1"] * scale
            y1 = s["y1"] * scale
            x2 = s["x2"] * scale
            y2 = s["y2"] * scale
            stroke_rgba = _resolve_color(s["stroke"], s["stroke_opacity"])
            sw = max(1.0, s["stroke_w"] * scale)
            draw.line(
                [(x1, y1), (x2, y2)],
                fill=stroke_rgba,
                width=int(round(sw)),
            )

    img.save(out_path, format="PNG", optimize=True)


def main() -> None:
    here = Path(__file__).resolve().parent
    svg_path = here / "logo.svg"
    for size in SIZES:
        out = here / f"logo-{size}.png"
        render(svg_path, out, size)
        print(f"exported {out.name} ({size}x{size}, {out.stat().st_size} bytes)")
    print(f"done → {here}")


if __name__ == "__main__":
    main()
