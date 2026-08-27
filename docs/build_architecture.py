#!/usr/bin/env python3
"""아키텍처 다이어그램 생성기 — docs/architecture.png 와 docs/architecture.svg 를 만든다.

    python3 docs/build_architecture.py

레이아웃을 아래 `BOXES` / `ARROWS` 한 곳에 정의하고 PNG 와 SVG 를 같이 뽑는다.
둘이 어긋날 수 없게 하려는 것이다. SVG 는 벡터라 Figma·Inkscape 로 열어 손볼 수 있고,
PNG 는 제출용이다.

PNG 를 만들려면 Pillow 가 필요하다(`pip install pillow`). 없으면 SVG 만 만든다.
라벨을 영문으로 둔 이유는 한글 글꼴이 없는 환경에서도 같은 그림이 나오게 하기 위해서다.
"""

from __future__ import annotations

import os
import sys

W, H = 1240, 940

# 색 (AWS 다이어그램 관례에 가깝게, 흑백 인쇄에서도 구분되도록 명도 차를 뒀다)
INK = (33, 37, 41)
MUTED = (108, 117, 125)
REGION = (0, 122, 158)
VPC = (36, 108, 190)
SUBNET = (26, 141, 96)
SG = (196, 88, 24)
NODE = (60, 64, 72)
BG = (255, 255, 255)
FILL_SUBNET = (238, 248, 243)
FILL_SG = (253, 244, 236)
FILL_NODE = (245, 246, 248)

#: (x, y, w, h, 제목, [본문 줄], 테두리색, 채움색, 점선 여부)
BOXES = [
    (455, 62, 330, 62, "Internet / Client", ["browser or curl"], NODE, FILL_NODE, False),
    (70, 62, 300, 62, "Admin laptop", ["source IP: <my IP>/32"], NODE, FILL_NODE, False),
    (60, 170, 1120, 680, "AWS Cloud  \u2014  ap-northeast-2 (Seoul)", [], REGION, None, True),
    (500, 206, 240, 58, "Internet Gateway", [], REGION, FILL_NODE, False),
    (100, 300, 1040, 520, "VPC   10.0.0.0/16", [], VPC, None, False),
    (150, 372, 920, 412, "Public Subnet   10.0.1.0/24   (ap-northeast-2a)",
     ["map-public-ip-on-launch: true"], SUBNET, FILL_SUBNET, False),
    (180, 452, 330, 104, "Route Table",
     ["0.0.0.0/0      \u2192  Internet Gateway", "10.0.0.0/16   \u2192  local"], SUBNET, BG, False),
    (560, 452, 480, 300, "Security Group   (inbound)",
     ["tcp 80  \u2190  0.0.0.0/0",
      "tcp 22  \u2190  <my IP>/32",
      "no all-ports rule"], SG, FILL_SG, False),
    (592, 574, 420, 156, "EC2   t3.micro   (public IP)",
     ["nginx :80   \u2014   Amazon Linux 2023",
      "GET /             \u2192  index.html",
      'GET /health   \u2192  200  "OK"',
      "root EBS gp3 8 GiB (DeleteOnTermination)"], NODE, BG, False),
]

#: 폴리라인 화살표 — (점 목록, 라벨, (라벨 x, 라벨 y), 정렬, 점선 여부)
#: 화살촉은 마지막 구간에만 붙는다. 중간에 머리가 생기면 흐름이 끊겨 보인다.
ARROWS = [
    ([(620, 124), (620, 204)], "HTTP  :80", (634, 150), "left", False),
    ([(620, 264), (620, 410), (900, 410), (900, 572)], "", None, "left", False),
    ([(220, 124), (220, 148), (118, 148), (118, 648), (590, 648)],
     "SSH  :22   (source-restricted)", (360, 636), "center", True),
    ([(1012, 652), (1105, 652), (1105, 235), (742, 235)], "outbound", (1092, 470), "right", True),
]

CAPTION = [
    "External request:  Internet  \u2192  Internet Gateway  \u2192  Public Subnet (route 0.0.0.0/0)  \u2192  Security Group  \u2192  EC2 nginx :80",
    "Outbound (dashed):  EC2  \u2192  route 0.0.0.0/0  \u2192  Internet Gateway  \u2192  Internet     |     SSH is allowed only from the admin IP.",
]

TITLE = "codyssey B6-1  \u2014  VPC / EC2 web service"


# ─────────────────────────────────────────────────────────────────────────────
# SVG
# ─────────────────────────────────────────────────────────────────────────────
def rgb(color) -> str:
    return "#%02x%02x%02x" % color


