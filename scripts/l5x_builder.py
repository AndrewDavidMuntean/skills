"""Emitters for building a Studio 5000 v36 program-scope .L5X file.

Typical use from a generator script:

    from l5x_builder import *

    tags  = [tag('CarWash_Mode_Ctrl', 'udtStateData', 'Unit Mode',
                 comments=[('.STS_STATE.0', 'Off State')]),
             boolean('SIMULATION', 'Simulation Enable'),
             dint('Drying_Time_SP', 45, 'Drying Time, s (10-180)')]

    routines = [routine('MainRoutine', [('NOP();', 'CarWash - Main Routine'),
                                        ('JSR(P_DIn,0);', None)])]

    write_l5x('out.L5X', tags, routines, program_name='MainProgram')

Rungs are passed as (neutral_text, comment) pairs; comment may be None.
"""

import os
import re
from datetime import date

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')


# --------------------------------------------------------------------------- tags

def _esc(text):
    """CDATA cannot contain the terminator sequence."""
    return text.replace(']]>', ']] >')


def tag(name, datatype, description=None, dimensions=None, data=None, comments=None):
    """A base tag. AOI/UDT instances should leave `data` as None so Logix fills defaults."""
    dim = f' Dimensions="{dimensions}"' if dimensions else ''
    out = (f'<Tag Name="{name}" TagType="Base" DataType="{datatype}"{dim} '
           f'Constant="false" ExternalAccess="Read/Write">\n')
    if description:
        out += f'<Description>\n<![CDATA[{_esc(description)}]]>\n</Description>\n'
    if comments:
        out += '<Comments>\n'
        for operand, text in comments:
            out += f'<Comment Operand="{operand}">\n<![CDATA[{_esc(text)}]]>\n</Comment>\n'
        out += '</Comments>\n'
    if data is not None:
        out += f'<Data Format="Decorated">\n{data}\n</Data>\n'
    return out + '</Tag>\n'


def dint(name, value, description=None):
    return tag(name, 'DINT', description,
               data=f'<DataValue DataType="DINT" Radix="Decimal" Value="{value}"/>')


def real(name, value, description=None):
    return tag(name, 'REAL', description,
               data=f'<DataValue DataType="REAL" Radix="Float" Value="{value}"/>')


def boolean(name, description=None):
    return tag(name, 'BOOL', description)


def array(name, datatype, dimensions, description=None):
    return tag(name, datatype, description, dimensions=dimensions)


# ----------------------------------------------------------------------- routines

def rung(number, text, comment=None):
    out = f'<Rung Number="{number}" Type="N">\n'
    if comment:
        out += f'<Comment>\n<![CDATA[{_esc(comment)}]]>\n</Comment>\n'
    return out + f'<Text>\n<![CDATA[{text}]]>\n</Text>\n</Rung>\n'


def routine(name, rungs):
    """rungs: iterable of (neutral_text, comment_or_None)."""
    out = f'<Routine Name="{name}" Type="RLL">\n<RLLContent>\n'
    for i, item in enumerate(rungs):
        text, comment = item if isinstance(item, (tuple, list)) else (item, None)
        out += rung(i, text, comment)
    return out + '</RLLContent>\n</Routine>\n'


def branch(*branches):
    """Join parallel branches in house spacing: [a ,b ,c ]"""
    return '[' + ' ,'.join(branches) + ' ]'


# ------------------------------------------------------------- standard fragments

def jsr_dispatcher(program_label, routines_in_order):
    """MainRoutine as a pure JSR dispatcher."""
    rungs = [('NOP();', f'{program_label} - Main Routine')]
    rungs += [(f'JSR({r},0);', None) for r in routines_in_order]
    return rungs


STANDARD_ROUTINE_ORDER = [
    'IO_Mapping_Inputs', 'P_Intlk', 'P_DIn', 'P_AIn', 'P_DOut', 'P_Motor', 'P_PIDE',
    'Unit_Setpoints', 'Unit_Timers', 'Unit_Alarms', 'Unit_Mode', 'Unit_State_Transitions',
    'Unit_State_Activations', 'HMI_Overview', 'HMI_DeviceControl', 'IO_Mapping_Outputs',
    'Clock', 'Temp_Control',
]


