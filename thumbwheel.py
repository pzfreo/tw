"""
Parametric thumb wheel for ISO flat-head socket-cap bolts (Allen key drive).

Usage:
    python thumbwheel.py [--m M] [--flutes N] [--out stem]

Geometry:
    - Cylindrical body, auto-scaled to bolt size
    - Vertical smooth-edged flutes around the outer surface
    - ISO 10642 countersink on top (90° included angle, flush with hex-socket head)
    - Full-length internal metric ISO thread (M3–M12)
"""

import argparse
from math import pi, cos, sin

from build123d import *
from bd_warehouse.fastener import CounterSunkScrew
from bd_warehouse.thread import IsoThread

PITCHES = {3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75}


def build_thumbwheel(M: int = 6, n_flutes: int = 16) -> Compound:
    pitch  = PITCHES[M]
    # Pull head geometry and tap-drill size direct from bd_warehouse ISO 10642 data
    screw  = CounterSunkScrew(size=f"M{M}-{pitch:g}", fastener_type="iso10642", length=10)
    head_d = screw.head_diameter
    head_h = screw.head_height
    tap_r  = float(list(screw.tap_drill_sizes.values())[0]) / 2  # tap drill radius

    # Auto-scaled dimensions
    wheel_r    = M * 4                               # M6 → r=24 mm (⌀48 mm)
    wheel_h    = max(M * 2.5, head_h + M * 1.5)     # M6 → 15 mm

    # Countersink (90° included angle = 45° half-angle → depth = Δr)
    cs_r_top   = head_d / 2
    cs_r_bot   = M / 2
    cs_depth   = cs_r_top - cs_r_bot  # M6 → 2.5 mm

    # Flute cutter: cylinder centred on outer surface
    arc_spacing = 2 * pi * wheel_r / n_flutes
    flute_r     = arc_spacing * 0.32               # ~3 mm for M6/16 flutes

    thread_len  = wheel_h - cs_depth

    print(f"M{M}: wheel ⌀{wheel_r*2}×{wheel_h} mm | "
          f"cs_depth={cs_depth} mm | "
          f"flute_r={flute_r:.2f} mm | "
          f"thread_len={thread_len} mm")

    # Build IsoThread OUTSIDE any BuildPart context — it auto-adds itself
    # to whatever BuildPart is active when created, which would corrupt the
    # build.  Create it here, then inject it with add().
    thread = IsoThread(
        major_diameter=M,
        pitch=pitch,
        length=thread_len,
        external=False,
        hand="right",
    )

    # ── 1. Base body ────────────────────────────────────────────
    with BuildPart() as tw:
        Cylinder(radius=wheel_r, height=wheel_h)

        # ── 2. Vertical flutes ───────────────────────────────────
        for i in range(n_flutes):
            a = 2 * pi * i / n_flutes
            with Locations([(wheel_r * cos(a), wheel_r * sin(a), 0)]):
                Cylinder(radius=flute_r, height=wheel_h + 2, mode=Mode.SUBTRACT)

        # ── 3. Bore + internal thread ────────────────────────────
        # Bore at major_radius to remove all ridge material, then add the
        # IsoThread ridges back.  Locations context positions the thread
        # (add() ignores .moved() location inside BuildPart).
        Cylinder(radius=tap_r, height=wheel_h, mode=Mode.SUBTRACT)
        with Locations([Location(Vector(0, 0, -wheel_h / 2))]):
            add(thread)

        # ── 4. Countersink last (trims any thread intrusion) ─────
        with Locations([(0, 0, wheel_h / 2 - cs_depth / 2)]):
            Cone(
                bottom_radius=cs_r_bot,
                top_radius=cs_r_top,
                height=cs_depth,
                mode=Mode.SUBTRACT,
            )

    # ── 5. Fillet all outer grip edges in one pass ───────────────
    # Single combined fillet so OCC creates smooth blended corners at the
    # ridge peaks (where rim and vertical edges meet).
    # Radius is limited by the ridge width (arc_spacing − 2×flute_r);
    # 1/3 of that is the safe maximum for the vertical edges.
    ridge_width = arc_spacing - 2 * flute_r        # M6/16 → ~3.4 mm
    fillet_r    = min(M * 0.25, ridge_width / 3.0) # M6 → ~1.0 mm

    def _radial(e):
        c = e.center()
        return (c.X ** 2 + c.Y ** 2) ** 0.5

    raw = tw.part
    tol = 0.1

    grip_edges = ShapeList([
        e for e in raw.edges()
        if _radial(e) > M * 2
        and (
            # rim: top and bottom face edges
            abs(e.center().Z - wheel_h / 2) < tol
            or abs(e.center().Z + wheel_h / 2) < tol
            # vertical: full-height ridge-flute junction edges
            or (abs(e.center().Z) < wheel_h * 0.25
                and e.length > wheel_h * 0.5)
        )
    ])

    part = raw
    if grip_edges:
        part = part.fillet(fillet_r, grip_edges)

    return part


def main():
    ap = argparse.ArgumentParser(description="Build parametric thumb wheel")
    ap.add_argument("--m",      type=int, default=6,  choices=sorted(PITCHES),
                    help="Bolt M size (default 6)")
    ap.add_argument("--flutes", type=int, default=16,
                    help="Number of grip flutes (default 16)")
    ap.add_argument("--out",    type=str, default="",
                    help="Output filename stem (default: thumbwheel_mN)")
    args = ap.parse_args()

    stem = args.out or f"thumbwheel_m{args.m}"

    wheel = build_thumbwheel(M=args.m, n_flutes=args.flutes)

    step_path = f"{stem}.step"
    stl_path  = f"{stem}.stl"
    export_step(wheel, step_path)
    export_stl(wheel,  stl_path)
    print(f"Exported: {step_path}  {stl_path}")


if __name__ == "__main__":
    main()
