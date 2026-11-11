"""The assistant inside MINT: installation, the request-to-card flow and the model process."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from PySide6.QtCore import QEventLoop, QObject, Signal
from PySide6.QtWidgets import QApplication, QPushButton, QToolBar

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.assistant import commands
from mint.assistant import controller as ctl
from mint.assistant import worker
from mint.assistant.config import AssistantConfig
from mint.assistant.engine import FAILED, READY, ModelEngine
from mint.assistant.prompt import ChatFormat
from mint.assistant.workspace import VariableSearch
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp
from mint.tests.test_30_assistant_actions import build_window

try:
    from iplotWidgets.chatPanel import ChatPanel
except ImportError:  # an iplotWidgets without the chat panel
    ChatPanel = None


def wait_until(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.01)
    return predicate()


class StubEngine(QObject):
    stateChanged = Signal(str)
    step = Signal(str)
    loaded = Signal(dict)
    primed = Signal(dict)
    completed = Signal(int, str, dict)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.state = READY
        self.answer = ""
        self.ids = []  # how sure the model was of each id it wrote (see doubt.py)
        self.prompts = []
        self.warms = []

    def complete(self, prompt, grammar, max_tokens=160):
        # Answers at once, before returning: the controller must cope with that too.
        self.prompts.append((prompt, grammar))
        self.completed.emit(len(self.prompts), self.answer, {"total_s": 0.4, "ids": self.ids})
        return len(self.prompts)

    def warm(self, prompt):
        self.warms.append(prompt)

    def prime(self, prompt, cache_dir=None):
        pass

    def cancel(self):
        pass

    def shutdown(self):
        pass


@unittest.skipIf(ChatPanel is None, "iplotWidgets has no chat panel")
class AssistantFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self.win = build_window()
        self.engine = StubEngine()
        self.ctl = ctl.AssistantController(self.win, AssistantConfig(enabled=True), ChatPanel, engine=self.engine)
        self.ctl.format = ChatFormat("chatml")
        self.draws = []
        self.ctl.workspace.draw = lambda: self.draws.append(1)
        self.said = []
        show = self.ctl.panel.add_assistant_message
        self.ctl.panel.add_assistant_message = lambda text: (self.said.append(text), show(text))[1]

    def note(self, card):
        return self.ctl.panel._cards[card].note.text()

    def tearDown(self):
        self.ctl.panel.deleteLater()
        self.win.close()

    def ask(self, request, answer):
        self.engine.answer = answer
        before = len(self.ctl._cards)
        self.ctl.panel.messageSubmitted.emit(request)
        self.assertTrue(wait_until(lambda: self.ctl._inflight is None))
        return [card for card in self.ctl._cards if card not in range(before)][-1:] if len(self.ctl._cards) > before \
            else []

    def rows(self):
        return list(self.ctl.workspace.table()["Variable"])

    def test_starting_up_tells_each_step_and_keeps_the_input_closed(self):
        panel = self.ctl.panel
        self.ctl._primed = False
        self.engine.state = "loading"
        self.engine.stateChanged.emit("loading")
        self.assertEqual(panel._busy_label.text(), "Waking up the assistant…")
        self.assertFalse(panel.input.isEnabled())
        self.assertEqual(panel.input.toolTip(), "Getting everything ready…")
        self.assertEqual(panel.input.placeholderText(), "Getting everything ready…")
        self.assertTrue(panel.stop_button.isHidden(), "nothing to stop while it starts")
        for step, text in (("checking", "Checking the model file…"), ("loading", "Loading the model…")):
            self.engine.step.emit(step)
            self.assertEqual(panel._busy_label.text(), text)
        self.engine.state = READY
        self.engine.loaded.emit({})
        self.assertEqual(panel._busy_label.text(), "Learning what MINT can do…")
        self.assertFalse(panel.input.isEnabled(), "still closed until the fixed prompt is ready")
        self.engine.primed.emit({})
        self.assertTrue(panel.input.isEnabled())
        self.assertFalse(panel._busy)
        self.assertEqual((panel.input.toolTip(), panel.input.placeholderText()), ("", ctl.PLACEHOLDER))

    def test_request_card_apply_and_undo(self):
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        prompt, grammar = self.engine.prompts[-1]
        self.assertIn("Request: smooth pirani 30s\nNames in the request: r1 = pirani", prompt)
        self.assertIn('row ::= "r1" | "r2" | "r3" | "r4"', grammar)
        self.assertEqual(len(cards), 1)
        self.assertIn("Nothing happens until you click Apply", self.said[-1], "said before the first card")
        self.assertEqual(len(self.rows()), 4, "nothing changes before Apply")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(self.rows()[1], "MAG-MCTB-F1:VAR1")
        self.assertEqual(len(self.rows()), 5)
        self.assertEqual(self.draws, [1])
        self.assertEqual(self.ctl._last_action, "process r1 moving_average window=30s", "as the model writes it")
        self.assertEqual(self.note(cards[0]), "Done.")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.UNDO, [])
        self.assertEqual(len(self.rows()), 4)
        self.assertEqual(self.draws, [1, 1])
        self.assertEqual(self.note(cards[0]), "Undone. It's back as it was.")
        # Later cards get a short acknowledgement, and turning one down is fine.
        cards = self.ask("remove row 2", "remove r2")
        self.assertNotIn("Apply", self.said[-1])
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.DISMISS, [])
        self.assertTrue(self.note(cards[0]).startswith("No problem"))

    def test_messages_and_refusals_create_no_card(self):
        for answer in ('say "Hello!"', 'ask "Which one?"', "not a command", "process r9 abs"):
            with self.subTest(answer=answer):
                count = self.ctl.panel.message_count()
                self.assertEqual(self.ask("hi", answer), [])
                self.assertEqual(self.ctl.panel.message_count(), count + 2)


    def test_a_number_answer_is_filled_in_without_the_model(self):
        self.assertEqual(self.ask("remove row 2 and low-pass the pirani", "remove r2\nprocess r1 lowpass"), [])
        self.assertTrue(self.said[-1].endswith("?"))
        asked = len(self.engine.prompts)
        cards = self.ask("2 Hz", "draw")
        self.assertEqual(len(self.engine.prompts), asked, "no model call for a plain number")
        lines = self.ctl._cards[cards[0]]["proposal"].lines
        self.assertEqual(len(lines), 2, "nothing asked for is lost")
        self.assertIn("slower than 2 Hz", lines[1])
        # The answer closed the question: the next "10 s" is a new request for the model.
        self.ask("10 s", 'say "Okay."')
        self.assertEqual(len(self.engine.prompts), asked + 1)

    def test_durations_in_any_unit_answer_a_window(self):
        self.ctl.workspace.range_summary = lambda: ("", None, False)  # no time range to guess a window from
        self.ctl.workspace.plot_x_span_seconds = lambda plot: None
        for answer, words in (("15 min", "15 min"), ("over 2 hours", "2 h"), ("250ms", "250 ms"), ("30", "30 s")):
            with self.subTest(answer=answer):
                self.ask("smooth the pirani", "process r1 moving_average")
                cards = self.ask(answer, "draw")
                self.assertIn(f"a {words} average", self.ctl._cards[cards[0]]["proposal"].lines[0])

    def test_a_signal_named_in_reply_to_which_one_takes_the_place_of_it(self):
        self.ask("smooth that", 'ask "Which one: the pirani or r2?"')
        self.assertEqual(self.said[-1], "Which one: the pirani or MAG-MCTB-F1:VAR2?")
        cards = self.ask("the pirani", "process r1 moving_average window=10s")
        self.assertIn("Request: smooth the pirani\nNames in the request: r1 = pirani", self.engine.prompts[-1][0])
        self.assertEqual(len(cards), 1)

    def test_other_short_answers_go_to_the_model_with_the_request_they_answer(self):
        self.ask("smooth the pirani or VAR2", 'ask "Which one?"')
        self.ask("the first one", "process r1 moving_average window=10s")
        self.assertIn("Request: smooth the pirani or VAR2. the first one\n", self.engine.prompts[-1][0])

    def test_still_unclear_after_an_answer_ends_with_a_way_forward_not_another_question(self):
        self.ask("smooth that", 'ask "Which one?"')
        self.ask("that one", 'ask "Which one?"')
        self.assertIn("Select the signals in the table", self.said[-1])
        self.assertIsNone(self.ctl._open_question)
        self.ask("hello", 'say "Hi!"')
        self.assertIn("Request: hello<|im_end|>", self.engine.prompts[-1][0], "a fresh request, not glued to the old one")

    def test_a_row_the_model_hesitated_on_becomes_a_question(self):
        self.engine.ids = [{"id": "r1", "p": 0.45, "alts": {"r2": 0.4}}]
        self.assertEqual(self.ask("smooth that one", "process r1 moving_average window=10s"), [], "no card")
        self.assertEqual(self.said[-1], "Sure, which one: pirani or MAG-MCTB-F1:VAR2?")
        self.assertIsNotNone(self.ctl._open_question)
        # The answer goes back with the request, and is not doubted again: one question per request.
        cards = self.ask("the pirani", "process r1 moving_average window=10s")
        self.assertIn("Request: smooth the pirani\nNames in the request: r1 = pirani", self.engine.prompts[-1][0])
        self.assertEqual(len(cards), 1)
        self.engine.ids = [{"id": "r1", "p": 0.9, "alts": {"r2": 0.05}}]
        self.assertEqual(len(self.ask("smooth the pirani", "process r1 moving_average window=10s")), 1, "sure: a card")

    def test_moving_the_signal_others_should_join_asks_which_one_goes(self):
        self.assertEqual(self.ask("put the current together with the pirani", "move r1 to new"), [])
        self.assertEqual(self.said[-1], "Sure, which signal should go with the pirani?")
        cards = self.ask("VAR3", "move r4 to p1")
        self.assertIn("Request: put the current together with the pirani. VAR3\n", self.engine.prompts[-1][0])
        self.assertEqual(len(cards), 1, "the answer is the signal that moves, not one more next to the pirani")

    def test_a_signal_picked_in_reply_still_gets_its_number_asked(self):
        self.ask("low-pass it", 'ask "Which one?"')
        self.ask("the pirani", "process r1 lowpass")
        self.assertTrue(self.said[-1].endswith("?"), self.said[-1])
        cards = self.ask("2 Hz", "draw")
        self.assertIn("slower than 2 Hz", self.ctl._cards[cards[0]]["proposal"].lines[0])

    def test_after_apply_the_change_reads_back_for_the_next_request(self):
        answer = 'range from "2026-11-03 08:00" to "2026-11-04 20:00"'
        cards = self.ask("show 3 to 4 November", answer)
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(self.note(cards[0]), "Done.", "applied, and said so")
        self.assertEqual(str(commands.parse(self.ctl._last_action)[0]), answer)

    def test_a_redraw_alone_shows_no_card(self):
        from mint.assistant.actions import Planner
        snap = self.ctl.workspace.snapshot()
        proposal = Planner(self.ctl.workspace, snap).plan(commands.parse("draw"))
        self.ctl._present(proposal, "redraw", snap, answering=False)
        self.assertEqual(self.ctl._cards, {})

    def test_a_code_that_is_in_no_row_offers_a_search_without_the_model(self):
        searched = []
        self.ctl.workspace.search_variables = lambda words, request="": (
            searched.append(words), VariableSearch("csv", [], 0, list(words)))[1]
        self.ask("need TF07 coil current", 'say "I can\'t compute statistics yet."')
        self.assertEqual(self.ctl.panel._suggestions, ["Find TF07"])
        calls = len(self.engine.prompts)
        self.ask("Find TF07", 'say "no model here"')
        self.assertEqual(searched, [["TF07"]])
        self.assertEqual(len(self.engine.prompts), calls)
        self.assertTrue(self.said[-1].startswith("I couldn't find anything called TF07"), self.said[-1])
        self.ask("Find TF07", 'say "Okay."')
        self.assertEqual(len(self.engine.prompts), calls + 1, "offered once: typed again, it is a request")

    def test_a_search_says_where_it_looked_and_how_many_to_tick(self):
        names = [(f"EC-GYA-{i:02d}:PSU-YSTA", "") for i in range(40)]
        self.ctl.workspace.search_variables = lambda words, request="": VariableSearch("sdnuda", names, 312, [], "EC")
        cards = self.ask("I need a workspace with 2 signals from EC in sdnuda, whatever you want", "find EC sdnuda")
        self.assertEqual(self.said[-1], "Here are the variables in sdnuda that start with EC. Tick the 2 you want and "
                                        "I'll add them. There are 312: these are the first 40, and Search Vars shows "
                                        "them all.")
        card = self.ctl.panel._cards[cards[0]]
        self.assertEqual(len(card.options), 40)
        self.assertEqual(self.ctl._cards[cards[0]]["source"], "sdnuda", "added from the source it found them in")

    def test_what_was_asked_and_kept_is_recorded_to_learn_from(self):
        import argparse
        from mint.assistant import record
        from mint.tools.assistant_train import cmd_feedback
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"IPLOT_DUMP_PATH": folder}):
            self.ctl.config.record = True
            kept = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
            self.ctl.panel.cardActionTriggered.emit(kept[0], ctl.APPLY, [])
            undone = self.ask("abs of the pirani", "process r1 abs")
            self.ctl.panel.cardActionTriggered.emit(undone[0], ctl.APPLY, [])
            self.ctl.panel.cardActionTriggered.emit(undone[0], ctl.UNDO, [])
            dropped = self.ask("remove row 2", "remove r2")
            self.ctl.panel.cardActionTriggered.emit(dropped[0], ctl.DISMISS, [])
            self.ask("low-pass the pirani", "process r1 lowpass")
            filled = self.ask("2 Hz", "draw")
            self.ctl.panel.cardActionTriggered.emit(filled[0], ctl.APPLY, [])
            with open(record.path(), encoding="utf-8") as f:
                lines = [json.loads(line) for line in f]
            self.assertEqual([line["outcome"] for line in lines], ["applied", "applied", "undone", "dismissed", "applied"])
            self.assertEqual(len(lines[0]["workspace"]["rows"]), 4, "the workspace the model saw")
            out = os.path.join(folder, "feedback.jsonl")
            cmd_feedback(argparse.Namespace(records=[record.path()], out=out))
            with open(out, encoding="utf-8") as f:
                cases = [json.loads(line) for line in f]
            # Only what stayed applied, with the number the user gave in the request it fills.
            self.assertEqual([(c["request"], c["answer"]) for c in cases],
                             [("smooth pirani 30s", "process r1 moving_average window=30s"),
                              ("low-pass the pirani. 2 Hz", "process r1 lowpass hz=2")])
            self.ctl.config.record = False
            self.ask("remove row 2", "remove r2")
            self.ctl.panel.cardActionTriggered.emit(self.ctl.panel.card_count() - 1 if hasattr(
                self.ctl.panel, "card_count") else max(self.ctl._cards), ctl.DISMISS, [])
            with open(record.path(), encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 5, "off: nothing more is kept")

    def test_undo_in_words_undoes_the_last_card_without_the_model(self):
        self.ask("undo", 'say "no model here"')
        self.assertEqual(self.said[-1], "There's nothing to undo yet.")
        self.assertEqual(self.engine.prompts, [])
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(len(self.rows()), 5)
        calls = len(self.engine.prompts)
        self.ask("deshaz eso", 'say "no model here"')
        self.assertEqual(len(self.rows()), 4)
        self.assertTrue(self.said[-1].startswith("Undone"), self.said[-1])
        self.assertEqual(len(self.engine.prompts), calls)
        self.assertEqual(self.note(cards[0]), "Undone. It's back as it was.")

    def test_enter_applies_the_card_on_screen_and_only_that_one(self):
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.assertIn("Enter", self.ctl.panel.input.placeholderText())
        self.ctl.panel.emptySubmitted.emit()
        self.assertEqual(len(self.rows()), 5, "applied")
        self.assertEqual(self.note(cards[0]), "Done.")
        self.assertNotIn("Enter", self.ctl.panel.input.placeholderText())
        self.ctl.panel.emptySubmitted.emit()
        self.assertEqual(len(self.rows()), 5, "nothing else to apply")
        self.ask("remove row 2", "remove r2")
        self.ask("hello", 'say "Hi!"')
        self.ctl.panel.emptySubmitted.emit()
        self.assertEqual(len(self.rows()), 5, "a card from before the last message is not applied by Enter")

    def test_after_apply_a_next_step_is_offered(self):
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        chips = self.ctl.panel._suggestions
        self.assertEqual(len(chips), 1, chips)
        self.assertTrue(chips[0].startswith("The same for "), chips)
        self.assertTrue(self.ctl.panel._chips.isVisibleTo(self.ctl.panel), "shown after the conversation started")
        self.ctl.panel.messageSubmitted.emit(chips[0])
        self.assertTrue(wait_until(lambda: self.ctl._inflight is None))
        self.assertIn("Last applied: process r1 moving_average window=30s", self.engine.prompts[-1][0])

    def test_suggestions_fit_the_workspace(self):
        from mint.assistant.snapshot import PlotInfo, RowInfo, Snapshot
        snap = Snapshot(rows=[RowInfo(id="r1", index=0, variable="VAC:MP0081-XI", alias="pirani", stack="1.1",
                                      plot="p1"),
                              RowInfo(id="r2", index=1, variable="CRYO:MT0001-XI", stack="2.1", plot="p2")],
                        plots=[PlotInfo(id="p1", row=1, col=1), PlotInfo(id="p2", row=2, col=1)])
        self.assertEqual(ctl.suggestions(snap), ["Log scale on the top plot", "Smooth pirani over 10 s",
                                                 "pirani minus MT0001-XI", "Show the last 6 hours"])
        snap.plots[0].log_scale, snap.selected = True, ["r2"]
        self.assertEqual(ctl.suggestions(snap)[0], "Smooth the selected signals over 10 s")
        self.ctl.set_visible(True)
        self.assertIn("Smooth pirani over 10 s", [b.text() for b in self.ctl.panel.findChildren(QPushButton)])

    def test_a_number_still_missing_after_an_answer_is_not_asked_again(self):
        self.ask("low-pass the pirani", "process r1 lowpass")
        self.ask("quite slow", "process r1 lowpass")
        self.assertIn("I still need a number", self.said[-1])
        self.assertIsNone(self.ctl._open_question)

    def test_a_long_reply_is_a_new_request(self):
        self.ask("smooth that", 'ask "Which one?"')
        self.ask("actually show me the last six hours of data please", "range last 6 hours")
        self.assertIn("Request: actually show me the last six hours of data please<|im_end|>", self.engine.prompts[-1][0])

    def test_redraw_alone_says_what_really_happened(self):
        self.ask("redraw", "draw")
        self.assertEqual(self.said[-1], "I've redrawn the plots.")
        self.ctl.workspace.is_streaming = lambda: True
        self.ask("redraw", "draw")
        self.assertIn("Click Stop first", self.said[-1])
        self.assertEqual(self.draws, [1])

    def test_a_model_failure_with_no_request_waiting_stays_out_of_the_chat(self):
        count = self.ctl.panel.message_count()
        self.engine.failed.emit(-1, "Traceback: something technical")
        self.assertEqual(self.ctl.panel.message_count(), count)
        self.assertTrue(all("Traceback" not in s for s in self.said))

    def test_streaming_blocks_changes_that_need_a_draw(self):
        cards = self.ask("remove row 2", "remove r2")
        self.ctl.workspace.is_streaming = lambda: True
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(len(self.rows()), 4)
        self.assertEqual(self.draws, [])

    def test_draw_alone_needs_no_card(self):
        self.assertEqual(self.ask("redraw", "draw"), [])
        self.assertEqual(self.draws, [1])

    def test_the_workspace_is_evaluated_while_the_user_types(self):
        self.ctl.panel.input.setPlainText("sm")
        self.ctl.panel.input.setPlainText("smo")
        self.assertEqual(len(self.engine.warms), 1, "once per workspace state, not per key")
        self.ctl.workspace.insert_row_at(0, {"DS": "csv", "Variable": "NEW", "Stack": "9.1"})
        self.assertEqual(len(self.engine.warms), 1, "editing the table alone costs nothing")
        self.ctl.panel.input.setPlainText("smoo")
        self.assertEqual(len(self.engine.warms), 2)
        self.assertIn("r1 in p4: NEW", self.engine.warms[-1])
        self.assertTrue(self.engine.warms[-1].endswith("Selected: none\n\nRequest:"))


@unittest.skipIf(ChatPanel is None, "iplotWidgets has no chat panel")
class AssistantInstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    @staticmethod
    def menu_texts(win):
        return [a.text() for m in win.menuBar().actions() if m.menu() for a in m.menu().actions()]

    def test_disabled_by_default_changes_nothing(self):
        with mock.patch.dict(os.environ, {"MINT_ASSISTANT": ""}):
            win = build_window()
        try:
            self.assertIsNone(win.assistant)
            self.assertNotIn("&AI Assistant", self.menu_texts(win))
            self.assertEqual(win._centralWidget.count(), 2)
        finally:
            win.close()

    def test_enabled_adds_button_menu_and_panel(self):
        env = {"MINT_ASSISTANT": "1\n", "MINT_ASSISTANT_MODEL": os.path.join(tempfile.gettempdir(), "missing.gguf")}
        with mock.patch.dict(os.environ, env):
            win = build_window()
        try:
            self.assertIsNotNone(win.assistant)
            self.assertIn("&AI Assistant", self.menu_texts(win))
            toolbar = win.sigCfgWidget.tool_bar().findChild(QToolBar)
            widgets = [toolbar.widgetForAction(a) for a in toolbar.actions()]
            search = widgets.index(win.sigCfgWidget.tool_bar().searchVarsBtn)
            self.assertIsInstance(widgets[search + 1], QPushButton)
            self.assertEqual(widgets[search + 1].text(), "AI Assistant")
            self.assertEqual(win._centralWidget.count(), 3)
            panel = win.assistant.panel
            self.assertFalse(panel.isVisible())
            win.assistant.toggle_action.setChecked(True)
            win.show()
            self.assertTrue(wait_until(panel.isVisible, 2))
            self.assertTrue(widgets[search + 1].isChecked())
            # No model runtime or no model file: the panel says why instead of failing.
            self.assertIsNone(win.assistant.engine)
            self.assertFalse(panel.input.isEnabled())
            # Detaching and reattaching the canvas keeps the panel on the right.
            win.toolBar.detachAction.trigger()
            win.toolBar.detachAction.trigger()
            self.assertIs(win._centralWidget.widget(win._centralWidget.count() - 1), panel)
            # In a window of its own, as Detach does with the canvas, and it stays there when the canvas comes back.
            floating = win.assistant.floating
            panel.pop_button.click()
            self.assertTrue(floating.isVisible() and panel.isVisible() and panel.window() is floating)
            self.assertEqual(win._centralWidget.count(), 2)
            win.toolBar.detachAction.trigger()
            win.toolBar.detachAction.trigger()
            self.assertIs(panel.window(), floating)
            panel.close_button.click()
            self.assertFalse(win.assistant.toggle_action.isChecked() or floating.isVisible(), "closed with its window")
            win.assistant.toggle_action.setChecked(True)
            self.assertTrue(floating.isVisible() and panel.isVisible(), "it opens again where it was")
            panel.pop_button.click()
            self.assertIs(win._centralWidget.widget(win._centralWidget.count() - 1), panel)
            self.assertTrue(panel.isVisible() and not floating.isVisible())
        finally:
            win.close()


class NetworkIsolationTest(unittest.TestCase):
    def test_without_user_namespaces_the_model_process_starts_again_without_them(self):
        from mint.assistant import engine
        ensure_qapp()
        model = ModelEngine("model.gguf", 1)
        started = []
        model.start = lambda: started.append(engine.network_isolation())
        model.isolated, model._state = True, engine.LOADING
        model._stderr_tail.append("unshare: unshare failed: Operation not permitted")
        failed = []
        model.failed.connect(lambda *args: failed.append(args))
        with mock.patch.object(engine, "_isolation_works", None), mock.patch.object(engine.sys, "platform", "linux"), \
                mock.patch.object(engine.shutil, "which", return_value="/usr/bin/unshare"):
            self.assertEqual(engine.network_isolation()[0], "/usr/bin/unshare", "tried first, with no probe")
            model._on_finished(1, None)
            self.assertEqual((started, failed), ([[]], []), "started again without it, and nothing failed")


class WorkerProcessTest(unittest.TestCase):
    def start(self):
        return subprocess.Popen([sys.executable, worker.__file__], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)

    def test_reports_errors_and_exits_when_stdin_closes(self):
        proc = self.start()
        try:
            proc.stdin.write(json.dumps({"op": "load", "model": "missing.gguf", "allowed_sha256": []}) + "\n")
            proc.stdin.write(json.dumps({"op": "complete", "id": 3, "prompt": "x"}) + "\n")
            proc.stdin.flush()
            first, second = json.loads(proc.stdout.readline()), json.loads(proc.stdout.readline())
            self.assertEqual(first["ev"], "error")
            self.assertIn("not found", first["message"])
            self.assertEqual((second["ev"], second["id"]), ("error", 3))
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=10), 0)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_unknown_weights_are_refused_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "model.gguf")
            with open(path, "wb") as f:
                f.write(b"GGUF not really")
            cache = os.path.join(tmp, "verified.json")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                with self.assertRaises(ValueError) as ctx:
                    worker.verify_model(fd, path, set(), cache)
                sha = worker.sha256_of(fd)
                self.assertIn(sha, str(ctx.exception))
                self.assertEqual(worker.verify_model(fd, path, {sha}, cache), sha)
                with mock.patch.object(worker, "sha256_of", side_effect=AssertionError("hashed again")):
                    self.assertEqual(worker.verify_model(fd, path, {sha}, cache), sha)
                key = worker.file_key(fd, path)
                self.assertTrue(worker.unchanged(fd, path, key))
                try:
                    os.replace(path, path + ".old")
                except PermissionError:  # Windows: a file open here cannot be renamed, so neither swapped
                    return
                with open(path, "wb") as f:
                    f.write(b"GGUF swapped")
                self.assertFalse(worker.unchanged(fd, path, key), "the path now leads to another file")
            finally:
                os.close(fd)

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX permissions")
    def test_a_model_file_other_users_can_change_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "model.gguf")
            with open(path, "wb") as f:
                f.write(b"GGUF not really")
            os.chmod(path, 0o666)
            with self.assertRaises(ValueError) as ctx:
                worker.Worker().load({"model": path, "allowed_sha256": []})
            self.assertIn("other users", str(ctx.exception))

    def test_engine_reports_a_missing_model(self):
        ensure_qapp()
        engine = ModelEngine(os.path.join(tempfile.gettempdir(), "missing.gguf"), 1)
        messages = []
        engine.failed.connect(lambda _id, message: messages.append(message))
        engine.start()
        try:
            self.assertTrue(wait_until(lambda: messages, timeout=20))
            self.assertIn("not found", messages[0])
            self.assertEqual(engine.state, FAILED)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
