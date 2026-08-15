# Ways Abaqus quietly gives you a wrong answer

An error is cheap. You see it, you fix it. What costs money is the run that
finishes, prints a number, and is wrong — because nothing in the chain ever
told you.

Every entry below was **measured on a real Abaqus 2021 solve**, not read out of
a manual. Each one names what you would reasonably write, what Abaqus actually
does with it, and where the check that catches it lives in this repository. If
you find one of these in your own model, that is the point of the page; you do
not need this tool to act on it.

The pattern they share is worth naming up front, because it is the thing to
carry away:

> **A job that completes is not a job that did what you asked.** Abaqus reports
> failures it *knows about*. Whole classes of mistake are not failures from its
> point of view — they are you asking for something it can honestly do nothing
> with, and it does nothing, successfully.

---

## 1. Asking for hex elements on a shape that has no hexes

**What you write** — `elemShape=HEX` with `technique=SYSTEM_ASSIGN` on a part,
then `generateMesh`.

**What Abaqus does** — accepts it. Meshes nothing. Raises nothing. The job
completes.

You get **zero elements** and no indication that anything went wrong. If your
model has other parts that did mesh, the job runs and solves them, and the part
you cared about is simply not in the analysis.

**How to tell** — ask before meshing, not after:
`getMeshControl(region=cell, attribute=TECHNIQUE)` answers `UNMESHABLE` for a
cell that cannot be meshed under the controls currently set. On a bolted
housing it reads `UNMESHABLE` under HEX and `FREE` under TET — which is exactly
the difference between "this part is impossible" and "you asked for hexes on a
shape that has none". A message that only says *no elements* is describing the
symptom.

*In this repo*: `runner/kernel_runtime.py:_mesh_diagnosis`. A part meshed by a
generic call is refused unless the spec states an expected element count
(`runner/build_v2.py`), because nothing else would notice.

---

## 2. A cut that removes nothing, and a cut that lands in the wrong place

**What you write** — `CutExtrude` with a sketch, to put a hole through a plate.

**What Abaqus does** — `sketchUpEdge` decides how sketch coordinates map to
global ones, and **getting it wrong fails silently**.

Measured, cutting an asymmetric r=4 hole at (12, 20) in a 60 × 100 × 5 plate:

| `sketchUpEdge` | result |
|---|---|
| top face, edges 0 and 2 | hole at (12, 20) — correct |
| top face, edges 1 and 3 | **no hole at all**, volume unchanged, no exception |
| bottom face, edge 1 | a real hole of the right radius at **(20, 12)** — x and y transposed |

Look at that last row. Same volume, same element count. **Every symmetric test
case in the world passes it.** That is the one to be afraid of: it is not a
missing feature, it is a correct-looking model of a different part.

There is no way to know the right edge from the geometry alone — it depends on
the face. So the only defence is to measure the result: is the volume what
`original − π r² h` says it should be, and is the hole where you asked for it.

*In this repo*: `runner/kernel_runtime.py:_cut` cuts, then verifies, then rolls
the feature back if the verification fails.

---

## 3. Your measuring instrument is a tessellation

If you check a hole's position by asking the cylindrical face for its centroid,
you are asking a *facet approximation*, not the geometry.

Measured on Abaqus 2021, over holes of r = 4, 6, 12 and 50 cut through depths
of 5 to 200 mm:

- `getRadius()` — exact, zero error in all five cases.
- a point **on** the face sits its own radius from the axis to 2.6e-07 (float noise).
- `getCentroid()` — lands on the axis exactly at r = 4 and r = 6, and **misses
  by 0.00901 at r = 12 and 0.02690 at r = 50**. That is roughly 5.4e-4 · r, and
  it grows with radius.

The removed volume agreed with π r² h to seven digits in every case, so **the
cuts were exact and the instrument was not**.

This one bites in the other direction too. An earlier version of our own check
allowed the centroid `r · 1e-4`, which is 7.5× too tight at r = 12: it **refused
a bore that was in exactly the right place**. A tolerance that does not scale
with the thing it measures is a false-refusal generator.

*In this repo*: the sharp test is radial; the centroid is kept only as a coarse
locator with a tolerance from the table above, and both must agree.

---

## 4. Tie constraints that silently do not tie

This is the most expensive one on the page, because the job converges and the
physics checks pass.

**What you write** — a tie between a bore and a bushing, with the default
position tolerance.

**What Abaqus does** — writes warnings into the `.dat` and solves anyway:

```
***WARNING: SLAVE NODE 830 INSTANCE BUSHING WILL NOT BE TIED TO THE MASTER
            SURFACE ASSEMBLY_BORETIE_MAIN. THE DISTANCE FROM THE MASTER
            SURFACE IS GREATER THAN THE POSITION TOLERANCE VALUE.
...
***NOTE: THE ABOVE WARNING MESSAGE IS BEING SUPPRESSED DUE TO EXCESSIVE
         REPORTING.
***WARNING: 74 nodes are either missing intersection with their respective
            master surface or are outside the adjust zone.
```

Measured on a real bearing block: **85 nodes were left unconstrained** — 11
named individually, then 74 more reported only as a count — the job converged
normally, and three separate equilibrium identities still passed. Equilibrium
does not care *which* nodes carry the load.

Note the suppression line above. **Abaqus stops naming them after a while.** If
you read the `.dat` by eye and count `SLAVE NODE` warnings, you get 11 and the
real number is 85.

