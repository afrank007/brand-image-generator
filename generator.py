"""
generator.py — Image generation engine
Uses Pillow to render on-brand social media images from brand kits + text input.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, textwrap, json, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

FORMATS = {
    "ig_square":   {"name": "Instagram Square",   "w": 1080, "h": 1080},
    "ig_portrait": {"name": "Instagram Portrait", "w": 1080, "h": 1350},
    "stories":     {"name": "Stories & Reels",    "w": 1080, "h": 1920},
    "pinterest":   {"name": "Pinterest",          "w": 1000, "h": 1500},
    "tiktok":      {"name": "TikTok",             "w": 1080, "h": 1920},
}

FONT_MAP = {
    "Playfair Display": "PlayfairDisplay-Regular.ttf",
    "Montserrat":       "Montserrat-Regular.ttf",
    "Lato":             "Lato-Regular.ttf",
    "Open Sans":        "OpenSans-Regular.ttf",
    "Inter":            "Inter-Regular.ttf",
}
BOLD_MAP = {
    "Lato": "Lato-Bold.ttf",
}
FALLBACK = "Inter-Regular.ttf"


# ── Color helpers ─────────────────────────────────────────────────────────────

def parse_hex(hex_color, fallback=(30, 30, 30)):
    try:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback

def luminance(rgb):
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def text_color_for_bg(bg_rgb):
    return (0, 0, 0) if luminance(bg_rgb) > 0.55 else (255, 255, 255)

def lighten(rgb, amount=40):
    return tuple(min(255, c + amount) for c in rgb)

def darken(rgb, amount=40):
    return tuple(max(0, c - amount) for c in rgb)

def with_alpha(rgb, alpha):
    return rgb + (alpha,)


# ── Font helpers ──────────────────────────────────────────────────────────────

def load_font(font_name, size, bold=False):
    fname = None
    if bold and font_name in BOLD_MAP:
        fname = BOLD_MAP[font_name]
    elif font_name in FONT_MAP:
        fname = FONT_MAP[font_name]
    if not fname:
        fname = FALLBACK
    path = os.path.join(FONTS_DIR, fname)
    if not os.path.exists(path):
        path = os.path.join(FONTS_DIR, FALLBACK)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ── Text wrapping ─────────────────────────────────────────────────────────────

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def draw_text_block(draw, lines, font, x, y, color, line_spacing=1.35, align="center", max_width=None):
    """Draw wrapped lines and return total height used."""
    try:
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_h = bbox[3] - bbox[1]
    except Exception:
        line_h = font.size if hasattr(font, 'size') else 20
    gap = int(line_h * (line_spacing - 1))
    total_h = len(lines) * line_h + (len(lines) - 1) * gap

    cy = y
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * (line_h // 2)

        if align == "center" and max_width:
            lx = x + (max_width - lw) // 2
        elif align == "right" and max_width:
            lx = x + max_width - lw
        else:
            lx = x

        draw.text((lx, cy), line, font=font, fill=color)
        cy += line_h + gap

    return total_h

def measure_text_block(draw, lines, font, line_spacing=1.35):
    try:
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_h = bbox[3] - bbox[1]
    except Exception:
        line_h = getattr(font, 'size', 20)
    gap = int(line_h * (line_spacing - 1))
    return len(lines) * line_h + max(0, len(lines) - 1) * gap


# ── Rounded rectangle ─────────────────────────────────────────────────────────

def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
    draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
    draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)


# ── Layout builders ───────────────────────────────────────────────────────────

def build_layout(brand, fmt_key, headline, subtext, cta_text, content_type, logo_img=None):
    fmt = FORMATS[fmt_key]
    W, H = fmt["w"], fmt["h"]

    c = brand.get("colors", {})
    primary    = parse_hex(c.get("primary", "#1A1916"))
    secondary  = parse_hex(c.get("secondary", "#F0EDE8"))
    accent     = parse_hex(c.get("accent", "") or c.get("primary", "#1A1916"))
    bg_color   = parse_hex(c.get("background", "#FFFFFF"))
    text_color = parse_hex(c.get("text", "#1A1916"))

    heading_font = brand.get("fonts", {}).get("heading", "Inter")
    body_font    = brand.get("fonts", {}).get("body", "Inter")
    tone         = (brand.get("tone", "") or "").lower()

    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    margin = int(W * 0.074)  # ~80px on 1080
    content_w = W - 2 * margin

    # ── Background style by tone ──
    if "luxury" in tone or "elevated" in tone:
        _draw_luxury_bg(img, draw, W, H, primary, secondary, bg_color)
    elif "bold" in tone or "edgy" in tone:
        _draw_bold_bg(img, draw, W, H, primary, secondary)
    elif "earthy" in tone or "organic" in tone:
        _draw_earthy_bg(img, draw, W, H, primary, secondary, bg_color)
    elif "playful" in tone or "fun" in tone:
        _draw_playful_bg(img, draw, W, H, primary, secondary, accent, bg_color)
    else:
        _draw_minimal_bg(img, draw, W, H, primary, secondary, bg_color)

    # ── Determine text color based on overlay ──
    overlay_rgb = primary if ("bold" in tone or "edgy" in tone) else bg_color
    on_overlay = text_color_for_bg(overlay_rgb)
    on_primary = text_color_for_bg(primary)

    is_vertical = H > W
    center_x = margin

    # ── Font sizes (scale with canvas size) ──
    base = W / 1080
    hs  = int(72 * base)   # headline
    ss  = int(36 * base)   # subtext
    bs  = int(26 * base)   # body/caption
    cs  = int(24 * base)   # CTA
    ls  = int(20 * base)   # label/handle

    hfont  = load_font(heading_font, hs, bold=True)
    sfont  = load_font(body_font, ss)
    bfont  = load_font(body_font, bs)
    cfont  = load_font(body_font, cs, bold=True)
    lfont  = load_font(body_font, ls)

    # ── Layout zones ──
    logo_h = int(H * 0.06)
    top_pad = margin
    bottom_pad = margin

    # Top: brand name / logo
    _draw_brand_mark(draw, brand, logo_img, margin, top_pad, content_w, logo_h, lfont, on_overlay, primary, on_primary)

    # Center block: headline + subtext
    headline_lines = wrap_text(draw, headline or brand["name"], hfont, content_w)
    sub_lines      = wrap_text(draw, subtext, sfont, content_w) if subtext else []

    h_hl = measure_text_block(draw, headline_lines, hfont)
    h_sl = measure_text_block(draw, sub_lines, sfont) if sub_lines else 0
    gap  = int(ss * 0.7)

    # CTA button height
    cta_h = int(cs * 2.2)
    cta_w = min(content_w, int(W * 0.55))

    total_block = h_hl + (gap + h_sl if sub_lines else 0) + gap * 2 + cta_h
    start_y = (H - total_block) // 2 + int(H * 0.03)  # slightly above center

    # Headline
    hl_color = on_overlay if ("bold" in tone or "edgy" in tone) else text_color
    draw_text_block(draw, headline_lines, hfont, margin, start_y, hl_color, align="center", max_width=content_w)
    cur_y = start_y + h_hl + gap

    # Subtext
    if sub_lines:
        sub_col = on_overlay if ("bold" in tone or "edgy" in tone) else parse_hex(c.get("primary", "#555555"))
        draw_text_block(draw, sub_lines, sfont, margin, cur_y, sub_col, align="center", max_width=content_w)
        cur_y += h_sl + gap

    # CTA button
    if cta_text:
        cx = (W - cta_w) // 2
        cy = cur_y + gap // 2
        btn_col = primary
        if "luxury" in tone:
            btn_col = darken(primary, 20)
        draw_rounded_rect(draw, (cx, cy, cx + cta_w, cy + cta_h), radius=cta_h // 2, fill=btn_col)
        btn_text_col = on_primary
        btn_lines = wrap_text(draw, cta_text, cfont, cta_w - 40)
        btn_h = measure_text_block(draw, btn_lines, cfont)
        btn_y = cy + (cta_h - btn_h) // 2
        draw_text_block(draw, btn_lines, cfont, cx, btn_y, btn_text_col, align="center", max_width=cta_w)

    # Handle at bottom
    handle = brand.get("handle", "")
    if handle:
        try:
            hbbox = draw.textbbox((0, 0), handle, font=lfont)
            hw = hbbox[2] - hbbox[0]
            hh = hbbox[3] - hbbox[1]
        except Exception:
            hw, hh = len(handle) * ls // 2, ls
        hx = (W - hw) // 2
        hy = H - bottom_pad - hh
        handle_col = on_overlay if ("bold" in tone or "edgy" in tone) else text_color
        draw.text((hx, hy), handle, font=lfont, fill=handle_col + (180,) if len(handle_col) == 3 else handle_col)

    return img


# ── Background styles ─────────────────────────────────────────────────────────

def _draw_minimal_bg(img, draw, W, H, primary, secondary, bg):
    # Subtle top strip
    strip_h = int(H * 0.007)
    draw.rectangle([0, 0, W, strip_h], fill=primary)

def _draw_luxury_bg(img, draw, W, H, primary, secondary, bg):
    # Soft gradient-like side panels using layered rects
    panel_w = int(W * 0.025)
    draw.rectangle([0, 0, panel_w, H], fill=secondary)
    draw.rectangle([W - panel_w, 0, W, H], fill=secondary)
    # thin gold line
    lw = max(1, int(W * 0.003))
    draw.rectangle([panel_w + int(W * 0.04), int(H * 0.06), panel_w + int(W * 0.04) + lw, H - int(H * 0.06)], fill=primary)
    draw.rectangle([W - panel_w - int(W * 0.04) - lw, int(H * 0.06), W - panel_w - int(W * 0.04), H - int(H * 0.06)], fill=primary)

def _draw_bold_bg(img, draw, W, H, primary, secondary):
    # Full bleed primary
    draw.rectangle([0, 0, W, H], fill=primary)
    # Diagonal accent block
    from PIL import ImageDraw as ID
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ID.Draw(overlay)
    pts = [(0, int(H * 0.6)), (W, int(H * 0.4)), (W, H), (0, H)]
    od.polygon(pts, fill=darken(primary, 30) + (180,))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))

def _draw_earthy_bg(img, draw, W, H, primary, secondary, bg):
    # Warm bottom block
    block_h = int(H * 0.38)
    draw.rectangle([0, H - block_h, W, H], fill=secondary)
    # Soft top border
    draw.rectangle([0, 0, W, int(H * 0.005)], fill=primary)
    # Small decorative circle
    cr = int(W * 0.18)
    draw.ellipse([W - cr, -cr // 2, W + cr // 2, cr], fill=lighten(secondary, 15))

def _draw_playful_bg(img, draw, W, H, primary, secondary, accent, bg):
    # Bold color block top-right
    draw.rectangle([int(W * 0.55), 0, W, int(H * 0.45)], fill=secondary)
    # accent strip bottom
    draw.rectangle([0, H - int(H * 0.012), W, H], fill=accent)
    # playful circle
    cr = int(W * 0.12)
    draw.ellipse([int(W * 0.04), int(H * 0.04), int(W * 0.04) + cr, int(H * 0.04) + cr], fill=lighten(primary, 60))


# ── Brand mark ────────────────────────────────────────────────────────────────

def _draw_brand_mark(draw, brand, logo_img, margin, top_pad, content_w, logo_h, font, text_col, primary, on_primary):
    name = brand.get("name", "")
    handle = brand.get("handle", "")
    mark = handle or name

    if logo_img:
        # Resize logo to fit logo_h while preserving aspect
        lw_orig, lh_orig = logo_img.size
        scale = logo_h / lh_orig
        nw = int(lw_orig * scale)
        logo_resized = logo_img.resize((nw, logo_h), Image.LANCZOS)
        # center it
        lx = margin + (content_w - nw) // 2
        if logo_resized.mode == "RGBA":
            draw._image.paste(logo_resized, (lx, top_pad), logo_resized)
        else:
            draw._image.paste(logo_resized, (lx, top_pad))
    else:
        # Text mark in a small pill
        try:
            bbox = draw.textbbox((0, 0), mark, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = len(mark) * 12, 20
        pad_x, pad_y = 18, 8
        px = margin + (content_w - (tw + 2 * pad_x)) // 2
        py = top_pad
        draw_rounded_rect(draw, (px, py, px + tw + 2 * pad_x, py + th + 2 * pad_y), radius=20, fill=primary)
        draw.text((px + pad_x, py + pad_y), mark, font=font, fill=on_primary)