def build_svg() -> str:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="{rgb(BG)}"/>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{rgb(MUTED)}"/></marker></defs>',
        f'<text x="{W // 2}" y="40" text-anchor="middle" font-size="24" '
        f'font-weight="bold" fill="{rgb(INK)}">{TITLE}</text>',
    ]

    for x, y, w, h, title, lines, border, fill, dashed in BOXES:
        dash = ' stroke-dasharray="9 6"' if dashed else ""
        fill_attr = rgb(fill) if fill else "none"
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
            f'fill="{fill_attr}" stroke="{rgb(border)}" stroke-width="2"{dash}/>'
        )
        out.append(
            f'<text x="{x + 16}" y="{y + 26}" font-size="15" font-weight="bold" '
            f'fill="{rgb(border)}">{escape(title)}</text>'
        )
        for i, line in enumerate(lines):
            out.append(
                f'<text x="{x + 16}" y="{y + 50 + i * 22}" font-size="13" '
                f'fill="{rgb(INK)}">{escape(line)}</text>'
            )

    for points, label, label_at, align, dashed in ARROWS:
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        path = " ".join(f"{x},{y}" for x, y in points)
        out.append(
            f'<polyline points="{path}" fill="none" stroke="{rgb(MUTED)}" '
            f'stroke-width="2"{dash} marker-end="url(#arrow)"/>'
        )
        if label and label_at:
            lx, ly = label_at
            anchor = {"left": "start", "right": "end", "center": "middle"}[align]
            out.append(
                f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="13" '
                f'fill="{rgb(MUTED)}">{escape(label)}</text>'
            )

    for i, line in enumerate(CAPTION):
        out.append(
            f'<text x="{W // 2}" y="{H - 46 + i * 22}" text-anchor="middle" font-size="13" '
            f'fill="{rgb(MUTED)}">{escape(line)}</text>'
        )

    out.append("</svg>")
    return "\n".join(out)


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─────────────────────────────────────────────────────────────────────────────
# PNG (Pillow)
# ─────────────────────────────────────────────────────────────────────────────
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def find_fonts():
    """(일반, 굵게) TrueType 경로. 못 찾으면 (None, None)."""
    try:  # matplotlib 이 DejaVu 를 번들로 갖고 있다
        import matplotlib

        base = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        regular = os.path.join(base, "DejaVuSans.ttf")
        bold = os.path.join(base, "DejaVuSans-Bold.ttf")
        if os.path.exists(regular):
            return regular, bold if os.path.exists(bold) else regular
    except ImportError:
        pass
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            return path, bold if os.path.exists(bold) else path
    return None, None


def build_png(path: str, scale: int = 2) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[SKIP] Pillow 가 없어 PNG 를 만들지 못했습니다. pip install pillow", file=sys.stderr)
        return False

    regular_path, bold_path = find_fonts()

    def font(size, bold=False):
        target = bold_path if bold else regular_path
        if target:
            return ImageFont.truetype(target, size * scale)
        return ImageFont.load_default()

    image = Image.new("RGB", (W * scale, H * scale), BG)
    draw = ImageDraw.Draw(image)
    s = scale

    draw.text((W * s // 2, 26 * s), TITLE, font=font(22, True), fill=INK, anchor="mm")

    for x, y, w, h, title, lines, border, fill, dashed in BOXES:
        box = (x * s, y * s, (x + w) * s, (y + h) * s)
        if fill:
            draw.rounded_rectangle(box, radius=10 * s, fill=fill)
        if dashed:
            dashed_rect(draw, box, border, 2 * s, 9 * s, 6 * s)
        else:
            draw.rounded_rectangle(box, radius=10 * s, outline=border, width=2 * s)
        draw.text(((x + 16) * s, (y + 18) * s), title, font=font(14, True), fill=border, anchor="lm")
        for i, line in enumerate(lines):
            draw.text(((x + 16) * s, (y + 44 + i * 22) * s), line, font=font(12), fill=INK, anchor="lm")

    for points, label, label_at, align, dashed in ARROWS:
        scaled = [(x * s, y * s) for x, y in points]
        polyline_arrow(draw, scaled, MUTED, 2 * s, dashed, s)
        if label and label_at:
            lx, ly = label_at
            anchor = {"left": "lm", "right": "rm", "center": "mm"}[align]
            draw.text((lx * s, ly * s), label, font=font(12), fill=MUTED, anchor=anchor)

    for i, line in enumerate(CAPTION):
        draw.text((W * s // 2, (H - 52 + i * 22) * s), line, font=font(12), fill=MUTED, anchor="mm")

    image.save(path, "PNG")
    return True


def dashed_rect(draw, box, color, width, dash, gap):
    x0, y0, x1, y1 = box
    for start, end, horizontal in (
        ((x0, y0), (x1, y0), True), ((x0, y1), (x1, y1), True),
        ((x0, y0), (x0, y1), False), ((x1, y0), (x1, y1), False),
    ):
        dashed_line(draw, start, end, color, width, dash, gap, horizontal)


def dashed_line(draw, start, end, color, width, dash, gap, horizontal):
    pos = start[0] if horizontal else start[1]
    limit = end[0] if horizontal else end[1]
    while pos < limit:
        stop = min(pos + dash, limit)
        if horizontal:
            draw.line([(pos, start[1]), (stop, start[1])], fill=color, width=width)
        else:
            draw.line([(start[0], pos), (start[0], stop)], fill=color, width=width)
        pos = stop + gap


def polyline_arrow(draw, points, color, width, dashed, scale):
    """꺾인 화살표. 화살촉은 마지막 구간에만 붙인다."""
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if dashed:
            horizontal = start[1] == end[1]
            a, b = (start, end) if (start[0] <= end[0] and start[1] <= end[1]) else (end, start)
            dashed_line(draw, a, b, color, width, 7 * scale, 5 * scale, horizontal)
        else:
            draw.line([start, end], fill=color, width=width)

    head = 7 * scale
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if x1 == x2:
        direction = 1 if y2 > y1 else -1
        draw.polygon(
            [(x2, y2), (x2 - head, y2 - head * direction), (x2 + head, y2 - head * direction)],
            fill=color,
        )
    else:
        direction = 1 if x2 > x1 else -1
        draw.polygon(
            [(x2, y2), (x2 - head * direction, y2 - head), (x2 - head * direction, y2 + head)],
            fill=color,
        )


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(here, "architecture.svg")
    png_path = os.path.join(here, "architecture.png")

    with open(svg_path, "w", encoding="utf-8") as fp:
        fp.write(build_svg())
    print(f"[ OK ] {svg_path}")

    if build_png(png_path):
        print(f"[ OK ] {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