**Why it happens** — both surfaces are mesh discretisations of the same r = 12
cylinder, so each is a set of flat facets sitting inside the true surface. The
facet chord height is **h² / (8r)**, which grows with the square of the seed.
The two sides were seeded differently, so their facets did not land on each
other at all.

**Now the part that is easy to get wrong.** There are two knobs — the seed and
the tolerance — and only one of them is a fix. Measured through datacheck alone
on Abaqus 2021, all four combinations:

| local seeds | `position_tolerance` | `WILL NOT BE TIED` blocks |
|---|---|---|
| 1.5 mm | 0.05 | 0 |
| 1.5 mm | 0.10 | 0 |
| none | 0.05 | **11** |
| none | 0.10 | 0 |

Seeding the curved faces down fixes it at *either* tolerance. But look at the
last row: **raising the tolerance from 0.05 to 0.10 silences the warning on a
mesh that has not improved by one element.** The nodes are now inside a window
you widened to contain them. Nothing about the model got better; the check
stopped being a check.

So a tie tolerance fails in two directions and you have to hold both:

- **too tight for the mesh** — real nodes drop out, and the physics identities
  will not notice, so something has to read the `.dat`;
- **too loose for the geometry** — a genuine misalignment binds quietly.
  Measured: push the bushing 0.5 mm out of its bore and at 0.1 mm the datacheck
  catches it; at 1.0 mm it does not.

Get the chord height down first, *then* set the tolerance above the chord
height and below a real misalignment. On a 4 mm wall, 0.1 mm still catches a
part in the wrong place.

One more thing worth having: `WILL NOT BE TIED` appears in
`<job>_syntaxcheck.dat` exactly as it does in the analysis `.dat` — measured,
eleven blocks in both. **You can find this with a datacheck in about 100
seconds instead of a 23-minute solve.**

*In this repo*: `runner/dat_warnings.py` parses every `.dat` warning by
signature, and a signature it does **not** recognise is still reported — because
"we did not recognise this warning" and "there was no warning" must never look
the same. An integrity finding withdraws the regression verdict rather than
letting green KPIs stand.

---

## 5. The launcher's exit code means nothing

**What you write** — a job option, in a script that checks `returncode`.

**What Abaqus does** — measured, all four of these **exit 0**:

| you wrote | what happened |
|---|---|
| `bogusoption=1` | "Abaqus Error", plus the launcher's own list of the 36 options it accepts, then no `.dat` and no `.odb` |
| `double=banana` | "The specified value … is not supported" |
| `user=nosuch.f` | "The following file(s) could not be located" |
| `oldjob=neverran` | same, about `neverran.odb`, when the deck really does carry `*RESTART, READ` |

If your automation branches on the exit code, all four look like success and
you go looking for the `.odb` that was never written.

One more trap in the same place: that printed list of accepted options is
**not** a validator. It omits `gpus`, and `gpus=1` runs — measured, it took 6
licence tokens instead of 5 and 3m45s instead of 11s on the same one-element
deck. A validator built from the launcher's own help text would refuse an
option that works.

*In this repo*: nothing reads the exit code. The verdict comes from the `.sta`
file's own statement about the job.

---

## 6. `odb.steps` is not a dict, and step 1 might not be step 1

Two small ones that produce large errors.

**`odb.steps` is an Abaqus Repository.** `1 in odb.steps` does not return
`False` — it **raises** `String Expected as dictionary Key`. A membership test
written the obvious way dies with a message about dictionary keys that names
neither the step nor the quantity you were reading.

**Indexing steps from zero.** If your post-processing takes a step number and
indexes a list, `step 1` reads the **second** step. On a three-step model —
gravity, then preload, then service — asking for step 1 and getting the preload
step returns a number that is entirely plausible and entirely wrong. Only
`step 3` fails loudly, by running off the end.

This is the shape of the whole page in miniature: **the off-by-one that raises
is harmless; the off-by-one that returns a number is not.**

*In this repo*: numeric step selectors are 1-based, because "step 1" means the
first step in every context an engineer writes it in, and an out-of-range
number is refused with the actual step names listed.

---

## 7. A criterion that can never fail

Not an Abaqus behaviour — a way of writing acceptance criteria that quietly
disables them, and one we shipped ourselves before catching it.

**What you write** — a baseline of `0` for something that should be zero: a
symmetric displacement, a net force that must cancel, a residual.

**What a naive comparison does** — computes relative error against zero,
finds it undefined or infinite, and falls through to "not compared". The
criterion reports pass. **It can never report anything else.** Every
should-be-zero check you wrote is decoration.

The fix is that a zero baseline needs an **absolute** tolerance, and a zero
baseline written *without* one is refused rather than skipped — because a
skipped check and a passed check must not look the same on a report.

---

## What to do with this

Most of these have the same shape: **Abaqus did exactly what it was told, and
what it was told was not what you meant.** No exception is coming, because from
the solver's point of view nothing went wrong.

So the practical rule is not "be careful". It is:

> **Measure the model you built, not just the answer it produced.** Element
> counts. Removed volume. Where the hole landed. How many nodes the constraint
> actually caught. Whether the criterion you wrote is capable of failing.

That is what this project automates — every capability here ships with a check
that runs on a real solver, and the checks refuse a doubtful answer instead of
returning it. See [README.md](../README.md) for what it does and
[docs/ROADMAP.md](ROADMAP.md) for what it does not.

Found one we are missing, or think one of these is wrong on your version? Open
an issue — a counter-measurement is worth more to this page than another entry.
