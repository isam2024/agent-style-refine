"""
Style Explorer Service

Divergent exploration of style space - the opposite of the trainer.
Instead of converging to match a reference, this service intentionally
mutates and diverges to discover new aesthetic directions.
"""
import json
import logging
import random
from pathlib import Path

from backend.models.schemas import (
    StyleProfile,
    MutationStrategy,
    ExplorationScores,
    ExplorationSnapshotResponse,
)
from backend.services.vlm import vlm_service
from backend.services.comfyui import comfyui_service
from backend.services.storage import storage_service
from backend.services.extractor import style_extractor
from backend.services.prompt_writer import PromptWriter
from backend.websocket import manager

logger = logging.getLogger(__name__)


# Donor styles for crossover mutation
DONOR_STYLES = [
    ("1970s psychedelic poster", "psychedelic swirling colors, vibrant neon, trippy patterns, groovy typography"),
    ("Japanese woodblock print", "ukiyo-e style, flat colors, bold outlines, traditional Japanese aesthetics"),
    ("Soviet constructivist propaganda", "bold geometric shapes, red and black, diagonal compositions, revolutionary"),
    ("Art nouveau organic curves", "flowing organic lines, natural forms, decorative ornament, elegant curves"),
    ("Brutalist concrete architecture", "raw concrete, massive geometric forms, stark shadows, imposing scale"),
    ("Vaporwave aesthetic", "pastel pinks and cyans, glitch effects, 90s nostalgia, digital artifacts"),
    ("Medieval illuminated manuscript", "gold leaf, intricate borders, rich colors, calligraphic elements"),
    ("Glitch art corruption", "digital distortion, pixel sorting, data moshing, corrupted imagery"),
    ("Infrared photography", "false colors, red foliage, dark skies, surreal landscape"),
    ("Blueprint technical drawing", "white lines on blue, technical precision, schematic style, annotations"),
    ("Noir film aesthetic", "high contrast black and white, dramatic shadows, moody atmosphere"),
    ("Pop art bold colors", "ben-day dots, bold outlines, primary colors, comic book style"),
    ("Impressionist painting", "visible brushstrokes, light and color, atmospheric, soft edges"),
    ("Cyberpunk neon city", "neon lights, rain-slicked streets, holographic displays, dystopian"),
    ("Watercolor wash", "soft gradients, bleeding colors, wet-on-wet technique, translucent"),
]

# Characteristic inversions for inversion mutation
CHARACTERISTIC_INVERSIONS = {
    "warm colors": ("cold colors", {"palette": {"color_descriptions": ["icy blue", "frost white", "cool gray", "arctic cyan"]}}),
    "cold colors": ("warm colors", {"palette": {"color_descriptions": ["golden amber", "sunset orange", "warm coral", "honey"]}}),
    "organic shapes": ("geometric shapes", {"line_and_shape": {"shape_language": "strict geometric forms, mathematical precision, angular shapes"}}),
    "geometric shapes": ("organic shapes", {"line_and_shape": {"shape_language": "flowing organic curves, natural forms, biomorphic shapes"}}),
    "soft lighting": ("harsh lighting", {"lighting": {"lighting_type": "harsh dramatic lighting, strong shadows, high contrast"}}),
    "harsh lighting": ("soft lighting", {"lighting": {"lighting_type": "soft diffused lighting, gentle gradients, ambient glow"}}),
    "busy composition": ("minimal composition", {"composition": {"framing": "minimal, vast empty space, isolated subject"}}),
    "minimal": ("maximalist", {"composition": {"framing": "horror vacui, densely packed, rich detail everywhere"}}),
    "realistic": ("abstract", {"line_and_shape": {"shape_language": "abstract forms, non-representational, pure shape and color"}}),
    "abstract": ("realistic", {"line_and_shape": {"shape_language": "photorealistic rendering, accurate proportions, lifelike detail"}}),
    "smooth textures": ("rough textures", {"texture": {"surface": "extremely rough, heavily textured, gritty surface"}}),
    "rough": ("smooth", {"texture": {"surface": "glass smooth, pristine surface, polished finish"}}),
    "high saturation": ("desaturated", {"palette": {"saturation": "very low", "color_descriptions": ["muted gray", "pale", "washed out"]}}),
    "desaturated": ("hypersaturated", {"palette": {"saturation": "extreme", "color_descriptions": ["neon", "electric", "vivid"]}}),
    "dark mood": ("bright mood", {"lighting": {"lighting_type": "bright, cheerful, high-key lighting", "shadows": "minimal, soft"}}),
    "bright": ("dark", {"lighting": {"lighting_type": "dark, moody, low-key lighting", "shadows": "deep, dramatic"}}),
    "flat": ("dimensional", {"lighting": {"lighting_type": "dramatic dimensional lighting", "shadows": "strong directional shadows"}}),
    "detailed": ("simplified", {"line_and_shape": {"line_quality": "simplified forms, reduced detail, essential shapes only"}}),
}

# Dimension extremes for random dimension push mutation
DIMENSION_EXTREMES = {
    "palette.saturation": [
        ("completely desaturated, monochrome, grayscale", "desaturated"),
        ("hypersaturated, neon, electric colors, vivid", "hypersaturated"),
    ],
    "palette.temperature": [
        ("freezing cold palette, icy blues, arctic whites, winter tones", "cold"),
        ("burning hot palette, volcanic oranges, fire reds, scorching yellows", "hot"),
    ],
    "palette.contrast": [
        ("flat, no contrast, uniform values, hazy", "low_contrast"),
        ("extreme high contrast, stark black and white, dramatic shadows", "high_contrast"),
    ],
    "line_and_shape.edges": [
        ("razor sharp vector edges, crisp lines, hard boundaries", "sharp_edges"),
        ("completely dissolved edges, blurry, soft focus, dreamlike", "soft_edges"),
    ],
    "line_and_shape.complexity": [
        ("minimal, single shape, vast emptiness, simple forms", "minimal"),
        ("infinitely complex, fractal detail, intricate patterns, ornate", "complex"),
    ],
    "texture.surface": [
        ("glass smooth, perfect render, pristine surface, polished", "smooth"),
        ("extremely rough, distressed, weathered, gritty texture", "rough"),
    ],
    "texture.noise": [
        ("clinical clean, noise-free, pure colors, smooth gradients", "clean"),
        ("heavy grain, static, film noise, analog texture", "noisy"),
    ],
    "lighting.intensity": [
        ("pitch black shadows, extreme darkness, noir, low-key", "dark"),
        ("blown out, overexposed, bright white, high-key lighting", "bright"),
    ],
    "lighting.direction": [
        ("flat frontal lighting, even illumination, shadowless", "frontal"),
        ("extreme side lighting, dramatic shadows, chiaroscuro", "side"),
    ],
    "composition.density": [
        ("single element, vast empty space, isolation, minimalist", "sparse"),
        ("horror vacui, packed full, dense detail, maximalist", "dense"),
    ],
    "composition.symmetry": [
        ("perfect mathematical symmetry, mirror balance, geometric order", "symmetric"),
        ("chaotic asymmetry, random placement, organic disorder", "asymmetric"),
    ],
}

