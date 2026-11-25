"""Questions about MINT itself (what a tool does, where it is, how to do something), answered from its manual.

The model knows only the commands it was trained on: asked how MINT works, all it can say is that it can't help.
A passage of the manual, found by the words of the question (BM25), is what the user would have looked up.
"""
import math
import pkgutil
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, List, Optional

# A question.
QUESTION = re.compile(r"\?|^\s*(?:how|what|where|why|which|is there|are there|can i|could i|do i|does)\b", re.IGNORECASE)
# "What is a workspace?", "what does the envelope column do?": answered by what the manual says the thing is.
DEFINES = re.compile(r"^\s*what(?:'s|\s+is|\s+are|\s+does|\s+do)\b", re.IGNORECASE)
WORD = re.compile(r"[a-z0-9]+")
STOP = set("""a an the and or of to in on at for with by from is are was be been it its this that these those i you
we my me your our do does did can could would should will how what where when why which who there here have has had
not no yes please mint use used using get make show see one some any all into out up about as if so then than just
also only more most way want need know tell like something thing things s t m don doesn""".split())
# What a question does with a thing, rather than the thing: "add a ruler" is about the ruler.
GENERIC = set("""add change set put turn enable disable open find look create mean meaning means happen work works
go do make see show saved stored kept get able possible way""".split())
# The manual's words for what people also say otherwise.
SAME = {"color": "colour", "bigger": "small", "larger": "small", "smaller": "small", "enlarge": "small",
        "remove": "delete", "erase": "delete"}
# How sure a passage must be to be the answer.
MIN_SCORE = 4.0
MAX_ANSWER = 320
HEADING = re.compile(r"^(#{2,4})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$")
# Not what a question about using MINT is answered with: the contents, the definitions, the references, the
# assistant, which answers for itself, and the errors, which the Status of a row explains.
SKIPPED = {"table-of-contents", "references", "definitions", "purpose-scope", "assistant"}
# What an entry is about, as the manual writes it in bold at its start: "- **RULER**: ...", "1. **Font is too small.**"
LEAD = re.compile(r"^(?:[-*]|\d+\.)?\s*(?:<img[^>]*>\s*)?\*\*(.+?)\*\*")


@dataclass(frozen=True)
class Passage:
    text: str
    section: str
    anchor: str
    words: tuple
    title: frozenset  # the words of its heading
    lead: frozenset  # what it is about, as it starts: "RULER: ...", "Why is the mini-map greyed out? ..."
    first: bool  # the first passage of its section
    asks: bool = False  # it starts with a question of the FAQ
    pairs: frozenset = frozenset()  # its words two by two, as they follow each other


