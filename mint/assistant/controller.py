"""Glue between the chat panel, the model and the workspace."""
import dataclasses
import os
import re
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QToolBar

from iplotLogging import setupLogger
from mint.assistant import (check, commands, diagnose, doubt, features, files, followup, prompt, recipes, record,
                            when)
from mint.assistant.actions import MAX_ADDED, ActionError, ApplyContext, MissingValue, Planner, Proposal, added_rows
from mint.assistant.config import AssistantConfig, prompt_cache_dir, runtime_available, state_dir
from mint.assistant.engine import BUSY, FAILED, LOADING, READY, ModelEngine
from mint.assistant.models import KNOWN_MODELS, chat_format, few_shot, reads_files
from mint.assistant.voice import Voice
from mint.assistant.workspace import (DRAWN, EMPTY, FOUND, NONE_BEFORE, NOT_COMPUTED, UNKNOWN_VARIABLE, UNTOLD,
                                      MintWorkspace)

logger = setupLogger.get_logger(__name__)

SUGGESTIONS = [
    "Smooth the selected signals over 10 s",
    "Log scale on the first plot",
    "Show the last 6 hours",
    "What can you do?",
]
MAX_SUGGESTION = 48
PLACEHOLDER = "Tell me what you need…"
# Words around a data source that only ask to search there instead: "no, take sdnuda", "use sdnuda instead".
SEARCH_AGAIN = set("no not nope take use using instead of looking look search searching find in on at from with try "
                   "it them the then ok okay please there again rather better en usa usar busca buscar prueba mejor "
                   "mira de del dans utilise cherche plutôt essaie im nimm suche versuch lieber stattdessen cerca "
                   "prova invece piuttosto em procure tente".split())
NOT_THIS = set("instead not rather vez lugar lieu statt anstatt invece".split())


def _time_offer(info) -> str:
    return f"Show the time in the {'text' if info.name == files.PASTED else 'file'}"


def _file_offers(info) -> dict:
    """What MINT offers once a file is read, each with the commands it is: no model is needed for them."""
    offers = {}
    if 0 < len(info.variables) <= MAX_ADDED:
        offers["Add them, one plot each"] = "add all"
        if len(info.variables) > 1:
            offers["Add them to one plot"] = "add all together"
    if info.times:
        offers[_time_offer(info)] = f"range from t1 to t{len(info.times)}" if len(info.times) > 1 else "range day t1"
    return offers


class _Codes(list):
    """Tags a file gives without their system, each looked up on its own (see MintWorkspace.search_codes)."""


# Variables looked up at most when a new time range leaves signals without data: one archive request each.
MAX_LOOKUPS = 8


def _called(row) -> str:
    """A row as a message names it: its alias, else the end of its variable."""
    return row.alias or row.variable.split(":")[-1]


