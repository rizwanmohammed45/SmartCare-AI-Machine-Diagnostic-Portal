"""
generate_qr.py — Smart Appliance Diagnostic System
====================================================
Generates two QR code sticker images for the hackathon demo.

Output files:
  qr_safe_diy.png       — Bosch WAU28PH9GB E18 (safe DIY pump fix)
  qr_critical_hazard.png — Samsung WW90T684DLN 3C (high-voltage motor hazard)

URLs use the machine's local Wi-Fi IPv4 address (auto-detected via socket),
so any phone on the same network can scan and open the portal instantly.

Dependencies:
    pip install qrcode[pil] pillow
"""

from __future__ import annotations

import socket

from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer


# ── Local IP detection ─────────────────────────────────────────────────────────

def get_local_ip() -> str:
    """
    Return the machine's local Wi-Fi / LAN IPv4 address by opening a
    UDP socket to a public address (no data is actually sent).
    Falls back to 127.0.0.1 if no network interface is available.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(("8.8.8.8", 80))          # doesn't send any data
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


LOCAL_IP = get_local_ip()
BASE_URL = f"http://{LOCAL_IP}:8000"

# ── Sticker definitions ────────────────────────────────────────────────────────

STICKERS = [
    {
        "filename": "qr_safe_diy.png",
        "url": (
            f"{BASE_URL}/frontend/index.html"
            "?brand=Bosch&model=WAU28PH9GB&error_code=E18"
            "&issue=Pump%20Filter%20Blockage"
        ),
        "header":       "BOSCH SERIE 6 FRONT-LOADER",
        "model_line":   "WAU28PH9GB  ·  9 kg i-DOS",
        "error_label":  "E18 — Pump Filter Blockage",
        "status_label": "SAFE DIY FIX",
        "telemetry":    "Pump filter blocked  ·  OEM: 0.8 bar min",
        # Colour scheme — blue/green (safe)
        "module_fill":  "#1d4ed8",
        "back_color":   "#ffffff",
        "header_bg":    "#1d4ed8",
        "header_fg":    "#ffffff",
        "status_bg":    "#dcfce7",
        "status_fg":    "#166534",
        "border_color": "#bfdbfe",
    },
    {
        "filename": "qr_critical_hazard.png",
        "url": (
            f"{BASE_URL}/frontend/index.html"
            "?brand=Samsung&model=WW90T684DLN&error_code=3C"
            "&issue=Motor%20Drive%20Short"
        ),
        "header":       "SAMSUNG ECOBUBBLE",
        "model_line":   "WW90T684DLN  ·  9 kg AddWash",
        "error_label":  "3C — Motor Drive Short",
        "status_label": "HIGH-VOLTAGE HAZARD",
        "telemetry":    "350 V DC bus  ·  Arc-flash risk",
        # Colour scheme — red (critical hazard)
        "module_fill":  "#dc2626",
        "back_color":   "#ffffff",
        "header_bg":    "#dc2626",
        "header_fg":    "#ffffff",
        "status_bg":    "#fee2e2",
        "status_fg":    "#991b1b",
        "border_color": "#fecaca",
    },
]

# ── Layout constants ───────────────────────────────────────────────────────────

STICKER_W   = 420
HEADER_H    = 56
QR_SIZE     = 280
QR_PADDING  = 18
INFO_H      = 118
CORNER_R    = 16
BORDER_W    = 3


# ── Font loader ────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
         "LiberationSans-Bold.ttf", "Verdana Bold.ttf"]
        if bold else
        ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
         "LiberationSans-Regular.ttf", "Verdana.ttf"]
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


# ── Drawing helpers ────────────────────────────────────────────────────────────

def _hcenter(draw: ImageDraw.ImageDraw, y: int, text: str,
             font: ImageFont.ImageFont, color: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((STICKER_W - tw) // 2, y), text, font=font, fill=color)


def _rrect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int,
           fill: str = None, outline: str = None, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


# ── Sticker renderer ───────────────────────────────────────────────────────────

def generate_sticker(cfg: dict) -> None:
    # 1. Build QR code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(cfg["url"])
    qr.make(fit=True)
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        fill_color=cfg["module_fill"],
        back_color=cfg["back_color"],
    ).convert("RGBA")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)

    # 2. Canvas
    total_h = HEADER_H + QR_PADDING + QR_SIZE + QR_PADDING + INFO_H
    canvas  = Image.new("RGBA", (STICKER_W, total_h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(canvas)

    # Outer card
    _rrect(draw, [(0, 0), (STICKER_W - 1, total_h - 1)],
           radius=CORNER_R, fill="#ffffff",
           outline=cfg["border_color"], width=BORDER_W)

    # 3. Header strip (rounded top)
    hdr_mask  = Image.new("L", (STICKER_W, HEADER_H), 0)
    hm        = ImageDraw.Draw(hdr_mask)
    hm.rounded_rectangle(
        [(0, 0), (STICKER_W - 1, HEADER_H + CORNER_R)],
        radius=CORNER_R, fill=255,
    )
    hdr_layer = Image.new("RGBA", (STICKER_W, HEADER_H), cfg["header_bg"])
    canvas.paste(hdr_layer, (0, 0), hdr_mask)

    _hcenter(draw, 8,  cfg["header"],     _font(18, bold=True), cfg["header_fg"])
    _hcenter(draw, 32, cfg["model_line"], _font(12),            cfg["header_fg"])

    # 4. QR code
    qr_x = (STICKER_W - QR_SIZE) // 2
    qr_y = HEADER_H + QR_PADDING
    canvas.paste(qr_img, (qr_x, qr_y), qr_img)

    # 5. Info panel
    info_y = HEADER_H + QR_PADDING + QR_SIZE + QR_PADDING

    # Error label pill
    f_err = _font(13, bold=True)
    err_bb = draw.textbbox((0, 0), cfg["error_label"], font=f_err)
    ew = err_bb[2] - err_bb[0] + 24
    ex = (STICKER_W - ew) // 2
    _rrect(draw, [(ex, info_y + 2), (ex + ew, info_y + 22)],
           radius=8, fill="#f1f5f9")
    _hcenter(draw, info_y + 4, cfg["error_label"], f_err, "#1e293b")

    # Telemetry line
    _hcenter(draw, info_y + 28, cfg["telemetry"], _font(10), "#64748b")

    # Status badge
    f_stat = _font(13, bold=True)
    sb_bb  = draw.textbbox((0, 0), cfg["status_label"], font=f_stat)
    sw = sb_bb[2] - sb_bb[0] + 28
    sx = (STICKER_W - sw) // 2
    _rrect(draw, [(sx, info_y + 48), (sx + sw, info_y + 72)],
           radius=10, fill=cfg["status_bg"], outline=cfg["status_fg"], width=1)
    _hcenter(draw, info_y + 51, cfg["status_label"], f_stat, cfg["status_fg"])

    # IP / URL hint
    short_url = cfg["url"].split("?")[0].replace("http://", "")
    hint = f"Scan → {short_url}"
    _hcenter(draw, info_y + 82, hint,                   _font(9),  "#94a3b8")
    _hcenter(draw, info_y + 96, f"IP: {LOCAL_IP}:8000", _font(9),  "#cbd5e1")

    # 6. Save
    canvas.convert("RGB").save(cfg["filename"], format="PNG", optimize=True)
    print("Saved: %s  (%dx%d px)" % (cfg["filename"], STICKER_W, total_h))
    print("  URL: %s\n" % cfg["url"])


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nDetected local IP: %s" % LOCAL_IP)
    print("Portal base URL : %s\n" % BASE_URL)
    for cfg in STICKERS:
        generate_sticker(cfg)
    print("Done — both QR sticker PNGs saved.")
    print("\nShare these URLs on your local network (%s):" % LOCAL_IP)
    for cfg in STICKERS:
        print("  %s" % cfg["url"])