def clock_routine(year=None):
    year = year or date.today().year
    return routine('Clock', [
        (f'XIC(PLC_Clock_Sync)[SSV(WallClockTime,,LocalDateTime,{year}) ,OTU(PLC_Clock_Sync) ];', None)
    ])


def empty_routine(name):
    """Placeholder so the JSR resolves for units that don't use this routine."""
    return routine(name, [(';', None)])


# ------------------------------------------------------------------------ assembly

def load_library():
    """The bundled <DataTypes> + <AddOnInstructionDefinitions> blocks."""
    with open(os.path.join(ASSETS, 'library.xml'), encoding='utf-8') as fh:
        return fh.read()


def assemble(tags, routines, program_name='MainProgram', main_routine='MainRoutine',
             controller_name='Controller', description=None,
             owner='Operator, McRae Integration Ltd.', library=None):
    """Return the complete .L5X text. `tags` and `routines` are lists of XML strings."""
    library = load_library() if library is None else library
    export_date = date.today().strftime('%a %b %d %Y')

    head = (
        '\ufeff<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="36.00" '
        f'TargetName="{program_name}" TargetType="Program" ContainsContext="true" '
        f'Owner="{owner}" ExportDate="{export_date}" '
        'ExportOptions="References NoRawData L5KData DecoratedData Context Dependencies '
        'ForceProtectedEncoding AllProjDocTrans">\n'
        f'<Controller Use="Context" Name="{controller_name}">\n'
        + library +
        '<Tags Use="Context">\n' + ''.join(tags) + '</Tags>\n'
    )

    prog = ('<Programs Use="Context">\n'
            f'<Program Use="Target" Name="{program_name}" TestEdits="false" '
            f'MainRoutineName="{main_routine}" Disabled="false" UseAsFolder="false">\n')
    if description:
        prog += f'<Description>\n<![CDATA[{_esc(description)}]]>\n</Description>\n'
    prog += ('<Tags/>\n<Routines>\n' + ''.join(routines) + '</Routines>\n'
             '</Program>\n</Programs>\n')

    tail = '<WallClockTime Use="Reference">\n</WallClockTime>\n</Controller>\n</RSLogix5000Content>\n'
    return head + prog + tail


def write_l5x(path, tags, routines, **kwargs):
    text = assemble(tags, routines, **kwargs)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


# ------------------------------------------------------------------ introspection

def aoi_members(aoi_name, library=None):
    """Parameter + local tag names of a bundled AOI. Useful for checking member spelling."""
    library = load_library() if library is None else library
    match = re.search(
        r'<AddOnInstructionDefinition [^>]*Name="' + re.escape(aoi_name) + r'"(.*?)'
        r'</AddOnInstructionDefinition>', library, re.S)
    if not match:
        return None
    return sorted(set(re.findall(r'<(?:Parameter|LocalTag) Name="([^"]+)"', match.group(1))))


def udt_members(udt_name, library=None):
    library = load_library() if library is None else library
    match = re.search(r'<DataType Name="' + re.escape(udt_name) + r'"(.*?)</DataType>',
                      library, re.S)
    if not match:
        return None
    return [m for m in re.findall(r'<Member Name="([^"]+)"', match.group(1))
            if not m.startswith('ZZZZZZZZZZ')]


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        name = sys.argv[1]
        members = aoi_members(name) or udt_members(name)
        print('\n'.join(members) if members else f'{name} not found in library')
    else:
        lib = load_library()
        print('DataTypes:', ', '.join(re.findall(r'<DataType Name="([^"]+)"', lib)))
        print('AOIs:', ', '.join(
            re.findall(r'<AddOnInstructionDefinition [^>]*Name="([^"]+)"', lib)))
