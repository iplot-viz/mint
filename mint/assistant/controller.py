"""Glue between the chat panel, the model and the workspace."""
import os

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QToolBar

from iplotLogging import setupLogger
from mint.assistant import check, commands, doubt, followup, prompt, recipes, record
from mint.assistant.actions import ActionError, ApplyContext, Change, Lazy, MissingValue, Planner, Proposal
from mint.assistant.config import AssistantConfig, prompt_cache_dir, runtime_available, state_dir
from mint.assistant.engine import BUSY, FAILED, LOADING, READY, ModelEngine
from mint.assistant.models import KNOWN_MODELS, chat_format, few_shot
from mint.assistant.voice import Voice
from mint.assistant.workspace import MintWorkspace

logger = setupLogger.get_logger(__name__)

SUGGESTIONS = [
    "Smooth the selected signals over 10 s",
    "Log scale on the first plot",
    "Show the last 6 hours",
    "What can you do?",
]
MAX_SUGGESTION = 48
PLACEHOLDER = "Tell me what you need…"


def _spoken(row) -> str:
    """How a suggestion calls a row: its alias or the end of its variable, if short and plain; else ''."""
    name = row.alias or row.variable.split(":")[-1]
    return name if "${" not in name and len(name) <= 24 else ""


def suggestions(snap) -> list:
    """A few requests that fit this workspace, written by MINT from the table: they show what can be asked."""
    rows = [r for r in snap.rows if r.plot and not r.derived]
    out = []
    for plot in snap.plots:
        measured = {prompt.measures(r) for r in rows if r.plot == plot.id}
        if measured == {"pressure"} and not plot.log_scale and len(snap.plots) > 1:
            out.append(f"Log scale on {snap.place(plot.id)}")
            break
    names = [name for name in map(_spoken, rows) if name]
    if snap.selected:
        out.append("Smooth the selected signals over 10 s")
    elif names:
        out.append(f"Smooth {names[0]} over 10 s")
    if len(names) > 1:
        out.append(f"{names[0]} minus {names[1]}")
    out += ["Show the last 6 hours", "What can you do?"]
    return [s for s in out if len(s) <= MAX_SUGGESTION][:4]


APPLY, UNDO, DISMISS, ADD_EACH, ADD_TOGETHER = "apply", "undo", "dismiss", "add_each", "add_together"


def install(window, splitter, signals_toolbar, view_menu):
    """Add the assistant to the main window when it is enabled; otherwise do nothing."""
    config = AssistantConfig.from_environment()
    if not config.enabled:
        return None
    try:
        from iplotWidgets.chatPanel import ChatPanel, assistant_icon
    except ImportError as e:
        logger.warning(f"MINT_ASSISTANT is set but this iplotWidgets has no chat panel: {e}")
        return None
    controller = AssistantController(window, config, ChatPanel)
    panel = controller.panel
    panel.hide()
    splitter.addWidget(panel)
    splitter.setCollapsible(splitter.indexOf(panel), True)

    def keep_last(*_):
        # Reattaching the canvas appends it to the splitter again, after the panel: put the panel back last.
        if not panel.is_detached():
            splitter.addWidget(panel)

    detach = getattr(getattr(window, "toolBar", None), "detachAction", None)
    if detach is not None:
        detach.triggered.connect(keep_last)

    icon = assistant_icon(window.palette().windowText().color())
    # A window of its own like the one Detach gives the canvas, with the same title bar buttons.
    floating = QMainWindow(parent=window, flags=(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
                                                 | Qt.WindowType.WindowMaximizeButtonHint
                                                 | Qt.WindowType.WindowMinimizeButtonHint))
    floating.setWindowTitle("MINT Assistant")
    floating.setWindowIcon(icon)
    floating.hide()
    controller.splitter, controller.floating = splitter, floating
    panel.set_detachable(True)
    panel.detachRequested.connect(controller.set_detached)

    action = QAction(icon, "&AI Assistant", window)
    action.setCheckable(True)
    action.setShortcut(QKeySequence("Ctrl+Shift+A"))
    action.setStatusTip("Ask the assistant to process signals, change plots or set the time range")
    action.toggled.connect(controller.set_visible)
    panel.closeRequested.connect(lambda: action.setChecked(False))
    view_menu.addAction(action)
    controller.toggle_action = action

    toolbar = signals_toolbar.findChild(QToolBar)
    search = getattr(signals_toolbar, "searchVarsBtn", None)
    if toolbar is not None and search is not None:
        button = QPushButton(icon, "AI Assistant")
        button.setCheckable(True)
        button.setToolTip("AI Assistant (Ctrl+Shift+A)")
        button.toggled.connect(action.setChecked)
        action.toggled.connect(button.setChecked)
        actions = toolbar.actions()
        anchor = next((a for a in actions if toolbar.widgetForAction(a) is search), None)
        following = actions[actions.index(anchor) + 1] if anchor in actions[:-1] else None
        if following is not None:
            toolbar.insertWidget(following, button)
        else:
            toolbar.addWidget(button)
        controller.toolbar_button = button
    return controller


