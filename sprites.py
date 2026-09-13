"""Static pixel artwork and colour palettes for the 64x64 matrix.

This module intentionally contains *data*, not drawing logic. Keeping sprite
coordinates and palettes separate makes main.py much easier to navigate and
lets people alter birds, ducks, UFOs and fish without having to understand the
weather/network code.

The tuples are immutable and are imported once at boot, so moving them here
does not add per-frame work to the display loop.
"""

# Fish -----------------------------------------------------------------------

FISH_COLOURS = (
    (118, 72, 8), (78, 96, 105), (112, 42, 24),
    (18, 100, 92), (92, 38, 112), (105, 100, 18),
)
FISH_ACCENTS = (
    (78, 40, 0), (44, 64, 72), (72, 22, 12),
    (8, 58, 54), (52, 18, 70), (62, 58, 6),
)
FISH_WIDTHS = (9, 11, 13)
FISH_HEIGHTS = (5, 6, 7)
FISH_TAIL_SHIFT = (0, -1, 0, 1)

# Festive divider lights ------------------------------------------------------

FESTIVE_COLOURS = ((110, 18, 18), (18, 92, 30), (115, 68, 0), (15, 48, 105))
FESTIVE_BRIGHT = ((175, 35, 28), (30, 145, 48), (185, 112, 5), (25, 82, 165))

# Small roaming UFOs ----------------------------------------------------------

