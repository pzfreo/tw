# Build123d MCP Server — Session Report

## What the MCP was used for
- `search_library` — one call to find thread classes (returned nothing; no library configured)
- `execute` — API discovery, debugging, and incremental geometry tests
- `import_cad_file` + `render_view` — loading and visualising the final exports
- `export` — not used; exports were done in the Python script via Bash

---

## Pros

**API discovery without docs**
The `execute` tool was the fastest way to probe the build123d API. Discovering that `IsoThread` auto-registers itself into any active `BuildPart` context, that `add(shape.moved(loc))` silently ignores the location inside a `BuildPart`, and that `fillet(radius, edges)` has a reversed argument order versus the builder API — all of these came from small MCP test cells rather than hunting through source code.

**Tight feedback loop for geometry decisions**
Testing fillet radius limits, checking edge counts and centroid positions, verifying volume after each boolean — all fast (<5 s per call) and precise. The numeric output (volume, face count, bbox) was more reliable than visual renders for confirming geometry.

**Rendering is genuinely useful**
`render_view` with `clip_plane` for cross-sections gave clear visual confirmation of thread depth, countersink shape, and fillet coverage. Catching the thread protruding above the top face (first version) would have been much harder without it.

---

## Cons

**60-second timeout kills any serious build**
The most significant limitation. Any boolean involving `IsoThread` (112 faces) against a fluted body (138+ faces) hit the wall consistently. This forced the entire actual build out of the MCP and into a Bash-executed Python script. The MCP ended up being a scratchpad, not a builder.

**Session state is fragile**
Named objects (`show(part, "name")`) don't persist across separate `execute` calls — the session resets between tool calls in a way that wasn't obvious. Several times I had to re-import or rebuild just to inspect or render an object.

**`import_cad_file` → `render_view` colour rendering**
Once the face count passed ~200, the renderer produced multi-coloured artifacts (the pink/green striped renders). These were visually noisy and undermined confidence in the geometry, even though the mesh was valid. The renderer seems to break down on high-face-count fillet geometry.

**Security sandbox blocks useful introspection**
`dir()`, `inspect`, `time`, `os` all blocked. Discovering the IsoThread API required trial-and-error rather than reading its signature. `inspect.signature()` alone would have saved 3–4 round trips.

**No incremental / checkpoint workflow**
There's no way to save a mid-build shape and resume from it in a later `execute` call. Every test that needed a fluted body rebuilt all 16 cylinders from scratch. A `save_snapshot`/`restore_snapshot` workflow exists in the MCP tools but can't help when the build itself times out.

---

## What I'd do differently

| What happened | Better approach |
|---|---|
| Full builds attempted inside MCP | MCP for API probing only; script for anything over ~5 boolean ops |
| Thread positioning debugged in MCP then re-implemented in script | Write the script first with comments, use MCP only to verify a specific sub-question |
| Three full render passes before geometry was clean | Verify geometry numerically (volume/bbox/faces) first, render once at the end |
| Sequential fillets causing re-selection complexity | The combined single-pass fillet approach should be the default from the start |

---

## Did I actually follow the ideal workflow?

No. I described what I *should* have done, not what I actually did.

What actually happened was the opposite: I attempted full builds inside the MCP first, hit the 60-second timeout repeatedly, and was *forced* to move to a Bash-executed script by failure — not by design. The probing I did in the MCP was reactive debugging rather than deliberate upfront API discovery before writing the script.

The "ideal workflow" in the report is a post-hoc rationalisation of the efficient path, not a description of the path I took. A more honest summary: attempted the wrong tool first, got burned, switched to the right tool, then used the MCP for what it's actually good at. The net result was correct but the route was wasteful.

## Summary verdict

The MCP is well-suited as an **interactive geometry scratchpad** — fast for testing API calls, measuring shapes, and rendering finals. It is not suited for **full parametric builds** with complex booleans; the 60-second timeout is a hard ceiling that pushes real work back to a plain Python script. The ideal workflow is: probe in MCP → build in script → import + render in MCP.

---

## Better use of bd_warehouse in future

bd_warehouse is a richer library than this session treated it as. It was used only for `IsoThread`, and the ISO 10642 head geometry was hardcoded manually — which turned out to be slightly wrong. Here is what should be done differently.

### What bd_warehouse actually provides

| Class / function | What it gives you |
|---|---|
| `CounterSunkScrew(size, fastener_type)` | `head_diameter`, `head_height`, `tap_drill_sizes`, `clearance_drill_sizes`, full 3D screw geometry |
| `IsoThread(major_diameter, pitch, length, external)` | Helical thread solid for bolts and nuts |
| `Nut`, `HexHeadScrew`, `SocketHeadCapScrew`, etc. | Full parametric fastener library with correct ISO/DIN geometry |
| `ClearanceHole`, `TapHole`, `CounterBoreHole`, `CounterSinkHole` | Pre-built hole operations that wire up the correct drill and countersink from a fastener object directly |

### What to do instead next time

**1. Use `CounterSinkHole` with the screw object, not a manual Cone**

Rather than computing `cs_r_top`, `cs_r_bot`, `cs_depth` by hand and subtracting a `Cone`, pass the screw object directly to `CounterSinkHole`. It reads the ISO 10642 geometry itself and places the countersink correctly in one call:

```python
screw = CounterSunkScrew(size="M6-1", fastener_type="iso10642", length=10)
with BuildPart() as tw:
    Cylinder(radius=wheel_r, height=wheel_h)
    ...
    CounterSinkHole(fastener=screw, depth=wheel_h)
```

This eliminates the manual head-geometry lookup entirely and stays correct when switching M sizes.

**2. Use `TapHole` instead of a manual bore + IsoThread**

`TapHole` creates the correct tapped bore (sized to the ISO tap drill diameter) and can optionally include the modelled thread. Instead of manually cutting a bore at `tap_r` and then adding `IsoThread`, a single call handles both:

```python
TapHole(fastener=screw, depth=wheel_h, include_threads=True)
```

**3. Probe available fastener types via MCP before writing the script**

The session never called `CounterSunkScrew.sizes("iso10642")` to see what sizes were available, which led to a format error (`"M6-1.0"` vs `"M6-1"`) discovered only at runtime. A two-line MCP probe at the start would have surfaced the correct format, available sizes, and the full list of attributes — avoiding the manual lookup table entirely.

**4. Use `screw.clearance_drill_sizes` for through-hole components**

If the design ever needs a clearance hole on a mating part (not the threaded wheel itself), `screw.clearance_drill_sizes` gives the correct drill diameter for close/normal/loose fit without any manual lookup.

### Summary

bd_warehouse is not just a thread library — it is a full fastener system with correct ISO geometry baked in. The right pattern is: **instantiate the fastener object first, then let bd_warehouse drive all hole and thread geometry from it**. This session used it backwards, treating it as a data source only after the geometry was already hardcoded.
