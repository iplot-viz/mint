"""Fixed sentences around the cards: on a CPU every word the model writes costs time."""

# A card is a proposal, not something done: the openers say so.
OPENERS = ("Here's what I'd do.", "Got it. Here's the change.", "Okay, how does this look?", "This should do it.")
FIRST_OPENER = "Here's what I'd change. Nothing happens until you click Apply, and Undo puts it back."
DONE = ("Done.", "There you go.", "All set.")


def _listed(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


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