UFO_WIDTHS = (7, 9, 13, 5, 15)
UFO_DOMES = (
    ((2, 0), (3, 0), (4, 0), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)),
    ((3, 0), (4, 0), (5, 0), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1)),
    ((4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1)),
    ((2, 0),),
    ((5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1), (10, 1), (11, 1)),
)
UFO_ROWS = (
    ((0, 6, 2),),
    ((1, 7, 2), (0, 8, 3)),
    ((2, 10, 2), (0, 12, 3), (2, 10, 4)),
    ((1, 3, 1), (0, 4, 2)),
    ((2, 12, 2), (0, 14, 3), (1, 13, 4), (3, 11, 5)),
)
UFO_LIGHTS = ((1, 3, 5), (1, 4, 7), (2, 4, 6, 8, 10), (0, 2, 4), (1, 4, 7, 10, 13))
UFO_LIGHT_Y = (2, 3, 3, 2, 4)
UFO_BEAM_Y = (3, 4, 5, 3, 6)
UFO_COLOURS = (
    ((35, 110, 105), (90, 35, 115)),
    ((110, 42, 32), (105, 95, 20)),
    ((42, 72, 120), (110, 40, 82)),
    ((78, 105, 28), (25, 92, 110)),
    ((112, 58, 18), (25, 105, 120)),
    ((75, 62, 112), (130, 92, 18)),
    ((105, 28, 82), (28, 112, 88)),
)
UFO_DIM_LIGHTS = tuple(tuple(channel // 3 for channel in colours[1]) for colours in UFO_COLOURS)
UFO_DAY_LIGHTS = tuple(tuple(min(220, channel * 2) for channel in colours[1]) for colours in UFO_COLOURS)
UFO_BOB = (0, 0, -1, -1, 0, 1, 1, 0)

# Day birds ------------------------------------------------------------------

# Each palette is body, breast, wing and beak. The species order is kept
# stable because main.py chooses a species by numeric index.
BIRD_COLOURS = (
    ((82, 48, 22), (150, 55, 18), (55, 38, 24), (150, 105, 22)),      # robin
    ((24, 72, 120), (130, 112, 18), (38, 95, 135), (125, 120, 55)),   # blue tit
    ((92, 58, 30), (135, 110, 72), (55, 35, 20), (125, 86, 30)),      # thrush
    ((20, 22, 25), (48, 48, 52), (8, 8, 10), (150, 92, 8)),           # blackbird
    ((35, 112, 42), (78, 145, 35), (18, 76, 38), (175, 62, 18)),      # ring-necked parakeet
    ((118, 20, 28), (165, 38, 22), (20, 70, 125), (175, 120, 45)),    # red macaw
    ((135, 110, 18), (165, 138, 28), (28, 105, 48), (175, 75, 15)),   # yellow parrot
)
BIRD_PECK_BODY = ((4,1),(5,1),(2,2),(3,2),(4,2),(5,2),(6,2),(1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(7,3),(1,4),(2,4),(3,4),(4,4),(5,4),(6,4),(7,4),(2,5),(3,5),(4,5),(5,5),(6,5),(7,5),(3,6),(4,6),(5,6),(6,6),(7,6))
BIRD_BODY = ((5,0),(6,0),(4,1),(5,1),(6,1),(2,2),(3,2),(4,2),(5,2),(6,2),(1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(1,4),(2,4),(3,4),(4,4),(5,4),(2,5),(3,5),(4,5))
BIRD_WING_FRAMES = (
    ((2,3),(3,3),(4,3),(3,4),(4,4)),
    ((2,2),(3,1),(3,2),(4,2),(4,3)),
    ((2,3),(3,3),(4,3),(3,4),(3,5)),
)
BIRD_WING_SEQUENCE = (0, 1, 0, 2)

# Duck family ----------------------------------------------------------------

DUCK_BODY = (
    (0,4),(1,3),(1,4),(1,5),(2,3),(3,3),(4,3),(5,3),(6,3),(7,3),(8,3),
    (2,4),(3,4),(4,4),(5,4),(6,4),(7,4),(8,4),(9,4),(10,4),
    (2,5),(3,5),(4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5),
    (3,6),(4,6),(5,6),(6,6),(7,6),(8,6),(9,6),
)
DUCK_HEAD = ((8,0),(9,0),(10,0),(7,1),(8,1),(9,1),(10,1),(11,1),(7,2),(8,2),(9,2),(10,2),(11,2),(8,3),(9,3),(10,3))
DUCK_WING = ((3,4),(4,4),(5,4),(6,4),(7,4),(4,5),(5,5),(6,5),(7,5),(5,6),(6,6))
DUCK_BILL = ((12,2),(13,2),(11,3),(12,3))
DUCKLING_BODY = ((0,2),(1,1),(1,2),(2,2),(1,3),(2,3),(2,0),(3,0),(3,1))
DUCKLING_BILL = ((4,1),)
DUCK_COLOURS = ((96,68,24),(18,100,65),(60,42,18),(175,105,12),(155,125,18),(110,75,8))
DUCK_FAMILY_WIDTH = 32

# Half-hour / hourly temperature-abduction mothership ------------------------

ABDUCTION_COLOURS = (
    ((92,96,112),(42,112,105),(150,112,12),(110,82,8)),
    ((100,78,116),(92,38,120),(25,125,145),(90,70,135)),
    ((70,105,118),(28,78,132),(145,42,82),(70,100,145)),
    ((105,88,62),(125,55,22),(35,125,62),(135,92,18)),
    ((88,105,72),(68,112,30),(125,38,112),(105,105,25)),
)
ABDUCTION_DIM_LIGHTS = tuple(tuple(channel // 3 for channel in colours[2]) for colours in ABDUCTION_COLOURS)
ABDUCTION_BEAM_SHADES = tuple(
    tuple(tuple(min(160, channel * level // 90) for channel in colours[3]) for level in (48, 66, 84, 102))
    for colours in ABDUCTION_COLOURS
)
ABDUCTION_DAY_LIGHTS = tuple(tuple(min(220, channel * 2) for channel in colours[2]) for colours in ABDUCTION_COLOURS)
ABDUCTION_DAY_BEAM_SHADES = tuple(
    tuple(tuple(min(220, channel * level // 90) for channel in colours[3]) for level in (72, 96, 120, 144))
    for colours in ABDUCTION_COLOURS
)

# Wind-blown leaves -----------------------------------------------------------

LEAF_FRAMES = (
    ((0,0),(1,1),(0,1),(-1,-1)),
    ((0,0),(1,0),(-1,0),(0,1)),
    ((0,0),(-1,1),(0,1),(1,-1)),
)
LEAF_FRAME_SEQUENCE = (0,0,0,1,0,0,0,2)
