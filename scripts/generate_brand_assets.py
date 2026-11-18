from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "assets" / "brand"
BRAND_DIR.mkdir(parents=True, exist_ok=True)

MASTER_ICON: Image.Image | None = None

COLORS = {
    "primary": "#22D3EE",
    "secondary": "#3B82F6",
    "accent": "#8B5CF6",
    "background": "#07111F",
    "surface": "#111C30",
    "text": "#F8FAFC",
    "muted": "#9DB6C8",
}


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded_gradient(size: int) -> Image.Image:
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = bg.load()
    c0 = hex_rgb("#071525")
    c1 = hex_rgb("#0A2940")
    for y in range(size):
        for x in range(size):
            t = min(1.0, max(0.0, (x + y) / (2 * size)))
            c = lerp(c0, c1, t)
            px[x, y] = (*c, 255)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=round(size * 0.22), fill=255
    )
    bg.putalpha(mask)
    return bg


def draw_mark(size: int, transparent: bool = False, safe_zone: float = 0.10) -> Image.Image:
    scale = 3
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    if not transparent:
        image.alpha_composite(rounded_gradient(canvas_size))
    draw = ImageDraw.Draw(image, "RGBA")
    pad = canvas_size * safe_zone
    left, top, right, bottom = pad, pad, canvas_size - pad, canvas_size - pad
    if transparent:
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=canvas_size * 0.19,
            fill=(*hex_rgb(COLORS["background"]), 255),
            outline=(*hex_rgb(COLORS["primary"]), 230),
            width=max(3, round(canvas_size * 0.018)),
        )
    else:
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=canvas_size * 0.19,
            outline=(*hex_rgb(COLORS["primary"]), 170),
            width=max(3, round(canvas_size * 0.014)),
        )

    cx = canvas_size / 2
    top_y = canvas_size * 0.20
    bottom_y = canvas_size * 0.80
    amplitude = canvas_size * 0.17
    samples = 160
    points_a: list[tuple[float, float]] = []
    points_b: list[tuple[float, float]] = []
    for i in range(samples):
        t = i / (samples - 1)
        y = top_y + (bottom_y - top_y) * t
        x = cx + amplitude * math.sin(t * math.pi * 2.18)
        points_a.append((x, y))
        points_b.append((2 * cx - x, y))

    line_width = max(8, round(canvas_size * 0.045))
    secondary = hex_rgb(COLORS["secondary"])
    primary = hex_rgb(COLORS["primary"])
    accent = hex_rgb(COLORS["accent"])

    # subtle glow
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow, "RGBA")
    glow_draw.line(points_a, fill=(*primary, 65), width=line_width * 2, joint="curve")
    glow_draw.line(points_b, fill=(*accent, 65), width=line_width * 2, joint="curve")
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image, "RGBA")

    # color segmented curves for a crisp identity
    for points, c_start, c_end in ((points_a, secondary, primary), (points_b, accent, secondary)):
        for i in range(len(points) - 1):
            t = i / (len(points) - 2)
            color = lerp(c_start, c_end, t)
            draw.line(
                (points[i], points[i + 1]), fill=(*color, 255), width=line_width, joint="curve"
            )

    rung_indices = [18, 43, 68, 92, 117, 142]
    rung_width = max(3, round(canvas_size * 0.012))
    for idx in rung_indices:
        p1, p2 = points_a[idx], points_b[idx]
        draw.line((p1, p2), fill=(*hex_rgb(COLORS["text"]), 175), width=rung_width)
        radius = canvas_size * 0.018
        draw.ellipse(
            (p1[0] - radius, p1[1] - radius, p1[0] + radius, p1[1] + radius), fill=(*secondary, 255)
        )
        draw.ellipse(
            (p2[0] - radius, p2[1] - radius, p2[0] + radius, p2[1] + radius), fill=(*accent, 255)
        )

    # intelligence node at the center, intentionally symbol-only for small-size clarity
    node_r = canvas_size * 0.055
    draw.ellipse(
        (cx - node_r, canvas_size * 0.5 - node_r, cx + node_r, canvas_size * 0.5 + node_r),
        fill=(*hex_rgb(COLORS["surface"]), 248),
        outline=(*secondary, 245),
        width=max(3, round(canvas_size * 0.012)),
    )
    for angle in (0, math.pi * 2 / 3, math.pi * 4 / 3):
        x2 = cx + math.cos(angle) * canvas_size * 0.095
        y2 = canvas_size * 0.5 + math.sin(angle) * canvas_size * 0.095
        draw.line(
            (cx, canvas_size * 0.5, x2, y2),
            fill=(*secondary, 180),
            width=max(2, round(canvas_size * 0.008)),
        )
        rr = canvas_size * 0.015
        draw.ellipse((x2 - rr, y2 - rr, x2 + rr, y2 + rr), fill=(*accent, 255))

    return image.resize((size, size), Image.Resampling.LANCZOS)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    choices = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in choices:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_splash(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), hex_rgb(COLORS["background"]))
    draw = ImageDraw.Draw(image, "RGBA")
    # restrained scientific grid
    step = max(40, round(min(width, height) * 0.06))
    for x in range(0, width, step):
        draw.line((x, 0, x, height), fill=(*hex_rgb(COLORS["primary"]), 17), width=1)
    for y in range(0, height, step):
        draw.line((0, y, width, y), fill=(*hex_rgb(COLORS["primary"]), 17), width=1)
    icon_size = round(min(width, height) * 0.30)
    source_icon = MASTER_ICON if MASTER_ICON is not None else draw_mark(1024)
    icon = source_icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
    icon_x = (width - icon_size) // 2
    icon_y = round(height * 0.22)
    image.paste(icon, (icon_x, icon_y), icon)
    title_font = font(round(min(width, height) * 0.066), bold=True)
    desc_font = font(round(min(width, height) * 0.025), bold=False)
    tagline_font = font(round(min(width, height) * 0.021), bold=True)
    founder_font = font(round(min(width, height) * 0.014), bold=False)
    title = "BioIntel AI"
    desc = "SCIENTIFIC INTELLIGENCE PLATFORM"
    tagline = "Biology, Engineered into Intelligence."
    founder = "Created and developed by Lavesh Dobriyal"
    y = icon_y + icon_size + round(height * 0.045)
    for text, fnt, color, gap in (
        (title, title_font, COLORS["text"], 0.018),
        (desc, desc_font, COLORS["muted"], 0.025),
        (tagline, tagline_font, COLORS["secondary"], 0.045),
        (founder, founder_font, COLORS["muted"], 0),
    ):
        box = draw.textbbox((0, 0), text, font=fnt)
        tw = box[2] - box[0]
        draw.text(((width - tw) / 2, y), text, font=fnt, fill=(*hex_rgb(color), 255))
        y += box[3] - box[1] + round(height * gap)
    return image