class AssistantController(QObject):
    def __init__(self, window, config: AssistantConfig, panel_class, engine=None):
        super().__init__(window)
        self.window = window
        self.config = config
        self.workspace = MintWorkspace(window)
        self.panel = panel_class()
        self.panel.setObjectName("assistantPanel")
        self.voice = Voice()
        self.panel.set_placeholder(PLACEHOLDER)
        self.panel.set_suggestions(SUGGESTIONS)
        self.panel.messageSubmitted.connect(self.on_request)
        self.panel.cardActionTriggered.connect(self.on_card_action)
        self.panel.stopRequested.connect(self.on_stop)
        self.panel.emptySubmitted.connect(self._apply_pending)  # Enter with nothing typed applies the card
        self._pending_card = None
        self.toggle_action = None
        self.toolbar_button = None
        self.splitter = None
        self.floating = None
        self.engine = None
        self.format = None
        self._queued = None
        self._inflight = None
        self._open_question = None
        self._cards = {}
        self._searches = {}  # suggestion text -> words, for the searches MINT offers itself
        self._last_action = ""
        self._sized = False
        self._session = f"{os.getpid()}-{id(self):x}"  # tells the cards of two MINT sessions apart in the record
        self._model_name = ""
        self._primed = True
        self._few_shot = True
        self._workspace_dirty = True
        self._watch_workspace()
        if engine is not None:
            self._attach(engine)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)


    def set_visible(self, visible: bool):
        self.panel.setVisible(visible)
        if self.panel.is_detached():
            self.floating.setVisible(visible)
        if not visible:
            return
        if self.panel.is_detached():
            self.floating.raise_()
            self.floating.activateWindow()
        else:
            self._fit_in_splitter()
        if not self.panel.message_count():
            try:
                self.panel.set_suggestions(suggestions(self.workspace.snapshot()) or SUGGESTIONS)
            except Exception as e:  # the fixed ones are fine too
                logger.debug(f"Assistant: no suggestions from the table: {e}")
        self.panel.input.setFocus()
        self._ensure_engine()

    def _fit_in_splitter(self):
        """The first time the panel shows in the splitter, it takes its width from the canvas."""
        if self._sized:
            return
        self._sized = True
        splitter = self.panel.parentWidget()
        if splitter is not None and hasattr(splitter, "sizes"):
            sizes = splitter.sizes()
            width = max(self.panel.minimumSizeHint().width(), 360)
            if len(sizes) >= 3 and sizes[-2] > 2 * width:
                sizes[-2] -= width
                sizes[-1] = width
                splitter.setSizes(sizes)

    def set_detached(self, detached: bool):
        """Move the panel to its own window, or back to the right of the plots, as Detach does with the canvas."""
        if detached == self.panel.is_detached():
            return
        if detached:
            size = self.panel.size()
            self.floating.setCentralWidget(self.panel)
            self.floating.resize(size)
            self.floating.show()
        else:
            self.splitter.addWidget(self.panel)
            self.floating.hide()
        self.panel.show()
        self.panel.set_detached(detached)
        if not detached:
            # Back in the splitter, it takes its width as the first time.
            self._sized = False
            self._fit_in_splitter()

    def _ensure_engine(self):
        if self.engine is not None and self.engine.state != FAILED:
            return
        problem = self._configuration_problem()
        if problem:
            self.panel.set_status(problem)
            self.panel.set_input_enabled(False)
            return
        if self.engine is not None:
            self.engine.deleteLater()
        self._attach(ModelEngine(self.config.model_path, self.config.threads, allowed_sha256=self._allowed_hashes(),
                                 verified_cache=os.path.join(state_dir(), "verified_models.json"), parent=self))
        self.engine.start()

    def _attach(self, engine):
        self.engine = engine
        engine.stateChanged.connect(self._on_engine_state)
        engine.loaded.connect(self._on_loaded)
        engine.primed.connect(self._on_primed)
        engine.completed.connect(self._on_completed)
        engine.failed.connect(self._on_failed)

    def _allowed_hashes(self):
        allowed = set(KNOWN_MODELS)
        if self.config.sha256:
            allowed.add(self.config.sha256)
        return sorted(allowed)

    def _configuration_problem(self) -> str:
        # Read by operators first: what is wrong and who can fix it, the technical detail after it.
        ask = "Ask whoever looks after MINT here."
        if not runtime_available():
            return f"The assistant isn't installed on this computer yet. {ask} (pip install iter-mint[assistant])"
        if not self.config.model_path:
            return f"The assistant isn't set up on this computer yet. {ask} (MINT_ASSISTANT_MODEL is not set)"
        if not os.path.isfile(self.config.model_path):
            return f"The assistant can't find its model file. {ask} ({self.config.model_path})"
        return ""

    def shutdown(self):
        if self.engine is not None:
            self.engine.shutdown()

    def _on_engine_state(self, state: str):
        busy = state == BUSY
        # Until the fixed prompt is ready (about a minute the first time on a machine) a request waits behind it.
        self.panel.set_busy(busy, "Thinking…" if self._primed else "Getting ready, then I'll answer…")
        if state == LOADING:
            self.panel.set_status("Starting up…")
        elif state == READY and not busy:
            self.panel.set_input_enabled(True)

    def _on_loaded(self, info: dict):
        declared = info.get("declared") or {}
        self.format = prompt.ChatFormat(chat_format(info.get("sha256", ""), declared))
        self._few_shot = few_shot(info.get("sha256", ""), declared)
        self._model_name = KNOWN_MODELS.get(info.get("sha256", ""), {}).get("name", "custom model")
        self._primed = False
        self.panel.set_status("Getting ready…")
        # The worker handles requests in order: whatever comes next waits for the prefix.
        self.engine.prime(prompt.fixed_prefix(self.format, self._few_shot), prompt_cache_dir())
        self._workspace_dirty = True
        self._warm()
        if self._queued:
            queued, self._queued = self._queued, None
            self._ask_model(*queued)

    def _on_primed(self, info: dict):
        self._primed = True
        logger.info(f"Assistant ready with {self._model_name} (format {self.format.name}, "
                    f"{'with' if self._few_shot else 'without'} worked examples)")
        self.panel.set_status("Ready")

    def _on_failed(self, request_id: int, message: str):
        # The details are for the log; the operator gets what happened and what to do.
        logger.warning(f"Assistant: {message}")
        self.panel.set_busy(False)
        waiting, self._inflight = self._inflight, None
        if self.engine is None or self.engine.state == FAILED:
            self.panel.set_status(self.voice.could_not_start() if self.format is None else
                                  "The assistant stopped. Send a message and it starts again.")
        if waiting is not None or self._queued is not None:
            self._queued = None
            self.panel.add_assistant_message(self.voice.went_wrong())

    # Edits only mark the prompt stale; it is evaluated again when the user starts typing,
    # so no CPU is spent while the table is edited.

    def _watch_workspace(self):
        model = self.workspace.model
        for signal in (model.dataChanged, model.layoutChanged, model.rowsInserted, model.rowsRemoved):
            signal.connect(self._mark_dirty)
        for item in self.window.sigCfgWidget.item_widgets:
            selection = item.view().selectionModel()
            if selection is not None:
                selection.selectionChanged.connect(self._mark_dirty)
        self.window.dataRangeSelector.modeChanged.connect(self._mark_dirty)
        self.panel.input.textChanged.connect(self._on_typing)

    def _mark_dirty(self, *_):
        self._workspace_dirty = True

    def _on_typing(self):
        if self._workspace_dirty and self.panel.input.toPlainText().strip():
            self._warm()

    def _warm(self):
        if self.engine is None or self.engine.state != READY or self.format is None:
            return
        self._workspace_dirty = False
        try:
            warm, _ = prompt.build(self.format, prompt.visible(self.workspace.snapshot()), "", self._few_shot)
        except Exception:
            logger.exception("Assistant: could not read the workspace")
            return
        self.engine.warm(warm)


    def on_request(self, text: str):
        self.panel.add_user_message(text)
        self._set_pending(None)
        search, self._searches = self._searches.get(text), {}
        if search:
            self._open_question = None
            self._show_search(search, text)
            return
        if followup.is_undo(text):
            self._open_question = None
            self._undo_last()
            return
        # A reply to the last question: fills a number, names the signal "it" meant, or goes to the model
        # with the request it answers. Anything longer is a new request.
        question, self._open_question = self._open_question, None
        answering = question is not None and followup.is_answer(text)
        named = False
        if answering and question.command is not None:
            value = followup.value_in(text, question.param)
            if value is not None:
                self._answer_with_number(question, value, text)
                return
        if answering:
            rewritten = check.chosen(self.workspace.snapshot(), question.request, text) and \
                check.in_place_of_it(question.request, text)
            named = bool(rewritten)
            text = rewritten or followup.with_answer(question, text)
        if self.engine is None or self.engine.state == FAILED:
            self._ensure_engine()
        if self.engine is None or self.engine.state == FAILED:  # the status says why
            return
        if self.engine.state == LOADING:
            self._queued = (text, answering, named)
            self.panel.set_busy(True, "Getting ready, I'll answer in a moment…")
            return
        self._ask_model(text, answering, named)

    def _answer_with_number(self, question, value: float, answer: str):
        question.command.params[question.param] = recipes.number(value)
        try:
            proposal = Planner(self.workspace, question.snap).plan(question.commands)
        except MissingValue:
            self.panel.add_assistant_message(self.voice.still_missing_number())
            return
        except ActionError as e:
            self.panel.add_assistant_message(str(e))
            return
        except Exception:
            logger.exception("Assistant could not plan with the user's answer")
            self.panel.add_assistant_message(self.voice.could_not_work_out())
            return
        # The request with its answer, as the model would have read it (and as a recorded card keeps it).
        self._present(proposal, followup.with_answer(question, answer), question.snap, answering=True)

    def _ask_model(self, text: str, answering: bool = False, named: bool = False):
        if self.engine.state != READY:
            self.panel.add_assistant_message(self.voice.still_busy())
            return
        try:
            snap = self.workspace.snapshot(self._last_action)
            shown = prompt.visible(snap)
            _, full = prompt.build(self.format, shown, text, self._few_shot)
            grammar = commands.build_grammar(*prompt.answer_ids(shown, text), recipes.load())
        except Exception:
            logger.exception("Assistant: could not prepare the request")
            self.panel.add_assistant_message(self.voice.could_not_work_out())
            return
        # Recorded before sending, so an answer arriving at once still finds its request.
        self._inflight = (snap, text, answering, named)
        try:
            self.engine.complete(full, grammar)
        except RuntimeError as e:
            logger.warning(f"Assistant: {e}")
            self._inflight = None
            self.panel.add_assistant_message(self.voice.went_wrong())

    def on_stop(self):
        if self.engine is not None:
            self.engine.cancel()
        self._queued = None

    def _on_completed(self, request_id: int, text: str, timings: dict):
        inflight, self._inflight = self._inflight, None
        if inflight is None:
            return
        snap, request, answering, named = inflight
        elapsed = timings.get("total_s")
        if elapsed is not None:
            self.panel.set_status(f"Answered in {elapsed:.1f} s")
        if timings.get("cancelled") or not text.strip():
            self.panel.add_assistant_message(self.voice.stopped())
            return
        if timings.get("finish") == "length":
            # Its last line may be half a command that still parses, e.g. a window cut from 30 s to 3 s.
            self.panel.add_assistant_message(self.voice.too_long())
            return
        try:
            cmds = check.review(snap, request, commands.parse(text))
            planner = Planner(self.workspace, snap)
            proposal = planner.plan(cmds)
            rows, plots = prompt.answer_ids(snap, request)
            # Not after an answer: one question per request.
            unsure = None if answering else doubt.doubtful(timings.get("ids"), set(rows) | set(plots))
            if unsure and proposal.changes:
                # It hesitated between two rows or plots: asking costs the user less than a wrong change.
                logger.info(f"Assistant unsure between {unsure[0]} and {unsure[1]} in {text!r}")
                proposal = planner.plan([commands.Command("ask", text=f"Sure, which one: {unsure[0]} or {unsure[1]}?")])
        except MissingValue as e:
            # One question per request: after an answer, say how to go on rather than ask again.
            # A signal picked in reply to "which one?" still gets its missing number asked for.
            if answering and not named:
                self.panel.add_assistant_message(self.voice.still_missing_number())
            else:
                self._open_question = followup.OpenQuestion(request, snap, cmds, e.command, e.param)
                self.panel.add_assistant_message(str(e))
            return
        except (commands.CommandError, ActionError) as e:
            logger.info(f"Assistant answer not applicable: {text!r}: {e}")
            self.panel.add_assistant_message(str(e) if isinstance(e, ActionError) else self.voice.not_understood())
            return
        except Exception:  # a slot must never die silently
            logger.exception(f"Assistant could not plan {text!r}")
            self.panel.add_assistant_message(self.voice.could_not_work_out())
            return
        self._present(proposal, request, snap, answering)
        if not proposal.changes and proposal.search is None:
            # A code that is in no row ("need TF07 coil current") is most likely a signal to add.
            codes = check.unknown_codes(snap, request)
            if codes:
                self._searches = {f"Find {codes[0]}": [codes[0]]}
                self._suggest(list(self._searches))

    def _suggest(self, texts):
        """Suggestions shown in the conversation, not only before it starts."""
        self.panel.set_suggestions(texts, anytime=True)

    def _present(self, proposal, request: str, snap, answering: bool):
        if proposal.question and not proposal.changes:
            if answering:
                self.panel.add_assistant_message(self.voice.still_unclear())
                return
            self._open_question = followup.OpenQuestion(request, snap)
        for message in proposal.messages:
            self.panel.add_assistant_message(message)
        if proposal.changes:
            card = self._show_proposal(proposal, spoken=bool(proposal.messages))
            if card is not None:  # None when it only redraws
                self._cards[card].update(request=request, snap=snap)
        if proposal.search is not None:
            self._show_search(proposal.search, request)

    def _show_proposal(self, proposal, spoken=False):
        if all(not c.lines for c in proposal.changes):
            self._redraw_only(proposal.changes)
            return
        opener = self.voice.opener(after_words=spoken)
        if opener:
            self.panel.add_assistant_message(opener)
        card = self.panel.add_card(proposal.title, proposal.lines, [(APPLY, "Apply"), (UNDO, "Undo"),
                                                                    (DISMISS, "Dismiss")],
                                   detail=proposal.detail, detail_label="Formula")
        self.panel.set_card_state(card, enabled=[APPLY, DISMISS])
        self._cards[card] = {"kind": "proposal", "proposal": proposal}
        self._set_pending(card)
        return card

    def _set_pending(self, card):
        """The card Enter applies: the newest one, until it is used or the user asks something else."""
        self._pending_card = card
        self.panel.set_placeholder(self.voice.PENDING if card is not None else PLACEHOLDER)

    def _apply_pending(self):
        if self._pending_card in self._cards:
            self.on_card_action(self._pending_card, APPLY, [])

    def _undo_last(self):
        applied = [card for card, entry in self._cards.items() if entry.get("applied")]
        if not applied:
            self.panel.add_assistant_message(self.voice.nothing_to_undo())
            return
        card = max(applied)
        self.on_card_action(card, UNDO, [])
        entry = self._cards[card]
        title = entry["proposal"].title if entry.get("proposal") is not None else ""
        self.panel.add_assistant_message(self.voice.could_not_apply() if entry.get("applied")
                                         else self.voice.undid(title))

    def _next_steps(self, entry) -> list:
        """A follow-up for what was just applied, written by MINT from the table (no model)."""
        snap = entry.get("snap")
        written = entry["proposal"].commands
        if snap is None or len(written) != 1:
            return []
        cmd = commands.parse(written[0])[0]
        if cmd.verb == "plot" and cmd.ids != ["all"] and len(snap.plots) > 1:
            return ["The same for all plots"]
        row = snap.row(cmd.ids[0]) if cmd.verb == "process" and len(cmd.ids) == 1 else None
        if row is None:
            return []
        meaning = prompt.measures(row)
        others = [(other, _spoken(other)) for other in snap.rows if other.id != row.id and other.plot
                  and not other.derived]
        others = [(other, name) for other, name in others if name]
        # The likeliest next one: a signal measuring the same, else one beside it, else any other.
        for fits in (lambda o: meaning and prompt.measures(o) == meaning, lambda o: o.plot == row.plot,
                     lambda o: True):
            for other, name in others:
                if fits(other):
                    return [f"The same for {name}"]
        return []

    def _show_search(self, words, request: str = ""):
        try:
            search = self.workspace.search_variables(words, request)
        except ActionError as e:
            self.panel.add_assistant_message(str(e))
            return
        if not search.found:
            self.panel.add_assistant_message(self.voice.nothing_found(search))
            return
        options = [(name, f"{name} — {description}" if description else name, False)
                   for name, description in search.found]
        self.panel.add_assistant_message(self.voice.found(search, check.wanted(request)))
        shown = len(search.found)
        count = f"{shown} of {search.total}" if search.total > shown else str(shown)
        title = f"{count} variable{'' if search.total == 1 else 's'} in {search.source}"
        if search.group:
            title += f" starting with {search.group}"
        card = self.panel.add_card(title, [], [(ADD_EACH, "Add, one plot each"), (ADD_TOGETHER, "Add to one plot"),
                                               (UNDO, "Undo")], options=options)
        self.panel.set_card_state(card, enabled=[ADD_EACH, ADD_TOGETHER])
        self._cards[card] = {"kind": "search", "source": search.source}


    def on_card_action(self, card_id: int, key: str, checked: list):
        entry = self._cards.get(card_id)
        if entry is None or entry.get("busy"):
            return
        if key in (ADD_EACH, ADD_TOGETHER) and not checked:
            self.panel.set_card_state(card_id, note=self.voice.tick_one())
            return
        if card_id == self._pending_card:
            self._set_pending(None)
        # Locked before anything runs: Draw spins the event loop, and a second click must not apply twice.
        entry["busy"] = True
        self.panel.set_card_state(card_id, enabled=[])
        try:
            if key == APPLY:
                self._apply(card_id, entry)
            elif key == UNDO:
                self._undo(card_id, entry)
            elif key == DISMISS:
                self.panel.set_card_state(card_id, enabled=[], note=self.voice.dismissed())
            elif key in (ADD_EACH, ADD_TOGETHER):
                entry["proposal"] = self._add_variables(entry["source"], checked, key == ADD_TOGETHER)
                self._apply(card_id, entry)
        except ActionError as e:
            self.panel.set_card_state(card_id, enabled=self._ready_actions(entry), note=str(e))
        except Exception:
            logger.exception("Assistant: card action failed")
            self.panel.set_card_state(card_id, enabled=self._ready_actions(entry), note=self.voice.could_not_apply())
        else:
            self._follow_up(card_id, entry, key)
        finally:
            entry["busy"] = False

    def _follow_up(self, card_id, entry, key):
        """After a button did its job: the record of it, and the likely next step. Never undoes the job."""
        try:
            outcome = {APPLY: "applied", UNDO: "undone", DISMISS: "dismissed"}.get(key)
            if outcome:
                self._record(card_id, entry, outcome)
            if key == APPLY and entry.get("snap") is not None:
                self._suggest(self._next_steps(entry))
        except Exception:
            logger.exception("Assistant: could not follow up a card")

    def _ready_actions(self, entry):
        if entry.get("applied"):
            return [UNDO]
        return [ADD_EACH, ADD_TOGETHER] if entry["kind"] == "search" else [APPLY, DISMISS]

    def _record(self, card_id, entry, outcome):
        if self.config.record and entry.get("request"):
            record.write(f"{self._session}-{card_id}", outcome, entry["request"], entry["snap"],
                         entry["proposal"].commands)

    def _apply(self, card_id, entry):
        proposal = entry["proposal"]
        if self.workspace.is_streaming() and any(c.needs_draw for c in proposal.changes):
            raise ActionError(self.voice.streaming("Add" if entry["kind"] == "search" else "Apply"))
        try:
            proposal.apply()
        except ActionError:
            raise
        except Exception:
            logger.exception("Assistant: apply failed")
            # Apply is all or nothing: whatever had been changed was put back.
            raise ActionError(self.voice.could_not_apply())
        entry["applied"] = True
        # As commands, so "the same for X" can repeat it exactly.
        self._last_action = "; ".join(proposal.commands)
        note = self.voice.done() + self._run_redraw(proposal.changes)
        self.panel.set_card_state(card_id, enabled=[UNDO], note=note)

    def _undo(self, card_id, entry):
        proposal = entry["proposal"]
        problems = proposal.undo()
        entry["applied"] = False
        self._last_action = ""
        note = self.voice.undone(problems) + self._run_redraw(proposal.changes)
        self.panel.set_card_state(card_id, enabled=self._ready_actions(entry), note=note)

    def _run_redraw(self, changes) -> str:
        """Redraw if the changes need it; returns a note to add when the redraw itself fails."""
        try:
            if any(c.needs_draw for c in changes):
                self.workspace.draw()
            elif any(c.needs_refresh for c in changes):
                self.workspace.refresh_plots()
        except Exception:
            logger.exception("Assistant: redraw failed")
            return self.voice.redraw_failed()
        return ""

    def _redraw_only(self, changes):
        # Draw does nothing while MINT streams, so say so rather than claim a redraw.
        if self.workspace.is_streaming():
            self.panel.add_assistant_message(self.voice.streaming())
            return
        failed = self._run_redraw(changes)
        self.panel.add_assistant_message(failed.strip() if failed else self.voice.redrawn())

    def _add_variables(self, source: str, names, together: bool) -> Proposal:
        context = ApplyContext(self.workspace)
        proposal = Proposal(title="Add variables", context=context)
        for n, name in enumerate(names):
            values = {"DS": source, "Variable": name, "Stack": Lazy("stack", "together" if together else name)}
            created = {}

            def do(values=values, created=created):
                created["uid"] = self.workspace.append_row(context.values(values))

            def undo(created=created):
                if created.get("uid"):
                    self.workspace.remove_row(created.pop("uid"))

            proposal.changes.append(Change([f"Add {name}"], do, undo, needs_draw=True))
        return proposal
