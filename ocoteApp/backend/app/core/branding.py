import io
import re
import warnings

from PIL import Image, UnidentifiedImageError

from app.core.errors import CommandError

PALETTE = {
    "primary": "#B85A1E",
    "primary-dark": "#7A3810",
    "on-primary": "#FFFFFF",
    "focus": "#2B5B84",
}
MAX_LOGO_BYTES = 1048576
MAX_LOGO_PIXELS = 4194304


def luminance(color):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise CommandError(422, "INVALID_BRANDING_COLOR")
    channels = [int(color[offset : offset + 2], 16) / 255 for offset in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return sum(value * weight for value, weight in
               zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def validate_palette(overrides):
    if not isinstance(overrides, dict) or set(overrides) - PALETTE.keys():
        raise CommandError(422, "BRANDING_TOKEN_NOT_ALLOWED")
    palette = PALETTE | overrides
    pairs = {
        "normal": (palette["on-primary"], palette["primary"]),
        "hover": (palette["on-primary"], palette["primary-dark"]),
        "outline": (palette["primary-dark"], "#FFFFFF"),
        "focus_surface": (palette["focus"], "#FFFFFF"),
        "focus_background": (palette["focus"], "#F6F4F0"),
        "error": ("#B83227", "#FFFFFF"),
    }
    ratios = {name: contrast(*pair) for name, pair in pairs.items()}
    if any(value < 4.5 for value in ratios.values()):
        raise CommandError(422, "BRANDING_CONTRAST_BELOW_AA")
    return ratios


def recode_logo(content, media_type, scanner):
    if not content or len(content) > MAX_LOGO_BYTES:
        raise CommandError(413, "LOGO_TOO_LARGE")
    expected = {"image/png": "PNG", "image/jpeg": "JPEG"}.get(media_type)
    if expected is None:
        raise CommandError(415, "INVALID_LOGO_TYPE")
    scan_version = scanner(content)
    if not isinstance(scan_version, str) or not scan_version.startswith("ClamAV "):
        raise CommandError(503, "LOGO_SCANNER_UNAVAILABLE")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as candidate:
                if candidate.format != expected or getattr(candidate, "n_frames", 1) != 1:
                    raise CommandError(415, "INVALID_LOGO_TYPE")
                if (candidate.width * candidate.height > MAX_LOGO_PIXELS
                        or max(candidate.size) > 4096):
                    raise CommandError(413, "LOGO_TOO_LARGE")
                candidate.verify()
            with Image.open(io.BytesIO(content)) as candidate:
                candidate.load()
                cleaned = Image.new("RGBA" if expected == "PNG" else "RGB", candidate.size)
                cleaned.paste(candidate.convert(cleaned.mode))
                output = io.BytesIO()
                cleaned.save(output, format=expected, **({"quality": 90} if expected == "JPEG"
                                                       else {}))
                result = output.getvalue()
                if len(result) > MAX_LOGO_BYTES:
                    raise CommandError(413, "LOGO_TOO_LARGE")
                scanner(result)
                return result, media_type, cleaned.width, cleaned.height, scan_version
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise CommandError(415, "INVALID_LOGO_IMAGE") from None