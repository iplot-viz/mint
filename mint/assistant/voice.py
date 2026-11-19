"""Fixed sentences around the cards: on a CPU every word the model writes costs time."""
from datetime import datetime, timezone

# A card is a proposal, not something done: the openers say so.
OPENERS = ("Here's what I'd do.", "Got it. Here's the change.", "Okay, how does this look?", "This should do it.")
FIRST_OPENER = "Here's what I'd change. Nothing happens until you click Apply, and Undo puts it back."
DONE = ("Done.", "There you go.", "All set.")


def _listed(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def _number(value: float) -> str:
    return f"{value:.4g}" if abs(value) < 1e6 else f"{value:.4e}"


def _is_date(x: float) -> bool:
    # Dates are ns since the epoch; a pulse or a relative axis counts seconds from its start.
    return abs(x) > 1e12


def _day(x: float):
    return datetime.fromtimestamp(x / 1e9, timezone.utc).date() if _is_date(x) else None


def _moment(x: float, with_day: bool) -> str:
    if not _is_date(x):
        return f"{_number(x)} s"
    moment = datetime.fromtimestamp(x / 1e9, timezone.utc)
    return f"{moment:%d %b %H:%M:%S} UTC" if with_day else f"{moment:%H:%M:%S} UTC"


class Voice:
    def __init__(self):
        self._said = {}

    def _next(self, key: str, options) -> str:
        count = self._said.get(key, 0)
        self._said[key] = count + 1
        return options[count % len(options)]

    def opener(self, after_words: bool = False) -> str:
        """Before a card: the first-time explanation, then a varied acknowledgement (none after the model's words)."""
        if "opener" not in self._said:
            self._said["opener"] = 0
            return FIRST_OPENER
        return "" if after_words else self._next("opener", OPENERS)

    def done(self) -> str:
        return self._next("done", DONE)

    @staticmethod
    def no_data(where: str, empty, all_empty: bool, latest, none_before=(), unknown=(), offer: str = "") -> str:
        """What to say of the signals (``empty``) a new time range left without data, and what the archive says.

        latest: [(name, when)], newest first; none_before: names; unknown: [(variable, source)]; offer: a span or ''.
        """
        if all_empty:
            said = [f"There's no data for {empty[0]} {where}." if len(empty) == 1 else f"There's no data {where}."]
        else:
            said = [f"{_listed(empty)} {'has' if len(empty) == 1 else 'have'} no data {where}."]
        if len(latest) == 1:
            name, moment = latest[0]
            said.append(f"Its latest sample is from {moment}." if len(empty) == 1
                        else f"The latest of {name} is from {moment}.")
        elif 1 < len(latest) <= 3:
            said.append("The latest samples are from " + _listed([f"{moment} ({name})" for name, moment in latest]) + ".")
        elif latest:
            said.append(f"The most recent is from {latest[0][1]} ({latest[0][0]}).")
        if none_before:
            said.append(f"{_listed(none_before)} {'has' if len(none_before) == 1 else 'have'} none before then either.")
        for name, source in unknown:
            said.append(f"{source} has no variable called {name}.")
        if offer:
            said.append(f"Shall I show the {offer} up to {'it' if len(latest) == 1 else 'the most recent'}?")
        return " ".join(said)

    @staticmethod
    def file_read(info, partial: str = "", codes=()) -> str:
        """What a file names, once read; ``partial`` says what was left unread, ``codes`` the tags to look up."""
        read = f"I read {info.name}" + (f" ({partial})" if partial else "")
        if not info.variables and codes:
            return (f"{read}: it gives {_listed(codes)} without the system part of the name. "
                    f"Shall I look for {'it' if len(codes) == 1 else 'them'} in {info.source}?")
        if not info.variables:
            return (f"{read}, but it names no signal I can use: I need the names written out in full, "
                    "like CRYO-CP-03:MT0021-XI.")
        found = [f"{len(info.variables)} signal name{'' if len(info.variables) == 1 else 's'}"]
        if info.times:
            found.append(f"{len(info.times)} date{'' if len(info.times) == 1 else 's'}")
        if info.pulses:
            found.append(f"{len(info.pulses)} pulse{'' if len(info.pulses) == 1 else 's'}")
        return f"{read}: {_listed(found)}. What should I do with them?"

    @staticmethod
    def problems(missing, fixes: dict, invalid, sources, more: int = 0) -> str:
        """Why rows aren't drawn: a data source that isn't here first, with what to change it to, then other rows.

        missing: [(source, row names)]; fixes: {source: the one to use, or None}; invalid: [(row name, reason)].
        """
        said = []
        here = f"the data sources here are {_listed(sources)}" if sources else "no data source is connected here"
        for source, names in missing:
            who = f"{names[0]} uses" if len(names) == 1 else f"{len(names)} rows use"
            them = "it" if len(names) == 1 else "them"
            said.append(f"{who} the data source {source}, which isn't available here, so "
                        f"{'it isn' if len(names) == 1 else 'they aren'}'t drawn: {here}.")
            fix = fixes.get(source)
            said.append(f"Shall I change {them} to {fix}?" if fix else
                        f"Which one should {them} use?" if sources else "")
        for name, reason in invalid:
            said.append(f"{name} isn't drawn: {reason}.")
        if more:
            said.append(f"{more} more {'row isn' if more == 1 else 'rows aren'}'t drawn either: the Status says why.")
        if invalid and not missing:
            said.append("Fix the cell in red, then Draw.")
        return " ".join(part for part in said if part)

    @staticmethod
    def change_source(old: str, new: str) -> str:
        return f"Change {old} to {new}"

    @staticmethod
    def data_summary(found, asked, undrawn=(), more: int = 0, unreadable=()) -> str:
        """What the data drawn says: one line per signal with what was asked (see insight); ``found`` is
        [(name, summary)], ``undrawn`` the names of those not drawn, ``unreadable`` of those whose data couldn't
        be read."""
        lines = []
        days = {_day(s[what][1]) for _, s in found for what in ("first", "last", "max", "min") if s.get(what)}
        for name, s in found:
            if "unit" in asked:
                lines.append(f"{name} is in {s['unit']}." if s.get("unit") else
                             f"{name}: the data source gives no unit for it.")
                if len(asked) == 1:
                    continue
            if not s.get("count"):
                lines.append(f"{name}: no sample with a value in what is drawn.")
                continue
            unit = f" {s['unit']}" if s.get("unit") else ""
            parts = []
            for what in asked:
                if what == "unit":
                    continue
                if what == "count":
                    parts.append(f"{s['count']} samples")
                elif what == "mean":
                    parts.append(f"mean {_number(s['mean'])}{unit}")
                else:
                    value, x = s[what]
                    parts.append(f"{what} {_number(value)}{unit} at {_moment(x, len(days) > 1)}")
            lines.append(f"{name}: " + ", ".join(parts) + ".")
        if unreadable:
            one = len(unreadable) == 1
            lines.append(f"{_listed(unreadable)} {'has' if one else 'have'} nothing drawn: "
                         f"{'its' if one else 'their'} data couldn't be read, as the Status says.")
        if undrawn:
            lines.append(f"{_listed(undrawn)} {'isn' if len(undrawn) == 1 else 'aren'}'t drawn: click Draw first.")
        if more:
            lines.append(f"…and {more} more: Statistics has them all.")
        if found:
            lines.append("That's over the time drawn; Statistics, the bar chart button above the plots, has the rest.")
        return "\n".join(lines)

    OPEN_HELP = "Open the help there"

    @staticmethod
    def opened(name: str) -> str:
        return {
            "export": "I've opened Export: choose the file there (Parquet or HDF5), the time and the sampling, then "
                      "click Export. Only signals with a Stack are exported.",
            "image": "Choose where to save the image of the canvas: PNG, SVG or JPEG, by its extension.",
            "csv": "Choose where to save the points drawn of each signal, as a CSV file.",
            "save_workspace": "Choose where to save the workspace: the table, the time range and the plots, to open "
                              "it again or share it.",
            "open_workspace": "Choose the workspace to open; it replaces the table and the plots.",
            "preferences": "Here are the preferences of the canvas, its plots and signals; Apply sets them.",
            "rulers": "Here is the Rulers window: each ruler, its values on every signal it crosses, and the "
                      "distance between them.",
        }.get(name, "Opened.")

    @staticmethod
    def not_openable(name: str) -> str:
        return "There are no rulers to show yet: the RULER tool puts one with a double-click, or ask me." \
            if name == "rulers" else "I couldn't open that now."

    @staticmethod
    def capabilities() -> str:
        return ("I work on this workspace with you: I smooth or filter signals and combine them, change the plots, "
                "their look and how they are laid out, zoom, pan and put rulers, add variables, set the time range, "
                "open MINT's windows, and tell you what the data drawn says or how MINT works. Each change comes as "
                "a card you apply or undo. For example:")

    @staticmethod
    def from_manual(text: str, section: str) -> str:
        return f"{text} (Help, {section.split(' › ')[-1]})"

    @staticmethod
    def nothing_drawn() -> str:
        return "Nothing is drawn yet, so I have no values to tell. Click Draw, then ask me again."

    @staticmethod
    def statistics_opened() -> str:
        return ("Here are the statistics of each signal drawn: minimum, average and maximum, first and last values "
                "with their times, and samples. The bar chart button above the plots opens them too.")

    @staticmethod
    def statistics_nothing_drawn() -> str:
        return ("Statistics shows the minimum, average and maximum, the first and last values and the samples of "
                "each signal drawn, and nothing is drawn yet. Click Draw, then ask me again.")

    @staticmethod
    def minimap(on: bool, was, plots: int, streaming: bool) -> str:
        """After turning the mini-map on or off: ``was`` says it already was, None that it can't be shown now."""
        if was is None:
            if streaming:
                return "The mini-map doesn't work while streaming. Click Stop first, then ask me again."
            return (f"The mini-map only works when a single plot is shown, alone or in full screen, and there "
                    f"are {plots} now.")
        if was:
            return "The mini-map is already on, under the plot." if on else "The mini-map is already off."
        if not on:
            return "I've hidden the mini-map."
        return ("Here's the mini-map, under the plot: the orange part is what the plot shows. Its button is next to "
                "Statistics, above the plots.")

    @staticmethod
    def search_vars_opened() -> str:
        return ("I've opened Search Vars: tick the variables there to add them. I can look for them too: tell me a "
                "system such as CRYO, or part of a name.")

    @staticmethod
    def find_codes(codes, source: str) -> str:
        return f"Find {'it' if len(codes) == 1 else 'them'} in {source}"

    @staticmethod
    def could_not_read(name: str) -> str:
        return f"I couldn't read {name}."

    @staticmethod
    def nothing_to_draw(empty, failed) -> str:
        """Applied, but a signal it computes came out with nothing to draw (``empty``) or not at all (``failed``)."""
        said = []
        if empty:
            said.append(f"{_listed(empty)} came out empty, so there's nothing to draw")
        if failed:
            whose = "its" if len(failed) == 1 else "their"
            said.append(f"MINT couldn't work out {_listed(failed)}: {whose} Status in the table says why")
        return "Done, but " + ", and ".join(said) + "."

    @staticmethod
    def undone(problems) -> str:
        if not problems:
            return "Undone. It's back as it was."
        return "I put back what I could, but not everything. " + " ".join(dict.fromkeys(problems))

    PENDING = "Press Enter to apply, or tell me what to change…"
    RECORDED = "What you ask here is kept for a while, without your name, to improve me."

    @staticmethod
    def undid(title: str) -> str:
        return f"Undone: {title.lower()}. It's back as it was." if title else "Undone. It's back as it was."

    @staticmethod
    def nothing_to_undo() -> str:
        return "There's nothing to undo yet."

    @staticmethod
    def dismissed() -> str:
        return "No problem, I've left everything as it was."

    @staticmethod
    def stopped() -> str:
        return "Okay, I've stopped."

    @staticmethod
    def still_busy() -> str:
        return "One moment, I'm still on your last request."

    @staticmethod
    def not_understood() -> str:
        return "Sorry, I didn't catch that. Could you say it another way?"

    @staticmethod
    def still_unclear() -> str:
        # After one question the user answered, asking again would go round in circles.
        return ("I'm still not sure what you mean, sorry. Select the signals in the table and tell me what "
                "to do with them, and I'll use the selected ones.")

    @staticmethod
    def already_for_it(applied: bool) -> str:
        """A correction naming the signal or plot the last card is for already."""
        return "That's the one I changed." if applied else \
            "The card is for that one already: click Apply when it looks right."

    @staticmethod
    def still_missing_number() -> str:
        return "I still need the number for that. Just the number is enough."

    @staticmethod
    def too_long() -> str:
        return "That's a lot in one go. Could you ask me for one or two things at a time?"

    @staticmethod
    def redrawn() -> str:
        return "I've redrawn the plots."

    @staticmethod
    def found(search, wanted=None, ticked=False) -> str:
        where = (f"Here are the variables in {search.source} that start with {search.group}." if search.group
                 else f"Here's what I found in {search.source}.")
        if wanted == 1:
            pick = "Tick the one you want and I'll add it."
        elif wanted:
            pick = f"Tick the {wanted} you want and I'll add them."
        else:
            pick = "Tick the ones you want and I'll add them."
        shown = len(search.found)
        more = (f" There are {search.total}: these are the first {shown}, and Search Vars shows them all."
                if search.total > shown else "")
        exact = " Those named exactly as in the file are ticked." if ticked else ""
        missing = f" I found nothing for {_listed(search.missing)}." if search.missing else ""
        return f"{where} {pick}{more}{exact}{missing}"

    @staticmethod
    def nothing_found(search) -> str:
        what = " or ".join(search.missing) if search.missing else " ".join(search.words) or search.group
        return (f"I couldn't find anything called {what} in {search.source}. "
                "Could you try other words? The Search Vars button can help too.")

    @staticmethod
    def tick_one() -> str:
        return "Tick at least one, then click Add."

    @staticmethod
    def streaming(button: str = "") -> str:
        then = f", then {button} again" if button else ", then ask me again"
        return f"MINT is streaming live data right now. Click Stop first{then}."

    @staticmethod
    def went_wrong() -> str:
        return "Sorry, that didn't work on my side. Could you try again in a moment?"

    @staticmethod
    def could_not_work_out() -> str:
        return "Sorry, I couldn't work that one out. Could you ask in another way?"

    @staticmethod
    def could_not_apply() -> str:
        return "Sorry, that didn't work, so I've left everything as it was. Could you try again?"

    @staticmethod
    def could_not_start() -> str:
        return "The assistant couldn't start on this computer. Ask whoever looks after MINT here."

    # What the model process is doing while it starts, in the order it does it.
    LOADING = {"start": "Waking up the assistant…", "checking": "Checking the model file…",
               "loading": "Loading the model…", "priming": "Learning what MINT can do…"}

    @staticmethod
    def loading(step: str) -> str:
        return Voice.LOADING.get(step, Voice.getting_ready())

    @staticmethod
    def getting_ready() -> str:
        return "Getting everything ready…"

    @staticmethod
    def redraw_failed() -> str:
        return " I couldn't redraw the plots, though: click Draw to see the change."
