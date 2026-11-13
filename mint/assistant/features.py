"""MINT's own tools a request can be about: Statistics, the mini-map and Search Vars. MINT opens them or says
what they are, without the model: a small model takes "the statistics" for a signal to look for."""
import re
from dataclasses import dataclass
from typing import Optional

STATISTICS = "statistics"
MINIMAP = "minimap"
SEARCH = "search"

OPEN = "open"
CLOSE = "close"
ABOUT = "about"

NAMES = {
    STATISTICS: re.compile(r"\bstat(?:s|istics?)\b|\bestad[ií]stic|\bstatisti|\bestat[ií]stic", re.IGNORECASE),
    MINIMAP: re.compile(r"\bmini[- ]?(?:map|mapa|carte|karte|mappa)s?\b", re.IGNORECASE),
    SEARCH: re.compile(r"\bsearch[- ]?vars?\b|\bsearch(?:ing)?(?: for)?(?: the)? variables\s*(?:window|dialog|panel|tree|"
                       r"browser|button)?\s*[?.!]?$|\bvariables? (?:browser|tree)\b|\bbuscador de variables\b",
                       re.IGNORECASE),
}
# What Statistics answers, asked without naming it: "the last value of each", "how many samples".
ANSWERED_BY_STATISTICS = re.compile(
    r"\blast (?:values?|samples?|points?)\b|\b(?:how many|number of|count of) (?:samples|points)\b|"
    r"\b[uú]ltim[oa]s? (?:valor|valores|muestras?)\b|\bcu[aá]ntas muestras\b|\bderni[eè]res? (?:valeurs?|[ée]chantillons?)\b|"
    r"\bcombien d'[ée]chantillons\b|\bletzten? (?:werte?|samples?)\b|\bwie viele (?:samples|werte|punkte)\b|"
    r"\bultim[oi] (?:valori|valore|campioni)\b|\bquanti campioni\b|\bquantas amostras\b",
    re.IGNORECASE)
OPENING = re.compile(
    r"\b(?:open|show|display|enable|activate|turn on|switch on|bring up|see|view|give me|abre|abrir|ab[ií]reme|muestra|"
    r"mu[eé]strame|mostrar|ense[ñn]a|activa|activar|enciende|ouvre|ouvrir|affiche|montre|active|activer|[öo]ffne|zeige?|"
    r"aktiviere|einblenden|apri|mostra|mostrami|attiva|visualizza|abra|mostre|ative|exiba)\b", re.IGNORECASE)
CLOSING = re.compile(
    r"\b(?:close|hide|disable|deactivate|turn off|switch off|get rid of|remove|cierra|cerrar|oculta|ocultar|desactiva|"
    r"desactivar|apaga|quita|ferme|fermer|cache|masque|d[ée]sactive|schlie(?:ß|ss)e|verstecke|ausblenden|deaktiviere|"
    r"chiudi|nascondi|disattiva|feche|fecha|oculte|esconda|desative|desativa)\b", re.IGNORECASE)
ASKING = re.compile(
    r"^\s*(?:what|where|how|which|why|is there|are there|qu[eé]|d[oó]nde|c[oó]mo|cu[aá]l|o[uù]|comment|qu'est|"
    r"was|wo|wie|welche|cosa|che cos|dove|come|o que|onde|como)\b", re.IGNORECASE)

ABOUT_TEXT = {
    STATISTICS: ("Statistics shows, for each signal drawn, its minimum, average and maximum, its first and last values "
                 "with their times, and how many samples it has. It's the bar chart button above the plots."),
    MINIMAP: ("The mini-map is a small overview of the plot under the canvas: it shows the whole time drawn, with "
              "the part you zoomed or panned to in orange. It works when a single plot is visible, and not while "
              "streaming. Its button is next to Statistics, above the plots."),
    SEARCH: ("Search Vars, above the table, lists the variables of each data source so you can tick and add them. "
             "I can look for them too: tell me a system such as CRYO, or part of a name."),
}


@dataclass(frozen=True)
class Asked:
    feature: str
    how: str  # OPEN, CLOSE or ABOUT


def asked(text: str) -> Optional[Asked]:
    """The tool the request is about and whether to open it, close it or say what it is; None if it names none."""
    text = text or ""
    found = [key for key, pattern in NAMES.items() if pattern.search(text)]
    if not found and ANSWERED_BY_STATISTICS.search(text):
        return Asked(STATISTICS, OPEN)
    if len(found) != 1:
        return None
    feature = found[0]
    if CLOSING.search(text):
        # Statistics is a window of its own, closed from there.
        return Asked(feature, CLOSE) if feature == MINIMAP else None
    if OPENING.search(text):
        return Asked(feature, OPEN)
    if ASKING.search(text):
        return Asked(feature, ABOUT)
    # The name alone ("the statistics", "mini-map please") asks for it; anything longer is another request.
    rest = NAMES[feature].sub(" ", text)
    return Asked(feature, OPEN) if len(re.findall(r"\w+", rest)) <= 3 else None
