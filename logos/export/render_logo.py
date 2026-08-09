#!/usr/bin/env python3
"""Render InsurIntellect logo.svg (nested rounded rects) to standard PNG sizes."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

NS = {"svg": "http://www.w3.org/2000/svg"}
SIZES = (16, 32, 48, 192, 512, 1024, 2048)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def parse_length(raw: str | None, default: float = 0.0) -> float:
    if raw is None:
        return default
    return float(re.sub(r"[a-zA-Z%]+$", "", raw.strip()))


def collect_rects(root: ET.Element) -> list[dict]:
    rects: list[dict] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag != "rect":
            continue
        fill = el.get("fill")
        if not fill or fill == "none" or fill.startswith("url("):
            continue
        rects.append(
            {
                "x": parse_length(el.get("x")),
                "y": parse_length(el.get("y")),
                "w": parse_length(el.get("width"), 1.0),
                "h": parse_length(el.get("height"), 1.0),
                "rx": parse_length(el.get("rx")),
                "fill": fill,
            }
        )
    return rects


def render(svg_path: Path, out_path: Path, size: int) -> None:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = (root.get("viewBox") or "0 0 512 512").split()
    vw, vh = float(vb[2]), float(vb[3])
    scale = size / max(vw, vh)

    # Transparent canvas; draw every rect including the dark plate.
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for rect in collect_rects(root):
        x0 = rect["x"] * scale
        y0 = rect["y"] * scale
        x1 = (rect["x"] + rect["w"]) * scale
        y1 = (rect["y"] + rect["h"]) * scale
        rx = rect["rx"] * scale
        color = (*hex_to_rgb(rect["fill"]), 255)
        if rx > 0:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=rx, fill=color)
        else:
            draw.rectangle([x0, y0, x1, y1], fill=color)

    # Keep transparent background (RGBA) so the logo sits directly on any backdrop.
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
