"""DPI <-> raw (a, r) conversion. The formula is a fitted hypothesis, see PROTOCOL.md."""

MIN_DPI, MAX_DPI, STEP = 100, 3200, 100

# Pairs the vendor app was observed to write for these values.
KNOWN = {800: (0x0B, 2), 1000: (0x0E, 2), 1200: (0x0C, 3), 1600: (0x0D, 4),
         2100: (0x0E, 5), 3200: (0x10, 7)}
_KNOWN_REVERSE = {raw: dpi for dpi, raw in KNOWN.items()}


def _formula(a, r):
    return 25 * (r + 1) * a


def raw_to_dpi(a, r):
    return _KNOWN_REVERSE.get((a, r), _formula(a, r))


def dpi_to_raw(dpi):
    if dpi % STEP or not MIN_DPI <= dpi <= MAX_DPI:
        raise ValueError(f"DPI must be a multiple of {STEP} between {MIN_DPI} and {MAX_DPI}")
    if dpi in KNOWN:
        return KNOWN[dpi]
    candidates = [(a, r) for r in range(1, 8) for a in range(1, 17)]
    return min(candidates, key=lambda ar: (abs(_formula(*ar) - dpi), ar[1]))