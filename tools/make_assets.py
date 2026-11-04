"""
Generate the A2M2 website image assets from the master logo.

The master logo has an OPAQUE BLACK background, so it cannot be placed on a
coloured surface as-is. This script unpremultiplies the black background into a
real alpha channel, then derives every asset the site needs.

logo2.tif also carries a light grey frame around the black panel, so the loader
crops to the panel interior (FRAME) before keying. Because this artwork is white
line art, the favicons are rendered on a dark tile; white-on-transparent would
vanish against light browser chrome.

Run from the project root:
    python3 tools/make_assets.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logo2.tif"
OUT = ROOT / "assets" / "img"

# Interior of the black panel, excluding the grey frame: left, top, right, bottom.
FRAME = (7, 76, 1152, 1234)

# Bands measured inside FRAME, taken from the blank gutters between elements.
BRAIN_ROWS = (60, 730)        # brain only
ALL_ROWS = (60, 1135)         # brain + A2M2 wordmark + tagline

# The brain without the decorative spark dashes to its left, which turn to mush
# below ~48px. Columns measured inside FRAME.
ICON_COLS = (120, 912)

# One spark overlaps the brain's own columns, so it cannot be cropped away by
# x-extent alone. Measured component areas in the trimmed mark: the four sparks
# are 1663-1877px, while the smallest element worth keeping (the cross outline)
# is 2912px. Anything under this share of the largest component is a spark.
SPARK_MAX_SHARE = 0.07

# Brand colours sampled from the logo gradient.
PURPLE = (88, 44, 127)
TEAL = (31, 163, 194)
INK = (11, 10, 18)


def load_with_alpha() -> Image.Image:
    """Convert the black-backed logo into a transparent-background RGBA image.

    A logo drawn on pure black behaves like a 'screen' blend: each channel is
    already multiplied by its own coverage. Taking alpha = max(r, g, b) and
    dividing the colour back out recovers clean, anti-aliased edges instead of
    the hard fringe you get from a simple colour-key.
    """
    panel = Image.open(SRC).convert("RGB").crop(FRAME)
    rgb = np.asarray(panel).astype(np.float64)
    alpha = rgb.max(axis=2)

    safe = np.where(alpha == 0, 1.0, alpha)
    colour = np.clip(rgb * (255.0 / safe[..., None]), 0, 255)

    out = np.dstack([colour, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def drop_sparks(img: Image.Image) -> Image.Image:
    """Remove the decorative dashes radiating from the brain.

    They are separate strokes, so they fall out as their own connected
    components. One of them overlaps the brain's columns, which rules out a
    simple crop. Keeping only the larger components leaves the hemispheres and
    everything drawn inside them.
    """
    alpha = np.asarray(img.convert("RGBA"))[..., 3]
    solid = (alpha > 20).astype(np.uint8)

    # Label 8-connected regions without pulling in SciPy or OpenCV: flood fill
    # each unvisited pixel iteratively, so a large mark cannot blow the stack.
    labels = np.zeros(solid.shape, dtype=np.int32)
    areas: list[int] = [0]
    height, width = solid.shape
    for sy in range(height):
        for sx in range(width):
            if not solid[sy, sx] or labels[sy, sx]:
                continue
            tag = len(areas)
            stack = [(sy, sx)]
            labels[sy, sx] = tag
            count = 0
            while stack:
                y, x = stack.pop()
                count += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < height and 0 <= nx < width:
                            if solid[ny, nx] and not labels[ny, nx]:
                                labels[ny, nx] = tag
                                stack.append((ny, nx))
            areas.append(count)

    if len(areas) <= 1:
        return img
    cutoff = max(areas) * SPARK_MAX_SHARE
    keep = {i for i, a in enumerate(areas) if i and a >= cutoff}
    dropped = [a for i, a in enumerate(areas) if i and i not in keep]
    if dropped:
        print(f"  dropped {len(dropped)} spark(s), areas {sorted(dropped)}")

    out = np.asarray(img.convert("RGBA")).copy()
    mask = np.isin(labels, list(keep))
    out[..., 3] = np.where(mask, out[..., 3], 0)
    return Image.fromarray(out, "RGBA")


def trim(img: Image.Image) -> Image.Image:
    bbox = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    return img.crop(bbox)


def resize_rgba(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Downscale RGBA correctly, via premultiplied alpha.

    PIL resamples the colour and alpha channels independently. Fully
    transparent pixels in this logo carry colour (0, 0, 0), so a direct resize
    bleeds black into every anti-aliased edge and visibly mutes the thin
    gradient ring. Premultiplying before resampling and dividing out after
    keeps edge colours true.
    """
    arr = np.asarray(img.convert("RGBA")).astype(np.float64)
    alpha = arr[..., 3:4] / 255.0
    premul = np.dstack([arr[..., :3] * alpha, arr[..., 3]]).astype(np.uint8)

    small = np.asarray(
        Image.fromarray(premul, "RGBA").resize(size, Image.LANCZOS)
    ).astype(np.float64)

    a = small[..., 3:4] / 255.0
    colour = np.divide(small[..., :3], a, out=np.zeros_like(small[..., :3]), where=a > 0)
    out = np.dstack([np.clip(colour, 0, 255), small[..., 3]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def scaled_to_fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    ratio = min(max_w / img.width, max_h / img.height)
    return resize_rgba(
        img, (max(int(img.width * ratio), 1), max(int(img.height * ratio), 1))
    )


def rounded_tile(size: int, radius_ratio: float = 0.22) -> Image.Image:
    """A near-black rounded square used behind icons.

    Kept deliberately dark: the mark's own purple/teal ring supplies the colour,
    so a saturated tile would flatten the ring into the background.
    """
    top = (10, 9, 16)
    bottom = (26, 20, 42)

    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        row = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        for x in range(size):
            px[x, y] = row

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * radius_ratio), fill=255
    )

    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), mask)
    return tile


