import base64
import io
import logging
from collections import Counter
import colorsys

from PIL import Image

logger = logging.getLogger(__name__)


def extract_colors_from_b64(image_b64: str, num_colors: int = 5) -> dict:
    """
    Extract dominant colors from a base64 encoded image using PIL.
    Uses direct pixel sampling and clustering for accurate color representation.
    """
    # Remove data URL prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    # Decode and open image
    image_data = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode in ("RGBA", "P", "LA", "L"):
        # Create white background for transparency
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        else:
            image = image.convert("RGB")

    logger.info(f"Image size: {image.size}, mode: {image.mode}")

    # Resize for processing - keep reasonable size for accuracy
    max_size = 256
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    width, height = image.size
    pixels = list(image.getdata())
    total_pixels = len(pixels)

    logger.info(f"Processing {total_pixels} pixels")

    # Sample pixels evenly across the image for better representation
    # Instead of just counting, we'll bin colors in HSV space
    color_bins = {}

    for pixel in pixels:
        r, g, b = pixel[:3]

        # Convert to HSV for better color grouping
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)

        # Quantize in HSV space (more perceptually uniform)
        # Hue: 12 bins (30 degrees each)
        # Saturation: 4 bins
        # Value: 4 bins
        h_bin = int(h * 12) % 12
        s_bin = min(int(s * 4), 3)
        v_bin = min(int(v * 4), 3)

        bin_key = (h_bin, s_bin, v_bin)

        if bin_key not in color_bins:
            color_bins[bin_key] = {"count": 0, "r_sum": 0, "g_sum": 0, "b_sum": 0}

        color_bins[bin_key]["count"] += 1
        color_bins[bin_key]["r_sum"] += r
        color_bins[bin_key]["g_sum"] += g
        color_bins[bin_key]["b_sum"] += b

    # Sort bins by count and get average color for each
    sorted_bins = sorted(color_bins.items(), key=lambda x: x[1]["count"], reverse=True)

    logger.info(f"Found {len(sorted_bins)} color bins")

    # Extract diverse colors
    extracted_colors = []

    for bin_key, bin_data in sorted_bins:
        if len(extracted_colors) >= num_colors:
            break

        count = bin_data["count"]
        # Skip if less than 1% of image
        if count < total_pixels * 0.01 and len(extracted_colors) > 0:
            continue

        # Calculate average color for this bin
        avg_r = int(bin_data["r_sum"] / count)
        avg_g = int(bin_data["g_sum"] / count)
        avg_b = int(bin_data["b_sum"] / count)

        color = (avg_r, avg_g, avg_b)

        # Check for uniqueness
        is_unique = True
        for existing in extracted_colors:
            if color_distance(color, existing) < 60:
                is_unique = False
                break

        if is_unique:
            extracted_colors.append(color)
            hex_color = rgb_to_hex(color)
            desc = describe_color(color)
            logger.info(f"Extracted: {hex_color} ({desc}) - {count} pixels ({count*100/total_pixels:.1f}%)")

    # If we still need more colors, relax constraints
    if len(extracted_colors) < 3:
        logger.info("Relaxing uniqueness constraints...")
        for bin_key, bin_data in sorted_bins:
            if len(extracted_colors) >= num_colors:
                break
            count = bin_data["count"]
            avg_r = int(bin_data["r_sum"] / count)
            avg_g = int(bin_data["g_sum"] / count)
            avg_b = int(bin_data["b_sum"] / count)
            color = (avg_r, avg_g, avg_b)

            if color not in extracted_colors:
                is_unique = True
                for existing in extracted_colors:
                    if color_distance(color, existing) < 30:
                        is_unique = False
                        break
                if is_unique:
                    extracted_colors.append(color)

    # Convert to hex
    hex_colors = [rgb_to_hex(c) for c in extracted_colors]
    logger.info(f"Final colors: {hex_colors}")

    # Split into dominant (first 3) and accents (rest)
    dominant = hex_colors[:3] if len(hex_colors) >= 3 else hex_colors
    accents = hex_colors[3:5] if len(hex_colors) > 3 else []

    # Generate color descriptions
    descriptions = [describe_color(c) for c in extracted_colors[:3]]

    # Calculate overall saturation and value
    avg_saturation = calculate_avg_saturation(extracted_colors[:5])
    value_range = calculate_value_range(extracted_colors[:5])

    return {
        "dominant_colors": dominant,
        "accents": accents,
        "color_descriptions": descriptions,
        "saturation": avg_saturation,
        "value_range": value_range,
    }


def rgb_to_hex(rgb: tuple) -> str:
    """Convert RGB tuple to hex string."""
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])


def hex_to_rgb(hex_str: str) -> tuple:
    """Convert hex string to RGB tuple."""
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def color_distance(c1: tuple, c2: tuple) -> float:
    """Calculate Euclidean distance between two RGB colors."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5


def rgb_to_hsv(rgb: tuple) -> tuple:
    """Convert RGB to HSV (0-360, 0-1, 0-1)."""
    r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360, s, v)


def describe_color(rgb: tuple) -> str:
    """Generate a human-readable color description."""
    h, s, v = rgb_to_hsv(rgb)

    # Check for grayscale first
    if s < 0.12:
        if v < 0.15:
            return "black"
        elif v < 0.30:
            return "charcoal"
        elif v < 0.50:
            return "dark gray"
        elif v < 0.70:
            return "gray"
        elif v < 0.85:
            return "light gray"
        else:
            return "white"

    # Determine hue name with more granularity
    hue_names = [
        (15, "red"),
        (35, "vermillion"),
        (50, "orange"),
        (65, "amber"),
        (80, "yellow"),
        (95, "lime"),
        (140, "green"),
        (170, "teal"),
        (195, "cyan"),
        (220, "azure"),
        (250, "blue"),
        (275, "violet"),
        (300, "purple"),
        (330, "magenta"),
        (345, "rose"),
        (360, "red"),
    ]

    hue_name = "red"
    for threshold, name in hue_names:
        if h < threshold:
            hue_name = name
            break

    # Build description based on saturation and value
    if s > 0.7:
        # Vivid/saturated colors
        if v > 0.7:
            return f"bright {hue_name}"
        elif v > 0.4:
            return f"vivid {hue_name}"
        else:
            return f"deep {hue_name}"
    elif s > 0.4:
        # Moderate saturation
        if v > 0.7:
            return f"soft {hue_name}"
        elif v > 0.4:
            return hue_name
        else:
            return f"dark {hue_name}"
    else:
        # Muted/desaturated
        if v > 0.7:
            return f"pale {hue_name}"
        elif v > 0.4:
            return f"dusty {hue_name}"
        else:
            return f"muted dark {hue_name}"


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
            return "high contrast"
        elif min_v < 0.3:
            return "dark with highlights"
        else:
            return "mid to bright"
