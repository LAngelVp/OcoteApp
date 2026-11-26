"""Generate bounded presentation assets from the unmodified official OCOTE images."""

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

DIRECTORY = Path(__file__).resolve().parents[2] / "public" / "logos"
VARIANTS = (
    ("logoComplete.jpg", "ocote-complete.webp", 1200),
    ("logoText.jpg", "ocote-text.webp", 1000),
    ("logoIcon.jpg", "ocote-icon.png", 256),
)


def derive(source, size, square):
    image = Image.open(source).convert("RGB")
    red, green, blue = image.split()
    ink = ImageChops.darker(ImageChops.darker(red, green), blue)
    bounds = ink.point(lambda value: 255 if value < 160 else 0).getbbox()
    if bounds is None:
        raise ValueError("Official image has no visible identity")
    left, top, right, bottom = bounds
    padding = 32
    bounds = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    image = image.crop(bounds)
    if square:
        image = ImageOps.pad(image, (size, size), color="#F6F4F0", method=Image.Resampling.LANCZOS)
    else:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG" if square else "WEBP", **({} if square else {"quality": 94}))
    return output.getvalue(), image.size, bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    report = []
    for source_name, target_name, size in VARIANTS:
        source, target = DIRECTORY / source_name, DIRECTORY / target_name
        content, dimensions, bounds = derive(source, size, target.suffix == ".png")
        if arguments.check:
            if not target.is_file() or target.read_bytes() != content:
                raise SystemExit("Official asset missing or stale: " + target_name)
        else:
            target.write_bytes(content)
        report.append(
            {
                "original": source_name,
                "original_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "derived": target_name,
                "dimensions": dimensions,
                "bounds": bounds,
                "bytes": len(content),
            }
        )
    print(json.dumps(report))


if __name__ == "__main__":
    main()