def _plain(markdown: str) -> str:
    text = re.sub(r"<p\b.*?</p>|<img\b[^>]*>", " ", markdown)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*`]+", "", text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return " ".join(text.split())


def _stem(word: str) -> str:
    word = SAME.get(word, word)
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _words(text: str) -> List[str]:
    return [_stem(w) for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 1]


def _pairs(text: str) -> frozenset:
    """Words that follow each other, articles left out: "shared time", "export data"."""
    words = [_stem(w) for w in WORD.findall(text.lower()) if w not in ("a", "an", "the", "of")]
    return frozenset(zip(words, words[1:]))


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


@lru_cache(maxsize=1)
def passages() -> List[Passage]:
    """The manual cut in the pieces an answer can be: list items, FAQ entries, table rows and paragraphs."""
    try:
        text = pkgutil.get_data("mint.data", "help/manual.md").decode("utf-8")
    except (OSError, AttributeError):
        return []
    found, section, anchor, fenced, first = [], "", "", False, True
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        heading = HEADING.match(line)
        if heading:
            level, title, given = len(heading.group(1)), heading.group(2).strip(), heading.group(3)
            if level <= 3 or not anchor:
                section, anchor = title, given or _anchor(title)
            else:  # a sub-heading without an anchor of its own: in its section
                section = f"{section.split(' › ')[0]} › {title}"
            first = True
            continue
        line = line.strip()
        if fenced or not line or anchor in SKIPPED or anchor.startswith("error") or \
                re.fullmatch(r"\|?[\s:|-]+\|?", line):
            continue
        lead = LEAD.match(line)
        lead = _plain(lead.group(1)) if lead else ""
        if line.startswith("|"):
            cells = [_plain(c) for c in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            line, lead = f"{cells[0]}: {' '.join(cells[1:])}", cells[0]
        line = _plain(re.sub(r"^(?:[-*]|\d+\.)\s+", "", line))
        # A question whose answer is not text (a command to run) answers nothing here.
        if len(line) < 20 or line.lower().startswith("see also") or line.endswith("?"):
            continue
        heading_words = re.sub(r"^[\d.]+\s*", "", section.split(" › ")[-1])
        found.append(Passage(line, section, anchor, tuple(_words(line)), frozenset(_words(heading_words)),
                             frozenset(_words(lead)), first, lead.endswith("?"), _pairs(line)))
        first = False
    return found


@lru_cache(maxsize=1)
def _index():
    items = passages()
    df = {}
    for p in items:
        for w in set(p.words) | p.title:
            df[w] = df.get(w, 0) + 1
    average = sum(len(p.words) for p in items) / max(1, len(items))
    return items, df, average


def answer(question: str, ignore: Iterable[str] = ()) -> Optional[Passage]:
    """The passage of the manual that answers a question about MINT, or None when none clearly does.

    ``ignore``: words that name things of the workspace (signals), which say nothing of what to look up.
    """
    if not QUESTION.search(question or ""):
        return None
    asked = set(_words(question)) - set(_words(" ".join(ignore))) - GENERIC
    items, df, average = _index()
    if not asked or not items or any(w not in df for w in asked):
        return None
    n, k1, b = len(items), 1.2, 0.75
    best, best_score = None, 0.0
    rarest = min(asked, key=lambda w: df[w])
    # Words the question puts together name one thing ("shared time"): together in the passage too.
    together = {pair for pair in _pairs(question) if set(pair) <= asked}
    definition = bool(DEFINES.match(question))
    for p in items:
        if any(pair not in p.pairs and not set(pair) <= p.lead | p.title for pair in together):
            continue
        # A question of the FAQ answers only one that asks about the same: its most telling word in it. None
        # says what a thing is.
        if p.asks and (rarest not in p.lead or definition):
            continue
        # What a thing is: the entry about it ("Envelope: ...", "RULER: ...") or a sentence that says it ("A
        # workspace is ..."), not a passage that only mentions it.
        defines = definition and any((w, verb) in p.pairs for w in asked for verb in ("is", "are"))
        entry = asked <= p.lead | p.title and (_words(p.text) or [""])[0] in asked
        if definition and not (entry or defines):
            continue
        # Every word of the question in it, and a single one as the term it defines ("RULER: ...", "Stack: ...").
        if not asked <= set(p.words) | p.title | p.lead or \
                (len(asked) == 1 and not (asked <= p.lead and len(p.lead) <= 3) and not defines):
            continue
        score = 0.0
        for w in asked:
            idf = math.log((n - df[w] + 0.5) / (df[w] + 0.5) + 1)
            tf = p.words.count(w)
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(p.words) / average))
            score += (0.8 * idf if w in p.title else 0) + (idf if w in p.lead else 0)
            # A section the question names is answered by how it starts.
            score += 0.6 * idf if p.first and asked <= p.title else 0
            score += idf if defines else 0
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= MIN_SCORE else None


def excerpt(passage: Passage) -> str:
    """The passage as an answer: its first sentences, as long as an answer in the panel should be."""
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", passage.text):
        if out and len(out) + len(sentence) > MAX_ANSWER:
            break
        out = f"{out} {sentence}".strip()
    return out if len(out) <= MAX_ANSWER + 80 else out[:MAX_ANSWER].rsplit(" ", 1)[0] + "…"
