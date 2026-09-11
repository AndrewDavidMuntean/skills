#!/usr/bin/env python3
"""Pre-delivery checks for a generated .L5X.

    python3 validate_l5x.py <file.L5X>

Checks, in order:
  1. XML is well-formed.
  2. Every rung has balanced [] and (), and ends with ';'.
  3. Rung numbers are contiguous from 0 within each routine.
  4. Every tag referenced in logic is declared.
  5. Every .Member reference exists on that tag's datatype.
  6. Every JSR target is a routine in the file.
  7. Every routine is reachable from the main routine.
  8. No rung comment exceeds the house-style length ceiling.

Exits non-zero if anything fails. Studio 5000 rejects files failing 1-6 with errors that
name the routine but not the rung, so it is much cheaper to catch them here.
"""

import re
import sys
import xml.etree.ElementTree as ET

INSTRUCTIONS = {
    'XIC', 'XIO', 'OTE', 'OTL', 'OTU', 'ONS', 'OSR', 'OSF', 'CLR', 'MOV', 'MOVE', 'COP',
    'CPS', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'SQR', 'NEG', 'ABS', 'CPT', 'GRT', 'GEQ',
    'LES', 'LEQ', 'EQU', 'NEQ', 'LIM', 'MEQ', 'TON', 'TOF', 'RTO', 'CTU', 'CTD', 'RES',
    'JSR', 'SBR', 'RET', 'JMP', 'LBL', 'NOP', 'AFI', 'MSG', 'GSV', 'SSV', 'FLL', 'AND',
    'OR', 'XOR', 'NOT', 'BTD', 'SWPB', 'TND', 'UID', 'UIE',
}
# GSV/SSV object and attribute names, not tags
GSV_WORDS = {'WallClockTime', 'LocalDateTime', 'Program', 'Task', 'Controller', 'DateTime'}
ATOMIC = {'BOOL', 'SINT', 'INT', 'DINT', 'LINT', 'REAL', 'STRING', 'TIMER', 'COUNTER',
          'CONTROL', 'MESSAGE', 'BIT'}
# Predefined in the target project; PlantPAx AOI local tags reference it.
PREDEFINED_TYPES = {'STRING_16'}

COMMENT_CEILING = 130


def fail(problems, message):
    problems.append(message)


