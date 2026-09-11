# L5X Format Notes

Target: Studio 5000 Logix Designer v36. `SoftwareRevision="36.00"` in the header imports into
v36.x including v36.011. Emit UTF-8 with a BOM.

## File skeleton

A program-scope export that carries its own dependencies:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="36.00" TargetName="MainProgram"
  TargetType="Program" ContainsContext="true" Owner="Operator, McRae Integration Ltd."
  ExportDate="..." ExportOptions="References NoRawData L5KData DecoratedData Context Dependencies ForceProtectedEncoding AllProjDocTrans">
<Controller Use="Context" Name="<ProjectName>">
  <DataTypes Use="Context"> ... </DataTypes>
  <AddOnInstructionDefinitions Use="Context"> ... </AddOnInstructionDefinitions>
  <Tags Use="Context"> ... controller-scoped tags ... </Tags>
  <Programs Use="Context">
    <Program Use="Target" Name="MainProgram" TestEdits="false" MainRoutineName="MainRoutine"
             Disabled="false" UseAsFolder="false">
      <Description><![CDATA[...]]></Description>
      <Tags/>
      <Routines> ... </Routines>
    </Program>
  </Programs>
  <WallClockTime Use="Reference"></WallClockTime>
</Controller>
</RSLogix5000Content>
```

`Use="Context"` marks supporting content; `Use="Target"` marks the one thing being imported.
`assets/library.xml` provides the `<DataTypes>` and `<AddOnInstructionDefinitions>` blocks
complete — paste it in as-is.

## Tags

```xml
<Tag Name="Dry_Timer" TagType="Base" DataType="Timer_SP_Calc" Constant="false" ExternalAccess="Read/Write">
<Description>
<![CDATA[Drying Timer]]>
</Description>
</Tag>
```

Atomic tags can carry an initial value:
```xml
<Data Format="Decorated">
<DataValue DataType="DINT" Radix="Decimal" Value="45"/>
</Data>
```
Use `Radix="Float"` for REAL. Arrays add `Dimensions="32"`.

AOI and UDT instances don't need a `<Data>` block — Studio 5000 fills defaults on import. Omitting
it keeps the file readable and avoids malformed L5K payloads, which are a common import failure.

Bit-level operand comments:
```xml
<Comments>
<Comment Operand=".STS_STATE.6">
<![CDATA[Shampoo State]]>
</Comment>
</Comments>
```

## Routines and rungs

```xml
<Routine Name="Unit_Alarms" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Comment>
<![CDATA[Shampoo No Flow]]>
</Comment>
<Text>
<![CDATA[XIC(Foo.Sts)OTE(Bar.Inp);]]>
</Text>
</Rung>
</RLLContent>
</Routine>
```

Rung numbers start at 0 and must be contiguous. `Type="N"` is a normal rung.

## Neutral text syntax

- Every rung ends with `;`. An empty rung is `;`; a comment-only placeholder is `NOP();`.
- Parallel branches: `[branch1 ,branch2 ,branch3 ]` — note the space before each comma and
  before the closing bracket. Studio 5000 accepts other spacing, but this matches the team's
  exports and keeps diffs clean.
- Branches nest: `[[XIC(A) ,XIC(B) ] XIC(C) OTE(D) ,OTE(E) ]`.
- Series elements are simply concatenated: `XIC(A)XIO(B)OTE(C);`
- AOI calls take the instance tag as the first operand: `P_DOut(Motor_Cmd)`. Some AOIs have
  extra required parameters — check the definition's `Required="true"` parameters if an import
  complains about operand count.
- Instructions used here: `XIC XIO OTE OTL OTU CLR MOVE ADD SUB CPT GRT LES GEQ LEQ EQU JSR NOP SSV`.

## Import gotchas

- **Unbalanced brackets or a missing semicolon** produce an import error that names the routine
  but not the rung. Validate before delivering.
- **Undeclared tags** fail the import outright. Every tag referenced in logic must exist in
  `<Tags>` or be a member of something that does.
- **Misspelled AOI members** fail the same way. `P_DOut` has `Sts_Out`, not `Sts_On`; `P_DIn` has
  `Sts`, not `Sts_PV` for the processed value. When unsure, grep the AOI's `<Parameter Name=...>`
  list in `assets/library.xml`.
- **`STRING_16`** is referenced by PlantPAx AOI local tags but is a predefined type resolved by
  the target project — it does not need to be declared, and the validator ignores it.
- **Rung comments containing `]]>`** break the CDATA. Don't emit that sequence.
- Importing a program whose name already exists prompts to overwrite; that's expected on
  re-import after a regeneration.

## Extracting from an existing export

To harvest a library or study a template:

```python
import re
src = open(path, encoding='utf-8-sig').read()
dt  = re.search(r'<DataType Name="udtStateData".*?</DataType>', src, re.S).group(0)
aoi = re.search(r'<AddOnInstructionDefinition [^>]*Name="P_DOut".*?</AddOnInstructionDefinition>', src, re.S).group(0)
rungs = re.findall(r'<Rung Number="(\d+)".*?<Text>\s*<!\[CDATA\[(.*?)\]\]>', src, re.S)
```

Read `encoding='utf-8-sig'` — Logix exports carry a BOM.
