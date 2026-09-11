---
name: sds-to-plc
description: Turn Software Design Spec workbooks (a Process Modeling state diagram and a Unit Device & Alarm Matrix, plus process/timer setpoint, alarm setpoint and I/O sheets) into a Studio 5000 / Logix ladder program, delivered as a zip of importable routine-scope .L5X files, in McRae Integration house style. Use this skill whenever the user mentions an SDS, a process model, a device matrix, an alarm matrix, alarm or timer setpoints, App05/App06, a state diagram spreadsheet, a unit program, ladder logic, RSLogix, Studio 5000, Logix Designer, .L5X, PlantPAx or P_ AOIs (P_DIn, P_DOut, P_AIn, P_Alarm, P_Intlk), rung generation, state machine transitions, Unit_State_Activations, or asks to build, extend, audit, or restyle PLC code from engineering documentation — even if they don't say "L5X" or "skill" explicitly. Also use it when the user supplies .xlsx design documents alongside a .L5X or controller tag CSV, or asks to make new PLC code match the style of existing PLC code.
---

# SDS → Studio 5000 Program

Convert engineering design documentation into a working, importable Logix program.

The two workbooks divide the design cleanly, and the translation from them to ladder is
close to mechanical. The value of this skill is doing that translation *completely and
traceably* — every arrow on the diagram and every cell in the matrix ends up as a rung,
and every rung says which document element it came from.

**The deliverable is a zip containing one routine-scope `.L5X` per routine**, ready for
Studio 5000's Import Routine. See step 5.

## Environment

Everything this skill needs is in its own directory. Paths below (`references/…`,
`scripts/…`, `assets/…`) are relative to that directory — normally
`.github/skills/sds-to-plc/` in the repository, or `~/.copilot/skills/sds-to-plc/`
if it is installed as a personal skill.

- **Input workbooks** come from the workspace, or from a path the user gives. Ask for the
  path if it isn't obvious; don't guess at a filename.
- **Output** goes to `out/` at the repository root unless the user names somewhere else.
  Create the directory if it isn't there. On a branch the user intends to keep, add `out/`
  to `.gitignore` rather than committing generated exports — unless the user is running you
  as the cloud agent and expects the zip on the PR branch, in which case commit it.
- **Python 3 with `openpyxl`** is required for reading the workbooks
  (`pip install openpyxl`). Everything else uses the standard library.
- Running the bundled scripts needs shell access, so expect a confirmation prompt
  unless the user has pre-approved it.

## What the documents contribute

| Document | Contains | Produces |
|---|---|---|
| **Process Modeling** (state diagram, usually drawn as Excel shapes) | Modes, state boxes, numbered transition arrows with condition text | `Unit_Mode`, `Unit_State_Transitions`, `Unit_Timers`, `Unit_Setpoints` |
| **Device & Alarm Matrix** | TAG row (device inventory), DEVICES half (per-state commands), ALARMS half (per-state gating) | device AOI routines, `Unit_State_Activations`, `Unit_Alarms`, `IO_Mapping_*` |
| **Process / timer setpoints** (usually a tab in the matrix workbook) | Times, delays and counters with presets and limits | `*_SP` tags, `Timer_SP_Calc` instances, `Unit_Setpoints`, `Unit_Timers` |
| **Alarm setpoints** (usually a tab in the matrix workbook) | Trip levels and confirm delays | `*_Trip_SP` tags, the comparisons inside the confirm timers |
| **I/O list** (if provided) | Physical points | `IO_Mapping_Inputs` / `IO_Mapping_Outputs` |

The setpoint tabs often carry a **Location / logic** column naming the tag and the
routine and rung where it belongs. Treat it as the tag dictionary and the rung
ordering spec — matching it is most of what makes the output look like the team's
own code. See the rung 0 convention in `references/house-style.md`.

## Workflow

### 1. Read the documents completely before writing anything

State diagrams are usually **drawings, not cells** — plain text extraction and openpyxl will
return almost nothing, because the content lives in the drawing XML. Unzip the workbook and
pull the shape text:

```bash
mkdir -p /tmp/pm && cd /tmp/pm && unzip -o -q <workbook.xlsx>
python3 -c "
import re
c = open('xl/drawings/drawing1.xml', encoding='utf-8').read()
for s in re.findall(r'<xdr:sp[ >](.*?)</xdr:sp>', c, re.S):
    t = ''.join(re.findall(r'<a:t>([^<]*)</a:t>', s))
    if t.strip(): print(repr(t.strip()))
"
```

Shapes come out in document order, so a state box is followed by its outgoing arrow numbers
and condition text. Read the matrix with openpyxl **by cell coordinate**, not as flattened
text — the column a letter sits in is what tells you which alarm it gates.

### 2. Establish the tag vocabulary before writing logic

If the user supplied an existing program or a controller tag CSV export, **their existing tag
names win** — reuse them exactly, and name anything new to match the same pattern. This matters
more than any other single thing for the output feeling like their code rather than generated code.
See `references/house-style.md`.

### 3. Build the inventory

Work out, on paper first: the state bit map, the device list with AOI types, the alarm list with
its armed states, the timer list, and the setpoint list. Getting this wrong is expensive to
unwind later because every routine references it.

