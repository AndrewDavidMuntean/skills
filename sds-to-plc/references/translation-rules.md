# Translation Rules

How each element of the design documents becomes ladder logic.

- [Reading the matrix](#reading-the-matrix)
- [State bit assignment](#state-bit-assignment)
- [Unit_Mode](#unit_mode)
- [Unit_State_Transitions](#unit_state_transitions)
- [Unit_State_Activations](#unit_state_activations)
- [Unit_Alarms](#unit_alarms)
- [Unit_Timers and Unit_Setpoints](#unit_timers-and-unit_setpoints)
- [Device routines](#device-routines)
- [P_Intlk](#p_intlk)
- [IO mapping](#io-mapping)
- [HMI routines](#hmi-routines)
- [Coverage audit](#coverage-audit)

---

## Reading the matrix

Row structure: MODE | STATE | NO. | *devices…* | *alarms…*

- The **NO.** column holds the state ID letter (A, B, B1, C, D…, Z). `Z` is always the operator row.
- **Device cells:** `1` or `ON` → command on. `0`, blank, or `OFF` → command off. `PID` → loop to auto
  with a setpoint. `NC` → no change, omit the branch so the previous latched command holds.
  `OPR` → operator owns the device.
- **Alarm cells:** the letter written in the cell says which state arms that alarm. A column with
  `D` in rows D through I means the alarm is gated on across those six states.
- A letter that is **not** the row's own letter is a destination, not a gate — e.g. `B1` written in
  the alarm column of row E means "if this alarm trips while in state E, go to state B1". Treat
  those columns as trip-to-alarm-stop alarms; plain-letter columns are annunciate-only.
- Greyed-out cells mean the alarm doesn't apply to that state. Leave them out of the gate.

Watch for notes in the margin columns and below the table — they carry real requirements
("transfers to STOPPED only if all alarms are cleared", "wait for the timer between X and Y").

## State bit assignment

One-hot bits in a DINT (`Sts_State`). If the user has an existing bit map — in a tag CSV's
`COMMENT` rows, or in an existing program — **use theirs**, including any ordering that looks
odd. Otherwise assign in diagram order, with the operator state last.

Mode bits (`Sts_Mode`) are conventionally `.0` Off, `.1` Auto, `.2` Operator.

## Unit_Mode

One rung per mode. Consume the HMI command, clear the mode word, latch the new bit:

```
XIC(Ctrl.Cmd_AutoMode)OTU(Ctrl.Cmd_AutoMode)<guards>[XIC(Ctrl.Sts_Mode.0) CLR(Ctrl.Sts_Mode) OTL(Ctrl.Sts_Mode.1) ,XIC(Ctrl.Sts_Mode.1) OTE(Ctrl.Cmd_DevicesToAuto) ];
```

Guards come from the diagram's mode conditions — e.g. "Auto selected AND Emergency Stop is NOT
active" becomes `XIO(EStop.Sts)` in series. If the diagram only shows a mode reachable from one
place, add the source-state guard; if it shows the arrow on every state, don't.

## Unit_State_Transitions

**One rung per destination state.** Each parallel branch is one numbered arrow pointing at that
state. Template:

```
[ XIC(<source state>) <condition contacts> , <next arrow> ]
XIO(<dest state>)
CLR(Ctrl.Sts_State)
[ OTL(<dest state>) , OTU(Ctrl.Cmd_AutoStart) ]
```

`CLR` before `OTL` is what keeps the word one-hot. The `XIO(<dest>)` guard stops the rung
re-firing every scan once the state is active. `OTU` the command the transition consumed.

Condition text → contacts:

| Text in the diagram | Rung element |
|---|---|
| "X timer is DONE" | `XIC(<Timer>.Done)` |
| "sensor detects / is On / = 1" | `XIC(<Din>.Sts)` |
| "is NOT true / = 0 / is Closed (feedback = 0)" | `XIO(<Din>.Sts)` |
| "pushbutton is pushed" | `XIC(<PB>.Sts)`, usually via a debounce timer's `.Done` if the setpoint sheet has a debounce time |
| "temp ≥ SP + offset" | a helper compare rung driving a named limit bit, then `XIC(<limit bit>)` |
| "for the duration of the cut-in delay" | a delay timer whose `.Inp` embeds the comparison; contact its `.Done` |
| "alarm active" | `XIC(<alarm>.Alm)` or a summary bit |
| "Auto Stop PB" | `XIC(Ctrl.Cmd_AutoStop)`, plus `OTU` on the output side |
| "no active alarms" | `XIO(<AnyAlarmActive summary bit>)` |

Repeated comparisons get one helper rung near the top of the routine rather than being rebuilt
in every branch.

Production counters ("cars washed", "batches complete") increment on the cycle-completion
transition. `ADD(Counter,1,Counter)` on that branch is inherently one-shot, because the source
state bit clears in the same scan.

## Unit_State_Activations

**One rung per matrix row**, in row order:

```
XIC(<state bit>)[ OTL(<devA>.PCmd_On) OTL(<devB>.PCmd_On) , OTL(<devC>.PCmd_Off) OTL(<devD>.PCmd_Off) ];
```

Group all the ON commands into one branch and all the OFF commands into another — it reads as
two lines on the ladder and matches how the matrix row reads.

| Cell | Branch |
|---|---|
| `1` / `ON` | `OTL(<dev>.PCmd_On)` |
| `0` / blank | `OTL(<dev>.PCmd_Off)` |
| `PID` | `OTL(<loop>.PCmd_Auto)` + `MOVE(<SP>, <loop>.PSet_SP)` |
| fixed position | `OTL(<loop>.PCmd_Man)` + `MOVE(<0 or 100>, <loop>.PSet_CV)` |
| `NC` | omit — the latch holds |
| `OPR` (row Z) | one rung: `XIC(<operator state>)OTE(Ctrl.Cmd_DevicesToOperator);` |

For fixed valve positions, the number depends on fail direction: a fail-open valve gets `100` in
the safe states, a fail-closed one gets `0`. Check the P&ID; if it isn't available, flag it.

Conditional behaviour inside a state (a device cycling on a cut-in/cut-out while the state holds)
becomes nested branches inside that state's rung.

## Unit_Alarms

**One rung per alarm column.** The state contacts are exactly the letters appearing in that
column; add an operator-mode branch for the `Z` row:

```
[[XIC(<state1>) ,XIC(<state2>) ,XIC(Ctrl.Sts_Mode.2) ] <trip condition> OTE(<alm>.Inp) ,OTE(<alm>.Cfg_Exists) ,XIC(AckAllAlarms) OTE(<alm>.PCmd_Ack) OTE(<alm>.PCmd_Reset) ,P_Alarm(<alm>) ];
```

Trip conditions: a discrete alarm contact is `XIC(<Din>.Sts)`; a timeout is the corresponding
timer's `.Done`; an analog trip is a confirm timer's `.Done` whose `.Inp` holds the comparison.

Close the routine with two summary rungs:

- `Trip_To_Alarm_Stop` — OR of the alarms whose matrix cells name the alarm-stopped state.
  `Unit_State_Transitions` uses this to force the trip.
- `Any_Alarm_Active` — OR of all alarms. Used by the "returns to stopped only when all alarms
  are cleared" transition.

Alarms that are gated by state but never change state are still worth building — they annunciate.
If the matrix margin asks whether such an alarm should exist, that's a question for the engineer,
not something to drop.

## Unit_Timers and Unit_Setpoints

Every "timer" phrase in the diagram and every timeout/delay in the setpoint sheet gets one
`Timer_SP_Calc` instance.

State timers:
```
[XIC(<state bit>) OTE(<Timer>.Inp) ,Timer_SP_Calc(<Timer>) ];
```

Timeout timers run while the state is active and the expected condition has *not* yet happened:
```
[[XIC(<stateA>) ,XIC(<stateB>) ] XIO(<arrival sensor>.Sts) OTE(<TO Timer>.Inp) ,Timer_SP_Calc(<TO Timer>) ];
```

Analog fault confirm timers embed the comparison so the alarm only trips after the delay:
```
[XIC(<valve>.Sts_Out) LES(<transmitter>.Val,<LowFlowTrip_SP>) OTE(<Timer>.Inp) ,Timer_SP_Calc(<Timer>) ];
```
Use `XIO(<valve>.Sts_Out)` with `GRT` for the leak/off-flow direction.

`Unit_Setpoints` loads each timer from its setpoint tag every scan, so the HMI-editable tag stays
the single source of truth:
```
[MOVE(0,<Timer>.HrSP) MOVE(0,<Timer>.MinSP) ,MOVE(<SP tag>,<Timer>.SecSP) ];
```

Give every setpoint tag the preset value from the sheet and put the units and limits in its
description. A setpoint on the sheet with no consumer in the matrix is a discrepancy — declare
it anyway and flag it.

## Device routines

One rung per instance. Configuration bits are set from what the matrix says the device has —
don't enable feedback or alarm options for hardware that isn't there.

```
P_DIn:  [OTE(<t>.Cfg_HasTgtDisagreeAlm) ,P_DIn(<t>) ];
P_DOut: [OTE(<t>.Cfg_HasOnFdbk) OTE(<t>.Cfg_UseOnFdbk) ,XIC(SIMULATION) OTE(<t>.Inp_Sim) ,XIC(AckAllAlarms) OTE(<t>.PCmd_Reset) ,XIC(Ctrl.Cmd_DevicesToAuto) OTL(<t>.PCmd_Prog) ,XIC(Ctrl.Cmd_DevicesToOperator) OTL(<t>.PCmd_Oper) ,P_DOut(<t>) ];
P_AIn:  [XIC(SIMULATION) OTE(<t>.Inp_Sim) ,XIC(AckAllAlarms) OTE(<t>.PCmd_Reset) ,P_AIn(<t>) ];
```

When analog alarming is handled by `P_Alarm` objects driven from the matrix, leave the embedded
`Cfg_HasHiAlm` / `Cfg_HasLoAlm` / `Cfg_HasFailAlm` bits off — enabling them with unconfigured
limits produces chatter. Note the reason in the routine's first rung comment.

## P_Intlk

Per device: a header `NOP()` rung naming the device, one rung per interlock condition driving
`Inp_IntlkNN`, then the close rung:

```
[XIC(<d>_Intlk.Sts_IntlkOK) OTE(<d>.Inp_IntlkOK) ,XIC(<d>_Intlk.Sts_NBIntlkOK) OTE(<d>.Inp_NBIntlkOK) ,XIC(<d>.Sts_BypActive) OTE(<d>_Intlk.Inp_BypActive) ,P_Intlk(<d>_Intlk) ];
```

`Inp_Intlk00` is conventionally "System Not OFF": `XIC(Ctrl.Sts_Mode.0)`. Beyond that, derive
interlocks from the physical arrangement rather than the matrix: E-stop on everything that moves,
mutual exclusion between opposed directions (forward/reverse, open/close), motor overloads, and
any permissive the process narrative states. Interlocks that shouldn't apply in operator mode get
`XIO(Ctrl.Sts_Mode.2)` in series.

## IO mapping

One rung per physical point.

```
inputs  discrete: XIC(<module tag>)OTE(<t>.Inp_PV);      (XIO for fail-safe/inverted contacts)
inputs  analog:   CPT(<t>.Inp_PV, <raw-to-EU expression>);
outputs discrete: XIC(<t>.Out)OTE(<module tag>);
```

With no I/O list, generate against clearly-named placeholder arrays (`IO_DI[]`, `IO_DO[]`,
`IO_AI[]`) so the program is complete and runnable, and say plainly in the routine comment and
the chat response that these need repointing.

## HMI routines

`HMI_Overview` — square colour from state (running / alarm / stopped / operator / off), border
colour from the alarm ack summary, and two rungs OR-ing every alarm's `.Alm` with `.Ack` / `.Ack`
inverted.

`HMI_DeviceControl` — one rung per device setting `<dev>_Ctrl.HMILabel`:
0 blank, 1 off mode, 2 operator mode, 3 operator override, 4 external, 5 hand, 6 out of service.

Both are boilerplate; copy the pattern per device.

## Coverage audit

Before delivering, confirm:

1. Every numbered condition on the diagram appears as exactly one branch, and every branch traces
   to a numbered condition.
2. Every non-blank device cell and every alarm letter is represented.
3. Every transition rung does `CLR` before `OTL`.
4. Off / stopped / standby rows drive every device to its documented safe position.
5. Every timer has a setpoint source.
6. Every setpoint on the sheets has a consumer, or is flagged.