def save_png(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


# Master assets
master = draw_mark(1024)
MASTER_ICON = master
save_png(BRAND_DIR / "biointel-icon-1024.png", master)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-labelledby="title"><title id="title">BioIntel AI logo</title><defs><linearGradient id="g" x1="8" y1="8" x2="56" y2="56"><stop stop-color="{COLORS["secondary"]}"/><stop offset=".52" stop-color="{COLORS["primary"]}"/><stop offset="1" stop-color="{COLORS["accent"]}"/></linearGradient></defs><rect x="2" y="2" width="60" height="60" rx="17" fill="{COLORS["background"]}" stroke="url(#g)" stroke-width="2"/><path d="M19 12C42 18 42 46 19 52" fill="none" stroke="url(#g)" stroke-width="5" stroke-linecap="round"/><path d="M45 12C22 18 22 46 45 52" fill="none" stroke="url(#g)" stroke-width="5" stroke-linecap="round"/><g stroke="{COLORS["text"]}" stroke-opacity=".72" stroke-width="2" stroke-linecap="round"><path d="M22 19H42"/><path d="M18 27H46"/><path d="M18 37H46"/><path d="M22 45H42"/></g><circle cx="32" cy="32" r="4" fill="{COLORS["surface"]}" stroke="{COLORS["secondary"]}" stroke-width="2"/></svg>'''
(BRAND_DIR / "biointel-mark.svg").write_text(svg, encoding="utf-8")
wordmark = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 150" role="img" aria-labelledby="title"><title id="title">BioIntel AI wordmark</title><rect width="680" height="150" rx="28" fill="{COLORS["background"]}"/><g transform="translate(22 22) scale(1.65)">{svg.split("<defs>")[0].split(">", 1)[1]}<defs>{svg.split("<defs>")[1].split("</defs>")[0]}</defs>{svg.split("</defs>")[1].split("</svg>")[0]}</g><text x="145" y="70" fill="{COLORS["text"]}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="43" font-weight="800">BioIntel AI</text><text x="148" y="102" fill="{COLORS["muted"]}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="15" font-weight="700" letter-spacing="2">SCIENTIFIC INTELLIGENCE PLATFORM</text><text x="148" y="127" fill="{COLORS["secondary"]}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="14" font-weight="650">Biology, Engineered into Intelligence.</text></svg>'''
(BRAND_DIR / "biointel-wordmark.svg").write_text(wordmark, encoding="utf-8")

manifest = {
    "brand": "BioIntel AI",
    "descriptor": "Scientific Intelligence for Life Sciences",
    "tagline": "Biology, Engineered into Intelligence.",
    "founder": "Lavesh Dobriyal",
    "colors": COLORS,
    "logo_rules": {
        "minimum_clear_space": "25% of the mark width",
        "minimum_digital_size": "24 px",
        "do_not": [
            "stretch",
            "rotate",
            "recolour outside the approved palette",
            "add unapproved text inside the icon",
        ],
    },
}
(BRAND_DIR / "brand-manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)

# Store masters and platform assets
save_png(ROOT / "store/assets/master/icon-1024.png", master)
save_png(ROOT / "store/assets/master/splash-portrait.png", draw_splash(1536, 2048))
save_png(ROOT / "store/assets/master/splash-landscape.png", draw_splash(2048, 1536))

for size in (20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024):
    save_png(
        ROOT / f"store/assets/apple/icon-{size}.png",
        master.resize((size, size), Image.Resampling.LANCZOS),
    )
for size in (16, 24, 32, 44, 48, 64, 128, 150, 256, 512):
    save_png(
        ROOT / f"store/assets/windows/icon-{size}.png",
        master.resize((size, size), Image.Resampling.LANCZOS),
    )

# Windows ICO with standard embedded sizes
ico_path = ROOT / "store/assets/windows/BioIntelAI.ico"
ico_source = master.resize((512, 512), Image.Resampling.LANCZOS)
ico_source.save(
    ico_path,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
(ROOT / "platform/desktop/assets").mkdir(parents=True, exist_ok=True)
(ROOT / "platform/desktop/assets/BioIntelAI.ico").write_bytes(ico_path.read_bytes())
save_png(ROOT / "platform/desktop/assets/icon.png", master)

# Adaptive mobile assets
save_png(
    ROOT / "store/assets/android/adaptive-background.png",
    Image.new("RGB", (1024, 1024), hex_rgb(COLORS["background"])),
)
foreground = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
foreground_mark = master.resize((680, 680), Image.Resampling.LANCZOS)
foreground.paste(foreground_mark, (172, 172), foreground_mark)
save_png(ROOT / "store/assets/android/adaptive-foreground.png", foreground)
save_png(
    ROOT / "platform/mobile/assets/icon-background.png",
    Image.new("RGB", (1024, 1024), hex_rgb(COLORS["background"])),
)
save_png(ROOT / "platform/mobile/assets/icon-foreground.png", foreground)
save_png(ROOT / "platform/mobile/assets/icon-only.png", master)
save_png(ROOT / "platform/mobile/assets/splash.png", draw_splash(1536, 2048))

print("Brand assets generated.")
