# This script reformats a printer config INI file, ordering
# the keys according to the contents of profile_config_keys.txt
# and adding a table of contents at the top of the file.
# Any comments from the original file will be lost.
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, List, Dict

SCRIPT_DIR = Path(sys.path[0])
INPUT_FILE = Path(sys.argv[1])
OUTPUT_FILE = Path(sys.argv[2] if len(sys.argv) > 2 else INPUT_FILE)

@dataclass
class Section:
    title: str
    hidden: bool = False
    keys: List[str] = field(default_factory=list)

def load_key_ordering() -> List[Section]:
    """
    Returns a list of sections in order, and a mapping of key names to section names
    """
    results = []
    current_section = None
    with open(SCRIPT_DIR / 'profile_config_keys.txt') as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] == ';':
                continue
            elif line.startswith('## HIDDEN'):
                current_section = Section(title='HIDDEN', hidden=True)
                results.append(current_section)
            elif line.startswith('## TODO'):
                break
            elif line[0] == '#':
                current_section = Section(title=line[1:].strip())
                results.append(current_section)
            else:
                current_section.keys.append(line)

    return results

def load_config_lines(path: Path) -> Dict[str, str]:
    """
    Returns a dictionary of config keys to the full, unaltered config line they were found on.
    """
    results = {}
    # We don't want to worry about configparser doing something different than 
    # PrusaSlicer's boost-based parser, so we parse the keys out ourselves
    with open(path) as fh:
        for line in fh:
            line = line.lstrip()
            if not line or line[0] == '#' or line[0] == ';':
                continue
            key = line.split('=', 1)[0].strip()
            results[key] = line
    return results 

TOC_HEADER = '''\
# This file contains printer configuration values, one per line.
# Comment lines beginning with # or ; will be ignored.
# For more convenient navigation, settings are grouped into categories
# with headings proceeded by two hash characters (##) and followed
# by a colon. You can search for a section heading by name to find the relevant
# settings.

## Table of Contents:
'''

sections = load_key_ordering()
config_lines = load_config_lines(INPUT_FILE)

header = TOC_HEADER
body = ''
for section in sections:
    if section.hidden:
        continue
    first = True
    for key in section.keys:
        if key in config_lines:
            if first:
                header += f"# - {section.title}\n"
                body += f"\n## {section.title}:\n"
                first = False
            body += config_lines[key]

known_keys = {key for section in sections for key in section.keys}
unknown_keys = set(config_lines.keys()).difference(known_keys)
if unknown_keys:
    print("Found the following unclassified keys:")
    for k in unknown_keys:
        print(f"    {k}")

with open(OUTPUT_FILE, 'w') as fh:
    fh.write(header + body) # Note body will begin with an empty line
