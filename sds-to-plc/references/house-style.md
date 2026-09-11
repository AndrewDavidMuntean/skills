# House Style

McRae Integration conventions. Following these is what makes generated code look like it was
written by the team rather than by a generator.

## Naming

**Existing names always win.** If the user supplies a controller tag CSV export, an existing
`.L5X`, or even a screenshot, harvest the tag names from it first and reuse them character for
character. Name new tags to match the same pattern. Getting this wrong is the most visible way
generated code reads as foreign.

Two naming families appear in practice. Pick whichever the user's existing artifacts use, and
never mix them in one program:

**Descriptive underscore style** (typical for standalone unit programs):

```
Carriage_Forward_Command      device output
Apply_Shampoo_Command         device output
Start_Wash_Button             discrete input
Car_Inside_Sensor             discrete input
Water_Flow_Level              analog input
Shampoo_No_Flow_Alarm         alarm object
Dry_Timer                     timer
Drying_Time_SP                setpoint
CarWash_Mode_Ctrl             unit state/mode tag
```

Rules: words capitalised and underscore-separated; devices end `_Command`; sensors end `_Sensor`,
`_Button`, `_Switch`; alarms end `_Alarm`; timers end `_Timer`; setpoints end `_SP`; interlock
objects end `_Intlk`; HMI control objects end `_Ctrl`.

**Site/instrument-tag style** (typical when the plant has an instrument index):

```
WRO_AHU124_FV_02              <area>_<unit>_<ISA type>_<loop number>
WRO_AHU124_TT_183
WRO_AHU124_FV_02_Intlk
WRO_AHU124_FV_02_Ctrl
DEH124_Ctrl                   unit state/mode tag
DEH124_HeatingTimer
```

The unit control tag is `<UnitName>_Ctrl` or `<UnitName>_Mode_Ctrl` in both families.

## Comments

Rung comments name the thing; they do not explain it. The comment is a label on a ladder rung
being read at a glance, not documentation prose.

Good:
```
to STOPPED (Cond 05)
AUTO MODE
Shampoo No Flow
CLOSE DOORS
Carriage Fwd Travel Timeout
E-Stop
```

Bad — this is what to avoid:
```
to STOPPED. Branch 1: Auto mode entry. Branch 2 = App05 cond 05 / App06 B1 note: ALARM STOPPED
transfers to STOPPED only when NO alarms are active
```

Keep traceability as a short parenthetical: `(Cond 05)`, `(Cond 02, 08)`, `(B1)`. Roughly 40
characters is comfortable; treat 120 as a hard ceiling.

The one comment allowed to run long is a `VERIFY` note flagging a documentation defect — that
one needs to survive as a warning, so state the problem and the likely correct value.

Section header rungs are `NOP();` with an all-caps comment: `OFF MODE`, `AUTO MODE`,
`OPERATOR MODE`. In `P_Intlk`, each device gets a `NOP();` header rung naming the device.

Tag descriptions follow the same discipline: a short noun phrase, with units and limits appended
for setpoints — `Wax Distribution Time, s (10-120)`.

Bit-level operand comments go on the unit control tag, one per mode bit and one per state bit
(`Off Mode`, `Auto Mode`, `Shampoo State`, `Dry State`). These round-trip into the controller
tag CSV export, which is how the team documents state maps.

## Routine order

`MainRoutine` (or `Main`) is a pure JSR dispatcher, no logic. The order matters — inputs, then
device processing, then decisions, then outputs:

```
1  IO_Mapping_Inputs
2  P_Intlk
3  P_DIn
4  P_AIn
5  P_DOut
6  P_Motor
7  P_PIDE
8  Unit_Setpoints
9  Unit_Timers
10 Unit_Alarms
11 Unit_Mode
12 Unit_State_Transitions
13 Unit_State_Activations
14 HMI_Overview
15 HMI_DeviceControl
16 IO_Mapping_Outputs
17 Clock
18 Temp_Control
```

Include every routine in the dispatcher even when a unit has no motors or loops — emit the
routine as a single empty rung (`;`) rather than dropping the JSR. Keeping the skeleton constant
across units is the point.

Device routines are named after the AOI they call (`P_DIn`, `P_DOut`, `P_AIn`, `P_Intlk`), not
after what they contain.

## Standard tags

Every unit program has these regardless of process:

```
<Unit>_Ctrl / <Unit>_Mode_Ctrl   udtStateData    mode + state words, HMI colours, unit commands
SIMULATION                       BOOL            drives every device AOI's Inp_Sim
AckAllAlarms                     BOOL            drives every PCmd_Reset / PCmd_Ack
PLC_Clock_Sync                   BOOL            consumed by the Clock routine
```

The `Clock` routine is a one-rung standard:
```
XIC(PLC_Clock_Sync)[SSV(WallClockTime,,LocalDateTime,<year>) ,OTU(PLC_Clock_Sync) ];
```

## Tag scope

Controller-scoped (`<Tags Use="Context">`) for device objects, alarms, timers, and setpoints, so
HMI and other programs can reach them. Program-scoped only for genuinely internal working bits.
Match whatever the user's existing export does.

## Structure conventions

- One program per unit, named for the unit.
- State words are one-hot DINTs; `CLR` before every `OTL`.
- Devices are commanded with latches (`PCmd_On` / `PCmd_Off`), never `OTE` — state activations
  latch, and the AOI arbitrates between program and operator ownership.
- Every device that can be commanded gets a matching `_Intlk` and `_Ctrl` object.
- Some sites put a per-transition enable bit (`zz_Placeholder[n]`) in series on each auto
  transition for commissioning. Ask before adding it; don't add it by default, since it leaves
  the program inert on first download.
