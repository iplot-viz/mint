"""Answers to the assistant's own questions."""
import math
import re
from dataclasses import dataclass, field
from typing import List, Optional

from mint.assistant.commands import Command
from mint.assistant.snapshot import Snapshot

SECONDS = {"ms": 0.001, "msec": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
           "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
           "min": 60, "mins": 60, "minute": 60, "minutes": 60,
           "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
           "d": 86400, "day": 86400, "days": 86400}
# The same units in the other languages the assistant understands.
SECONDS.update({unit: seconds for units, seconds in (
    ("segundo segundos seconde secondes sekunde sekunden secondo secondi", 1),
    ("minuto minutos minuten minuti", 60),
    ("hora horas heure heures stunde stunden ora ore", 3600),
    ("día días dia dias jour jours tag tage giorno giorni", 86400)) for unit in units.split()})
VALUE = re.compile(r"^\s*(?:about|around|over|at|by|of|x|×)?\s*(-?\d+(?:[.,]\d+)?)\s*([^\W\d_]+)?\s*$")
# More words than this is a new request rather than an answer.
MAX_ANSWER_WORDS = 6
# Words that only agree, in the languages the assistant understands: alone, they take the example asked with.
AGREE = set("ok okay okey yes yeah yep sure fine good great perfect perfecto vale sí si venga dale claro bien "
            "oui d'accord parfait ja gut genau passt sì certo bene perfetto sim beleza".split())
# Words around a number that only acknowledge, ask politely or correct: "50 s it's okay", "vale, 30 s",
# "go with 2 Hz please", "no, 1 min". Anything else ("and log scale", a signal) goes to the model.
POLITE = AGREE | set("it it's its is that that's this then please pls thanks thank you just go with let's lets say "
                     "use make do try set to the one example enough sounds works for me por favor gracias pon ponle "
                     "usa con es eso ese esa está esta suficiente mejor pues entonces de acuerdo ejemplo merci alors "
                     "s'il te vous plaît plait avec exemple assez bitte danke dann mit nimm beispiel reicht va per "
                     "favore grazie allora esempio basta obrigado então pode ser exemplo now ahora maintenant "
                     "jetzt adesso agora".split())
CORRECTING = set("no nope nah non nein não nao actually rather instead".split())
# Turning down the card on screen: "no", "no thanks", "not now".
DECLINE = set("no nope nah not cancel dismiss non nein não nao".split())
# "Both", "all of them", "las dos": every option of the question, in the languages the assistant understands.
EVERY = set("all both each every two todos todas ambos ambas cada dos tous toutes chacun chacune deux alle beide "
            "jeder jede jedes zwei tutti tutte entrambi entrambe ognuno due dois duas".split())
EVERY_AROUND = set("of them the these those ones one signals signal rows plots los las les eux elles ellos ellas "
                   "die sie le la loro i gli eles elas os as and y et und e".split())


@dataclass
class OpenQuestion:
    request: str
    snap: Snapshot
    commands: List[Command] = field(default_factory=list)
    command: Optional[Command] = None
    param: str = ""
    example: Optional[float] = None  # the value the question suggested
    options: List[str] = field(default_factory=list)  # the rows or plots "which one?" offered


def _words(text: str) -> List[str]:
    # Punctuation between words, not inside a number ("2,5 s"); curly apostrophes as straight ones.
    text = (text or "").replace("’", "'")
    return re.sub(r"[,;:!?]+(?!\d)|\.(?!\d)", " ", text).split()


def _saying(text: str, skip: set) -> List[str]:
    return [word for word in _words(text) if word.lower() not in skip]


def value_in(text: str, param: str) -> Optional[float]:
    """The number a short answer gives for a parameter ("10 s", "2 Hz", "x 3.6", "50 s it's okay"), in its
    unit, or None."""
    m = VALUE.match(" ".join(_saying(text, POLITE | CORRECTING)))
    if not m:
        return None
    unit = (m.group(2) or "").lower()
    if param == "seconds":
        scale = SECONDS.get(unit) if unit else 1  # a bare number answering "over how long" is seconds
    elif param == "hz":
        scale = 1 if unit in ("", "hz") else None
    else:
        scale = None if unit else 1
    value = None if scale is None else float(m.group(1).replace(",", ".")) * scale
    return value if value is not None and math.isfinite(value) else None


def agrees(text: str) -> bool:
    """A reply that only agrees ("ok", "yes, that's fine", "vale"): to a question with an example, that one."""
    words = [word.lower() for word in _words(text)]
    return (bool(words) and "?" not in text and not _saying(text, POLITE)
            and any(word in AGREE for word in words))


def declines(text: str) -> bool:
    """A reply that only turns down ("no", "no thanks", "not now")."""
    words = [word.lower() for word in _words(text)]
    return (bool(words) and "?" not in text and not _saying(text, POLITE | DECLINE)
            and any(word in DECLINE for word in words) and not any(word in AGREE for word in words))


def means_every(text: str) -> bool:
    """A reply that takes every option offered: "both", "all of them", "las dos", "tous"."""
    words = [word.lower() for word in _words(text)]
    said = [word for word in words if word not in EVERY_AROUND and word not in POLITE]
    return bool(said) and "?" not in text and all(word in EVERY for word in said)


def is_answer(text: str) -> bool:
    return 0 < len((text or "").split()) <= MAX_ANSWER_WORDS


# "undo that", in the languages the assistant understands: MINT undoes the last card itself.
UNDO_WORDS = {"undo", "deshaz", "deshazlo", "deshacer", "annule", "annuler", "rückgängig", "annulla", "desfaz",
              "desfazer", "revert"}


def is_undo(text: str) -> bool:
    words = re.findall(r"\w+", (text or "").lower())
    return 0 < len(words) <= 4 and words[0] in UNDO_WORDS


def with_answer(question: OpenQuestion, answer: str) -> str:
    """The original request with the user's answer, for the model."""
    return f"{question.request.rstrip(' .?!')}. {answer.strip()}"
