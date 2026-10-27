"""Python port of the dataviz skill's validate_palette.js checks (OKLab, Machado 2009 CVD, WCAG contrast)."""
import math
import sys

BAND = {"light": (0.43, 0.77)}
CHROMA_FLOOR, CVD_TARGET, CVD_FLOOR, NORMAL_FLOOR, CONTRAST_MIN = 0.10, 8.0, 6.0, 15.0, 3.0
SURFACE = "#fcfcfb"
ORD_DL, ORD_LIGHT = 0.06, 2.0
M = {"protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
     "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
     "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]}


def srgb(h):
    h = h.strip().lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def lin(h):
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb(h)]


def oklab_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]


def oklch(h):
    L, a, b = oklab_lin(lin(h))
    return L, math.hypot(a, b), (math.degrees(math.atan2(b, a)) % 360)


def sim(h, k):
    r, g, b = lin(h)
    return [max(0, min(1, M[k][i][0] * r + M[k][i][1] * g + M[k][i][2] * b)) for i in range(3)]


def dE(h1, h2, k=None):
    a = oklab_lin(sim(h1, k) if k else lin(h1))
    b = oklab_lin(sim(h2, k) if k else lin(h2))
    return 100 * math.dist(a, b)


def contrast(h1, h2):
    Y = lambda h: sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), lin(h)))
    a, b = sorted((Y(h1), Y(h2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def categorical(p, pairs="adjacent"):
    lo, hi = BAND["light"]
    out = []
    off = [(c, round(oklch(c)[0], 3)) for c in p if not lo <= oklch(c)[0] <= hi]
    out.append(("Lightness band", not off, off or f"all {len(p)} in L {lo}-{hi}"))
    lowc = [(c, round(oklch(c)[1], 3)) for c in p if oklch(c)[1] < CHROMA_FLOOR]
    out.append(("Chroma floor", not lowc, lowc or f"all >= {CHROMA_FLOOR}"))
    pl = [(i, j) for i in range(len(p)) for j in range(i + 1, len(p))] if pairs == "all" else [(i, i + 1) for i in range(len(p) - 1)]
    w = min((dE(p[i], p[j], k), k, p[i], p[j]) for k in ("protan", "deutan") for i, j in pl)
    st = "PASS" if w[0] >= CVD_TARGET else ("WARN" if w[0] >= CVD_FLOOR else "FAIL")
    out.append(("CVD separation", st, f"worst {pairs} {w[2]}<->{w[3]} dE {w[0]:.1f} ({w[1]})"))
    nw = min((dE(p[i], p[j]), p[i], p[j]) for i, j in pl)
    out.append(("Normal-vision floor", nw[0] >= NORMAL_FLOOR, f"worst {nw[1]}<->{nw[2]} dE {nw[0]:.1f}"))
    low = [(c, round(contrast(c, SURFACE), 2)) for c in p if contrast(c, SURFACE) < CONTRAST_MIN]
    out.append(("Contrast vs surface", "WARN(relief)" if low else True, low or "all >= 3:1"))
    return out


def ordinal(p):
    Ls = [oklch(c)[0] for c in p]
    mono = Ls == sorted(Ls) or Ls == sorted(Ls, reverse=True)
    gaps = [abs(Ls[i + 1] - Ls[i]) for i in range(len(Ls) - 1)]
    light = max(p, key=lambda c: oklch(c)[0])
    hues = [oklch(c)[2] for c in p]
    spread = max(hues) - min(hues)
    spread = 360 - spread if spread > 180 else spread
    return [("Lightness monotone", mono, [round(x, 3) for x in Ls]), ("Adjacent dL", min(gaps) >= ORD_DL, [round(g, 3) for g in gaps]),
            ("Light-end contrast", contrast(light, SURFACE) >= ORD_LIGHT, f"{light} {contrast(light, SURFACE):.2f}:1"),
            ("Single hue", spread <= 40, f"spread {spread:.0f} deg")]


if __name__ == "__main__":
    pal = sys.argv[1].split(",")
    res = ordinal(pal) if "--ordinal" in sys.argv else categorical(pal, "all" if "--all" in sys.argv else "adjacent")
    for name, ok, msg in res:
        print(f"{'PASS' if ok is True else ('FAIL' if ok is False else ok):12} {name:22} {msg}")
