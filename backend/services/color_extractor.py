import base64
import io
import logging
from collections import Counter

from PIL import Image

logger = logging.getLogger(__name__)


def extract_colors_from_b64(image_b64: str, num_colors: int = 5) -> dict:
    """
    Extract dominant colors from a base64 encoded image using PIL.
    Uses k-means style clustering for better color representation.

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

    logger.info(f"Image size: {image.size}, mode: {image.mode}")

    # Resize for faster processing - but not too small
    max_size = 200
    image.thumbnail((max_size, max_size))

    # Get all pixels
    pixels = list(image.getdata())
    logger.info(f"Total pixels: {len(pixels)}")

    # Use PIL's built-in quantize for better color clustering
    # This uses median cut algorithm for better color selection
    try:
        # Quantize to a small palette
        quantized_img = image.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
        palette = quantized_img.getpalette()

        # Extract RGB tuples from palette (first 16 colors * 3 channels)
        palette_colors = []
        for i in range(16):
            r = palette[i * 3]
            g = palette[i * 3 + 1]
            b = palette[i * 3 + 2]
            palette_colors.append((r, g, b))

        # Count how many pixels use each palette color
        quantized_pixels = list(quantized_img.getdata())
        color_counts = Counter(quantized_pixels)

        # Map palette indices to actual colors with their counts
        colors_with_counts = []
        for idx, count in color_counts.most_common():
            if idx < len(palette_colors):
                colors_with_counts.append((palette_colors[idx], count))

        logger.info(f"Quantized palette colors: {[c[0] for c in colors_with_counts[:5]]}")

    except Exception as e:
        logger.warning(f"Quantize failed: {e}, falling back to manual clustering")
        # Fallback: Use manual quantization with smaller steps
        def quantize(color):
            # Round to nearest 8 (less aggressive than 16)
            return tuple((c // 8) * 8 for c in color)

        quantized = [quantize(p) for p in pixels]
        color_counts_raw = Counter(quantized)
        colors_with_counts = [(color, count) for color, count in color_counts_raw.most_common(50)]

    # Filter to get diverse colors
    filtered_colors = []
    for color, count in colors_with_counts:
        if len(filtered_colors) >= num_colors:
            break

        # Skip very dark colors (likely shadows/borders) unless we have few colors
        h, s, v = rgb_to_hsv(color)
        if v < 0.1 and len(filtered_colors) > 0:
            continue

        # Check if too similar to existing colors
        is_unique = True
        for existing in filtered_colors:
            if color_distance(color, existing) < 40:  # Reduced threshold
                is_unique = False
                break

        if is_unique:
            filtered_colors.append(color)
            logger.info(f"Added color: {rgb_to_hex(color)} - {describe_color(color)}")

    # If we still don't have enough colors, be less picky
    if len(filtered_colors) < 3:
        logger.info("Not enough unique colors, relaxing constraints...")
        for color, count in colors_with_counts:
            if len(filtered_colors) >= num_colors:
                break
            if color not in filtered_colors:
                is_unique = True
                for existing in filtered_colors:
                    if color_distance(color, existing) < 20:
                        is_unique = False
                        break
                if is_unique:
                    filtered_colors.append(color)

    # Convert to hex
    hex_colors = [rgb_to_hex(c) for c in filtered_colors]
    logger.info(f"Final hex colors: {hex_colors}")

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
    if v < 0.15:
        lightness = "very dark"
    elif v < 0.35:
        lightness = "dark"
    elif v < 0.65:
        lightness = "medium"
    elif v < 0.85:
        lightness = "light"
    else:
        lightness = "very light"

    # Determine saturation descriptor
    if s < 0.15:
        sat_desc = "gray"
    elif s < 0.35:
        sat_desc = "muted"
    elif s < 0.65:
        sat_desc = "moderate"
    else:
        sat_desc = "vibrant"

    # Determine hue name
    if s < 0.15:
        # Grayscale
        if v < 0.15:
            return "black"
        elif v < 0.35:
            return "charcoal"
        elif v < 0.65:
            return "gray"
        elif v < 0.85:
            return "silver"
        else:
            return "white"

    # Color names by hue
    if h < 15 or h >= 345:
        hue_name = "red"
    elif h < 35:
        hue_name = "orange"
    elif h < 55:
        hue_name = "gold"
    elif h < 75:
        hue_name = "yellow"
    elif h < 95:
        hue_name = "lime"
    elif h < 150:
        hue_name = "green"
    elif h < 175:
        hue_name = "teal"
    elif h < 200:
        hue_name = "cyan"
    elif h < 230:
        hue_name = "blue"
    elif h < 260:
        hue_name = "indigo"
    elif h < 290:
        hue_name = "purple"
    elif h < 320:
        hue_name = "magenta"
    elif h < 345:
        hue_name = "pink"
    else:
        hue_name = "red"

    # Combine descriptors based on what's most notable
    if sat_desc == "vibrant":
        if lightness in ["very dark", "dark"]:
            return f"deep {hue_name}"
        elif lightness in ["very light", "light"]:
            return f"bright {hue_name}"
        else:
            return f"vivid {hue_name}"
    elif sat_desc == "muted":
        if lightness in ["very dark", "dark"]:
            return f"dark muted {hue_name}"
        elif lightness in ["very light", "light"]:
            return f"pale {hue_name}"
        else:
            return f"dusty {hue_name}"
    else:
        if lightness in ["very dark", "dark"]:
            return f"dark {hue_name}"
        elif lightness in ["very light", "light"]:
            return f"light {hue_name}"
        else:
            return hue_name


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
            return "high contrast, dark to bright"
        elif min_v < 0.3:
            return "dark base with highlights"
        else:
            return "mid-tones to highlights"