def make_icon(core: Image.Image, size: int, inset: float, radius_ratio: float) -> Image.Image:
    """Render an app icon by compositing at high resolution, then downscaling.

    Building the tile and mark at 1024px and shrinking the finished, opaque
    composite avoids resampling a part-transparent mark at small sizes, which
    is where thin details break up.
    """
    render = 1024
    usable = int(render * (1 - inset * 2))

    tile = rounded_tile(render, radius_ratio)
    mark = scaled_to_fit(core, usable, usable)
    tile.alpha_composite(
        mark, ((render - mark.width) // 2, (render - mark.height) // 2)
    )

    return tile if size == render else resize_rgba(tile, (size, size))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    logo = load_with_alpha()

    # 1. Full logo (brain + wordmark + tagline), transparent, tightly trimmed.
    full = trim(logo.crop((0, ALL_ROWS[0], logo.width, ALL_ROWS[1])))
    full.save(OUT / "logo-full.png", optimize=True)
    print(f"logo-full.png        {full.size}")

    # 2. Logo mark only: the split brain, without the wordmark underneath.
    mark = trim(logo.crop((0, BRAIN_ROWS[0], logo.width, BRAIN_ROWS[1])))
    mark.save(OUT / "logo-mark.png", optimize=True)
    print(f"logo-mark.png        {mark.size}")

    # 3. Icon core: the brain with the spark dashes dropped, so the shape fills
    #    the icon tile instead of sitting off-centre beside them.
    icon_core = trim(
        drop_sparks(logo.crop((ICON_COLS[0], BRAIN_ROWS[0], ICON_COLS[1], BRAIN_ROWS[1])))
    )

    # The same tight crop, transparent, for the site header, where the mark
    # renders at roughly 42px.
    icon_core.save(OUT / "logo-mark-tight.png", optimize=True)
    print(f"logo-mark-tight.png  {icon_core.size}")

    # 4. Favicons and touch icon on a dark tile so the white face stays visible
    #    against light browser chrome.
    for size, name in (
        (512, "icon-512.png"),
        (192, "icon-192.png"),
        (180, "apple-touch-icon.png"),
    ):
        icon = make_icon(icon_core, size, inset=0.10, radius_ratio=0.22)
        icon.save(OUT / name, optimize=True)
        print(f"{name:20s} {icon.size}")

    # Favicon sits at 16-32px in a browser tab, so it gets a tighter inset and
    # squarer corners to keep the mark as large and legible as possible.
    make_icon(icon_core, 256, inset=0.06, radius_ratio=0.16).save(
        OUT / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("favicon.ico          multi-size")

    # 5. Open Graph / Twitter card: 1200x630 brand gradient with the full logo.
    og_w, og_h = 1200, 630
    base = Image.new("RGB", (og_w, og_h), INK)
    grad = Image.new("RGB", (og_w, og_h))
    gpx = grad.load()
    for y in range(og_h):
        for x in range(og_w):
            t = (x / og_w) * 0.6 + (1 - y / og_h) * 0.4
            gpx[x, y] = (
                int(INK[0] + (PURPLE[0] - INK[0]) * t * 1.15),
                int(INK[1] + (PURPLE[1] - INK[1]) * t * 0.95),
                int(INK[2] + (TEAL[2] - INK[2]) * t * 0.85),
            )
    base = Image.blend(base, grad, 0.9)

    # Soft teal glow behind the mark for depth.
    glow = Image.new("RGB", (og_w, og_h), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-150, 120, 520, 820), fill=(16, 90, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    base = Image.blend(base, Image.blend(base, glow, 0.45), 0.5)

    card = base.convert("RGBA")
    og_logo = scaled_to_fit(full, 760, 430)
    card.alpha_composite(
        og_logo, ((og_w - og_logo.width) // 2, (og_h - og_logo.height) // 2)
    )
    card.convert("RGB").save(OUT / "og-image.png", optimize=True)
    print(f"og-image.png         {card.size}")

    # 6. Neutral silhouette placeholder for team members without a photo.
    ph = 600
    avatar = Image.new("RGBA", (ph, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(avatar)
    d.rounded_rectangle((0, 0, ph - 1, ph - 1), radius=28, fill=(233, 231, 240, 255))
    d.ellipse((ph * 0.33, ph * 0.20, ph * 0.67, ph * 0.54), fill=(187, 182, 203, 255))
    d.ellipse((ph * 0.16, ph * 0.60, ph * 0.84, ph * 1.28), fill=(187, 182, 203, 255))
    avatar.save(OUT / "team" / "placeholder.png", optimize=True)
    print(f"team/placeholder.png {avatar.size}")


if __name__ == "__main__":
    main()