def main(path):
    raw = open(path, encoding='utf-8-sig').read()
    problems = []
    notes = []

    # 1 -----------------------------------------------------------------------
    try:
        ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f'FAIL  XML is not well-formed: {exc}')
        return 1
    notes.append('XML well-formed')

    split = raw.find('<Programs')
    library, program = raw[:split], raw[split:]

    # datatype/AOI definitions available anywhere in the file
    def members_of(typename):
        match = re.search(
            r'<(?:DataType|AddOnInstructionDefinition) [^>]*Name="'
            + re.escape(typename) + r'"(.*?)</(?:DataType|AddOnInstructionDefinition)>',
            raw, re.S)
        if not match:
            return None
        return set(re.findall(r'<(?:Member|Parameter|LocalTag) Name="([^"]+)"', match.group(1)))

    # declared tags: controller context + program scope
    declared = {}
    for m in re.finditer(r'<Tag Name="([^"]+)" TagType="Base" DataType="([^"]+)"'
                         r'(?: Dimensions="(\d+)")?', raw):
        declared[m.group(1)] = (m.group(2), m.group(3))
    notes.append(f'{len(declared)} tags declared')

    routines = re.findall(r'<Routine Name="([^"]+)" Type="RLL">(.*?)</Routine>', program, re.S)
    routine_names = {name for name, _ in routines}
    notes.append(f'{len(routines)} routines')

    # AOI names are callable instructions, not tags
    callable_names = set(INSTRUCTIONS) | routine_names | GSV_WORDS | set(
        re.findall(r'<AddOnInstructionDefinition [^>]*Name="([^"]+)"', raw))

    # 2, 3, 8 -----------------------------------------------------------------
    total_rungs = 0
    references = set()
    jsr_targets = set()
    for name, body in routines:
        rungs = re.findall(r'<Rung Number="(\d+)"[^>]*>(.*?)</Rung>', body, re.S)
        expected = 0
        for number, chunk in rungs:
            total_rungs += 1
            if int(number) != expected:
                fail(problems, f'{name}: rung numbering jumps at {number} (expected {expected})')
            expected += 1

            text_m = re.search(r'<Text>\s*<!\[CDATA\[(.*?)\]\]>', chunk, re.S)
            if not text_m:
                fail(problems, f'{name} rung {number}: no <Text> block')
                continue
            text = text_m.group(1)
            if text.count('[') != text.count(']'):
                fail(problems, f'{name} rung {number}: unbalanced brackets')
            if text.count('(') != text.count(')'):
                fail(problems, f'{name} rung {number}: unbalanced parentheses')
            if not text.strip().endswith(';'):
                fail(problems, f'{name} rung {number}: missing terminating semicolon')

            comment_m = re.search(r'<Comment>\s*<!\[CDATA\[(.*?)\]\]>', chunk, re.S)
            if comment_m:
                comment = ' '.join(comment_m.group(1).split())
                if len(comment) > COMMENT_CEILING and 'VERIFY' not in comment:
                    fail(problems, f'{name} rung {number}: comment is {len(comment)} chars '
                                   f'(house style ceiling {COMMENT_CEILING}, VERIFY notes exempt)')

            for target in re.findall(r'JSR\((\w+)', text):
                jsr_targets.add((name, target))
            for m in re.finditer(
                    r'\b([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]+\])?(?:\.([A-Za-z_][A-Za-z0-9_]*))?',
                    text):
                references.add((name, number, m.group(1), m.group(2) or '', m.group(3) or ''))
    notes.append(f'{total_rungs} rungs, brackets and terminators OK')

    # 4, 5 --------------------------------------------------------------------
    member_cache = {}
    undeclared = set()
    bad_members = set()
    for routine_name, number, base, index, member in sorted(references):
        if base in callable_names:
            continue
        if base not in declared:
            undeclared.add(base)
            continue
        datatype, dims = declared[base]
        if index and not dims:
            fail(problems, f'{routine_name} rung {number}: {base} is indexed but not an array')
        if not member:
            continue
        if datatype in ATOMIC:
            if not member.isdigit():
                bad_members.add(f'{base}.{member}: {datatype} has no members '
                                f'({routine_name} rung {number})')
            continue
        if datatype not in member_cache:
            member_cache[datatype] = members_of(datatype)
        available = member_cache[datatype]
        if available is None:
            if datatype not in PREDEFINED_TYPES:
                fail(problems, f'datatype {datatype} used by {base} is not defined in the file')
        elif member not in available:
            bad_members.add(f'{base}.{member} is not a member of {datatype} '
                            f'({routine_name} rung {number})')
    for item in sorted(undeclared):
        fail(problems, f'undeclared tag: {item}')
    for item in sorted(bad_members):
        fail(problems, f'bad member: {item}')
    if not undeclared and not bad_members:
        notes.append('all tag and member references resolve')

    # 6, 7 --------------------------------------------------------------------
    for source, target in sorted(jsr_targets):
        if target not in routine_names:
            fail(problems, f'{source}: JSR target {target} does not exist')
    main_name = re.search(r'MainRoutineName="([^"]+)"', program)
    if main_name:
        called = {t for _, t in jsr_targets}
        orphans = routine_names - called - {main_name.group(1)}
        if orphans:
            fail(problems, 'routines never called by a JSR: ' + ', '.join(sorted(orphans)))
        else:
            notes.append(f'all routines reachable from {main_name.group(1)}')

    # report ------------------------------------------------------------------
    for note in notes:
        print(f'ok    {note}')
    verify = len(re.findall(r'VERIFY', program))
    if verify:
        print(f'note  {verify} VERIFY flag(s) in the program - list these in the response')
    if problems:
        print()
        for problem in problems:
            print(f'FAIL  {problem}')
        print(f'\n{len(problems)} problem(s) - Studio 5000 will likely reject this file.')
        return 1
    print('\nAll checks passed.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