# Era/decade aesthetics for time_shift mutation
ERA_AESTHETICS = [
    ("1920s Art Deco", {
        "palette": {"color_descriptions": ["gold", "black", "cream", "jade green"], "saturation": "medium-high"},
        "line_and_shape": {"shape_language": "geometric sunbursts, chevrons, stepped forms, symmetrical patterns", "line_quality": "bold clean lines, sharp angles"},
        "texture": {"surface": "smooth lacquered finish, metallic accents"},
        "lighting": {"lighting_type": "glamorous dramatic lighting, theatrical"}
    }),
    ("1950s Mid-Century Modern", {
        "palette": {"color_descriptions": ["avocado green", "burnt orange", "mustard yellow", "teal"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "organic boomerang shapes, atomic starbursts, tapered legs", "line_quality": "clean minimalist lines"},
        "texture": {"surface": "smooth plastic, polished wood grain"},
        "lighting": {"lighting_type": "bright optimistic lighting, soft shadows"}
    }),
    ("1960s Psychedelic", {
        "palette": {"color_descriptions": ["electric purple", "hot pink", "acid green", "orange"], "saturation": "extreme"},
        "line_and_shape": {"shape_language": "swirling spirals, melting forms, paisley patterns", "line_quality": "flowing wavy lines"},
        "texture": {"surface": "trippy undulating surfaces, op-art patterns"},
        "lighting": {"lighting_type": "black light glow, fluorescent"}
    }),
    ("1970s Disco/Retro", {
        "palette": {"color_descriptions": ["gold", "brown", "orange", "cream"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "curved flowing forms, rounded corners, sunburst patterns", "line_quality": "soft organic lines"},
        "texture": {"surface": "shag texture, velvet, chrome reflections"},
        "lighting": {"lighting_type": "warm amber lighting, disco ball reflections"}
    }),
    ("1980s Memphis Design", {
        "palette": {"color_descriptions": ["hot pink", "electric blue", "yellow", "mint green"], "saturation": "high"},
        "line_and_shape": {"shape_language": "squiggles, confetti shapes, geometric primitives", "line_quality": "bold graphic lines, zigzags"},
        "texture": {"surface": "terrazzo patterns, bold graphic patterns"},
        "lighting": {"lighting_type": "flat even lighting, minimal shadows"}
    }),
    ("1990s Grunge", {
        "palette": {"color_descriptions": ["muted olive", "dirty brown", "faded black", "rust"], "saturation": "low"},
        "line_and_shape": {"shape_language": "distressed torn edges, raw unfinished forms", "line_quality": "rough scratchy lines"},
        "texture": {"surface": "worn weathered texture, distressed surfaces, paper grain"},
        "lighting": {"lighting_type": "dim moody lighting, harsh shadows"}
    }),
    ("2000s Y2K/Futurism", {
        "palette": {"color_descriptions": ["silver chrome", "translucent blue", "hot pink", "white"], "saturation": "medium-high"},
        "line_and_shape": {"shape_language": "bubble shapes, swooshes, organic curves", "line_quality": "sleek glossy lines"},
        "texture": {"surface": "glossy plastic, chrome reflections, translucent materials"},
        "lighting": {"lighting_type": "bright studio lighting, soft gradients"}
    }),
    ("Victorian Gothic", {
        "palette": {"color_descriptions": ["deep burgundy", "forest green", "gold", "black"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "ornate filigree, pointed arches, intricate scrollwork", "line_quality": "elaborate detailed lines"},
        "texture": {"surface": "rich velvet, aged patina, ornate carvings"},
        "lighting": {"lighting_type": "candlelit dramatic lighting, deep shadows"}
    }),
    ("Renaissance Classical", {
        "palette": {"color_descriptions": ["ochre", "ultramarine blue", "vermillion red", "earth brown"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "balanced proportions, classical columns, flowing drapery", "line_quality": "refined graceful lines"},
        "texture": {"surface": "oil paint texture, canvas grain, sfumato blending"},
        "lighting": {"lighting_type": "chiaroscuro dramatic lighting, divine rays"}
    }),
    ("Futuristic 2100", {
        "palette": {"color_descriptions": ["holographic iridescent", "void black", "plasma blue", "neon white"], "saturation": "high"},
        "line_and_shape": {"shape_language": "impossible geometry, floating forms, fractals", "line_quality": "razor precise lines, digital perfection"},
        "texture": {"surface": "holographic shimmer, energy fields, crystalline"},
        "lighting": {"lighting_type": "bioluminescent glow, volumetric light rays"}
    }),
]

# Artistic mediums for medium_swap mutation
ARTISTIC_MEDIUMS = [
    ("Oil painting", {
        "texture": {"surface": "thick impasto brushstrokes, visible paint texture, canvas grain"},
        "line_and_shape": {"line_quality": "soft blended edges, painterly strokes"},
        "lighting": {"lighting_type": "rich glazed lighting, deep luminous shadows"}
    }),
    ("Watercolor", {
        "texture": {"surface": "soft bleeding washes, wet-on-wet blending, paper texture"},
        "palette": {"saturation": "medium", "color_descriptions": ["soft washes", "translucent layers", "granulating pigments"]},
        "lighting": {"lighting_type": "soft diffused light, white paper showing through"}
    }),
    ("Pencil sketch", {
        "texture": {"surface": "graphite shading, paper grain, crosshatching"},
        "palette": {"saturation": "very low", "color_descriptions": ["graphite gray", "charcoal black", "paper white"]},
        "line_and_shape": {"line_quality": "sketchy gestural lines, varied line weight"}
    }),
    ("Ink drawing", {
        "texture": {"surface": "stark black ink, crisp edges, occasional splatter"},
        "palette": {"saturation": "very low", "color_descriptions": ["pure black", "stark white"]},
        "line_and_shape": {"line_quality": "bold confident ink lines, hatching for tone"}
    }),
    ("Pastel chalk", {
        "texture": {"surface": "soft chalky texture, smudged blending, textured paper"},
        "palette": {"saturation": "medium-low"},
        "line_and_shape": {"line_quality": "soft fuzzy edges, blended strokes"}
    }),
    ("Digital vector", {
        "texture": {"surface": "perfectly smooth, flat color fills, no texture"},
        "line_and_shape": {"line_quality": "crisp vector edges, mathematically perfect curves"},
        "lighting": {"lighting_type": "flat graphic lighting, no gradients"}
    }),
    ("Woodcut print", {
        "texture": {"surface": "wood grain texture, rough carved edges, ink bleed"},
        "palette": {"color_descriptions": ["black ink", "natural paper", "limited colors"]},
        "line_and_shape": {"line_quality": "bold carved lines, stark contrast, rough edges"}
    }),
    ("Stained glass", {
        "texture": {"surface": "translucent colored glass, lead lines between sections"},
        "palette": {"saturation": "high", "color_descriptions": ["jewel tones", "ruby red", "sapphire blue", "emerald green"]},
        "line_and_shape": {"line_quality": "bold black outlines dividing color sections"},
        "lighting": {"lighting_type": "backlit glowing, light shining through"}
    }),
    ("Mosaic tiles", {
        "texture": {"surface": "small tile fragments, grout lines, tessellated pattern"},
        "line_and_shape": {"shape_language": "fragmented tessellations, small geometric pieces"},
        "lighting": {"lighting_type": "varied reflections from tile angles"}
    }),
    ("Spray paint graffiti", {
        "texture": {"surface": "spray paint drips, overspray haze, wall texture"},
        "palette": {"saturation": "high"},
        "line_and_shape": {"line_quality": "bold tags, sharp stencil edges, dripping paint"}
    }),
    ("3D render", {
        "texture": {"surface": "smooth CG surface, subsurface scattering, perfect materials"},
        "lighting": {"lighting_type": "studio HDRI lighting, global illumination, soft shadows"},
        "line_and_shape": {"line_quality": "smooth bezier curves, perfect geometry"}
    }),
    ("Collage cutouts", {
        "texture": {"surface": "torn paper edges, layered materials, visible glue"},
        "line_and_shape": {"shape_language": "cut paper shapes, layered compositions, mixed materials"},
        "lighting": {"lighting_type": "flat even lighting, some paper shadows"}
    }),
]

# Moods/emotions for mood_shift mutation
MOOD_PALETTE = [
    ("Serene/Peaceful", {
        "palette": {"color_descriptions": ["soft blue", "pale green", "cream white", "gentle lavender"], "saturation": "low"},
        "lighting": {"lighting_type": "soft diffused golden hour light, gentle gradients", "shadows": "barely visible, soft"},
        "texture": {"surface": "smooth calm surfaces, gentle ripples"},
        "composition": {"framing": "balanced, open space, room to breathe"}
    }),
    ("Anxious/Tense", {
        "palette": {"color_descriptions": ["sickly yellow-green", "harsh white", "cold gray", "warning red"], "saturation": "medium"},
        "lighting": {"lighting_type": "harsh fluorescent, uneven lighting, flickering", "shadows": "sharp jagged shadows"},
        "texture": {"surface": "gritty uneasy texture, static noise"},
        "composition": {"framing": "tight claustrophobic framing, off-balance"}
    }),
    ("Melancholic/Sad", {
        "palette": {"color_descriptions": ["muted blue", "faded gray", "desaturated purple", "rain-washed"], "saturation": "low"},
        "lighting": {"lighting_type": "overcast diffused light, no direct sun", "shadows": "soft undefined shadows"},
        "texture": {"surface": "slightly blurred, rain-streaked, foggy"},
        "composition": {"framing": "isolated subject, empty space, downward gaze"}
    }),
    ("Joyful/Celebratory", {
        "palette": {"color_descriptions": ["sunshine yellow", "coral pink", "sky blue", "fresh green"], "saturation": "high"},
        "lighting": {"lighting_type": "bright cheerful sunlight, sparkles, warm", "shadows": "light playful shadows"},
        "texture": {"surface": "confetti texture, glossy, festive"},
        "composition": {"framing": "dynamic upward movement, expansive"}
    }),
    ("Mysterious/Enigmatic", {
        "palette": {"color_descriptions": ["deep purple", "midnight blue", "smoky gray", "glowing amber"], "saturation": "medium"},
        "lighting": {"lighting_type": "dramatic rim lighting, obscured source, foggy", "shadows": "deep obscuring shadows"},
        "texture": {"surface": "smoky haze, mysterious fog, half-hidden"},
        "composition": {"framing": "partially obscured, questions unanswered"}
    }),
    ("Aggressive/Intense", {
        "palette": {"color_descriptions": ["blood red", "harsh black", "electric yellow", "bruise purple"], "saturation": "high"},
        "lighting": {"lighting_type": "harsh stark lighting, extreme contrast", "shadows": "sharp cutting shadows"},
        "texture": {"surface": "rough aggressive texture, sharp edges"},
        "composition": {"framing": "confrontational, in-your-face, dynamic angles"}
    }),
    ("Nostalgic/Wistful", {
        "palette": {"color_descriptions": ["sepia brown", "faded gold", "dusty rose", "aged cream"], "saturation": "low"},
        "lighting": {"lighting_type": "warm afternoon light, lens flare, hazy", "shadows": "soft warm shadows"},
        "texture": {"surface": "film grain, slight blur, aged patina"},
        "composition": {"framing": "snapshot composition, memory-like"}
    }),
    ("Eerie/Unsettling", {
        "palette": {"color_descriptions": ["corpse pale", "sickly green", "dried blood", "void black"], "saturation": "low"},
        "lighting": {"lighting_type": "unnatural lighting angles, wrong color temperature", "shadows": "shadows that don't match"},
        "texture": {"surface": "uncanny valley smooth, wrongly textured"},
        "composition": {"framing": "something wrong in the composition, off-center"}
    }),
    ("Romantic/Dreamy", {
        "palette": {"color_descriptions": ["rose pink", "soft peach", "champagne gold", "blush"], "saturation": "medium-low"},
        "lighting": {"lighting_type": "soft backlighting, lens flare, bokeh", "shadows": "minimal, glowing edges"},
        "texture": {"surface": "soft focus, dreamy blur, silky"},
        "composition": {"framing": "intimate close framing, soft vignette"}
    }),
    ("Heroic/Epic", {
        "palette": {"color_descriptions": ["gold", "royal blue", "crimson red", "silver"], "saturation": "high"},
        "lighting": {"lighting_type": "dramatic god rays, epic backlighting", "shadows": "bold heroic shadows"},
        "texture": {"surface": "gleaming polished surfaces, flowing capes"},
        "composition": {"framing": "low angle looking up, monumental scale"}
    }),
]

# Scale/perspective shifts for scale_warp mutation
SCALE_PERSPECTIVES = [
    ("Macro/Microscopic", {
        "composition": {"framing": "extreme close-up, macro lens perspective, tiny world made huge", "camera": "macro lens, shallow depth of field"},
        "texture": {"surface": "intricate surface details visible, usually invisible textures revealed"},
        "lighting": {"lighting_type": "focused spot lighting, dramatic depth"}
    }),
    ("Cosmic/Astronomical", {
        "composition": {"framing": "vast cosmic scale, planetary perspective, infinite space", "camera": "pulled back to astronomical scale"},
        "palette": {"color_descriptions": ["nebula purple", "star white", "void black", "cosmic blue"]},
        "lighting": {"lighting_type": "distant star illumination, rim-lit planets, space lighting"}
    }),
    ("Miniature/Tilt-shift", {
        "composition": {"framing": "bird's eye view, miniature world effect, model-like", "camera": "overhead tilt-shift lens effect"},
        "texture": {"surface": "toy-like surfaces, model train aesthetic"},
        "lighting": {"lighting_type": "bright even lighting like photography studio"}
    }),
    ("Monumental/Colossal", {
        "composition": {"framing": "looking up at towering scale, monuments dwarfing viewer", "camera": "extreme low angle"},
        "texture": {"surface": "massive stone texture, architectural grandeur"},
        "lighting": {"lighting_type": "dramatic sky lighting, clouds swirling around peaks"}
    }),
    ("Intimate/Personal", {
        "composition": {"framing": "close personal space, intimate portrait distance", "camera": "portrait lens, eye level"},
        "texture": {"surface": "skin texture visible, personal details"},
        "lighting": {"lighting_type": "soft intimate lighting, gentle on subject"}
    }),
    ("Aerial/Bird's Eye", {
        "composition": {"framing": "directly overhead view, map-like perspective", "camera": "drone/satellite view"},
        "texture": {"surface": "landscape patterns, agricultural grids, city blocks"},
        "lighting": {"lighting_type": "midday sun, minimal shadows, even coverage"}
    }),
    ("Underwater/Submerged", {
        "composition": {"framing": "underwater perspective, looking through water", "camera": "underwater housing distortion"},
        "palette": {"color_descriptions": ["aqua blue", "filtered sunlight", "deep blue", "bioluminescent"]},
        "texture": {"surface": "caustic light patterns, bubbles, murky depths"},
        "lighting": {"lighting_type": "filtered sunbeams, caustic patterns, underwater diffusion"}
    }),
    ("Worm's Eye/Ground Level", {
        "composition": {"framing": "ground level looking up, grass blade perspective", "camera": "ground level ultra wide"},
        "texture": {"surface": "ground texture prominent, towering elements above"},
        "lighting": {"lighting_type": "dramatic sky backdrop, silhouettes against light"}
    }),
]

# Decay/entropy levels for decay mutation
DECAY_LEVELS = [
    ("Pristine to Weathered", {
        "texture": {"surface": "light wear, slight patina, gentle aging", "noise_level": "medium"},
        "palette": {"color_descriptions": ["slightly faded colors", "warm aged tones"]},
        "lighting": {"lighting_type": "warm aged lighting, slight haze"}
    }),
    ("Weathered to Rusted", {
        "texture": {"surface": "rust spots, peeling paint, oxidation, corrosion", "noise_level": "high"},
        "palette": {"color_descriptions": ["rust orange", "oxidized green", "faded", "stained"]},
        "lighting": {"lighting_type": "harsh revealing light, showing all imperfections"}
    }),
    ("Rusted to Ruined", {
        "texture": {"surface": "crumbling edges, broken pieces, structural decay, holes"},
        "palette": {"color_descriptions": ["gray rubble", "exposed materials", "dust", "debris"]},
        "composition": {"framing": "broken framing, incomplete forms, missing pieces"}
    }),
    ("Ruined to Overgrown", {
        "texture": {"surface": "vines creeping, moss covering, nature reclaiming", "special_effects": ["plant growth", "organic intrusion"]},
        "palette": {"color_descriptions": ["green moss", "brown decay", "flowering weeds", "lichen"]},
        "lighting": {"lighting_type": "dappled light through foliage, nature's soft light"}
    }),
    ("Overgrown to Ancient", {
        "texture": {"surface": "completely covered in vegetation, geological timescale"},
        "palette": {"color_descriptions": ["forest green", "stone gray", "earth brown", "ancient moss"]},
        "composition": {"framing": "barely recognizable original form, consumed by time"}
    }),
    ("Digital Corruption", {
        "texture": {"surface": "pixel corruption, data decay, glitch artifacts", "special_effects": ["glitch", "datamosh", "compression artifacts"]},
        "palette": {"color_descriptions": ["shifted RGB", "banding artifacts", "wrong colors"]},
        "line_and_shape": {"shape_language": "fragmented, displaced blocks, stretched pixels"}
    }),
    ("Burned/Charred", {
        "texture": {"surface": "charred black, ash gray, ember glow at edges"},
        "palette": {"color_descriptions": ["charcoal black", "ash gray", "ember orange", "smoke"]},
        "lighting": {"lighting_type": "dim with occasional ember glow, smoke-filled"}
    }),
    ("Frozen/Crystallized", {
        "texture": {"surface": "ice crystals forming, frost patterns, frozen in time"},
        "palette": {"color_descriptions": ["ice blue", "frost white", "frozen gray", "crystal clear"]},
        "lighting": {"lighting_type": "cold blue light, crystalline reflections"}
    }),
]

# Cultural aesthetics for culture_shift mutation
CULTURAL_AESTHETICS = [
    ("Japanese Wabi-Sabi", {
        "palette": {"color_descriptions": ["natural earth tones", "aged patina", "muted greens", "weathered wood"], "saturation": "low"},
        "texture": {"surface": "imperfect beauty, natural materials, handcraft marks"},
        "composition": {"framing": "asymmetrical balance, negative space, simplicity"},
        "lighting": {"lighting_type": "soft natural light, paper lantern glow"}
    }),
    ("Moroccan/Islamic Geometric", {
        "palette": {"color_descriptions": ["cobalt blue", "turquoise", "terracotta", "gold"], "saturation": "high"},
        "line_and_shape": {"shape_language": "intricate geometric tessellations, arabesque patterns, eight-pointed stars"},
        "texture": {"surface": "zellige tiles, carved plaster, brass inlay"},
        "lighting": {"lighting_type": "warm desert light, filtered through screens"}
    }),
    ("Scandinavian Minimalism", {
        "palette": {"color_descriptions": ["white", "pale wood", "soft gray", "muted blue"], "saturation": "very low"},
        "texture": {"surface": "smooth wood, clean surfaces, cozy textiles"},
        "composition": {"framing": "clean lines, functional simplicity, hygge warmth"},
        "lighting": {"lighting_type": "bright northern light, candlelit warmth"}
    }),
    ("Indian/Hindu Vibrant", {
        "palette": {"color_descriptions": ["saffron orange", "hot pink", "royal purple", "gold"], "saturation": "extreme"},
        "texture": {"surface": "rich embroidery, intricate patterns, metallic threads"},
        "line_and_shape": {"shape_language": "mandala patterns, lotus motifs, ornate borders"},
        "lighting": {"lighting_type": "warm festive lighting, oil lamp glow, diya flames"}
    }),
    ("Mexican Dia de los Muertos", {
        "palette": {"color_descriptions": ["marigold orange", "hot pink", "turquoise", "purple"], "saturation": "high"},
        "line_and_shape": {"shape_language": "sugar skull patterns, papel picado, floral motifs"},
        "texture": {"surface": "papel picado texture, painted ceramics, embroidered cloth"},
        "lighting": {"lighting_type": "warm candlelit, altar lighting, festive"}
    }),
    ("African Tribal/Kente", {
        "palette": {"color_descriptions": ["bold yellow", "forest green", "deep red", "royal blue"], "saturation": "high"},
        "line_and_shape": {"shape_language": "bold geometric patterns, tribal symbols, kente stripes"},
        "texture": {"surface": "woven textile, beadwork, carved wood"},
        "lighting": {"lighting_type": "warm savanna sun, golden hour light"}
    }),
    ("Chinese Traditional", {
        "palette": {"color_descriptions": ["lucky red", "gold", "jade green", "imperial yellow"], "saturation": "medium-high"},
        "line_and_shape": {"shape_language": "dragon motifs, cloud patterns, calligraphic strokes"},
        "texture": {"surface": "silk texture, lacquer shine, porcelain smooth"},
        "lighting": {"lighting_type": "soft lantern light, moon glow, misty atmosphere"}
    }),
    ("Persian/Iranian", {
        "palette": {"color_descriptions": ["lapis blue", "turquoise", "saffron yellow", "pomegranate red"], "saturation": "medium-high"},
        "line_and_shape": {"shape_language": "floral arabesques, paisley patterns, miniature painting style"},
        "texture": {"surface": "carpet texture, enamel work, calligraphy"},
        "lighting": {"lighting_type": "warm golden light, garden pavilion atmosphere"}
    }),
    ("Celtic/Irish", {
        "palette": {"color_descriptions": ["forest green", "gold", "deep blue", "earth brown"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "interlaced knots, spirals, zoomorphic designs"},
        "texture": {"surface": "carved stone, illuminated manuscript, metalwork"},
        "lighting": {"lighting_type": "misty emerald isle light, dramatic stormy skies"}
    }),
    ("Aboriginal Australian", {
        "palette": {"color_descriptions": ["ochre red", "burnt sienna", "white", "yellow"], "saturation": "medium"},
        "line_and_shape": {"shape_language": "dot painting patterns, dreamtime symbols, concentric circles"},
        "texture": {"surface": "sandy texture, bark painting, rock surface"},
        "lighting": {"lighting_type": "harsh outback sun, red desert light"}
    }),
]

# Constraint types for constrain mutation
CONSTRAINT_TYPES = [
    ("Monochrome Single Hue", lambda profile: {
        "palette": {
            "color_descriptions": [f"{random.choice(['blue', 'red', 'green', 'purple', 'orange', 'yellow'])} only - all shades"],
            "saturation": random.choice(["medium", "high"]),
            "dominant_colors": [],
            "accents": []
        }
    }),
    ("Duotone", lambda profile: {
        "palette": {
            "color_descriptions": random.choice([
                ["deep blue", "bright orange"],
                ["hot pink", "cyan"],
                ["purple", "yellow"],
                ["red", "teal"],
                ["black", "gold"]
            ]),
            "saturation": "high"
        }
    }),
    ("Basic Shapes Only", lambda profile: {
        "line_and_shape": {
            "shape_language": "only circles, squares, and triangles - basic geometric primitives",
            "line_quality": "simple clean lines, no complex curves"
        }
    }),
    ("Horizontal Lines Only", lambda profile: {
        "line_and_shape": {
            "shape_language": "horizontal lines and bands only, no verticals or diagonals",
            "line_quality": "strictly horizontal strokes"
        },
        "composition": {"framing": "horizontal banding, layered stripes"}
    }),
    ("No Curves", lambda profile: {
        "line_and_shape": {
            "shape_language": "angular only, no curves allowed, faceted forms",
            "line_quality": "straight lines only, sharp angles"
        }
    }),
    ("Single Light Source", lambda profile: {
        "lighting": {
            "lighting_type": "single harsh spotlight, all light from one point",
            "shadows": "dramatic single-source shadows, no fill light"
        }
    }),
    ("Flat No Shadows", lambda profile: {
        "lighting": {
            "lighting_type": "completely flat lighting, no depth",
            "shadows": "no shadows whatsoever"
        },
        "texture": {"surface": "flat color fills only"}
    }),
    ("Three Colors Maximum", lambda profile: {
        "palette": {
            "color_descriptions": random.choice([
                ["red", "white", "black"],
                ["blue", "yellow", "white"],
                ["green", "brown", "cream"],
                ["purple", "gold", "black"]
            ]),
            "saturation": "medium"
        }
    }),
]

# ============================================================
# NEW MUTATION DATA STRUCTURES
# ============================================================

# Topology/spatial distortions for topology_fold mutation
TOPOLOGY_FOLDS = [
    ("Escher Impossible", {
        "composition": {"framing": "impossible geometry, Escher-like stairs that loop forever, contradictory perspectives"},
        "line_and_shape": {"shape_language": "paradoxical forms, infinite loops, penrose triangles"},
        "lighting": {"shadows": "shadows that defy the light source direction"}
    }),
    ("Recursive Loops", {
        "composition": {"framing": "recursive self-containing structures, image within image within image"},
        "line_and_shape": {"shape_language": "fractal-like self-similarity, nested forms"},
        "texture": {"special_effects": ["droste effect", "infinite recursion"]}
    }),
    ("Inverted Depth", {
        "composition": {"framing": "depth planes reversed, far appears near, near appears far"},
        "lighting": {"lighting_type": "atmospheric perspective inverted, distant objects brighter"}
    }),
    ("Möbius Surface", {
        "line_and_shape": {"shape_language": "one-sided surfaces, twisted continuous forms"},
        "composition": {"framing": "surfaces that twist through themselves"}
    }),
    ("Non-Euclidean Space", {
        "composition": {"framing": "curved space, parallel lines converging, angles that don't sum to 180"},
        "line_and_shape": {"shape_language": "hyperbolic geometry, spherical distortions"}
    }),
    ("Dimensional Leak", {
        "composition": {"framing": "4D objects projected into 3D, impossible intersections"},
        "texture": {"special_effects": ["tesseract shadows", "hypercube projections"]}
    }),
]

# Silhouette modifications for silhouette_shift mutation
SILHOUETTE_SHIFTS = [
    ("Spiked Contours", {
        "line_and_shape": {"shape_language": "jagged spiky outlines, aggressive pointed forms", "line_quality": "sharp angular edges on all silhouettes"}
    }),
    ("Rounded Soft", {
        "line_and_shape": {"shape_language": "all edges softened and rounded, pillow-like forms", "line_quality": "smooth curved outlines, no sharp corners"}
    }),
    ("Hollow Forms", {
        "line_and_shape": {"shape_language": "hollow silhouettes, outline-only forms, negative space within shapes"},
        "texture": {"surface": "translucent edges, see-through forms"}
    }),
    ("Fragmented Edges", {
        "line_and_shape": {"shape_language": "broken discontinuous outlines, shattered silhouettes", "line_quality": "interrupted fragmented edges"}
    }),
    ("Organic Tendrils", {
        "line_and_shape": {"shape_language": "flowing organic extensions, tentacle-like protrusions from all forms", "line_quality": "sinuous flowing edges"}
    }),
    ("Crystalline Facets", {
        "line_and_shape": {"shape_language": "geometric crystalline edges, faceted like cut gems", "line_quality": "sharp planar intersections"}
    }),
    ("Melting Drips", {
        "line_and_shape": {"shape_language": "dripping melting silhouettes, forms flowing downward", "line_quality": "liquid edges, gravity-affected outlines"}
    }),
    ("Pixelated Blocks", {
        "line_and_shape": {"shape_language": "blocky pixelated outlines, stair-step edges", "line_quality": "aliased digital edges"}
    }),
]

# Perspective distortions for perspective_drift mutation
PERSPECTIVE_DRIFTS = [
    ("Tilted Horizon", {
        "composition": {"framing": "dramatically tilted horizon, Dutch angle", "camera": "canted 15-30 degrees off level"}
    }),
    ("Multiple Vanishing Points", {
        "composition": {"framing": "conflicting vanishing points, each object has its own perspective", "camera": "cubist multiple viewpoints"}
    }),
    ("Sliding Vanishing", {
        "composition": {"framing": "vanishing point that shifts across the image, unstable perspective"}
    }),
    ("Fisheye Warp", {
        "composition": {"framing": "extreme fisheye barrel distortion, curved world", "camera": "ultra-wide fisheye lens"}
    }),
    ("Reverse Perspective", {
        "composition": {"framing": "Byzantine reverse perspective, distant objects larger than near ones"}
    }),
    ("Impossible Lens", {
        "composition": {"framing": "optical impossibilities, simultaneous telephoto and wide-angle characteristics", "camera": "lens that doesn't exist"}
    }),
    ("Vertigo Effect", {
        "composition": {"framing": "dolly zoom effect frozen in time, background and foreground scale mismatch"}
    }),
]

# Axis swaps for axis_swap mutation
AXIS_SWAPS = [
    ("Vertical to Horizontal", {
        "composition": {"framing": "what was vertical is now horizontal, rotated hierarchy"},
        "line_and_shape": {"shape_language": "forms stretched horizontally that should be vertical"}
    }),
    ("Center to Edge", {
        "composition": {"framing": "focal point moved to extreme edge, central emptiness", "negative_space_behavior": "center is void, importance at periphery"}
    }),
    ("Foreground Background Swap", {
        "composition": {"framing": "background becomes dominant, foreground minimized or blurred"}
    }),
    ("Light Dark Inversion", {
        "lighting": {"lighting_type": "inverted luminosity, bright shadows dark highlights"}
    }),
    ("Scale Hierarchy Flip", {
        "composition": {"framing": "small elements dominate, large elements recede"}
    }),
]

# Physics alterations for physics_bend mutation
PHYSICS_BENDS = [
    ("Upward Gravity", {
        "composition": {"framing": "everything drifts upward, gravity reversed"},
        "line_and_shape": {"shape_language": "forms stretching toward the sky, upward flow"}
    }),
    ("Liquid Light", {
        "lighting": {"lighting_type": "light behaves like liquid, pooling and dripping", "highlights": "light that flows and collects in puddles"}
    }),
    ("Elastic Solids", {
        "texture": {"surface": "solid materials stretch like rubber, bouncy deformation"},
        "line_and_shape": {"shape_language": "stretched elastic forms, cartoon physics"}
    }),
    ("Frozen Motion", {
        "texture": {"special_effects": ["frozen splashes", "suspended particles", "time-stopped physics"]},
        "composition": {"framing": "moment of impact frozen, physics paused mid-action"}
    }),
    ("Magnetic Fields", {
        "line_and_shape": {"shape_language": "forms aligned to invisible field lines, magnetic attraction visible"},
        "composition": {"framing": "objects clustering along force lines"}
    }),
    ("Zero Gravity Float", {
        "composition": {"framing": "everything floating freely, no up or down"},
        "line_and_shape": {"shape_language": "untethered floating forms, space-like drift"}
    }),
    ("Viscous Air", {
        "texture": {"surface": "air visible as thick medium, movement trails through syrupy atmosphere"},
        "line_and_shape": {"shape_language": "forms dragged through thick air, resistance visible"}
    }),
]

# Color clustering for chromatic_gravity mutation
CHROMATIC_GRAVITIES = [
    ("Warm Cluster", {
        "palette": {"color_descriptions": ["warm colors pulled together", "reds oranges yellows clustered", "cool colors pushed to edges"]},
        "composition": {"framing": "warm color mass in center, cool periphery"}
    }),
    ("Cool Cluster", {
        "palette": {"color_descriptions": ["cool colors pulled together", "blues greens purples clustered", "warm colors pushed to edges"]},
        "composition": {"framing": "cool color mass in center, warm periphery"}
    }),
    ("Chromatic Repulsion", {
        "palette": {"color_descriptions": ["colors maximally separated", "no adjacent similar hues", "each color isolated"]},
        "composition": {"framing": "colors distributed to avoid proximity"}
    }),
    ("Gradient Bands", {
        "palette": {"color_descriptions": ["colors organized in gradient bands", "smooth transitions in stripes"]},
        "composition": {"framing": "banded color organization"}
    }),
    ("Complementary Poles", {
        "palette": {"color_descriptions": ["complementary colors at opposite ends", "color tension across composition"]},
        "composition": {"framing": "color polarity, warm and cool poles"}
    }),
    ("Saturation Gravity", {
        "palette": {"color_descriptions": ["saturated colors cluster at focal point", "desaturated at edges"], "saturation": "extreme at center, low at edges"}
    }),
]

# Material swaps for material_transmute mutation
MATERIAL_TRANSMUTES = [
    ("Glass to Fur", {
        "texture": {"surface": "transparent surfaces now fuzzy and soft, hairy glass"}
    }),
    ("Metal to Cloth", {
        "texture": {"surface": "metallic surfaces now draped fabric, flowing steel"}
    }),
    ("Stone to Liquid", {
        "texture": {"surface": "solid stone now rippling liquid, flowing rock"}
    }),
    ("Wood to Crystal", {
        "texture": {"surface": "organic wood now faceted crystal, transparent trees"}
    }),
    ("Flesh to Porcelain", {
        "texture": {"surface": "skin now smooth ceramic, porcelain figures"}
    }),
    ("Water to Smoke", {
        "texture": {"surface": "liquids now wispy smoke, gaseous water"}
    }),
    ("Fabric to Ice", {
        "texture": {"surface": "soft cloth now frozen rigid ice, crystalline draping"}
    }),
    ("Paper to Metal", {
        "texture": {"surface": "thin paper now heavy metal sheet, metallic pages"}
    }),
]

# Temporal effects for temporal_exposure mutation
TEMPORAL_EXPOSURES = [
    ("Long Exposure Trails", {
        "texture": {"special_effects": ["motion blur trails", "light painting streaks", "long exposure movement"]},
        "lighting": {"highlights": "stretched light trails, time-smeared luminosity"}
    }),
    ("Freeze Frame Shatter", {
        "texture": {"special_effects": ["frozen moment", "time-sliced fragments", "bullet-time freeze"]},
        "composition": {"framing": "single instant captured with impossible detail"}
    }),
    ("Ghost Afterimages", {
        "texture": {"special_effects": ["translucent afterimages", "motion echoes", "temporal ghosts"]},
        "composition": {"framing": "multiple overlaid moments, ghostly trails"}
    }),
    ("Stroboscopic Multiple", {
        "texture": {"special_effects": ["stroboscopic effect", "repeated frozen moments", "sequential overlay"]},
        "composition": {"framing": "same subject repeated across motion arc"}
    }),
    ("Time Dilation", {
        "texture": {"special_effects": ["different time speeds coexisting", "fast and slow in same frame"]},
        "composition": {"framing": "some elements motion-blurred, others frozen"}
    }),
    ("Chronophotography", {
        "texture": {"special_effects": ["Muybridge-style sequential overlay", "scientific motion study"]},
        "composition": {"framing": "analytical breakdown of movement"}
    }),
]

# Foreign motifs for motif_splice mutation
MOTIF_SPLICES = [
    ("Eyes", "watchful eyes hidden in shadows, textures, and patterns"),
    ("Keys", "keys scattered throughout, in negative spaces and highlights"),
    ("Spirals", "spiral motifs woven into textures and compositions"),
    ("Birds", "bird silhouettes emerging from shapes and shadows"),
    ("Clocks", "timepieces hidden in patterns, clock hands in lines"),
    ("Hands", "reaching hands subtly formed in backgrounds and edges"),
    ("Flames", "flame shapes flickering through the composition"),
    ("Chains", "chain links woven through textures and borders"),
    ("Moons", "crescent and full moon shapes recurring throughout"),
    ("Skulls", "memento mori skull forms hidden in shadows"),
    ("Flowers", "floral motifs blooming from unexpected places"),
    ("Geometric Symbols", "sacred geometry symbols embedded subtly"),
]

# Rhythm patterns for rhythm_overlay mutation
RHYTHM_OVERLAYS = [
    ("Staccato", {
        "line_and_shape": {"shape_language": "sharp disconnected elements, punchy visual beats"},
        "composition": {"framing": "rhythmic spacing with sharp gaps"}
    }),
    ("Legato Flow", {
        "line_and_shape": {"shape_language": "smoothly connected flowing forms, sustained visual lines"},
        "composition": {"framing": "continuous flowing movement through composition"}
    }),
    ("Syncopated", {
        "composition": {"framing": "off-beat placement, unexpected rhythmic emphasis"},
        "line_and_shape": {"shape_language": "accents in unexpected positions"}
    }),
    ("Crescendo Build", {
        "composition": {"framing": "elements growing in intensity from edge to center"},
        "texture": {"surface": "increasing detail density toward focal point"}
    }),
    ("Polyrhythmic", {
        "composition": {"framing": "multiple competing visual rhythms overlaid"},
        "line_and_shape": {"shape_language": "different pattern frequencies coexisting"}
    }),
    ("Rest Spaces", {
        "composition": {"framing": "deliberate empty beats, visual silence", "negative_space_behavior": "rhythmic pauses in the composition"}
    }),
]

# Musical harmony for harmonic_balance mutation
HARMONIC_BALANCES = [
    ("Major Key Bright", {
        "palette": {"color_descriptions": ["bright harmonious colors", "uplifting color chord"], "saturation": "medium-high"},
        "lighting": {"lighting_type": "bright optimistic lighting"},
        "mood": "uplifting, resolved, consonant"
    }),
    ("Minor Key Melancholy", {
        "palette": {"color_descriptions": ["muted melancholic tones", "minor key colors"], "saturation": "low"},
        "lighting": {"lighting_type": "dim atmospheric lighting"},
        "mood": "wistful, unresolved tension"
    }),
    ("Dissonant Tension", {
        "palette": {"color_descriptions": ["clashing uncomfortable colors", "dissonant color combinations"]},
        "composition": {"framing": "visual tension, unresolved elements"},
        "mood": "unsettling, discordant"
    }),
    ("Arpeggio Sequence", {
        "composition": {"framing": "elements arranged in sequential progression, arpeggio-like repetition"},
        "line_and_shape": {"shape_language": "repeating elements at different scales"}
    }),
    ("Chord Stack", {
        "composition": {"framing": "layered simultaneous elements, chord-like stacking"},
        "line_and_shape": {"shape_language": "harmonically related shapes stacked"}
    }),
    ("Resolution", {
        "composition": {"framing": "tension releasing toward stable focal point"},
        "mood": "satisfying conclusion, visual resolution"
    }),
]

# Symmetry operations for symmetry_break mutation
SYMMETRY_OPERATIONS = [
    ("Break Bilateral", {
        "composition": {"framing": "bilateral symmetry deliberately broken, one side different"},
        "line_and_shape": {"shape_language": "asymmetric elements introduced"}
    }),
    ("Force Radial", {
        "composition": {"framing": "forced radial symmetry, everything radiates from center"},
        "line_and_shape": {"shape_language": "radial arrangement imposed"}
    }),
    ("Partial Mirror", {
        "composition": {"framing": "partial reflection, incomplete mirror"},
        "line_and_shape": {"shape_language": "some elements mirrored, others not"}
    }),
    ("Rotational Impose", {
        "composition": {"framing": "rotational symmetry imposed, 3-fold or 4-fold"},
        "line_and_shape": {"shape_language": "rotated repetition"}
    }),
    ("Glide Reflection", {
        "composition": {"framing": "translated mirror, shifted reflection"},
        "line_and_shape": {"shape_language": "mirrored and offset patterns"}
    }),
    ("Chaos from Order", {
        "composition": {"framing": "orderly structure disrupted, symmetry destroyed"},
        "line_and_shape": {"shape_language": "chaotic elements breaking geometric order"}
    }),
]

# Density variations for density_shift mutation
DENSITY_SHIFTS = [
    ("Sparse from Dense", {
        "texture": {"surface": "previously dense areas now minimal", "noise_level": "low"},
        "composition": {"framing": "breathing room, expanded spacing"},
        "line_and_shape": {"shape_language": "simplified, fewer elements"}
    }),
    ("Dense from Sparse", {
        "texture": {"surface": "previously empty areas now intricate", "noise_level": "high"},
        "composition": {"framing": "horror vacui, filled spaces"},
        "line_and_shape": {"shape_language": "complex, many elements"}
    }),
    ("Density Gradient", {
        "composition": {"framing": "gradual transition from sparse to dense"},
        "texture": {"surface": "increasing detail toward focal point"}
    }),
    ("Density Islands", {
        "composition": {"framing": "clusters of detail in sea of emptiness"},
        "texture": {"surface": "localized intricate patches"}
    }),
    ("Uniform Density", {
        "composition": {"framing": "even distribution throughout"},
        "texture": {"surface": "consistent detail level everywhere"}
    }),
]

# Dimensional appearances for dimensional_shift mutation
DIMENSIONAL_SHIFTS = [
    ("Flatten to 2D", {
        "lighting": {"shadows": "no shadows", "lighting_type": "flat even lighting"},
        "texture": {"surface": "flat graphic fills"},
        "composition": {"framing": "no depth cues, paper cutout appearance"}
    }),
    ("Paper Cutout 2.5D", {
        "composition": {"framing": "layered flat planes at different depths, diorama effect"},
        "lighting": {"shadows": "discrete layered shadows"},
        "texture": {"surface": "flat within layers, depth between"}
    }),
    ("Fake 3D Pop", {
        "lighting": {"shadows": "exaggerated drop shadows", "highlights": "extreme dimensional shading"},
        "texture": {"surface": "hyper-rendered dimensional appearance"}
    }),
    ("Isometric Lock", {
        "composition": {"camera": "isometric projection, no vanishing points", "framing": "parallel projection"},
        "line_and_shape": {"shape_language": "isometric geometry"}
    }),
    ("Trompe l'oeil Depth", {
        "composition": {"framing": "hyper-realistic depth illusion"},
        "lighting": {"shadows": "perfect perspective shadows", "highlights": "realistic depth shading"}
    }),
]

# Scale swaps for micro_macro_swap mutation
MICRO_MACRO_SWAPS = [
    ("Micro to Macro", {
        "texture": {"surface": "tiny textures now dominate as large shapes"},
        "line_and_shape": {"shape_language": "microscopic patterns scaled to architectural size"},
        "composition": {"framing": "texture becomes structure"}
    }),
    ("Macro to Micro", {
        "line_and_shape": {"shape_language": "large shapes shrunk to textural patterns"},
        "texture": {"surface": "structural elements become fine texture"},
        "composition": {"framing": "structure becomes texture"}
    }),
    ("Scale Inversion", {
        "composition": {"framing": "all scales inverted, big and small swapped"},
        "line_and_shape": {"shape_language": "complete scale hierarchy reversal"}
    }),
    ("Fractal Scale", {
        "line_and_shape": {"shape_language": "same patterns at every scale, fractal self-similarity"},
        "texture": {"surface": "scale-independent patterns"}
    }),
]

# Narrative elements for narrative_resonance mutation
NARRATIVE_RESONANCES = [
    ("Lost Civilization", {
        "texture": {"special_effects": ["ancient ruins glimpsed", "forgotten symbols"]},
        "mood": "archaeological mystery, deep time"
    }),
    ("Ritual Space", {
        "composition": {"framing": "ceremonial arrangement, sacred geometry"},
        "lighting": {"lighting_type": "ritualistic lighting, altar-like focus"},
        "mood": "spiritual, ceremonial"
    }),
    ("Journey Path", {
        "composition": {"framing": "implied movement through space, pathway visible"},
        "mood": "pilgrimage, quest, travel"
    }),
    ("Aftermath", {
        "texture": {"special_effects": ["traces of past events", "remnants and echoes"]},
        "mood": "post-event stillness, consequence"
    }),
    ("Threshold", {
        "composition": {"framing": "doorway, boundary, liminal space"},
        "mood": "transition, potential, crossing"
    }),
    ("Secret Garden", {
        "composition": {"framing": "hidden discovery, enclosed sanctuary"},
        "mood": "wonder, privacy, sanctuary"
    }),
    ("Prophecy", {
        "lighting": {"lighting_type": "ominous portentous light"},
        "mood": "foreshadowing, fate, destiny"
    }),
]

# Jungian archetypes for archetype_mask mutation
ARCHETYPE_MASKS = [
    ("The Hero", {
        "lighting": {"lighting_type": "heroic uplighting, triumphant radiance"},
        "composition": {"framing": "central dominant figure, upward aspiration"},
        "mood": "courage, triumph, ascension"
    }),
    ("The Shadow", {
        "lighting": {"lighting_type": "obscured, darkness dominant", "shadows": "deep engulfing shadows"},
        "palette": {"saturation": "low", "color_descriptions": ["dark muted tones"]},
        "mood": "hidden, repressed, unconscious"
    }),
    ("The Trickster", {
        "composition": {"framing": "off-balance, unexpected arrangements"},
        "line_and_shape": {"shape_language": "playful, rule-breaking forms"},
        "mood": "mischief, disruption, clever"
    }),
    ("The Oracle", {
        "lighting": {"lighting_type": "mysterious emanating light"},
        "texture": {"special_effects": ["ethereal mist", "prophetic glow"]},
        "mood": "wisdom, mystery, knowing"
    }),
    ("The Mother", {
        "composition": {"framing": "embracing, protective enclosure"},
        "palette": {"color_descriptions": ["nurturing warm tones"]},
        "mood": "nurture, protection, fertility"
    }),
    ("The Wanderer", {
        "composition": {"framing": "vast space, small figure, horizon focus"},
        "mood": "solitude, seeking, journey"
    }),
    ("The Ruler", {
        "composition": {"framing": "formal symmetry, hierarchical arrangement"},
        "lighting": {"lighting_type": "regal golden light"},
        "mood": "authority, order, power"
    }),
]

# Climate/atmosphere for climate_morph mutation
CLIMATE_MORPHS = [
    ("Dust Storm", {
        "texture": {"special_effects": ["airborne particles", "visibility reduction", "sand/dust haze"]},
        "palette": {"color_descriptions": ["ochre", "tan", "dusty"], "saturation": "low"},
        "lighting": {"lighting_type": "diffused by particles, orange cast"}
    }),
    ("Tropical Mist", {
        "texture": {"special_effects": ["humid haze", "moisture droplets", "jungle humidity"]},
        "palette": {"color_descriptions": ["lush green", "warm humidity"]},
        "lighting": {"lighting_type": "soft diffused tropical light"}
    }),
    ("Cosmic Vacuum", {
        "palette": {"color_descriptions": ["void black", "stellar white", "nebula colors"]},
        "lighting": {"lighting_type": "harsh unfiltered starlight, no atmosphere"},
        "texture": {"special_effects": ["no atmospheric scattering", "stark contrast"]}
    }),
    ("Heavy Fog", {
        "texture": {"special_effects": ["dense fog", "limited visibility", "moisture suspension"]},
        "palette": {"saturation": "very low"},
        "lighting": {"lighting_type": "heavily diffused, no direct light"}
    }),
    ("Underwater Bloom", {
        "texture": {"special_effects": ["caustic light patterns", "floating particles", "underwater haze"]},
        "palette": {"color_descriptions": ["aquatic blue-green", "filtered sunlight"]},
        "lighting": {"lighting_type": "filtered through water, caustics"}
    }),
    ("Arctic Clear", {
        "palette": {"color_descriptions": ["ice blue", "pristine white", "cold clarity"]},
        "lighting": {"lighting_type": "crisp cold light, high clarity"},
        "texture": {"special_effects": ["crystalline air", "ice particles"]}
    }),
    ("Volcanic Ash", {
        "texture": {"special_effects": ["ash fall", "ember glow", "smoke plumes"]},
        "palette": {"color_descriptions": ["gray ash", "ember orange", "smoke black"]},
        "lighting": {"lighting_type": "obscured sun, ember glow"}
    }),
]

# Biome environments for biome_shift mutation
BIOME_SHIFTS = [
    ("Desert Dunes", {
        "palette": {"color_descriptions": ["sand gold", "sun-bleached tan", "heat shimmer"]},
        "texture": {"surface": "wind-sculpted sand, rippled dunes"},
        "lighting": {"lighting_type": "harsh desert sun, long shadows"}
    }),
    ("Coral Reef", {
        "palette": {"color_descriptions": ["coral pink", "tropical fish colors", "aqua blue"], "saturation": "high"},
        "texture": {"surface": "organic coral textures, underwater life"},
        "lighting": {"lighting_type": "filtered underwater light, caustics"}
    }),
    ("Ice Cave", {
        "palette": {"color_descriptions": ["glacial blue", "frozen white", "deep ice"]},
        "texture": {"surface": "crystalline ice, frozen formations"},
        "lighting": {"lighting_type": "translucent ice glow, refracted light"}
    }),
    ("Fungal Forest", {
        "palette": {"color_descriptions": ["bioluminescent", "decay brown", "mycelium white"]},
        "texture": {"surface": "organic fungal growth, spore clouds"},
        "lighting": {"lighting_type": "bioluminescent glow, damp darkness"}
    }),
    ("Gas Giant Atmosphere", {
        "palette": {"color_descriptions": ["jupiter bands", "storm swirls", "atmospheric layers"]},
        "texture": {"surface": "gas cloud swirls, storm vortices"},
        "lighting": {"lighting_type": "diffused through dense atmosphere"}
    }),
    ("Volcanic Hellscape", {
        "palette": {"color_descriptions": ["lava orange", "basalt black", "sulfur yellow"]},
        "texture": {"surface": "cooling lava, volcanic rock"},
        "lighting": {"lighting_type": "lava glow, volcanic fire"}
    }),
    ("Bioluminescent Deep Sea", {
        "palette": {"color_descriptions": ["abyssal black", "bioluminescent spots"], "saturation": "low except lights"},
        "texture": {"surface": "deep sea organisms, pressure-adapted forms"},
        "lighting": {"lighting_type": "only bioluminescent points in darkness"}
    }),
]

# Computational artifacts for algorithmic_wrinkle mutation
ALGORITHMIC_WRINKLES = [
    ("CRT Scanlines", {
        "texture": {"special_effects": ["horizontal scanlines", "CRT curvature", "phosphor glow"]},
        "line_and_shape": {"line_quality": "scanline-interrupted edges"}
    }),
    ("JPEG Compression", {
        "texture": {"special_effects": ["compression blocks", "DCT artifacts", "mosquito noise"]},
        "line_and_shape": {"shape_language": "block-boundary artifacts"}
    }),
    ("Halftone Dots", {
        "texture": {"surface": "CMYK halftone dot pattern, newsprint texture", "special_effects": ["halftone rosettes", "dot gain"]},
    }),
    ("Dithering Pattern", {
        "texture": {"surface": "ordered dithering pattern, limited palette simulation", "special_effects": ["Bayer matrix dither"]}
    }),
    ("VHS Tracking", {
        "texture": {"special_effects": ["tracking lines", "color bleeding", "tape wobble"]},
        "palette": {"color_descriptions": ["oversaturated video colors"]}
    }),
    ("ASCII Art", {
        "texture": {"surface": "character-based rendering, ASCII density mapping"},
        "line_and_shape": {"shape_language": "monospace character grid"}
    }),
    ("Interlacing", {
        "texture": {"special_effects": ["interlaced lines", "motion combing", "field separation"]}
    }),
    ("Posterization", {
        "palette": {"color_descriptions": ["limited color bands", "stepped gradients"]},
        "texture": {"surface": "banded color regions, no smooth gradients"}
    }),
]

# Symbolic reduction for symbolic_reduction mutation
SYMBOLIC_REDUCTIONS = [
    ("Geometric Primitives", {
        "line_and_shape": {"shape_language": "reduced to circles, squares, triangles only", "line_quality": "clean simple outlines"},
        "texture": {"surface": "flat fills, no texture detail"}
    }),
    ("Pictogram", {
        "line_and_shape": {"shape_language": "international symbol style, universal pictogram forms", "line_quality": "uniform stroke weight"},
        "palette": {"color_descriptions": ["limited signage colors"]}
    }),
    ("Hieroglyphic", {
        "line_and_shape": {"shape_language": "symbolic representative forms, icon-like reduction"},
        "composition": {"framing": "arranged like written symbols"}
    }),
    ("Circuit Diagram", {
        "line_and_shape": {"shape_language": "schematic symbols, node and connection logic", "line_quality": "technical drawing lines"},
        "palette": {"color_descriptions": ["schematic colors"]}
    }),
    ("Stick Figure", {
        "line_and_shape": {"shape_language": "minimalist line-based representation", "line_quality": "single-weight strokes only"}
    }),
    ("Emoji Reduction", {
        "line_and_shape": {"shape_language": "emoji-style simplification, expressive minimalism"},
        "palette": {"saturation": "high", "color_descriptions": ["bright emoji colors"]}
    }),
]


class StyleExplorer:
    """
    Service for divergent style exploration.

    Takes a style and intentionally mutates it to discover new directions,
    saving every step as a snapshot for later exploration.
    """

    def __init__(self):
        self.prompt_writer = PromptWriter()
        self.mutation_prompt_path = Path(__file__).parent.parent / "prompts" / "explorer_mutation.md"

    async def extract_base_style(
        self,
        image_b64: str,
        session_id: str | None = None,
    ) -> StyleProfile:
        """
        Extract base style profile from reference image.
        Reuses the standard extractor.
        """
        return await style_extractor.extract(image_b64, session_id)

    def _mutate_random_dimension(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str, str]:
        """
        Apply random dimension push mutation.

        Picks a random style dimension and pushes it to an extreme.

        Returns:
            (mutated_profile, mutation_description, dimension_key)
        """
        # Pick a random dimension
        dimension = random.choice(list(DIMENSION_EXTREMES.keys()))
        extremes = DIMENSION_EXTREMES[dimension]

        # Pick a random extreme (either direction)
        extreme_desc, extreme_key = random.choice(extremes)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply mutation based on dimension
        parts = dimension.split(".")

        if parts[0] == "palette":
            if parts[1] == "saturation":
                profile_dict["palette"]["saturation"] = extreme_key
                # Also update color descriptions to reflect change
                if "desaturated" in extreme_key:
                    profile_dict["palette"]["color_descriptions"] = ["grayscale", "monochrome", "neutral gray", "charcoal", "silver"]
                else:
                    profile_dict["palette"]["color_descriptions"] = ["neon pink", "electric blue", "vivid green", "hot orange", "bright purple"]
            elif parts[1] == "temperature":
                if "cold" in extreme_key:
                    profile_dict["palette"]["color_descriptions"] = ["icy blue", "arctic white", "frost", "pale cyan", "winter gray"]
                else:
                    profile_dict["palette"]["color_descriptions"] = ["volcanic orange", "fire red", "molten gold", "ember", "scorched amber"]
            elif parts[1] == "contrast":
                profile_dict["palette"]["value_range"] = extreme_desc

        elif parts[0] == "line_and_shape":
            if parts[1] == "edges":
                profile_dict["line_and_shape"]["line_quality"] = extreme_desc
            elif parts[1] == "complexity":
                profile_dict["line_and_shape"]["shape_language"] = extreme_desc
                profile_dict["line_and_shape"]["geometry_notes"] = extreme_desc

        elif parts[0] == "texture":
            if parts[1] == "surface":
                profile_dict["texture"]["surface"] = extreme_desc
            elif parts[1] == "noise":
                profile_dict["texture"]["noise_level"] = "high" if extreme_key == "noisy" else "none"
                profile_dict["texture"]["surface"] = extreme_desc

        elif parts[0] == "lighting":
            if parts[1] == "intensity":
                profile_dict["lighting"]["lighting_type"] = extreme_desc
                if "dark" in extreme_key:
                    profile_dict["lighting"]["shadows"] = "deep pitch black shadows dominating"
                    profile_dict["lighting"]["highlights"] = "minimal, isolated points of light"
                else:
                    profile_dict["lighting"]["shadows"] = "barely visible, washed out"
                    profile_dict["lighting"]["highlights"] = "overwhelming bright, blown out"
            elif parts[1] == "direction":
                profile_dict["lighting"]["lighting_type"] = extreme_desc

        elif parts[0] == "composition":
            if parts[1] == "density":
                profile_dict["composition"]["framing"] = extreme_desc
                profile_dict["composition"]["negative_space_behavior"] = "dominant empty space" if extreme_key == "sparse" else "no empty space"
            elif parts[1] == "symmetry":
                profile_dict["composition"]["framing"] = extreme_desc

        # Update style name to reflect mutation
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({extreme_key})"

        # Add mutation to core invariants
        profile_dict["core_invariants"] = [extreme_desc] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Random dimension push: {dimension} → {extreme_key}. {extreme_desc}"

        return StyleProfile(**profile_dict), mutation_description, dimension

    async def _mutate_what_if(
        self,
        profile: StyleProfile,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply VLM-guided "what if?" mutation.

        Asks the VLM to suggest a wild creative mutation based on the current style.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Summarize current profile for the VLM
        profile_summary = self._summarize_profile(profile)

        what_if_prompt = f"""You are a creative style mutator. Looking at this visual style description, suggest ONE wild "what if?" variation that would create something visually striking and unexpected.

Current style:
{profile_summary}

Think of unexpected, dramatic transformations like:
- "What if this watercolor style used only neon colors?"
- "What if the minimal design became maximally ornate?"
- "What if the lighting came from inside the objects?"
- "What if everything was rendered as stained glass?"
- "What if the shadows were made of liquid gold?"

Suggest a SPECIFIC, DRAMATIC change. Be creative and bold!

Output ONLY valid JSON in this exact format:
{{
    "mutation_idea": "A short description of the creative change (1 sentence)",
    "style_changes": {{
        "palette": {{
            "color_descriptions": ["color1", "color2", "color3", "color4"],
            "saturation": "low/medium/high/extreme"
        }},
        "texture": {{
            "surface": "description of new surface quality"
        }},
        "lighting": {{
            "lighting_type": "description of new lighting"
        }},
        "line_and_shape": {{
            "line_quality": "description of new line treatment",
            "shape_language": "description of new shapes"
        }}
    }}
}}

Only include the fields you want to change. Be bold and creative!"""

        try:
            response = await vlm_service.generate_text(
                prompt=what_if_prompt,
                system="You are a creative AI that suggests bold, unexpected style mutations. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            mutation_idea = data.get("mutation_idea", "Creative mutation")
            style_changes = data.get("style_changes", {})

            # Apply changes to profile
            profile_dict = profile.model_dump()

            # Deep merge the style changes
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section]:
                            profile_dict[section][key] = value

            # Update style name
            original_name = profile_dict.get("style_name", "Style")
            profile_dict["style_name"] = f"{original_name} (what-if)"

            # Add mutation to core invariants
            profile_dict["core_invariants"] = [mutation_idea] + profile_dict.get("core_invariants", [])[:4]

            mutation_description = f"What-if: {mutation_idea}"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.warning(f"What-if mutation failed: {e}, falling back to random dimension")
            mutated, desc, _ = self._mutate_random_dimension(profile)
            return mutated, f"[what-if fallback] {desc}"

    def _mutate_crossover(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply crossover mutation - blend with a random donor style.

        Picks a random well-known style and merges key characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random donor style
        donor_name, donor_desc = random.choice(DONOR_STYLES)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Extract keywords from donor description and inject them
        donor_keywords = [kw.strip() for kw in donor_desc.split(",")]

        # Merge donor characteristics into the profile
        # Add donor keywords to core invariants
        profile_dict["core_invariants"] = donor_keywords[:2] + profile_dict.get("core_invariants", [])[:3]

        # Blend texture with donor style
        original_texture = profile_dict["texture"]["surface"]
        profile_dict["texture"]["surface"] = f"{original_texture}, blended with {donor_name} aesthetic"

        # Add donor style to lighting description
        if "dramatic" in donor_desc.lower() or "shadow" in donor_desc.lower():
            profile_dict["lighting"]["lighting_type"] = f"dramatic {donor_name}-influenced lighting"

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} × {donor_name}"

        mutation_description = f"Crossover: Blended with '{donor_name}' ({donor_desc[:50]}...)"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_inversion(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply inversion mutation - flip a key characteristic to its opposite.

        Searches for matching characteristics in the profile and inverts them.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Convert profile to string for searching
        profile_dict = profile.model_dump()
        profile_str = json.dumps(profile_dict).lower()

        # Find a matching characteristic to invert
        matched_original = None
        matched_inverted = None
        matched_changes = None

        for original, (inverted, changes) in CHARACTERISTIC_INVERSIONS.items():
            if original.lower() in profile_str:
                matched_original = original
                matched_inverted = inverted
                matched_changes = changes
                break

        # If no match, pick a random inversion
        if matched_original is None:
            matched_original, (matched_inverted, matched_changes) = random.choice(
                list(CHARACTERISTIC_INVERSIONS.items())
            )

        # Apply the inversion changes
        for section, changes in matched_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (inverted)"

        # Add inversion to core invariants
        profile_dict["core_invariants"] = [f"inverted from {matched_original} to {matched_inverted}"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Inversion: '{matched_original}' → '{matched_inverted}'"

        return StyleProfile(**profile_dict), mutation_description

    async def _mutate_amplify(
        self,
        profile: StyleProfile,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply amplification mutation - exaggerate existing traits to extremes.

        Uses VLM to identify the most distinctive trait and push it further.

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        amplify_prompt = f"""Analyze this visual style and identify its MOST DISTINCTIVE trait, then amplify it to an extreme.

Current style:
{profile_summary}

Examples of amplification:
- If slightly desaturated → completely monochrome
- If somewhat geometric → pure mathematical shapes only
- If soft shadows → shadows that glow and pulse
- If warm colors → molten lava heat, volcanic intensity
- If textured → extremely rough, almost 3D relief

Push the most distinctive element past realistic into stylized/surreal territory.

Output ONLY valid JSON:
{{
    "distinctive_trait": "what trait you identified",
    "amplified_version": "the extreme version",
    "style_changes": {{
        "palette": {{"color_descriptions": ["color1", "color2"], "saturation": "level"}},
        "texture": {{"surface": "new surface description"}},
        "lighting": {{"lighting_type": "new lighting"}},
        "line_and_shape": {{"line_quality": "new lines", "shape_language": "new shapes"}}
    }}
}}

Only include fields that need to change for the amplification."""

        try:
            response = await vlm_service.generate_text(
                prompt=amplify_prompt,
                system="You are a style amplifier that pushes visual characteristics to creative extremes. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            distinctive_trait = data.get("distinctive_trait", "style element")
            amplified_version = data.get("amplified_version", "extreme version")
            style_changes = data.get("style_changes", {})

            # Apply changes
            profile_dict = profile.model_dump()

            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            profile_dict[section][key] = value

            # Update style name
            original_name = profile_dict.get("style_name", "Style")
            profile_dict["style_name"] = f"{original_name} (amplified)"

            # Add amplification to core invariants
            profile_dict["core_invariants"] = [amplified_version] + profile_dict.get("core_invariants", [])[:4]

            mutation_description = f"Amplify: '{distinctive_trait}' → '{amplified_version}'"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.warning(f"Amplify mutation failed: {e}, falling back to random dimension")
            mutated, desc, _ = self._mutate_random_dimension(profile)
            return mutated, f"[amplify fallback] {desc}"

    async def _mutate_diverge(
        self,
        profile: StyleProfile,
        parent_image_b64: str | None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply diverge mutation - extract-and-deviate using critique-like analysis.

        This is the inverse of the training loop:
        1. Analyze the current style's most distinctive traits
        2. Ask VLM to suggest deliberate deviations from those traits
        3. Create a new profile that intentionally breaks from the original

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        # Step 1: Ask VLM to identify what to deviate from and how
        diverge_prompt = f"""You are a style DIVERGENCE engine. Your goal is to analyze a style and create a deliberate, artistic departure from it.

Current style to diverge FROM:
{profile_summary}

Core traits that define this style:
{', '.join(profile.core_invariants[:5]) if profile.core_invariants else 'Not specified'}

Your task: Create a NEW style that is deliberately DIFFERENT but still coherent and interesting.

Think about:
- If the original is warm, go cold (or vice versa)
- If the original is soft, go sharp (or vice versa)
- If the original is busy, go minimal (or vice versa)
- If the original is realistic, go abstract (or vice versa)
- Change the mood, era, or artistic movement entirely

Be BOLD - don't make small changes, make transformative ones that result in a completely different aesthetic while maintaining artistic quality.

Output ONLY valid JSON:
{{
    "divergence_strategy": "A 1-sentence description of how you're diverging (e.g., 'Transforming from warm organic impressionism to cold geometric minimalism')",
    "traits_abandoned": ["list 2-3 key traits from the original that you're abandoning"],
    "traits_introduced": ["list 2-3 new traits you're introducing instead"],
    "new_style": {{
        "style_name": "A new name for this divergent style",
        "core_invariants": ["3-5 NEW defining traits for the divergent style"],
        "palette": {{
            "color_descriptions": ["4-5 colors for the new style"],
            "saturation": "low/medium/high"
        }},
        "texture": {{
            "surface": "description of new surface quality"
        }},
        "lighting": {{
            "lighting_type": "description of new lighting approach",
            "shadows": "description of shadow treatment"
        }},
        "line_and_shape": {{
            "line_quality": "description of new line treatment",
            "shape_language": "description of new shapes"
        }},
        "composition": {{
            "framing": "description of new composition approach"
        }}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=diverge_prompt,
                system="You are a creative AI that transforms visual styles into deliberate artistic departures. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            divergence_strategy = data.get("divergence_strategy", "Diverging from original style")
            traits_abandoned = data.get("traits_abandoned", [])
            traits_introduced = data.get("traits_introduced", [])
            new_style = data.get("new_style", {})

            # Build the mutated profile
            profile_dict = profile.model_dump()

            # Apply the new style characteristics
            if new_style.get("style_name"):
                profile_dict["style_name"] = new_style["style_name"]

            if new_style.get("core_invariants"):
                # Ensure core_invariants are strings
                invariants = new_style["core_invariants"]
                if isinstance(invariants, list):
                    profile_dict["core_invariants"] = [str(inv) for inv in invariants if inv][:5]

            if new_style.get("palette"):
                palette = new_style["palette"]
                if palette.get("color_descriptions"):
                    colors = palette["color_descriptions"]
                    if isinstance(colors, list):
                        profile_dict["palette"]["color_descriptions"] = [str(c) for c in colors if c][:5]
                if palette.get("saturation"):
                    profile_dict["palette"]["saturation"] = str(palette["saturation"])

            if new_style.get("texture") and new_style["texture"].get("surface"):
                profile_dict["texture"]["surface"] = str(new_style["texture"]["surface"])

            if new_style.get("lighting"):
                lighting = new_style["lighting"]
                if lighting.get("lighting_type"):
                    profile_dict["lighting"]["lighting_type"] = str(lighting["lighting_type"])
                if lighting.get("shadows"):
                    profile_dict["lighting"]["shadows"] = str(lighting["shadows"])

            if new_style.get("line_and_shape"):
                line_shape = new_style["line_and_shape"]
                if line_shape.get("line_quality"):
                    profile_dict["line_and_shape"]["line_quality"] = str(line_shape["line_quality"])
                if line_shape.get("shape_language"):
                    profile_dict["line_and_shape"]["shape_language"] = str(line_shape["shape_language"])

            if new_style.get("composition") and new_style["composition"].get("framing"):
                profile_dict["composition"]["framing"] = str(new_style["composition"]["framing"])

            # Build mutation description
            abandoned_str = ", ".join(traits_abandoned[:2]) if traits_abandoned else "original traits"
            introduced_str = ", ".join(traits_introduced[:2]) if traits_introduced else "new direction"
            mutation_description = f"Diverge: {divergence_strategy}. Abandoned: {abandoned_str}. Introduced: {introduced_str}"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.warning(f"Diverge mutation failed: {e}, falling back to inversion")
            mutated, desc = self._mutate_inversion(profile)
            return mutated, f"[diverge fallback] {desc}"

    def _mutate_time_shift(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply time_shift mutation - transport the style to a different era/decade.

        Picks a random era aesthetic and applies its characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random era
        era_name, era_changes = random.choice(ERA_AESTHETICS)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply era changes
        for section, changes in era_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({era_name})"

        # Add era to core invariants
        profile_dict["core_invariants"] = [f"{era_name} aesthetic"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Time Shift: Transported to {era_name} era"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_medium_swap(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply medium_swap mutation - change the apparent artistic medium.

        Picks a random medium and applies its visual characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random medium
        medium_name, medium_changes = random.choice(ARTISTIC_MEDIUMS)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply medium changes
        for section, changes in medium_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({medium_name})"

        # Add medium to core invariants
        profile_dict["core_invariants"] = [f"{medium_name} medium"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Medium Swap: Rendered as {medium_name}"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_mood_shift(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply mood_shift mutation - transform the emotional tone.

        Picks a random mood and applies its visual characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random mood
        mood_name, mood_changes = random.choice(MOOD_PALETTE)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply mood changes
        for section, changes in mood_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({mood_name})"

        # Add mood to core invariants
        profile_dict["core_invariants"] = [f"{mood_name} mood"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Mood Shift: Transformed to {mood_name}"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_scale_warp(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply scale_warp mutation - change the apparent scale/perspective.

        Picks a random scale perspective and applies its characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random scale
        scale_name, scale_changes = random.choice(SCALE_PERSPECTIVES)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply scale changes
        for section, changes in scale_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({scale_name})"

        # Add scale to core invariants
        profile_dict["core_invariants"] = [f"{scale_name} perspective"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Scale Warp: Shifted to {scale_name} perspective"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_decay(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply decay mutation - add entropy/age/weathering.

        Picks a random decay level and applies its visual characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random decay level
        decay_name, decay_changes = random.choice(DECAY_LEVELS)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply decay changes
        for section, changes in decay_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (decayed)"

        # Add decay to core invariants
        profile_dict["core_invariants"] = [f"{decay_name} decay"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Decay: Applied {decay_name} entropy"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_remix(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply remix mutation - shuffle elements between style sections.

        Randomly swaps characteristics between different parts of the style
        (e.g., palette descriptions become texture, lighting becomes line quality).

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_dict = profile.model_dump()

        # Collect shuffleable text elements
        elements = []
        sources = []

        if profile_dict["palette"].get("color_descriptions"):
            for desc in profile_dict["palette"]["color_descriptions"][:2]:
                elements.append(desc)
                sources.append("palette")

        if profile_dict["texture"].get("surface"):
            elements.append(profile_dict["texture"]["surface"])
            sources.append("texture")

        if profile_dict["lighting"].get("lighting_type"):
            elements.append(profile_dict["lighting"]["lighting_type"])
            sources.append("lighting")

        if profile_dict["line_and_shape"].get("shape_language"):
            elements.append(profile_dict["line_and_shape"]["shape_language"])
            sources.append("shape")

        # Shuffle and reassign
        if len(elements) >= 2:
            shuffled = elements.copy()
            random.shuffle(shuffled)

            # Reassign to different sections
            swap_desc = []
            if shuffled[0] != elements[0]:
                profile_dict["texture"]["surface"] = f"remix: {shuffled[0]}"
                swap_desc.append(f"{sources[0]}→texture")

            if len(shuffled) > 1 and shuffled[1] != elements[1]:
                profile_dict["lighting"]["lighting_type"] = f"remix lighting: {shuffled[1]}"
                swap_desc.append(f"{sources[1]}→lighting")

            if len(shuffled) > 2:
                profile_dict["line_and_shape"]["shape_language"] = f"remix shapes: {shuffled[2]}"

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (remixed)"

        # Add remix to core invariants
        profile_dict["core_invariants"] = ["remixed style elements"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Remix: Shuffled style elements ({', '.join(swap_desc[:2]) if swap_desc else 'scrambled'})"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_constrain(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply constrain mutation - limit to a strict constraint.

        Picks a random constraint type and applies its limitations.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random constraint
        constraint_name, constraint_fn = random.choice(CONSTRAINT_TYPES)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Get constraint changes (call the lambda)
        constraint_changes = constraint_fn(profile)

        # Apply constraint changes
        for section, changes in constraint_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({constraint_name})"

        # Add constraint to core invariants
        profile_dict["core_invariants"] = [f"constrained: {constraint_name}"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Constrain: Applied {constraint_name} constraint"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_culture_shift(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply culture_shift mutation - apply aesthetics from a different culture.

        Picks a random cultural aesthetic and applies its characteristics.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Pick a random culture
        culture_name, culture_changes = random.choice(CULTURAL_AESTHETICS)

        # Clone the profile
        profile_dict = profile.model_dump()

        # Apply culture changes
        for section, changes in culture_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({culture_name})"

        # Add culture to core invariants
        profile_dict["core_invariants"] = [f"{culture_name} aesthetic"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Culture Shift: Applied {culture_name} aesthetic"

        return StyleProfile(**profile_dict), mutation_description

    def _mutate_chaos(
        self,
        profile: StyleProfile,
    ) -> tuple[StyleProfile, str]:
        """
        Apply chaos mutation - multiple random small mutations at once.

        Applies 3-5 random small changes across different style dimensions.

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_dict = profile.model_dump()

        # List of possible chaos mutations
        chaos_mutations = [
            ("palette.saturation", lambda: random.choice(["very low", "low", "medium", "high", "extreme"])),
            ("palette.color_shift", lambda: random.choice([
                ["shifted to warm tones"],
                ["shifted to cool tones"],
                ["inverted colors"],
                ["complementary swap"],
            ])),
            ("texture.noise", lambda: random.choice(["none", "subtle grain", "heavy grain", "static noise"])),
            ("lighting.intensity", lambda: random.choice(["darker", "brighter", "more contrast", "flattened"])),
            ("line_quality", lambda: random.choice(["softer edges", "sharper edges", "sketchy", "smooth"])),
            ("composition.shift", lambda: random.choice(["zoomed in", "zoomed out", "off-center", "rotated feel"])),
        ]

        # Apply 3-5 random mutations
        num_mutations = random.randint(3, 5)
        selected = random.sample(chaos_mutations, min(num_mutations, len(chaos_mutations)))

        changes = []
        for mutation_key, mutation_fn in selected:
            value = mutation_fn()
            if "palette.saturation" in mutation_key:
                profile_dict["palette"]["saturation"] = value
                changes.append(f"saturation→{value}")
            elif "palette.color_shift" in mutation_key:
                profile_dict["palette"]["color_descriptions"] = value + profile_dict["palette"].get("color_descriptions", [])[:2]
                changes.append(f"colors {value[0]}")
            elif "texture.noise" in mutation_key:
                profile_dict["texture"]["noise_level"] = value
                changes.append(f"noise→{value}")
            elif "lighting.intensity" in mutation_key:
                profile_dict["lighting"]["lighting_type"] = f"{value} {profile_dict['lighting'].get('lighting_type', 'lighting')}"
                changes.append(f"lighting {value}")
            elif "line_quality" in mutation_key:
                profile_dict["line_and_shape"]["line_quality"] = value
                changes.append(f"lines→{value}")
            elif "composition.shift" in mutation_key:
                profile_dict["composition"]["framing"] = f"{value}, {profile_dict['composition'].get('framing', '')}"
                changes.append(f"composition {value}")

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (chaos)"

        # Add chaos to core invariants
        profile_dict["core_invariants"] = ["chaotic mutations applied"] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"Chaos: Applied {len(changes)} mutations ({', '.join(changes[:3])}...)"

        return StyleProfile(**profile_dict), mutation_description

    async def _mutate_refine(
        self,
        profile: StyleProfile,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply refine mutation - reduce extremes toward balance.

        Uses VLM to identify extreme traits and moderate them.
        The opposite of amplify.

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        refine_prompt = f"""Analyze this visual style and identify its MOST EXTREME trait, then moderate it toward balance.

Current style:
{profile_summary}

Examples of refinement:
- If hypersaturated → bring saturation to medium-high
- If extremely geometric → add some organic softness
- If pitch black shadows → lighten to dramatic but visible
- If blazing hot colors → warm but not overwhelming
- If maximum noise/grain → reduce to subtle texture

Find the element that is pushed furthest from center and pull it back toward moderation while keeping the style interesting.

Output ONLY valid JSON:
{{
    "extreme_trait": "what trait is most extreme",
    "refined_version": "the moderated version",
    "style_changes": {{
        "palette": {{"color_descriptions": ["color1", "color2"], "saturation": "level"}},
        "texture": {{"surface": "new surface description"}},
        "lighting": {{"lighting_type": "new lighting"}},
        "line_and_shape": {{"line_quality": "new lines", "shape_language": "new shapes"}}
    }}
}}

Only include fields that need to change for the refinement."""

        try:
            response = await vlm_service.generate_text(
                prompt=refine_prompt,
                system="You are a style refiner that brings extreme visual characteristics toward balance while maintaining interest. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            extreme_trait = data.get("extreme_trait", "style element")
            refined_version = data.get("refined_version", "moderated version")
            style_changes = data.get("style_changes", {})

            # Apply changes
            profile_dict = profile.model_dump()

            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            profile_dict[section][key] = value

            # Update style name
            original_name = profile_dict.get("style_name", "Style")
            profile_dict["style_name"] = f"{original_name} (refined)"

            # Add refinement to core invariants
            profile_dict["core_invariants"] = [refined_version] + profile_dict.get("core_invariants", [])[:4]

            mutation_description = f"Refine: '{extreme_trait}' → '{refined_version}'"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.warning(f"Refine mutation failed: {e}, falling back to small random adjustment")
            # Fallback: just moderate the saturation
            profile_dict = profile.model_dump()
            profile_dict["palette"]["saturation"] = "medium"
            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (refined)"
            profile_dict["core_invariants"] = ["balanced refinement"] + profile_dict.get("core_invariants", [])[:4]
            return StyleProfile(**profile_dict), "[refine fallback] Moderated saturation to medium"

    def _apply_preset_mutation(
        self,
        profile: StyleProfile,
        preset_name: str,
        preset_changes: dict,
        category: str,
        suffix: str,
    ) -> tuple[StyleProfile, str]:
        """Helper to apply preset-based mutations consistently."""
        profile_dict = profile.model_dump()

        # Apply changes
        for section, changes in preset_changes.items():
            if section == "mood":
                # Store mood in core_invariants
                continue
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({suffix})"

        # Add to core invariants
        mood = preset_changes.get("mood", "")
        if mood:
            profile_dict["core_invariants"] = [mood] + profile_dict.get("core_invariants", [])[:4]
        else:
            profile_dict["core_invariants"] = [preset_name] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"{category}: {preset_name}"
        return StyleProfile(**profile_dict), mutation_description

    # === SPATIAL MUTATIONS ===

    def _mutate_topology_fold(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Apply non-Euclidean or impossible geometry distortions."""
        fold_name, fold_changes = random.choice(TOPOLOGY_FOLDS)
        return self._apply_preset_mutation(profile, fold_name, fold_changes, "Topology Fold", "folded")

    def _mutate_silhouette_shift(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Modify contour/silhouette while keeping internal style traits."""
        shift_name, shift_changes = random.choice(SILHOUETTE_SHIFTS)
        return self._apply_preset_mutation(profile, shift_name, shift_changes, "Silhouette Shift", "silhouette")

    def _mutate_perspective_drift(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Apply surreal camera angles and perspective distortions."""
        drift_name, drift_changes = random.choice(PERSPECTIVE_DRIFTS)
        return self._apply_preset_mutation(profile, drift_name, drift_changes, "Perspective Drift", "drifted")

    def _mutate_axis_swap(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Rotate conceptual axes (vertical↔horizontal, center↔edge)."""
        swap_name, swap_changes = random.choice(AXIS_SWAPS)
        return self._apply_preset_mutation(profile, swap_name, swap_changes, "Axis Swap", "axis-swapped")

    # === PHYSICS MUTATIONS ===

    def _mutate_physics_bend(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Alter physical laws (gravity, light behavior, etc.)."""
        bend_name, bend_changes = random.choice(PHYSICS_BENDS)
        return self._apply_preset_mutation(profile, bend_name, bend_changes, "Physics Bend", "physics-bent")

    def _mutate_chromatic_gravity(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Make colors cluster or repel in new ways."""
        gravity_name, gravity_changes = random.choice(CHROMATIC_GRAVITIES)
        return self._apply_preset_mutation(profile, gravity_name, gravity_changes, "Chromatic Gravity", "color-gravity")

    def _mutate_material_transmute(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Change surface properties (glass→fur, metal→cloth)."""
        transmute_name, transmute_changes = random.choice(MATERIAL_TRANSMUTES)
        return self._apply_preset_mutation(profile, transmute_name, transmute_changes, "Material Transmute", "transmuted")

    def _mutate_temporal_exposure(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Alter 'shutter speed' - long exposure, freeze frames, ghosts."""
        exposure_name, exposure_changes = random.choice(TEMPORAL_EXPOSURES)
        return self._apply_preset_mutation(profile, exposure_name, exposure_changes, "Temporal Exposure", "time-exposed")

    # === PATTERN MUTATIONS ===

    def _mutate_motif_splice(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Inject a foreign recurring motif (eyes, keys, spirals, etc.)."""
        motif_name, motif_desc = random.choice(MOTIF_SPLICES)
        profile_dict = profile.model_dump()

        # Add motif to special effects and texture
        current_effects = profile_dict["texture"].get("special_effects", [])
        profile_dict["texture"]["special_effects"] = [motif_desc] + current_effects[:2]

        # Add motif to motifs section
        current_recurring = profile_dict["motifs"].get("recurring_elements", [])
        profile_dict["motifs"]["recurring_elements"] = [f"{motif_name} motif throughout"] + current_recurring[:2]

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (+{motif_name})"

        # Add to core invariants
        profile_dict["core_invariants"] = [f"recurring {motif_name} motif"] + profile_dict.get("core_invariants", [])[:4]

        return StyleProfile(**profile_dict), f"Motif Splice: {motif_name} woven throughout"

    def _mutate_rhythm_overlay(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Apply tempo-based visual patterns (staccato, legato, syncopated)."""
        rhythm_name, rhythm_changes = random.choice(RHYTHM_OVERLAYS)
        return self._apply_preset_mutation(profile, rhythm_name, rhythm_changes, "Rhythm Overlay", "rhythmic")

    def _mutate_harmonic_balance(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Apply musical composition logic (major/minor, dissonance/harmony)."""
        harmony_name, harmony_changes = random.choice(HARMONIC_BALANCES)
        return self._apply_preset_mutation(profile, harmony_name, harmony_changes, "Harmonic Balance", "harmonized")

    def _mutate_symmetry_break(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Break symmetry or force symmetry onto chaos."""
        symmetry_name, symmetry_changes = random.choice(SYMMETRY_OPERATIONS)
        return self._apply_preset_mutation(profile, symmetry_name, symmetry_changes, "Symmetry Break", "symmetry-altered")

    # === DENSITY MUTATIONS ===

    def _mutate_density_shift(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Vary visual information density (sparse↔dense)."""
        density_name, density_changes = random.choice(DENSITY_SHIFTS)
        return self._apply_preset_mutation(profile, density_name, density_changes, "Density Shift", "density-shifted")

    def _mutate_dimensional_shift(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Flatten or deepen dimensionality (2D↔2.5D↔3D)."""
        dim_name, dim_changes = random.choice(DIMENSIONAL_SHIFTS)
        return self._apply_preset_mutation(profile, dim_name, dim_changes, "Dimensional Shift", "dimension-shifted")

    def _mutate_micro_macro_swap(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Switch scales internally (tiny textures→big shapes)."""
        swap_name, swap_changes = random.choice(MICRO_MACRO_SWAPS)
        return self._apply_preset_mutation(profile, swap_name, swap_changes, "Micro/Macro Swap", "scale-swapped")

    async def _mutate_essence_strip(
        self,
        profile: StyleProfile,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Remove secondary features to reveal core essence (more drastic than refine)."""
        profile_summary = self._summarize_profile(profile)

        strip_prompt = f"""Analyze this visual style and strip it to its absolute ESSENCE.

Current style:
{profile_summary}

Remove ALL secondary details. Keep ONLY:
1. The single most defining color relationship
2. The essential line quality (one word)
3. The core lighting approach (simplified)
4. The fundamental compositional structure

Everything else should be reduced to "minimal" or "absent".

Output ONLY valid JSON with stripped-down values:
{{
    "essence_description": "3-5 word description of pure essence",
    "style_changes": {{
        "palette": {{"color_descriptions": ["1-2 essential colors only"], "saturation": "level"}},
        "texture": {{"surface": "minimal or single texture word", "noise_level": "low"}},
        "lighting": {{"lighting_type": "simplified essential lighting"}},
        "line_and_shape": {{"line_quality": "one essential quality", "shape_language": "one essential shape type"}}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=strip_prompt,
                system="You are a style minimalist. Strip styles to their pure essence. Output only valid JSON.",
                use_text_model=True,
            )

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            essence_desc = data.get("essence_description", "pure essence")
            style_changes = data.get("style_changes", {})

            profile_dict = profile.model_dump()
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            profile_dict[section][key] = value

            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (essence)"
            profile_dict["core_invariants"] = [essence_desc] + profile_dict.get("core_invariants", [])[:2]

            return StyleProfile(**profile_dict), f"Essence Strip: {essence_desc}"

        except Exception as e:
            logger.warning(f"Essence strip failed: {e}, using fallback")
            profile_dict = profile.model_dump()
            profile_dict["texture"]["noise_level"] = "minimal"
            profile_dict["texture"]["special_effects"] = []
            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (essence)"
            profile_dict["core_invariants"] = ["stripped to essence"] + profile_dict.get("core_invariants", [])[:2]
            return StyleProfile(**profile_dict), "[essence strip fallback] Removed special effects, minimized texture"

    # === NARRATIVE MUTATIONS ===

    def _mutate_narrative_resonance(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Add implied story fragments (lost civilization, ritual, journey)."""
        narrative_name, narrative_changes = random.choice(NARRATIVE_RESONANCES)
        return self._apply_preset_mutation(profile, narrative_name, narrative_changes, "Narrative Resonance", "narrative")

    def _mutate_archetype_mask(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Map onto mythological/Jungian archetypes (hero, shadow, oracle)."""
        archetype_name, archetype_changes = random.choice(ARCHETYPE_MASKS)
        return self._apply_preset_mutation(profile, archetype_name, archetype_changes, "Archetype Mask", "archetypal")

    async def _mutate_anomaly_inject(
        self,
        profile: StyleProfile,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add a single deliberate anomaly that violates the style rules."""
        profile_summary = self._summarize_profile(profile)

        anomaly_prompt = f"""Analyze this visual style and find its MOST RIGID RULE.
Then create ONE controlled violation of that rule to create visual tension.

Current style:
{profile_summary}

Examples:
- If style is "always warm colors" → inject one cold blue element
- If style is "soft edges" → add one sharp angular shape
- If style is "symmetrical" → introduce one asymmetric element
- If style is "muted tones" → add one saturated accent

The anomaly should be NOTICEABLE but not overwhelming - tension, not chaos.

Output ONLY valid JSON:
{{
    "rigid_rule": "the rule being violated",
    "anomaly": "the controlled violation",
    "style_changes": {{
        "texture": {{"special_effects": ["anomaly description"]}},
        "composition": {{"framing": "composition note if relevant"}}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=anomaly_prompt,
                system="You are a style disruptor. Find the most rigid rule and create one deliberate violation. Output only valid JSON.",
                use_text_model=True,
            )

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            rigid_rule = data.get("rigid_rule", "style rule")
            anomaly = data.get("anomaly", "controlled violation")
            style_changes = data.get("style_changes", {})

            profile_dict = profile.model_dump()
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            if key == "special_effects":
                                current = profile_dict[section].get(key, [])
                                profile_dict[section][key] = value + current[:2]
                            else:
                                profile_dict[section][key] = value

            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (anomaly)"
            profile_dict["core_invariants"] = [f"intentional anomaly: {anomaly}"] + profile_dict.get("core_invariants", [])[:4]

            return StyleProfile(**profile_dict), f"Anomaly Inject: violates '{rigid_rule}' with {anomaly}"

        except Exception as e:
            logger.warning(f"Anomaly inject failed: {e}, using fallback")
            profile_dict = profile.model_dump()
            # Fallback: invert one color
            profile_dict["texture"]["special_effects"] = ["one deliberately wrong-colored element"] + profile_dict["texture"].get("special_effects", [])[:2]
            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (anomaly)"
            profile_dict["core_invariants"] = ["single color anomaly"] + profile_dict.get("core_invariants", [])[:4]
            return StyleProfile(**profile_dict), "[anomaly inject fallback] Added one wrong-colored element"

    def _mutate_spectral_echo(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Add faint ghost-layers as texture (echoes of earlier generations)."""
        profile_dict = profile.model_dump()

        # Add ghost layer effects
        current_effects = profile_dict["texture"].get("special_effects", [])
        ghost_effects = [
            "translucent ghost layers",
            "faint echoes of previous forms",
            "spectral afterimages bleeding through"
        ]
        profile_dict["texture"]["special_effects"] = ghost_effects[:2] + current_effects[:1]

        # Modify surface texture
        current_surface = profile_dict["texture"].get("surface", "")
        profile_dict["texture"]["surface"] = f"{current_surface}, layered with translucent echoes"

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} (spectral)"

        # Add to core invariants
        profile_dict["core_invariants"] = ["spectral ghost echoes throughout"] + profile_dict.get("core_invariants", [])[:4]

        return StyleProfile(**profile_dict), "Spectral Echo: ghost-layers of past forms visible"

    # === ENVIRONMENT MUTATIONS ===

    def _mutate_climate_morph(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Apply environmental system changes (dust storm, fog, cosmic vacuum)."""
        climate_name, climate_changes = random.choice(CLIMATE_MORPHS)
        return self._apply_preset_mutation(profile, climate_name, climate_changes, "Climate Morph", "climate")

    def _mutate_biome_shift(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Reframe as a new ecosystem (desert, coral reef, fungal forest)."""
        biome_name, biome_changes = random.choice(BIOME_SHIFTS)
        return self._apply_preset_mutation(profile, biome_name, biome_changes, "Biome Shift", "biome")

    # === TECHNICAL MUTATIONS ===

    def _mutate_algorithmic_wrinkle(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Introduce deterministic computational artifacts (CRT, JPEG, halftone)."""
        artifact_name, artifact_changes = random.choice(ALGORITHMIC_WRINKLES)
        return self._apply_preset_mutation(profile, artifact_name, artifact_changes, "Algorithmic Wrinkle", "processed")

    def _mutate_symbolic_reduction(self, profile: StyleProfile) -> tuple[StyleProfile, str]:
        """Turn features into metaphoric/symbolic shapes."""
        symbol_name, symbol_changes = random.choice(SYMBOLIC_REDUCTIONS)
        return self._apply_preset_mutation(profile, symbol_name, symbol_changes, "Symbolic Reduction", "symbolic")

    def _summarize_profile(self, profile: StyleProfile) -> str:
        """Create a text summary of a style profile for VLM prompts."""
        parts = []

        if profile.style_name:
            parts.append(f"Style: {profile.style_name}")

        if profile.core_invariants:
            parts.append(f"Key traits: {', '.join(profile.core_invariants[:3])}")

        if profile.palette.color_descriptions:
            parts.append(f"Colors: {', '.join(profile.palette.color_descriptions[:4])}")

        if profile.palette.saturation:
            parts.append(f"Saturation: {profile.palette.saturation}")

        if profile.texture.surface:
            parts.append(f"Texture: {profile.texture.surface}")

        if profile.lighting.lighting_type:
            parts.append(f"Lighting: {profile.lighting.lighting_type}")

        if profile.line_and_shape.line_quality:
            parts.append(f"Lines: {profile.line_and_shape.line_quality}")

        if profile.line_and_shape.shape_language:
            parts.append(f"Shapes: {profile.line_and_shape.shape_language}")

        if profile.composition.framing:
            parts.append(f"Composition: {profile.composition.framing}")

        return "\n".join(parts)

    async def mutate(
        self,
        profile: StyleProfile,
        strategy: MutationStrategy,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply a mutation strategy to create a divergent style.

        Args:
            profile: The current style profile to mutate
            strategy: Which mutation strategy to use
            session_id: Optional session ID for WebSocket logging

        Returns:
            (mutated_profile, mutation_description)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log(f"Applying mutation strategy: {strategy.value}")

        if strategy == MutationStrategy.RANDOM_DIMENSION:
            mutated, description, _ = self._mutate_random_dimension(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.WHAT_IF:
            mutated, description = await self._mutate_what_if(profile, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CROSSOVER:
            mutated, description = self._mutate_crossover(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.INVERSION:
            mutated, description = self._mutate_inversion(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.AMPLIFY:
            mutated, description = await self._mutate_amplify(profile, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DIVERGE:
            mutated, description = await self._mutate_diverge(profile, None, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TIME_SHIFT:
            mutated, description = self._mutate_time_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MEDIUM_SWAP:
            mutated, description = self._mutate_medium_swap(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MOOD_SHIFT:
            mutated, description = self._mutate_mood_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SCALE_WARP:
            mutated, description = self._mutate_scale_warp(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DECAY:
            mutated, description = self._mutate_decay(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.REMIX:
            mutated, description = self._mutate_remix(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CONSTRAIN:
            mutated, description = self._mutate_constrain(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CULTURE_SHIFT:
            mutated, description = self._mutate_culture_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHAOS:
            mutated, description = self._mutate_chaos(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.REFINE:
            mutated, description = await self._mutate_refine(profile, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === SPATIAL MUTATIONS ===
        elif strategy == MutationStrategy.TOPOLOGY_FOLD:
            mutated, description = self._mutate_topology_fold(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SILHOUETTE_SHIFT:
            mutated, description = self._mutate_silhouette_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.PERSPECTIVE_DRIFT:
            mutated, description = self._mutate_perspective_drift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.AXIS_SWAP:
            mutated, description = self._mutate_axis_swap(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        # === PHYSICS MUTATIONS ===
        elif strategy == MutationStrategy.PHYSICS_BEND:
            mutated, description = self._mutate_physics_bend(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_GRAVITY:
            mutated, description = self._mutate_chromatic_gravity(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MATERIAL_TRANSMUTE:
            mutated, description = self._mutate_material_transmute(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TEMPORAL_EXPOSURE:
            mutated, description = self._mutate_temporal_exposure(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        # === PATTERN MUTATIONS ===
        elif strategy == MutationStrategy.MOTIF_SPLICE:
            mutated, description = self._mutate_motif_splice(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.RHYTHM_OVERLAY:
            mutated, description = self._mutate_rhythm_overlay(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.HARMONIC_BALANCE:
            mutated, description = self._mutate_harmonic_balance(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SYMMETRY_BREAK:
            mutated, description = self._mutate_symmetry_break(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        # === DENSITY MUTATIONS ===
        elif strategy == MutationStrategy.DENSITY_SHIFT:
            mutated, description = self._mutate_density_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DIMENSIONAL_SHIFT:
            mutated, description = self._mutate_dimensional_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MICRO_MACRO_SWAP:
            mutated, description = self._mutate_micro_macro_swap(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ESSENCE_STRIP:
            mutated, description = await self._mutate_essence_strip(profile, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === NARRATIVE MUTATIONS ===
        elif strategy == MutationStrategy.NARRATIVE_RESONANCE:
            mutated, description = self._mutate_narrative_resonance(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ARCHETYPE_MASK:
            mutated, description = self._mutate_archetype_mask(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ANOMALY_INJECT:
            mutated, description = await self._mutate_anomaly_inject(profile, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SPECTRAL_ECHO:
            mutated, description = self._mutate_spectral_echo(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        # === ENVIRONMENT MUTATIONS ===
        elif strategy == MutationStrategy.CLIMATE_MORPH:
            mutated, description = self._mutate_climate_morph(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.BIOME_SHIFT:
            mutated, description = self._mutate_biome_shift(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        # === TECHNICAL MUTATIONS ===
        elif strategy == MutationStrategy.ALGORITHMIC_WRINKLE:
            mutated, description = self._mutate_algorithmic_wrinkle(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SYMBOLIC_REDUCTION:
            mutated, description = self._mutate_symbolic_reduction(profile)
            await log(f"Mutation: {description}")
            return mutated, description

        else:
            raise ValueError(f"Unknown mutation strategy: {strategy}")

    def _build_exploration_prompt(
        self,
        profile: StyleProfile,
        subject: str,
    ) -> str:
        """
        Build a prompt from the mutated style profile.
        Uses mechanical assembly for predictability.
        """
        # Build style descriptors
        style_parts = []

        # Core invariants (mutation markers)
        if profile.core_invariants:
            style_parts.extend(profile.core_invariants[:3])

        # Palette
        if profile.palette.color_descriptions:
            colors = ", ".join(profile.palette.color_descriptions[:4])
            style_parts.append(f"color palette of {colors}")
        if profile.palette.saturation:
            style_parts.append(f"{profile.palette.saturation} saturation")

        # Texture
        if profile.texture.surface:
            style_parts.append(profile.texture.surface)
        if profile.texture.noise_level and profile.texture.noise_level != "medium":
            style_parts.append(f"{profile.texture.noise_level} noise/grain")

        # Lighting
        if profile.lighting.lighting_type:
            style_parts.append(profile.lighting.lighting_type)
        if profile.lighting.shadows:
            style_parts.append(profile.lighting.shadows)

        # Line and shape
        if profile.line_and_shape.line_quality:
            style_parts.append(profile.line_and_shape.line_quality)
        if profile.line_and_shape.shape_language:
            style_parts.append(profile.line_and_shape.shape_language)

        # Composition
        if profile.composition.framing:
            style_parts.append(profile.composition.framing)

        # Combine with subject
        style_desc = ", ".join(style_parts)
        return f"{subject}. {style_desc}"

    async def generate_exploration_image(
        self,
        profile: StyleProfile,
        subject: str,
        session_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Generate an image from a mutated style profile.

        Args:
            profile: The mutated style profile
            subject: What to generate
            session_id: Optional session ID for logging

        Returns:
            (image_b64, prompt_used)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        # Build prompt from mutated profile
        prompt = self._build_exploration_prompt(profile, subject)
        await log(f"Generating with prompt: {prompt[:100]}...")

        # Generate image
        image_b64 = await comfyui_service.generate(
            prompt=prompt,
            session_id=session_id,
        )

        await log("Exploration image generated", "success")
        return image_b64, prompt

    async def score_exploration(
        self,
        parent_image_b64: str | None,
        child_image_b64: str,
        mutation_description: str,
        session_id: str | None = None,
    ) -> ExplorationScores:
        """
        Score an exploration snapshot on novelty, coherence, and interest.

        Args:
            parent_image_b64: The parent image (None if this is root/first)
            child_image_b64: The newly generated image
            mutation_description: Description of the mutation applied
            session_id: Optional session ID for logging

        Returns:
            ExplorationScores with all three dimensions and combined score
        """
        import re

        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log("Scoring exploration (novelty, coherence, interest)...")

        # Default scores
        novelty = 50.0
        coherence = 70.0
        interest = 60.0

        # === NOVELTY SCORING ===
        # How different is this from the parent?
        if parent_image_b64:
            novelty_prompt = """Compare these two images and score from 0-100 how DIFFERENT the second image's visual style is from the first.

0 = Identical style (same colors, lighting, texture, composition)
25 = Minor variations (slightly different but clearly same style)
50 = Noticeably different (some shared elements but distinct feel)
75 = Very different (few similarities, transformed appearance)
100 = Completely transformed (unrecognizable as related)

Focus on STYLE differences, not subject matter. Look at:
- Color palette and saturation
- Lighting quality and direction
- Texture and surface treatment
- Composition and framing
- Overall mood and atmosphere

Output ONLY a JSON object: {"novelty_score": <number>}"""

            try:
                response = await vlm_service.analyze(
                    prompt=novelty_prompt,
                    images=[parent_image_b64, child_image_b64],
                    max_retries=2,
                )

                response = response.strip()
                if response.startswith("{"):
                    data = json.loads(response)
                    novelty = float(data.get("novelty_score", 50))
                else:
                    match = re.search(r'(\d+)', response)
                    if match:
                        novelty = float(match.group(1))

                novelty = max(0, min(100, novelty))
                await log(f"Novelty score: {novelty:.1f}", "success")

            except Exception as e:
                await log(f"Novelty scoring failed: {e}", "warning")
                novelty = random.uniform(45, 75)
        else:
            await log("First snapshot - baseline novelty = 0", "info")
            novelty = 0

        # === COHERENCE SCORING ===
        # Is this a valid, consistent style (not random noise)?
        coherence_prompt = """Analyze this image and score from 0-100 how COHERENT its visual style is.

A coherent style means:
- Consistent color palette throughout
- Unified lighting approach
- Consistent texture/surface treatment
- Elements work together harmoniously
- Intentional artistic choices are evident

0 = Random noise, no consistent style, chaotic mess
25 = Some style elements but very inconsistent
50 = Moderately coherent, some unity but rough edges
75 = Strong coherence, clear intentional style
100 = Perfect coherence, masterfully unified style

Output ONLY a JSON object: {"coherence_score": <number>}"""

        try:
            response = await vlm_service.analyze(
                prompt=coherence_prompt,
                images=[child_image_b64],
                max_retries=2,
            )

            response = response.strip()
            if response.startswith("{"):
                data = json.loads(response)
                coherence = float(data.get("coherence_score", 70))
            else:
                match = re.search(r'(\d+)', response)
                if match:
                    coherence = float(match.group(1))

            coherence = max(0, min(100, coherence))
            await log(f"Coherence score: {coherence:.1f}", "success")

        except Exception as e:
            await log(f"Coherence scoring failed: {e}", "warning")
            coherence = random.uniform(60, 80)

        # === INTEREST SCORING ===
        # Is this visually striking and compelling?
        interest_prompt = """Score this image from 0-100 on visual INTEREST and aesthetic appeal.

Consider:
- Is it visually striking or memorable?
- Does it evoke an emotional response?
- Is there something unique or surprising about it?
- Would someone stop scrolling to look at this?
- Does it have artistic merit?

0 = Boring, generic, forgettable, no appeal
25 = Mildly interesting, some visual merit
50 = Moderately interesting, decent aesthetic
75 = Very interesting, visually compelling
100 = Stunning, unforgettable, would stop anyone in their tracks

Output ONLY a JSON object: {"interest_score": <number>}"""

        try:
            response = await vlm_service.analyze(
                prompt=interest_prompt,
                images=[child_image_b64],
                max_retries=2,
            )

            response = response.strip()
            if response.startswith("{"):
                data = json.loads(response)
                interest = float(data.get("interest_score", 60))
            else:
                match = re.search(r'(\d+)', response)
                if match:
                    interest = float(match.group(1))

            interest = max(0, min(100, interest))
            await log(f"Interest score: {interest:.1f}", "success")

        except Exception as e:
            await log(f"Interest scoring failed: {e}", "warning")
            interest = random.uniform(50, 70)

        # === COMBINED SCORE ===
        # Weighted combination: novelty and interest matter most, coherence is sanity check
        combined = (novelty * 0.4) + (interest * 0.4) + (coherence * 0.2)

        await log(f"Final scores - Novelty: {novelty:.1f}, Coherence: {coherence:.1f}, Interest: {interest:.1f}, Combined: {combined:.1f}")

        return ExplorationScores(
            novelty=novelty,
            coherence=coherence,
            interest=interest,
            combined=combined,
        )

    async def explore_step(
        self,
        current_profile: StyleProfile,
        parent_image_b64: str | None,
        subject: str,
        strategy: MutationStrategy | None = None,
        preferred_strategies: list[MutationStrategy] | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str, str, str, ExplorationScores]:
        """
        Run one complete exploration step.

        This is the main entry point that:
        1. Applies a mutation to the profile
        2. Generates an image from the mutated profile
        3. Scores the exploration

        Args:
            current_profile: The style profile to mutate from
            parent_image_b64: Parent image for comparison (None if first)
            subject: What to generate
            strategy: Specific strategy to use, or None for random
            preferred_strategies: List of strategies to choose from
            session_id: Optional session ID for logging

        Returns:
            (mutated_profile, mutation_description, image_b64, prompt_used, scores)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log("Starting exploration step...")

        # Select strategy
        if strategy is None:
            if preferred_strategies:
                strategy = random.choice(preferred_strategies)
            else:
                strategy = MutationStrategy.RANDOM_DIMENSION

        await log(f"Selected strategy: {strategy.value}")

        # Step 1: Mutate the profile
        mutated_profile, mutation_description = await self.mutate(
            profile=current_profile,
            strategy=strategy,
            session_id=session_id,
        )

        # Step 2: Generate image
        image_b64, prompt_used = await self.generate_exploration_image(
            profile=mutated_profile,
            subject=subject,
            session_id=session_id,
        )

        # Step 3: Score the exploration
        scores = await self.score_exploration(
            parent_image_b64=parent_image_b64,
            child_image_b64=image_b64,
            mutation_description=mutation_description,
            session_id=session_id,
        )

        await log(f"Exploration step complete. Novelty: {scores.novelty:.1f}", "success")

        return mutated_profile, mutation_description, image_b64, prompt_used, scores


# Singleton instance
style_explorer = StyleExplorer()
