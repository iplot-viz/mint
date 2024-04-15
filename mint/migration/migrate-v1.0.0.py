"""Fix deprecated expresions in workspaces (.json) files (IDV-333, IDV-407)
"""

import argparse
from pathlib import Path
import re
from shutil import copyfile
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file', nargs='+', help='Filenames to fix. backup files are generated. '
                                            'Shell parameter expansion can be used (*.json)')
args = parser.parse_args()

for fn in args.file:
    print(f'Processing {fn}')
    pn = Path(fn)
    if not pn.is_file():
        print(f'{fn} not found.')
        sys.exit(1)
    start_text = pn.read_text()

    text = start_text
    # IDV-333
    text = text.replace('"${self}.data"', '"${self}.data_store[1]"')
    text = text.replace('"${self}.data_secondary"', '"${self}.data_store[2]"')
    # IDV-407 "step": "None"
    text = re.sub(r'"step":\s*"none"', '"step": "linear"', text, 0, re.I)

    if text == start_text:
        print(f'Nothing was changed for {fn}.\n')
        continue

    startbck = pn.name + '.backup.'
    backups = pn.parent.glob(startbck + '*')
    last = 0
    for bck in backups:
        name = bck.name
        token = name[len(startbck):]
        if token.isdigit():
            last = max(last, int(token))
    bckupno = last + 1
    bckpn = pn.with_name(f'{startbck}{bckupno}')
    print(f'Copying to backup {bckpn}')
    copyfile(pn, bckpn)
    print(f'Rewriting {fn}')
    pn.write_text(text)