### 4. Generate with a script, not by hand

Write a Python generator that emits the files. Hand-writing 200+ rungs invites typos and makes
revisions painful; a generator makes "regenerate with X changed" cheap. `scripts/l5x_builder.py`
has the emitters (`tag`, `rung`, `routine`, `branch`) and loads the bundled AOI library.

Add the skill's `scripts/` directory to `sys.path` so the module resolves wherever the
generator itself lives:

```python
import sys
sys.path.insert(0, '.github/skills/sds-to-plc/scripts')   # adjust if installed elsewhere
from l5x_builder import *
```

`l5x_builder.py` finds `assets/library.xml` relative to its own location, so it works from any
working directory.

Read `references/translation-rules.md` for the document-element → rung mapping, and
`references/house-style.md` for naming, comment style, and routine order.

### 5. Emit a routine-scope bundle — this is the deliverable

The output is a **zip of one `.L5X` per routine**, not a single file. Engineers import
routines one at a time into an existing program, and Studio 5000's Import Routine only
accepts files whose `TargetType` is `Routine`. A program-scope export is a different
artifact for a different menu item, and handing one over means the work can't be imported
at all.

```python
from l5x_builder import write_bundle
write_bundle('out/<Unit>_Routines.zip', tags, routines,
             program_name='<Unit>', controller_name='<Unit>_Unit',
             sources='Generated from <workbook names>.',
             notes='I/O NOTE: ... placeholders to repoint ...')
```

`write_bundle` numbers each file `NN_<RoutineName>.L5X` in scan order, sorts the dispatcher
last so its JSR targets exist by the time it lands, writes a README explaining the import
procedure, and includes the program-scope export alongside for anyone who wants the whole
thing in one go. Every routine file carries the full AOI library and tag list as
`Use="Context"`, so any one of them imports standalone into an empty project.

If your copy of `scripts/l5x_builder.py` has no `write_bundle` — check with
`grep -n "def write_bundle" scripts/l5x_builder.py` — build the bundle yourself from
`assemble()`, emitting each routine with `TargetName` set to the routine, `TargetType="Routine"`,
and every enclosing element marked `Use="Context"`. Say so in your reply rather than quietly
falling back to a single program-scope file; the routine-scope bundle is the thing the
engineer can actually import. `references/l5x-format.md` explains the `Use` attributes.

Emit every routine every time, including the empty placeholders — the constant skeleton is
the point. See `references/l5x-format.md` for the file shape.

### 6. Validate before delivering

```bash
python3 .github/skills/sds-to-plc/scripts/validate_l5x.py out/<output>.zip
```

Point it at the zip, not at a single file — several of the checks are cross-file. It checks
XML well-formedness, that the header target actually carries `Use="Target"`, balanced brackets
and terminating semicolons in every rung, that every tag referenced in logic is declared, that
every `.Member` exists on its datatype, that each filename matches its routine, that every JSR
target has a file and every file is reachable, that the dispatcher sorts last, and that the
routine files agree with the program file rung for rung. Anything it reports would have become
an unhelpful Studio 5000 error at import. Fix all of it.

If the validator only accepts a single file, run it over each `.L5X` in the zip and note in
your reply that the cross-file checks didn't run.

Then check coverage by hand: every numbered condition in the diagram appears as exactly one
branch, and every non-blank matrix cell is represented. Worth scripting as a one-off — read the
matrix back with openpyxl and assert each cell against the generated rung text.

### 7. Report discrepancies rather than silently fixing them

Design documents contain errors — a transition that references the wrong sensor, a timer with no
setpoint, an alarm armed in a state where its condition can't occur, a setpoint with no consumer.
Translate what the document says, add `VERIFY` to the rung comment or tag description explaining
the problem and what it probably should be, and list them in your reply. The engineer
reviewing the import needs to make that call, and silently "fixing" it hides a documentation
defect that will bite on the next revision.

## Output

Write `<Unit>_Routines.zip` to the output directory and give its path. Then give a short table of
routines with their rung counts and the document element each came from — the user is reviewing a
translation and needs to be able to check your work. Say plainly which parts are placeholders
(I/O mapping, almost always). Close with the `VERIFY` list, one line each, stating the problem and
the likely correct value.

Don't offer a bare program-scope `.L5X` as the deliverable. If the user explicitly asks for a
single-file program export instead, give them that — but the zip is the default.

## Reference files

- `references/translation-rules.md` — document element → rung patterns. Read this before generating.
- `references/house-style.md` — naming, comments, routine order, rung templates. Read this before generating.
- `references/l5x-format.md` — the two export shapes, file skeletons, neutral-text syntax, import gotchas. Read this before generating.
- `assets/library.xml` — PlantPAx AOI definitions (`P_AIn`, `P_DIn`, `P_DOut`, `P_Alarm`, `P_Intlk`, `P_Gate`, `P_CmdSrc`, `Timer_SP_Calc`) and UDTs (`udtStateData`, `udtDeviceCtrl`, STRING types), exported from a v36 project. Goes into every generated file so each imports standalone.
- `scripts/l5x_builder.py` — emitters, `assemble`, `write_l5x`, and `write_bundle`.
- `scripts/validate_l5x.py` — pre-delivery checks; accepts a zip, a directory, or one file.
