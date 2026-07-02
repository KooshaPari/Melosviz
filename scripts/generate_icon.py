#!/usr/bin/env python3
"""Generate MelosViz app icon (1024×1024 PNG).

Programmatically creates a waveform-spectrum visual with dark background.
"""

from PIL import Image, ImageDraw
import math

# Icon dimensions
SIZE = 1024
OUTPUT = "desktop/assets/icon.png"

# Color palette (dark-first, matches brand)
BG_BASE = (13, 13, 16)  # #0d0d10
ACCENT_LO = (76, 64, 176)  # #4c40b0
ACCENT = (124, 106, 247)  # #7c6af7
ACCENT_HI = (167, 139, 250)  # #a78bfa
NEON_PINK = (244, 114, 182)  # #f472b6
NEON_CYAN = (34, 211, 238)  # #22d3ee

def create_icon():
    """Generate icon with animated waveform spectrum."""
    img = Image.new("RGBA", (SIZE, SIZE), BG_BASE + (255,))
    draw = ImageDraw.Draw(img)

    # Background: subtle gradient (dark violet)
    for y in range(SIZE):
        # Vertical gradient from dark violet to black
        ratio = y / SIZE
        r = int(20 + (13 - 20) * ratio)
        g = int(15 + (13 - 15) * ratio)
        b = int(30 + (16 - 30) * ratio)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

    # Concentric circles (retro spectrum aesthetic)
    center_x, center_y = SIZE // 2, SIZE // 2
    circle_radii = [200, 280, 360, 420]

    for i, radius in enumerate(circle_radii):
        # Gradient opacity from inner to outer
        alpha = int(40 - i * 10)
        color = (ACCENT[0], ACCENT[1], ACCENT[2], alpha)
        draw.ellipse(
            [(center_x - radius, center_y - radius), (center_x + radius, center_y + radius)],
            outline=color,
            width=2
        )

    # Waveform bars (spectrum visualization)
    bar_count = 24
    bar_width = int(SIZE * 0.6 / bar_count)
    max_height = SIZE * 0.35
    start_x = center_x - (bar_count * bar_width) // 2

    colors = [
        (ACCENT_LO[0], ACCENT_LO[1], ACCENT_LO[2], 200),
        (ACCENT[0], ACCENT[1], ACCENT[2], 220),
        (ACCENT_HI[0], ACCENT_HI[1], ACCENT_HI[2], 230),
        (NEON_PINK[0], NEON_PINK[1], NEON_PINK[2], 240),
    ]

    for i in range(bar_count):
        # Animated sine wave for bar heights
        t = i / bar_count
        height_factor = 0.3 + 0.7 * (math.sin(t * math.pi * 2) * 0.5 + 0.5)
        bar_height = int(max_height * height_factor)

        x1 = start_x + i * bar_width + 2
        x2 = x1 + bar_width - 4
        y1 = center_y - bar_height // 2
        y2 = center_y + bar_height // 2

        color = colors[i % len(colors)]
        draw.rectangle([(x1, y1), (x2, y2)], fill=color)

    # Center dot (focal point)
    dot_size = 24
    draw.ellipse(
        [(center_x - dot_size, center_y - dot_size), (center_x + dot_size, center_y + dot_size)],
        fill=(NEON_CYAN[0], NEON_CYAN[1], NEON_CYAN[2], 255),
    )

    # Save
    img.save(OUTPUT, "PNG", quality=95)
    print(f"✓ Icon generated: {OUTPUT} ({SIZE}×{SIZE})")

if __name__ == "__main__":
    create_icon()
