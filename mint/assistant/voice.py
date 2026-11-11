"""Fixed sentences around the cards: on a CPU every word the model writes costs time."""

# A card is a proposal, not something done: the openers say so.
OPENERS = ("Here's what I'd do.", "Got it. Here's the change.", "Okay, how does this look?", "This should do it.")
FIRST_OPENER = "Here's what I'd change. Nothing happens until you click Apply, and Undo puts it back."
DONE = ("Done.", "There you go.", "All set.")


class Voice:
    def __init__(self):
        self._said = {}

    def _next(self, key: str, options) -> str:
        count = self._said.get(key, 0)
        self._said[key] = count + 1
        return options[count % len(options)]

    def opener(self, after_words: bool = False) -> str:
        """Before a card: the first-time explanation, then a short varied acknowledgement.

        After the model's own words only the explanation is added.
        """
        if "opener" not in self._said:
            self._said["opener"] = 0
            return FIRST_OPENER
        return "" if after_words else self._next("opener", OPENERS)

    def done(self) -> str:
        return self._next("done", DONE)

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
        return ("I still need a number for that. Tell me the whole thing in one go, "
                "for example \"smooth the pirani over 10 s\".")

    @staticmethod
    def too_long() -> str:
        return "That's a lot in one go. Could you ask me for one or two things at a time?"

    @staticmethod
    def redrawn() -> str:
        return "I've redrawn the plots."

    @staticmethod
    def found(search, wanted=None) -> str:
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
        return f"{where} {pick}{more}"

    @staticmethod
    def nothing_found(search) -> str:
        what = " ".join(search.words) or search.group
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