def _moment(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


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
    # (path, files.Found or the exception), from the thread that read the file.
    fileRead = Signal(str, object)

    def __init__(self, window, config: AssistantConfig, panel_class, engine=None):
        super().__init__(window)
        self.window = window
        self.config = config
        self.workspace = MintWorkspace(window)
        self.panel = panel_class()
        self.panel.setObjectName("assistantPanel")
        self.panel.set_title("AI Assistant")  # as the button that opens it
        self.voice = Voice()
        self.panel.set_placeholder(PLACEHOLDER)
        self.panel.set_suggestions(SUGGESTIONS)
        self.panel.messageSubmitted.connect(self.on_request)
        self.panel.cardActionTriggered.connect(self.on_card_action)
        self.panel.stopRequested.connect(self.on_stop)
        self.panel.emptySubmitted.connect(self._apply_pending)  # Enter with nothing typed applies the card
        self.panel.fileAttached.connect(self.on_file_attached)
        self.panel.attachmentRemoved.connect(self.on_attachment_removed)
        self.fileRead.connect(self._on_file_read)
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
        self._planned = {}  # suggestion text -> commands MINT plans itself, without the model
        self._fix_offer = ""  # the one change of data source just offered, which "yes" takes
        self._told_problems = ""  # the missing data sources last told on opening the panel
        self._last_search = None  # (words, data source) of the last search shown, for "no, in sdnuda"
        self._search_source = ""  # the data source the user chose to search in, until they choose the default again
        self._turns = 0
        self._file = None  # snapshot.FileInfo of the attached file
        self._reading = ""  # the file being read, whose result is the one awaited
        self._reads_files = False  # the model was trained on attached files (see models.reads_files)
        self._last_action = ""
        self._last_applied = None  # the card entry of the last change applied and not undone
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
            self._release_model()
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
        self._tell_problems(on_open=True)

    def _release_model(self):
        """Closing the panel frees the memory the model takes; opening it again loads it in a few seconds."""
        if self.engine is None:
            return
        engine, self.engine = self.engine, None
        engine.shutdown()
        engine.deleteLater()
        self._inflight, self._queued, self._primed = None, None, False
        self.panel.set_busy(False)

    def _tell_problems(self, on_open: bool = False) -> bool:
        """Why rows aren't drawn, from MINT's own state, with the change of data source that fixes the commonest case.

        On opening the panel only a data source that isn't here is told, and once. False when nothing is told.
        """
        try:
            snap = self.workspace.snapshot()
            problems = diagnose.find(snap, self.workspace.data_source_choices())
        except Exception:
            logger.exception("Assistant: could not look at the table's problems")
            return False
        told = repr(sorted((source, [row.uid for row in rows]) for source, rows in problems.missing.items()))
        if not problems or (on_open and (not problems.missing or told == self._told_problems)):
            return False
        self._told_problems = told
        planner = Planner(self.workspace, snap)
        fixes = {source: diagnose.replacement(source, problems.sources) for source in problems.missing}
        offers = {}
        for source, rows in problems.missing.items():
            for target in [fixes[source]] if fixes[source] else problems.sources[:3]:
                offers[self.voice.change_source(source, target)] = f"source {' '.join(r.id for r in rows)} to {target}"
        shown = problems.invalid[:3]
        self.panel.add_assistant_message(self.voice.problems(
            [(source, [planner.name(row) for row in rows]) for source, rows in problems.missing.items()], fixes,
            [(planner.name(row), reason) for row, reason in shown], problems.sources,
            more=len(problems.invalid) - len(shown)))
        self._planned = offers
        # "Yes" to "Shall I change them to imas?" is that one change.
        self._fix_offer = next(iter(offers)) if len(offers) == 1 else ""
        self._suggest(list(offers))
        return True

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
        self._primed = False
        self.engine.start()

    def _attach(self, engine):
        self.engine = engine
        engine.stateChanged.connect(self._on_engine_state)
        engine.step.connect(self._loading)
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
        if state == LOADING:
            self._loading("start")
        elif state == BUSY:
            # A request queued during start-up waits for the fixed prompt to be evaluated first.
            self.panel.set_busy(True, "Thinking…" if self._primed else "Getting ready, then I'll answer…")
        elif state == READY and self._primed:
            self.panel.set_busy(False)
            self.panel.set_input_enabled(True)

    def _loading(self, step: str):
        """While the model starts: the step it is at, and the input closed until it can answer."""
        self.panel.set_progress(self.voice.loading(step))
        self.panel.set_input_enabled(False)
        self.panel.set_placeholder(self.voice.getting_ready())
        self.panel.input.setToolTip(self.voice.getting_ready())
        self.panel.set_status("")

    def _ready(self):
        self.panel.set_progress("")
        self.panel.input.setToolTip("")
        self.panel.set_placeholder(PLACEHOLDER)
        self.panel.set_status("Ready")
        if self.engine is None or self.engine.state != BUSY:
            self.panel.set_busy(False)
            self.panel.set_input_enabled(True)
            self.panel.input.setFocus()

    def _on_loaded(self, info: dict):
        declared = info.get("declared") or {}
        self.format = prompt.ChatFormat(chat_format(info.get("sha256", ""), declared))
        self._few_shot = few_shot(info.get("sha256", ""), declared)
        self._reads_files = reads_files(info.get("sha256", ""), declared)
        self.panel.set_attachable(files.NAME_FILTER if self._reads_files else "")
        self._model_name = KNOWN_MODELS.get(info.get("sha256", ""), {}).get("name", "custom model")
        self._primed = False
        self._loading("priming")
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
        self._ready()

    def _on_failed(self, request_id: int, message: str):
        # The details are for the log; the operator gets what happened and what to do.
        logger.warning(f"Assistant: {message}")
        self.panel.set_busy(False)
        waiting, self._inflight = self._inflight, None
        if self.engine is None or self.engine.state == FAILED:
            self.panel.set_progress("")
            self.panel.input.setToolTip("")
            self.panel.set_placeholder(PLACEHOLDER)
            # Once it has run, a message starts it again; if it never started, there is nothing to send to.
            self.panel.set_input_enabled(self.format is not None)
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
            warm, _ = prompt.build(self.format, prompt.visible(self._snapshot()), "", self._few_shot)
        except Exception:
            logger.exception("Assistant: could not read the workspace")
            return
        self.engine.warm(warm)

    def _snapshot(self, last_action: str = ""):
        """The workspace as the model reads it, with the attached file."""
        snap = self.workspace.snapshot(last_action)
        snap.file = self._file
        return snap

    def on_file_attached(self, path: str):
        """Read off the GUI thread: a PDF of many pages takes seconds."""
        self.panel.add_user_message(os.path.basename(path))
        self._reading = path

        def read():
            try:
                result = files.read(path)
            except Exception as e:  # handed to the GUI thread, which says what went wrong
                result = e
            self.fileRead.emit(path, result)

        QThreadPool.globalInstance().start(read)

    def _on_file_read(self, path: str, result):
        if path != self._reading:  # another file was attached meanwhile
            return
        self._reading = ""
        name = os.path.basename(path)
        if isinstance(result, files.FileError):
            self.panel.add_assistant_message(str(result))
            return
        if isinstance(result, Exception):
            logger.error(f"Assistant: could not read {path}: {result!r}")
            self.panel.add_assistant_message(self.voice.could_not_read(name))
            return
        self._take_file(name, result, name)

    def _take_file(self, name: str, found, label: str, say: bool = True):
        """What the next requests go with, shown above the input box; told, with what to do, if ``say``."""
        try:
            source = self.workspace.default_data_source()[0] or ""
        except Exception as e:
            logger.warning(f"Assistant: no default data source for the variables of {name}: {e!r}")
            source = ""
        self._file = files.info(name, found, source)
        self._workspace_dirty = True
        self.panel.set_attachment(label)
        if say:
            codes = found.codes if source and not found.variables else []
            self.panel.add_assistant_message(self.voice.file_read(self._file, found.partial, codes))
            self._searches = {self.voice.find_codes(codes, source): _Codes(codes)} if codes else {}
            self._planned = _file_offers(self._file)
            self._suggest(list(self._searches) + list(self._planned))
        # Read now, while the user reads the answer: then a request only adds its own words.
        self._warm()

    def on_attachment_removed(self):
        self._file, self._reading, self._planned = None, "", {}
        self._workspace_dirty = True
        self.panel.set_attachment("")

    def _plan_direct(self, cmds, request: str):
        """Commands MINT knows without the model (a suggestion it offered), shown like the model's."""
        snap = self._snapshot(self._last_action)
        try:
            proposal = Planner(self.workspace, snap).plan(cmds)
        except ActionError as e:
            self.panel.add_assistant_message(str(e))
            return
        self._present(proposal, request, snap, answering=False)

    def on_request(self, text: str):
        self.panel.add_user_message(text)
        pending = self._pending_card
        self._set_pending(None)
        fix, self._fix_offer = self._fix_offer, ""
        if fix and followup.agrees(text):
            text = fix
        known = [row.variable for row in self.workspace.snapshot().rows] if self._reads_files else ()
        pasted = files.pasted(text, known) if self._reads_files else None
        if pasted is not None:
            # A list of signals pasted into the message is taken as a file, and the words around it as the request.
            found, text = pasted
            self._open_question, self._reading = None, ""
            self._take_file(files.PASTED, found, "Pasted text", say=not text)
            if not text:
                return
        search, self._searches = self._searches.get(text), {}
        planned, self._planned = self._planned.get(text), {}
        if search:
            self._open_question = None
            self._show_search(search, text)
            return
        if planned:
            self._open_question = None
            self._plan_direct(commands.parse(planned), text)
            return
        if followup.is_undo(text):
            self._open_question = None
            self._undo_last()
            return
        # Only right after it: "use sdnuda" later on is another request.
        last_search, self._last_search = self._last_search, None
        wanted = features.asked(text)
        if wanted is not None:
            self._open_question = None
            self._use_feature(wanted, text)
            return
        source = self._other_source(text, last_search)
        if source:
            self._open_question = None
            self._record_turn(text, [f"find {' '.join(last_search[0])} {source}"], by="MINT")
            self._show_search(last_search[0], source=source)
            return
        if diagnose.asks_about_state(text) and self._tell_problems():
            self._open_question = None
            self._record_turn(text, ["why are rows not drawn"], by="MINT")
            return
        # A reply to the last question: fills a number, names the signal "it" meant, or goes to the model
        # with the request it answers. Anything longer is a new request.
        question, self._open_question = self._open_question, None
        if question is None and pending in self._cards and self._answer_card(pending, text):
            return
        answering = question is not None and followup.is_answer(text)
        named = False
        if answering and question.options and followup.means_every(text, len(question.options)):
            if self._every_option(question, text):
                return
            # "All three" to the model's "which one: A, B or C?" names each of them.
            text = self._every_named(question)
        if answering and question.command is not None:
            value = followup.value_in(text, question.param)
            if value is None and question.example is not None and followup.agrees(text):
                value = question.example
            if value is not None:
                self._answer_with_number(question, value, text)
                return
        if question is None and self._again_with(text, pending):
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
            # Answered once it is ready; the progress in the panel already says what it is doing.
            self._queued = (text, answering, named)
            return
        self._ask_model(text, answering, named)

    def _every_option(self, question, answer: str) -> bool:
        """"Both" to "which one: A or B?": what the model meant, done to all of them, without asking it again."""
        widened = []
        for cmd in question.commands:
            ids = [i for i in cmd.ids if i not in question.options]
            if len(ids) != len(cmd.ids) and cmd.verb != "combine":
                cmd = dataclasses.replace(cmd, ids=ids + list(question.options))
            widened.append(cmd)
        if not widened or widened == question.commands:
            return False
        self._plan_with_number(widened, question.snap, followup.with_answer(question, answer))
        return True

    @staticmethod
    def _every_named(question) -> str:
        snap = question.snap
        names = [snap.place(option) if option.startswith("p") else (snap.row(option).alias or snap.row(option).variable)
                 for option in question.options]
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"

    def _use_feature(self, wanted, request: str):
        """Statistics, the mini-map or Search Vars, opened, closed or told about (see features)."""
        ws, voice = self.workspace, self.voice
        try:
            if wanted.how == features.ABOUT:
                said = features.ABOUT_TEXT[wanted.feature]
            elif wanted.feature == features.STATISTICS:
                said = voice.statistics_opened() if ws.open_statistics() else voice.statistics_nothing_drawn()
            elif wanted.feature == features.MINIMAP:
                on = wanted.how == features.OPEN
                said = voice.minimap(on, ws.minimap(on), len(ws.snapshot().plots), ws.is_streaming())
            else:
                ws.open_search_vars()
                said = voice.search_vars_opened()
        except Exception:
            logger.exception(f"Assistant could not {wanted.how} {wanted.feature}")
            said = voice.went_wrong()
        self.panel.add_assistant_message(said)
        self._record_turn(request, [f"{wanted.how} {wanted.feature}"], by="MINT")

    def _other_source(self, text: str, last_search) -> str:
        """Right after a search, "no, take sdnuda" or "use sdnuda instead": the data source to search again in."""
        if last_search is None:
            return ""
        names = {name.lower(): name for name in self.workspace.data_source_names()}
        said = [word.lower() for word in re.findall(r"[\w.-]+", text or "")]
        if any(word not in names and word not in SEARCH_AGAIN for word in said):
            return ""
        # "Instead of looking in codacuda", "not codacuda": the one to leave.
        left = {names[word] for i, word in enumerate(said)
                if word in names and NOT_THIS & set(said[max(0, i - 4):i])}
        named = {names[word] for word in said if word in names} - left - {last_search[1]}
        return next(iter(named)) if len(named) == 1 else ""

    def _record_turn(self, request: str, answer, snap=None, by: str = "model"):
        """Every request and its answer go in the record, not only the cards: a question answered wrong is what
        retraining needs most."""
        if not self.config.record:
            return
        self._turns += 1
        try:
            snap = snap if snap is not None else self.workspace.snapshot()
        except Exception as e:
            logger.debug(f"Assistant: no snapshot for the record: {e}")
            return
        record.write_turn(f"{self._session}-t{self._turns}", request, snap, list(answer), by)

    def _answer_card(self, card, text: str) -> bool:
        """"ok" or "no" to the card on screen, as its Apply or Dismiss; False when the text says something else."""
        if followup.agrees(text):
            self.on_card_action(card, APPLY, [])
        elif followup.declines(text):
            self.on_card_action(card, DISMISS, [])
        else:
            return False
        return True

    def _again_with(self, text: str, pending) -> bool:
        """A number alone ("12 s") after a processing card, on screen or just applied: that one with the number."""
        entry = self._cards[pending] if pending in self._cards else self._last_applied
        if entry is None or entry.get("snap") is None:
            return False
        written = entry["proposal"].commands
        try:
            cmds = commands.parse(written[0]) if len(written) == 1 else []
        except commands.CommandError:
            return False
        if len(cmds) != 1 or cmds[0].verb != "process":
            return False
        params = list((recipes.load().get(cmds[0].words[0]) or {}).get("params") or {})
        value = followup.value_in(text, params[0]) if len(params) == 1 else None
        if value is None:
            return False
        cmds[0].params[params[0]] = recipes.number(value)
        request = followup.with_answer(followup.OpenQuestion(entry.get("request") or "", entry["snap"]), text)
        self._plan_with_number(cmds, entry["snap"], request)
        return True

    def _answer_with_number(self, question, value: float, answer: str):
        question.command.params[question.param] = recipes.number(value)
        # The request with its answer, as the model would have read it (and as a recorded card keeps it).
        self._plan_with_number(question.commands, question.snap, followup.with_answer(question, answer))

    def _plan_with_number(self, cmds, snap, request: str):
        try:
            proposal = Planner(self.workspace, snap).plan(cmds)
        except MissingValue as e:
            # This number would not show either: say why and keep the question open for the next one.
            self._open_question = followup.OpenQuestion(request, snap, cmds, e.command, e.param, e.example)
            self.panel.add_assistant_message(str(e))
            return
        except ActionError as e:
            self.panel.add_assistant_message(str(e))
            return
        except Exception:
            logger.exception("Assistant could not plan with the user's number")
            self.panel.add_assistant_message(self.voice.could_not_work_out())
            return
        self._present(proposal, request, snap, answering=True)

    def _ask_model(self, text: str, answering: bool = False, named: bool = False):
        if self.engine.state != READY:
            self.panel.add_assistant_message(self.voice.still_busy())
            return
        try:
            snap = self._snapshot(self._last_action)
            shown = prompt.visible(snap)
            _, full = prompt.build(self.format, shown, text, self._few_shot)
            grammar = commands.build_grammar(*prompt.answer_ids(shown, text), recipes.load(),
                                             *prompt.file_ids(shown, text))
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
        self._record_turn(request, text.strip().splitlines(), snap)
        if timings.get("finish") == "length":
            # Its last line may be half a command that still parses, e.g. a window cut from 30 s to 3 s.
            self.panel.add_assistant_message(self.voice.too_long())
            return
        between = None
        try:
            cmds = check.review(snap, request, commands.parse(text))
            rewritten = None if answering else check.selection_for_it(snap, request, cmds)
            if rewritten:
                # "Derivative of this" with a row selected: no question, the model is asked about that row.
                self._ask_model(rewritten, answering=True, named=True)
                return
            planner = Planner(self.workspace, snap)
            proposal = planner.plan(cmds)
            rows, plots = prompt.answer_ids(snap, request)
            # Not after an answer: one question per request.
            unsure = None if answering else doubt.doubtful(timings.get("ids"), set(rows) | set(plots))
            if unsure and proposal.changes:
                # It hesitated between two rows or plots: asking costs the user less than a wrong change.
                logger.info(f"Assistant unsure between {unsure[0]} and {unsure[1]} in {text!r}")
                proposal = planner.plan([commands.Command("ask", text=f"Sure, which one: {unsure[0]} or {unsure[1]}?")])
                # "Both" is then what the model meant, for each of them.
                between = (cmds, list(unsure))
        except MissingValue as e:
            # The question stays open, so a reply with just the number fills in the request it belongs to.
            # After an answer it isn't asked in full again; a signal picked in reply to "which one?" still is.
            self._open_question = followup.OpenQuestion(request, snap, cmds, e.command, e.param, e.example)
            if answering and not named and e.example is None:
                self.panel.add_assistant_message(self.voice.still_missing_number())
            else:
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
        if between and self._open_question is not None:
            self._open_question.commands, self._open_question.options = between
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
            # "All three" to "which one: A, B or C?" takes the rows the question names.
            asked = " ".join(proposal.messages)
            self._open_question.options = sorted((row.id for row, _ in prompt.named(snap, asked, meanings=False)),
                                                 key=lambda row_id: int(row_id[1:]))
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
        if cmd.verb == "add":
            return self._file_time_step()
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

    def _file_time_step(self) -> list:
        """Once variables of the file are added, the time it gives, unless the plots already show it."""
        if self._file is None or not self._file.times:
            return []
        offer = _time_offer(self._file)
        written = _file_offers(self._file)[offer]
        try:
            span = Planner(self.workspace, self._snapshot()).period_ns(commands.parse(written)[0])
        except ActionError:
            return []
        return [] if self.workspace.time_range_ns() == span else [offer]

    def _show_search(self, words, request: str = "", source: str = ""):
        by_code = isinstance(words, _Codes)
        try:
            search = self.workspace.search_codes(words) if by_code else \
                self.workspace.search_variables(words, request, source or self._search_source)
        except ActionError as e:
            self.panel.add_assistant_message(str(e))
            return
        if not by_code:
            self._last_search = ([word for word in words if word.lower() != search.source.lower()], search.source)
            # A source the user chose stays the one searched until they choose the default again.
            self._search_source = "" if search.source == self.workspace.default_data_source()[0] else search.source
        if not search.found:
            self.panel.add_assistant_message(self.voice.nothing_found(search))
            return
        # A tag of the file that one variable has exactly is surely that one.
        exact = [[name for name, _ in search.found if name.split(":")[-1] == code] for code in words] if by_code else []
        ticked = {names[0] for names in exact if len(names) == 1}
        options = [(name, f"{name} — {description}" if description else name, name in ticked)
                   for name, description in search.found]
        self.panel.add_assistant_message(self.voice.found(search, check.wanted(request), ticked=bool(ticked)))
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
                steps = self._next_steps(entry)
                offers = _file_offers(self._file) if self._file else {}
                self._planned = {step: offers[step] for step in steps if step in offers}
                self._suggest(steps)
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
        self._last_applied = entry
        redraw_problem = self._run_redraw(proposal.changes)
        note = "" if redraw_problem else self._nothing_to_draw(proposal.changes)
        if not note:
            note = self.voice.done() + redraw_problem
        self.panel.set_card_state(card_id, enabled=[UNDO], note=note)
        if not redraw_problem and any(c.sets_range for c in proposal.changes):
            self._look_for_data()

    def _undo(self, card_id, entry):
        proposal = entry["proposal"]
        problems = proposal.undo()
        entry["applied"] = False
        self._last_action = ""
        if self._last_applied is entry:
            self._last_applied = None
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

    def _nothing_to_draw(self, changes) -> str:
        """What to say when a signal the changes compute came out with nothing to draw; "" otherwise.

        A signal still being read, or not drawn, says nothing: only what came out is told.
        """
        empty, failed = [], []
        try:
            for change in changes:
                uid = change.computes() if change.computes else None
                outcome = self.workspace.drawn_outcome(uid) if uid else None
                if outcome == EMPTY:
                    empty.append(self.workspace.name_of(uid))
                elif outcome == NOT_COMPUTED:
                    failed.append(self.workspace.name_of(uid))
        except Exception:
            # Applied already: a check that fails must not say it wasn't.
            logger.exception("Assistant: could not check what the change drew")
            return ""
        return self.voice.nothing_to_draw(empty, failed) if empty or failed else ""

    def _look_for_data(self):
        """After a new time range, what the archive says of the signals it left without data and, if nothing was drawn,
        the same span up to the newest sample. Only what MINT read or the archive answered is said."""
        try:
            window = self.workspace.time_range_ns()
            if window is None:
                return
            snap = self.workspace.snapshot()
            rows = [r for r in snap.rows + snap.unlisted if r.plot and not r.derived]
            outcomes = {r.uid: self.workspace.drawn_outcome(r.uid) for r in rows}
            read = [r for r in rows if outcomes[r.uid] is not None]  # still being read: nothing to tell yet
            empty = [r for r in read if outcomes[r.uid] != DRAWN]
            if not empty:
                return
            nothing_drawn = len(empty) == len(read)
            start_ns, end_ns = window
            answers, silent = {}, set()
            for row in empty[:MAX_LOOKUPS]:
                key = (row.data_source, row.variable)
                if key not in answers and row.data_source not in silent:
                    answers[key] = self.workspace.latest_sample(row.data_source, row.variable, end_ns)
                    if answers[key][0] == UNTOLD:  # a source that can't say, or doesn't answer, is not asked again
                        silent.add(row.data_source)

            def without_data(row):
                # What MINT read empty or the archive answered for; a sample inside the range means reading failed.
                kind, ns = answers.get((row.data_source, row.variable), (UNTOLD, None))
                return ns < start_ns if kind == FOUND else kind != UNTOLD or outcomes[row.uid] == EMPTY

            empty = [r for r in empty if without_data(r)]
            if not empty:
                return
            latest, none_before, unknown = {}, {}, {}
            for row in empty:
                kind, ns = answers.get((row.data_source, row.variable), (UNTOLD, None))
                if kind == FOUND:
                    latest.setdefault(_called(row), ns)
                elif kind == NONE_BEFORE:
                    none_before.setdefault(_called(row))
                elif kind == UNKNOWN_VARIABLE:
                    unknown.setdefault(row.variable, row.data_source)
            latest = sorted(((ns, name) for name, ns in latest.items()), reverse=True)
            span_s = (end_ns - start_ns) / 1e9
            minutes = max(1, round(span_s / 60))
            offer = self._range_up_to(latest[0][0], minutes, snap) if nothing_drawn and latest else None
            relative = self.workspace.range_dict().get("mode") == "RELATIVE_TIME"
            self.panel.add_assistant_message(self.voice.no_data(
                f"in the last {when.period(span_s)}" if relative else "in this time range",
                list(dict.fromkeys(_called(r) for r in empty)), len(empty) == len(read),
                [(name, when.at(_moment(ns), snap.now)) for ns, name in latest], list(none_before),
                list(unknown.items()), when.period(minutes * 60) if offer is not None else ""))
            if offer is not None:
                self._show_proposal(offer, spoken=True)
        except Exception:  # applied already: telling more must not fail it
            logger.exception("Assistant: could not look for the data of the new time range")

    def _range_up_to(self, last_ns: int, minutes: int, snap):
        """A proposal for that many minutes, ending just after the sample at ``last_ns``; or None."""
        end = (_moment(last_ns) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        start = end - timedelta(minutes=minutes)
        try:
            return Planner(self.workspace, snap).plan(commands.parse(
                f'range from "{start:%Y-%m-%d %H:%M}" to "{end:%Y-%m-%d %H:%M}"'))
        except (ActionError, commands.CommandError) as e:
            logger.info(f"Assistant: no range to offer up to {end}: {e}")
            return None

    def _redraw_only(self, changes):
        # Draw does nothing while MINT streams, so say so rather than claim a redraw.
        if self.workspace.is_streaming():
            self.panel.add_assistant_message(self.voice.streaming())
            return
        failed = self._run_redraw(changes)
        self.panel.add_assistant_message(failed.strip() if failed else self.voice.redrawn())

    def _add_variables(self, source: str, names, together: bool) -> Proposal:
        context = ApplyContext(self.workspace)
        return Proposal(title="Add variables", context=context,
                        changes=added_rows(self.workspace, context, source, names, together))
