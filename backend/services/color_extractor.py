import base64
import io
import logging
from collections import Counter

from PIL import Image

logger = logging.getLogger(__name__)


def extract_colors_from_b64(image_b64: str, num_colors: int = 5) -> dict:
    """
    Extract dominant colors from a base64 encoded image using PIL.

    Returns:
        dict with dominant_colors, accents, and color_descriptions
    """
    # Remove data URL prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    # Decode and open image
    image_data = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Resize for faster processing (maintain aspect ratio)
    max_size = 150
    image.thumbnail((max_size, max_size))

    # Get all pixels
    pixels = list(image.getdata())

    # Quantize colors to reduce noise (round to nearest 16)
    def quantize(color):
        return tuple((c // 16) * 16 for c in color)

    quantized = [quantize(p) for p in pixels]

    # Count occurrences
    color_counts = Counter(quantized)

    # Get most common colors
    most_common = color_counts.most_common(num_colors * 3)  # Get extra to filter

    # Filter out very similar colors
    filtered_colors = []
    for color, count in most_common:
        if len(filtered_colors) >= num_colors:
            break

        # Check if too similar to existing colors
        is_unique = True
        for existing in filtered_colors:
            if color_distance(color, existing) < 50:
                is_unique = False
                break

        if is_unique:
            filtered_colors.append(color)

    # Convert to hex
    hex_colors = [rgb_to_hex(c) for c in filtered_colors]

    # Split into dominant (first 3) and accents (rest)
    dominant = hex_colors[:3] if len(hex_colors) >= 3 else hex_colors
    accents = hex_colors[3:5] if len(hex_colors) > 3 else []

    # Generate color descriptions
    descriptions = [describe_color(c) for c in filtered_colors[:3]]

    # Calculate overall saturation and value
    avg_saturation = calculate_avg_saturation(filtered_colors[:5])
    value_range = calculate_value_range(filtered_colors[:5])

    return {
        "dominant_colors": dominant,
        "accents": accents,
        "color_descriptions": descriptions,
        "saturation": avg_saturation,
        "value_range": value_range,
    }


def rgb_to_hex(rgb: tuple) -> str:
    """Convert RGB tuple to hex string."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def hex_to_rgb(hex_str: str) -> tuple:
    """Convert hex string to RGB tuple."""
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def color_distance(c1: tuple, c2: tuple) -> float:
    """Calculate Euclidean distance between two RGB colors."""
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def rgb_to_hsv(rgb: tuple) -> tuple:
    """Convert RGB to HSV."""
    r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # Value
    v = max_c

    # Saturation
    s = 0 if max_c == 0 else diff / max_c

    # Hue
    if diff == 0:
        h = 0
    elif max_c == r:
        h = 60 * ((g - b) / diff % 6)
    elif max_c == g:
        h = 60 * ((b - r) / diff + 2)
    else:
        h = 60 * ((r - g) / diff + 4)

    return (h, s, v)


def describe_color(rgb: tuple) -> str:
    """Generate a human-readable color description."""
    h, s, v = rgb_to_hsv(rgb)

    # Determine lightness/darkness
    if v < 0.2:
        lightness = "very dark"
    elif v < 0.4:
        lightness = "dark"
    elif v < 0.6:
        lightness = "medium"
    elif v < 0.8:
        lightness = "light"
    else:
        lightness = "very light"

    # Determine saturation descriptor
    if s < 0.1:
        sat_desc = "gray"
    elif s < 0.3:
        sat_desc = "muted"
    elif s < 0.6:
        sat_desc = "moderate"
    else:
        sat_desc = "vibrant"

    # Determine hue name
    if s < 0.1:
        # Grayscale
        if v < 0.2:
            return "black"
        elif v < 0.4:
            return "charcoal gray"
        elif v < 0.6:
            return "medium gray"
        elif v < 0.8:
            return "light gray"
        else:
            return "off-white"

    # Color names by hue
    if h < 15 or h >= 345:
        hue_name = "red"
    elif h < 45:
        hue_name = "orange"
    elif h < 70:
        hue_name = "yellow"
    elif h < 150:
        hue_name = "green"
    elif h < 190:
        hue_name = "cyan"
    elif h < 260:
        hue_name = "blue"
    elif h < 290:
        hue_name = "purple"
    elif h < 345:
        hue_name = "magenta"
    else:
        hue_name = "red"

    # Combine descriptors
    if sat_desc == "muted":
        return f"muted {hue_name}"
    elif lightness in ["very dark", "dark"]:
        return f"dark {hue_name}"
    elif lightness in ["very light", "light"]:
        return f"light {hue_name}"
    else:
        return f"{sat_desc} {hue_name}"


def calculate_avg_saturation(colors: list) -> str:
    """Calculate average saturation level."""
    if not colors:
        return "medium"

    saturations = [rgb_to_hsv(c)[1] for c in colors]
    avg = sum(saturations) / len(saturations)

    if avg < 0.2:
        return "low"
    elif avg < 0.4:
        return "medium-low"
    elif avg < 0.6:
        return "medium"
    elif avg < 0.8:
        return "medium-high"
    else:
        return "high"


def calculate_value_range(colors: list) -> str:
    """Calculate the value/brightness range."""
    if not colors:
        return "medium values"

    values = [rgb_to_hsv(c)[2] for c in colors]
    min_v = min(values)
    max_v = max(values)
    avg_v = sum(values) / len(values)

    range_size = max_v - min_v

    if range_size < 0.3:
        if avg_v < 0.4:
            return "predominantly dark"
        elif avg_v > 0.6:
            return "predominantly light"
        else:
            return "mid-tones"
    else:
        if min_v < 0.3 and max_v > 0.7:
            return "high contrast, dark shadows to bright highlights"
        elif min_v < 0.3:
            return "dark base with mid-tone highlights"
        else:
            return "mid-tones to bright highlights"
