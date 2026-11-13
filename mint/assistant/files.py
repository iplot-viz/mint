"""Signal names, times and pulses written in a file the user attaches (CSV, Excel, PDF, signal set) or pastes."""
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, List, Optional, Tuple

from mint.assistant.snapshot import FileInfo, FileVariable

NAME_FILTER = "Tables and documents (*.csv *.tsv *.txt *.scsv *.xlsx *.xlsm *.pdf)"
TEXT, EXCEL, PDF = (".csv", ".tsv", ".txt", ".scsv"), (".xlsx", ".xlsm"), (".pdf",)
MAX_BYTES = 20 * 1024 * 1024
MAX_LINES = 20000
MAX_PAGES = 100
MAX_VARIABLES = 200
MAX_TIMES = 6
MAX_PULSES = 4
MAX_NOTE = 40
MAX_CODES = 6
PASTED = "the text you pasted"

# An ITER signal name: system and subsystems, a colon, the tag (CRYO-CP-03:MT0021-XI, MAG-MCTB-F1:VAR1).
NAME = re.compile(r"(?<![\w:.-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+:[A-Z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?(?![\w:-])")
PULSE = re.compile(r"(?<![\w:/-])[A-Z][A-Z0-9_]*:[A-Za-z0-9_-]+/\d+(?![\w/])")
# Date and time apart by a T or by any white space: text taken out of a PDF often has tabs between its words.
ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:(?:T|\s+)(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?(?![\d:])")
MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
WORDED = re.compile(r"(?<!\d)(\d{1,2})\s+(" + "|".join(MONTH_NAMES) + r")[a-z]*\.?,?\s+(\d{4})"
                    r"(?:,?\s+(?:at\s+)?(\d{1,2}):(\d{2}))?(?![\d:])", re.IGNORECASE)
SEPARATORS = re.compile(r"[\s,;|\t]+")
# A signal by its tag alone, without its system (MT0021, PT-1101, MLT1000-AA-IN), as reports often write it;
# not a standard (ISO-8601), and a full stop after it ends the sentence.
CODE = re.compile(r"(?<![\w:./-])(?!(?:ISO|IEC|EN|DIN|RFC)-?\d)[A-Z]{1,4}-?\d{3,5}(?:-[A-Z0-9]{1,8}){0,3}"
                  r"(?![\w:/-]|\.\w)")
# A row of a table copied as text: its cells are apart by tabs, semicolons or bars.
CELLS = re.compile(r"[\t;|]")


class FileError(Exception):
    """A file that cannot be read; the message says why, for the user."""


@dataclass
class Found:
    variables: List[Tuple[str, str]] = field(default_factory=list)  # (name, the words beside it)
    times: List[str] = field(default_factory=list)
    pulses: List[str] = field(default_factory=list)
    partial: str = ""  # what was left unread, if anything
    codes: List[str] = field(default_factory=list)  # tags written without their system, to look up


def read(path: str) -> Found:
    """Reads the file and finds what it names. Raises FileError with a message for the user."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if ext not in TEXT + EXCEL + PDF:
        raise FileError(f"I can read CSV, Excel and PDF files, not {ext or 'this kind of'} files.")
    try:
        size = os.path.getsize(path)
    except OSError:
        raise FileError(f"I can't open {name}.")
    if size > MAX_BYTES:
        raise FileError(f"{name} is {size // (1024 * 1024)} MB: I read files up to {MAX_BYTES // (1024 * 1024)} MB.")
    lines, partial = (_excel_lines if ext in EXCEL else _pdf_lines if ext in PDF else _text_lines)(path, name)
    found = find(lines)
    found.partial = partial
    return found


def info(file_name: str, found: Found, source: str) -> FileInfo:
    variables = [FileVariable(f"v{i + 1}", n, note) for i, (n, note) in enumerate(found.variables)]
    return FileInfo(file_name, variables, list(found.times), list(found.pulses), source)


def find(lines: Iterable[str]) -> Found:
    found, seen, times = Found(), set(), {}
    for line in lines:
        names = NAME.findall(line)
        for name in names:
            if name not in seen and len(found.variables) < MAX_VARIABLES:
                seen.add(name)
                found.variables.append((name, _note(line, names)))
        for pulse in PULSE.findall(line):
            if pulse not in found.pulses and len(found.pulses) < MAX_PULSES:
                found.pulses.append(pulse)
        for code in CODE.findall(line):
            if code not in found.codes and len(found.codes) < MAX_CODES:
                found.codes.append(code)
        for moment in _moments(line):
            times.setdefault(moment, None)
    found.times = sorted(times)[:MAX_TIMES]
    return found


# A run of names in a line ("A, B and C"), and the words before it that already say what they are.
NAME_RUN = re.compile(r"\x00(?:[\s,;&]*(?:and|y|et|und|e|or)?[\s,;&]*\x00)*")
SAID_BEFORE = re.compile(r"\b(?:variables?|signals?|names?|these|those|following|vars)\s*:?\s*$", re.IGNORECASE)


def pasted(text: str, known=()) -> Optional[Tuple[Found, str]]:
    """A message holding a list of signals, one per line or in a line: what it names, and the request around it.

    In a line, names already in the table don't count: "combine A and B" is about those rows.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        found = find(lines)
        if len(found.variables) < 2:
            return None
        said = [line.strip() for line in lines if not (NAME.search(line) or CELLS.search(line) or _moments(line))]
        return found, " ".join(said)
    known = set(known)
    names = [name for name in dict.fromkeys(NAME.findall(text)) if name not in known]
    if len(names) < 2:
        return None
    found = Found(variables=[(name, "") for name in names[:MAX_VARIABLES]])
    # "add A, B and C, one plot each" -> "add them, one plot each"
    marked = NAME.sub("\x00", text)
    said, start = "", 0
    for run in NAME_RUN.finditer(marked):
        before = marked[start:run.start()]
        said += before + (" " if SAID_BEFORE.search(before) else " them ")
        start = run.end()
    said = " ".join((said + marked[start:]).split())
    said = re.sub(r"\s+([,.;:!?])", r"\1", said).strip(" ,;:")
    return found, "" if said.lower() == "them" else said


def _note(line: str, names: List[str]) -> str:
    """The words beside a name on its line or row, which often say what it measures."""
    for name in names:
        line = line.replace(name, " ")
    words = SEPARATORS.sub(" ", ISO.sub(" ", line)).strip(" -:")
    return words if len(words) <= MAX_NOTE else words[:MAX_NOTE - 1].rstrip() + "…"


def _moments(line: str) -> List[str]:
    out = []
    for y, mo, d, h, mi in ISO.findall(line):
        out += _moment(int(y), int(mo), int(d), h, mi)
    for d, mo, y, h, mi in WORDED.findall(line):
        out += _moment(int(y), MONTH_NAMES.index(mo[:3].lower()) + 1, int(d), h, mi)
    return out


def _moment(year, month, day, hour, minute) -> List[str]:
    try:
        moment = datetime(year, month, day, int(hour or 0), int(minute or 0))
    except ValueError:
        return []
    return [moment.strftime("%Y-%m-%d %H:%M") if hour else moment.strftime("%Y-%m-%d")]


def _text_lines(path, name):
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    return lines[:MAX_LINES], (f"its first {MAX_LINES} lines" if len(lines) > MAX_LINES else "")


def _excel_lines(path, name):
    try:
        import openpyxl
    except ImportError:
        raise FileError("To read Excel files MINT needs openpyxl, which isn't installed here "
                        "(pip install openpyxl). A CSV export of the sheet works too.")
    try:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        raise FileError(f"I can't read {name} as an Excel file.")
    lines = []
    try:
        for sheet in book.worksheets:
            for row in sheet.iter_rows(values_only=True):
                if len(lines) == MAX_LINES:
                    return lines, f"its first {MAX_LINES} rows"
                cells = [_cell(v) for v in row if v is not None]
                if cells:
                    lines.append(" | ".join(cells))
    finally:
        book.close()
    return lines, ""


def _cell(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M") if (value.hour, value.minute) != (0, 0) else value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _page_text(page) -> str:
    # In layout mode a row of a table stays on one line, with the words that describe its signal.
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except Exception:
        return page.extract_text() or ""


def _pdf_lines(path, name):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise FileError("To read PDF files MINT needs pypdf, which isn't installed here (pip install pypdf).")
    try:
        reader = PdfReader(path)
        pages = reader.pages
        lines = [line for page in pages[:MAX_PAGES] for line in _page_text(page).splitlines()]
    except Exception:
        raise FileError(f"I can't read {name} as a PDF.")
    if not any(line.strip() for line in lines):
        raise FileError(f"{name} has no text I can read: it may be a scanned image.")
    return lines, (f"its first {MAX_PAGES} pages" if len(pages) > MAX_PAGES else "")
