"""Create consistent, web-optimised director portraits from the supplied photos.

The original files stay untouched in the project root. Output portraits use a
square, face-centred crop suitable for profile cards.

Run from the project root:
    python3 tools/make_team_photos.py
"""

from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "img" / "team"

# The source portraits are both vertical. These crop rectangles were chosen by
# visual inspection to retain the complete head and enough shoulders for an
# approachable, professional profile image.
SOURCES = {
    "naeha-sharif.jpg": (ROOT / "naeha_profile.jpg", (0, 58, 758, 816)),
    "ghulam-mubashar-hassan.jpg": (ROOT / "Mubashar_Profile.jpg", (0, 10, 245, 255)),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    for output_name, (source, crop) in SOURCES.items():
        image = ImageOps.exif_transpose(Image.open(source).convert("RGB"))
        portrait = image.crop(crop).resize((720, 720), Image.Resampling.LANCZOS)
        portrait.save(OUT / output_name, "JPEG", quality=88, optimize=True, progressive=True)
        print(f"{output_name:29s} {portrait.size}  {(OUT / output_name).stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
