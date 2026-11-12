"""The assistant inside MINT: installation, the request-to-card flow and the model process."""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from PySide6.QtCore import QEventLoop, QObject, Signal
from PySide6.QtWidgets import QApplication, QPushButton, QToolBar

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.assistant import commands
from mint.assistant import controller as ctl
from mint.assistant import voice
from mint.assistant import worker
from mint.assistant.config import AssistantConfig
from mint.assistant.engine import FAILED, READY, ModelEngine
from mint.assistant.prompt import ChatFormat
from mint.assistant.workspace import VariableSearch
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
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
        self.assertEqual(panel.title(), "AI Assistant", "as the button that opens it")
        # Shown as progress in the empty conversation, not as a message.
        self.assertEqual(panel._progress_label.text(), "Waking up the assistant…")
        self.assertFalse(panel._busy)
        self.assertFalse(panel.input.isEnabled())
        self.assertEqual(panel.input.toolTip(), "Getting everything ready…")
        self.assertEqual(panel.input.placeholderText(), "Getting everything ready…")
        self.assertTrue(panel.stop_button.isHidden(), "nothing to stop while it starts")
        # Started again after it stopped: a message waits under the progress, with no Stop that would stop nothing.
        panel.messageSubmitted.emit("smooth pirani 30s")
        self.assertEqual(self.ctl._queued[0], "smooth pirani 30s")
        self.assertTrue(panel._preparing and not panel._busy)
        for step, text in (("checking", "Checking the model file…"), ("loading", "Loading the model…")):
            self.engine.step.emit(step)
            self.assertEqual(panel._progress_label.text(), text)
        self.engine.state = READY
        self.engine.loaded.emit({})
        self.assertEqual(panel._progress_label.text(), "Learning what MINT can do…")
        self.assertFalse(panel.input.isEnabled(), "still closed until the fixed prompt is ready")
        self.engine.primed.emit({})
        self.assertTrue(panel.input.isEnabled())
        self.assertFalse(panel._preparing)
        self.assertEqual((panel.input.toolTip(), panel.input.placeholderText()), ("", ctl.PLACEHOLDER))

    def _attach(self, name="signals.csv", text=None):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text is not None else
                    "Signal;Description\nMAG-MCTB-F1:VAR2;coil current\nCRYO-CP-01:MT0001-XI;inlet temperature\n"
                    "Test from 2024-10-29 07:05 to 2024-10-30 19:00\n")
        said = len(self.said)
        self.ctl.panel.fileAttached.emit(path)
        self.assertTrue(wait_until(lambda: len(self.said) > said), "read off the GUI thread, then told")
        return path

    def test_files_can_be_attached_only_with_a_model_trained_on_them(self):
        panel = self.ctl.panel
        trained = {"mint.assistant.format": "qwen3-nothink", "mint.assistant.few_shot": "false"}
        self.engine.loaded.emit({"declared": trained})
        self.assertFalse(panel.attach_button.isVisibleTo(panel))
        self.engine.loaded.emit({"declared": dict(trained, **{"mint.assistant.files": "true"})})
        self.assertTrue(panel.attach_button.isVisibleTo(panel))

    def test_an_attached_file_is_read_and_its_offers_need_no_model(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._attach()
        panel = self.ctl.panel
        self.assertEqual(self.said[-1], "I read signals.csv: 2 signal names and 2 dates. What should I do with them?")
        self.assertTrue(panel._attachment.isVisibleTo(panel))
        self.assertEqual(panel._suggestions, ["Add them, one plot each", "Add them to one plot",
                                              "Show the time in the file"])
        calls = len(self.engine.prompts)
        cards = self.ask("Add them, one plot each", 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls, "MINT knows what this one is")
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].lines,
                         ["Add MAG-MCTB-F1:VAR2", "Add CRYO-CP-01:MT0001-XI", "Each in a new plot"])
        rows = len(self.rows())
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(self.rows()[rows:], ["MAG-MCTB-F1:VAR2", "CRYO-CP-01:MT0001-XI"])
        self.assertEqual(panel._suggestions, ["Show the time in the file"], "the time of the file comes next")
        cards = self.ask("Show the time in the file", 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls)
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].lines,
                         ["Time range: 29 Oct 2024 07:05 → 30 Oct 2024 19:00 UTC"])
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        cards = self.ask("add MT0001 from the file too", "add v2")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(panel._suggestions, [], "the plots show the time of the file already")

    def test_a_file_is_read_into_the_prompt_before_the_next_request(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._attach()
        self.assertIn('File "signals.csv":\nv1 MAG-MCTB-F1:VAR2', self.engine.warms[-1],
                      "while the user reads what was found, not after the next request is sent")

    def test_tags_without_their_system_are_looked_up_without_the_model(self):
        class Source:
            def get_var_list(self, pattern):
                names = ["CRYO-CP3:MT0012-XI", "CRYO-CP4:MT0012-XI", "CRYO-CH-MM-CRST:MLT1000-AA-IN",
                         "CRYO-CH-MM-CRST:MLT1000-AA-IN-ALEN"]
                return [n for n in names if re.fullmatch(pattern, n)]

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ctl.workspace.default_data_source = lambda: ("codacuda", Source())
        self._attach("names.csv", "MAG-MCTB-F1:VAR2;coil current, was PT-1101\n")
        self.assertEqual(self.ctl.panel._suggestions, ["Add them, one plot each"], "full names: no tag to look up")
        self._attach("tags.csv", "Tag;Description\nMLT1000-AA-IN;cold box level\nMT0012;inlet temperature\n")
        self.assertEqual(self.said[-1], "I read tags.csv: it gives MLT1000-AA-IN and MT0012 without the system part of "
                                        "the name. Shall I look for them in codacuda?")
        panel = self.ctl.panel
        self.assertEqual(panel._suggestions, ["Find them in codacuda"])
        calls = len(self.engine.prompts)
        cards = self.ask("Find them in codacuda", 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls, "MINT looks them up itself")
        boxes = {box.property("optionKey"): box.isChecked() for box in panel._cards[cards[0]].options}
        self.assertEqual(boxes, {"CRYO-CH-MM-CRST:MLT1000-AA-IN": True, "CRYO-CP3:MT0012-XI": False,
                                 "CRYO-CP4:MT0012-XI": False}, "only a tag one variable has exactly is ticked")
        self.assertIn("Those named exactly as in the file are ticked.", self.said[-1])
        rows = len(self.rows())
        panel.cardActionTriggered.emit(cards[0], ctl.ADD_EACH, ["CRYO-CH-MM-CRST:MLT1000-AA-IN"])
        self.assertEqual(self.rows()[rows:], ["CRYO-CH-MM-CRST:MLT1000-AA-IN"])

    def test_a_list_pasted_in_a_message_is_taken_as_a_file(self):
        trained = {"mint.assistant.format": "qwen3-nothink", "mint.assistant.few_shot": "false"}
        listing = ("CRYO-CH-MM-CRST:MLT1000-AA-IN\tcold box level\nCRYO-CH-CB3-HESC:VOL3600-XI\thelium volume\n"
                   "Checked on 29 Oct 2024 07:05")
        self.engine.loaded.emit({"declared": trained})
        self.ask(listing, 'say "Which of them?"')
        self.assertIsNone(self.ctl._file, "not for a model that wasn't trained on files")
        self.engine.loaded.emit({"declared": dict(trained, **{"mint.assistant.files": "true"})})
        calls = len(self.engine.prompts)
        self.ask(listing, 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls, "the list alone: MINT says what it read")
        self.assertEqual(self.said[-1],
                         "I read the text you pasted: 2 signal names and 1 date. What should I do with them?")
        panel = self.ctl.panel
        self.assertTrue(panel._attachment.isVisibleTo(panel))
        self.assertEqual(panel._suggestions, ["Add them, one plot each", "Add them to one plot",
                                              "Show the time in the text"])
        cards = self.ask("put these two together\n" + listing, "add all together")
        prompt_text, grammar = self.engine.prompts[-1]
        self.assertIn('File "the text you pasted":\nv1 CRYO-CH-MM-CRST:MLT1000-AA-IN (cold box level)', prompt_text)
        self.assertIn("put these two together", prompt_text)
        self.assertEqual(prompt_text.count("CRYO-CH-CB3-HESC:VOL3600-XI"), 1, "the list is the file, not the request")
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].lines,
                         ["Add CRYO-CH-MM-CRST:MLT1000-AA-IN", "Add CRYO-CH-CB3-HESC:VOL3600-XI", "All in one new plot"])
        from mint.assistant import files
        self.ctl._reading = "report.csv"
        self.ask(listing, 'say "no model here"')
        self.ctl._on_file_read("report.csv", files.Found([("SYS-A:X1", "")]))
        self.assertEqual(self.ctl._file.name, "the text you pasted", "a file read before the paste is not taken")

    def test_the_model_reads_the_file_and_may_answer_from_it_until_it_is_left_out(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._attach()
        cards = self.ask("add MT0001 from the file", "add v2")
        prompt_text, grammar = self.engine.prompts[-1]
        self.assertIn('File "signals.csv":\nv1 MAG-MCTB-F1:VAR2 (coil current)\nv2 CRYO-CP-01:MT0001-XI', prompt_text)
        self.assertIn("Times: t1 2024-10-29 07:05, t2 2024-10-30 19:00", prompt_text)
        self.assertIn('fvar ::= "v1" | "v2"', grammar)
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].lines, ["Add CRYO-CP-01:MT0001-XI", "In a new plot"])
        self.ctl.panel.attachmentRemoved.emit()
        self.assertFalse(self.ctl.panel._attachment.isVisibleTo(self.ctl.panel))
        self.ask("hello", 'say "Hi!"')
        prompt_text, grammar = self.engine.prompts[-1]
        self.assertNotIn('File "', prompt_text)
        self.assertNotIn("fvar", grammar)

    def test_only_the_last_file_attached_is_taken(self):
        from mint.assistant import files
        self.ctl._reading = "second.csv"
        said = len(self.said)
        self.ctl._on_file_read("first.csv", files.Found([("SYS-A:X1", "")]))
        self.assertEqual((len(self.said), self.ctl._file), (said, None), "read after the second was attached")
        self.ctl._on_file_read("second.csv", files.Found([("SYS-B:X2", "")]))
        self.assertEqual(self.ctl._file.variables[0].name, "SYS-B:X2")

    def test_a_file_that_cannot_be_read_says_why_and_attaches_nothing(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._attach("photo.png", "")
        self.assertIn("not .png files", self.said[-1])
        self.assertIsNone(self.ctl._file)
        self._attach("empty.csv", "nothing to see here\n")
        self.assertIn("names no signal I can use", self.said[-1])
        self.assertEqual(self.ctl.panel._suggestions[:1], [], "nothing to offer")

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

    def test_a_processed_signal_with_nothing_to_draw_is_told_after_apply(self):
        import pandas as pd
        from mint.assistant.voice import DONE
        from mint.models.accessModes.mtGeneric import MTGenericAccessMode
        # Drawn for real, from the CSV pulse: one signal all below zero, one above.
        del self.ctl.workspace.draw
        self.win.sigCfgWidget.model.set_dataframe(pd.DataFrame({
            "DS": ["csv", "csv"], "Variable": ["MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2"], "Stack": ["1.1", "2.1"],
            "Alias": ["below", "above"], "y": ["${self}.data - 1000", ""], "Plot type": ["PlotXY", "PlotXY"]}))
        self.win.dataRangeSelector.import_dict({"mode": MTGenericAccessMode.PULSE_NUMBER,
                                                "pulse_nb": ["ITER:MCTB-TEST/111"], "base": "Second(s)",
                                                "t_start": "-5", "t_end": "4"})
        cards = self.ask("log10 of below", "process r1 log10")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(self.note(cards[0]), "Done, but below_log10 came out empty, so there's nothing to draw.")
        cards = self.ask("log10 of above", "process r3 log10")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(list(self.ctl.workspace.table()["Alias"]), ["below", "below_log10", "above", "above_log10"])
        self.assertIn(self.note(cards[0]), DONE, "drawn: nothing more to say")

    def _archive(self, outcome, latest, end):
        """The drawn rows come out as ``outcome`` and the archive answers ``latest`` per variable (a moment, None for
        no such variable, or what it says instead); now is ``end``."""
        from mint.assistant.workspace import FOUND, UNKNOWN_VARIABLE
        ws = self.ctl.workspace
        ws.time_range_ns = lambda: (int((end - timedelta(hours=6)).timestamp()) * 10**9, int(end.timestamp()) * 10**9)
        ws.drawn_outcome = lambda uid: outcome(uid)
        answers = {name: (FOUND, int(moment.timestamp()) * 10**9) if isinstance(moment, datetime) else
                   (moment or UNKNOWN_VARIABLE, None) for name, moment in latest.items()}
        ws.latest_sample = lambda source, variable, before: answers[variable]

    def test_a_new_range_without_data_says_when_the_latest_is_and_offers_it(self):
        from mint.assistant import when
        from mint.assistant.workspace import DRAWN, EMPTY
        end = datetime.now(timezone.utc).replace(microsecond=0)
        newest, older = end - timedelta(days=1, hours=3, seconds=13), end - timedelta(days=6)
        state = {"outcome": EMPTY}
        self._archive(lambda uid: state["outcome"],
                      {"MAG-MCTB-F1:VAR1": newest, "MAG-MCTB-F1:VAR2": older, "CRYO:MT0001": None}, end)
        cards = self.ask("show the last 6 hours", "range last 6 hours")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        now = datetime.now(timezone.utc)
        self.assertEqual(self.said[-1], f"There's no data in the last 6 hours. The latest samples are from "
                                        f"{when.at(newest, now)} (pirani) and {when.at(older, now)} (VAR2). other has "
                                        f"no variable called CRYO:MT0001. Shall I show the 6 hours up to the most "
                                        f"recent?")
        offer = max(self.ctl._cards)
        start = (newest + timedelta(minutes=1)).replace(second=0) - timedelta(hours=6)
        self.assertEqual(self.ctl._cards[offer]["proposal"].lines,
                         [f"Time range: {when.span(start, start + timedelta(hours=6), now)}"])
        state["outcome"] = DRAWN
        calls = len(self.engine.prompts)
        self.ask("ok", 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls, "ok to the card on screen is its Apply")
        self.assertIn(self.note(offer), voice.DONE)
        self.assertEqual(self.win.dataRangeSelector.get_time_range(),
                         (int(start.timestamp()) * 10**9, int((start + timedelta(hours=6)).timestamp()) * 10**9))

    def test_an_offered_range_can_be_turned_down(self):
        from mint.assistant.workspace import EMPTY
        end = datetime.now(timezone.utc)
        self._archive(lambda uid: EMPTY, {"MAG-MCTB-F1:VAR1": end - timedelta(days=2), "MAG-MCTB-F1:VAR2": None,
                                          "CRYO:MT0001": None}, end)
        cards = self.ask("show the last 6 hours", "range last 6 hours")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        offer = max(self.ctl._cards)
        self.ask("no thanks", 'say "no model here"')
        self.assertTrue(self.note(offer).startswith("No problem"))
        self.assertEqual(self.ctl.workspace.range_dict()["mode"], MTGenericAccessMode.RELATIVE_TIME)

    def test_signals_without_data_next_to_others_with_data_are_named_without_moving_the_range(self):
        from mint.assistant import when
        from mint.assistant.workspace import DRAWN, EMPTY
        end = datetime.now(timezone.utc)
        older = end - timedelta(days=6)
        uid = self.ctl.workspace.uid_of(0)
        self._archive(lambda u: EMPTY if u == uid else DRAWN, {"MAG-MCTB-F1:VAR1": older}, end)
        cards = self.ask("show the last 6 hours", "range last 6 hours")
        count = len(self.ctl._cards)
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(self.said[-1], f"pirani has no data in the last 6 hours. Its latest sample is from "
                                        f"{when.at(older, datetime.now(timezone.utc))}.")
        self.assertEqual(len(self.ctl._cards), count, "the others show data: no range offered")

    def test_a_sample_inside_the_range_is_not_called_no_data(self):
        from mint.assistant.workspace import EMPTY
        end = datetime.now(timezone.utc)
        inside = end - timedelta(hours=1)
        self._archive(lambda uid: EMPTY, {"MAG-MCTB-F1:VAR1": inside, "MAG-MCTB-F1:VAR2": inside,
                                          "CRYO:MT0001": inside}, end)
        cards = self.ask("show the last 6 hours", "range last 6 hours")
        said = len(self.said)
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(len(self.said), said, "reading failed; the Status says why, not 'no data'")
        self.assertIn(self.note(cards[0]), voice.DONE)

    def test_a_signal_the_archive_says_nothing_about_is_not_called_without_data(self):
        from mint.assistant import when
        from mint.assistant.workspace import NOT_COMPUTED, UNTOLD
        end = datetime.now(timezone.utc)
        older = end - timedelta(days=6)
        silent = dict.fromkeys(("MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2", "CRYO:MT0001"), UNTOLD)
        for latest, expected in ((silent, None),
                                 (dict(silent, **{"MAG-MCTB-F1:VAR1": older}),
                                  f"pirani has no data in the last 6 hours. Its latest sample is from "
                                  f"{when.at(older, end)}. Shall I show the 6 hours up to it?")):
            with self.subTest(expected=expected):
                self._archive(lambda uid: NOT_COMPUTED, latest, end)
                cards = self.ask("show the last 6 hours", "range last 6 hours")
                said = len(self.said)
                self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
                # A read that failed with no answer from the archive (server down, say) is left to its Status.
                self.assertEqual(self.said[said:], [expected] if expected else [])

    def test_a_number_alone_after_a_processing_repeats_it_with_that_number(self):
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        calls = len(self.engine.prompts)
        cards = self.ask("now 12 s", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["process r1 moving_average window=12s"])
        self.assertEqual(len(self.engine.prompts), calls)
        self.ask("undo", 'say "no model here"')  # the 12 s card was not applied: the 30 s one is undone
        self.ask("12 s", 'say "Sure."')
        self.assertEqual(len(self.engine.prompts), calls + 1, "nothing applied any more: a request for the model")

    def test_a_number_alone_changes_the_processing_on_screen_rather_than_the_one_applied(self):
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.ask("smooth VAR2 over 30 s", "process r3 moving_average seconds=30")
        cards = self.ask("12 s", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["process r3 moving_average window=12s"])

    def test_ok_and_no_answer_the_card_on_screen(self):
        cards = self.ask("remove row 2", "remove r2")
        self.ask("yes please", 'say "no model here"')
        self.assertEqual(len(self.rows()), 3)
        cards = self.ask("remove row 1", "remove r1")
        self.ask("no", 'say "no model here"')
        self.assertTrue(self.note(cards[0]).startswith("No problem"))
        self.assertEqual(len(self.rows()), 3)
        self.ask("remove row 1", "remove r1")
        self.ask("is that ok?", 'say "It takes row 1 out of the table."')
        self.assertEqual(len(self.rows()), 3, "a question about the card is not its Apply")

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

    def test_this_with_a_row_selected_needs_no_question(self):
        self.win.sigCfgWidget.item_widgets[0].view().selectRow(1)
        answers = iter(['ask "Sure, which one: pirani or MAG-MCTB-F1:VAR2?"', "process r2 derivative"])
        complete = self.engine.complete

        def answer_in_turn(prompt_text, grammar, max_tokens=160):
            self.engine.answer = next(answers)
            return complete(prompt_text, grammar, max_tokens)

        self.engine.complete = answer_in_turn
        cards = self.ask("derivative of this", "")
        self.assertIn("Request: derivative of MAG-MCTB-F1:VAR2", self.engine.prompts[-1][0])
        self.assertEqual(len(self.engine.prompts), 2, "asked again once, about the selected row")
        self.assertEqual(len(cards), 1)
        self.assertNotIn("which one", " ".join(self.said).lower())

    def test_both_does_to_each_what_the_model_meant(self):
        self.engine.ids = [{"id": "r1", "p": 0.45, "alts": {"r2": 0.4}}]
        self.assertEqual(self.ask("smooth that one", "process r1 moving_average window=10s"), [])
        calls = len(self.engine.prompts)
        cards = self.ask("both", 'say "no model here"')
        self.assertEqual(len(self.engine.prompts), calls, "every option, without asking the model again")
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["process r1 r2 moving_average window=10s"])

    def test_a_data_source_not_here_is_told_on_opening_and_fixed_without_the_model(self):
        self.ctl.set_visible(True)
        self.assertEqual(self.said[-1], "CRYO:MT0001 uses the data source other, which isn't available here, so it "
                                        "isn't drawn: the data sources here are csv. Shall I change it to csv?")
        self.assertIn("Change other to csv", [b.text() for b in self.ctl.panel.findChildren(QPushButton)])
        calls = len(self.engine.prompts)
        cards = self.ask("Change other to csv", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].lines, ["CRYO:MT0001: other → csv"])
        self.ctl.on_card_action(cards[0], ctl.APPLY, [])
        self.assertEqual(list(self.ctl.workspace.table()["DS"])[:4], ["csv"] * 4)
        self.ctl.on_card_action(cards[0], ctl.UNDO, [])
        # Asked why, MINT says it again; a yes is the change it offers.
        self.ask("why is one of them red?", 'say "no model here"')
        self.assertIn("uses the data source other", self.said[-1])
        cards = self.ask("yes", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["source r3 to csv"])
        self.assertEqual(len(self.engine.prompts), calls, "none of it needs the model")

    def test_closing_the_panel_frees_the_model(self):
        self.ctl.set_visible(True)
        stopped = []
        self.engine.shutdown = lambda: stopped.append(1)
        self.ctl.set_visible(False)
        self.assertIsNone(self.ctl.engine)
        self.assertEqual(stopped, [1])

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
        self.ctl.workspace.search_variables = lambda words, request="", source="": (
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
        self.ctl.workspace.search_variables = lambda words, request="", source="": VariableSearch("sdnuda", names, 312,
                                                                                                  [], "EC")
        cards = self.ask("I need a workspace with 2 signals from EC in sdnuda, whatever you want", "find EC sdnuda")
        self.assertEqual(self.said[-1], "Here are the variables in sdnuda that start with EC. Tick the 2 you want and "
                                        "I'll add them. There are 312: these are the first 40, and Search Vars shows "
                                        "them all.")
        card = self.ctl.panel._cards[cards[0]]
        self.assertEqual(len(card.options), 40)
        self.assertEqual(self.ctl._cards[cards[0]]["source"], "sdnuda", "added from the source it found them in")

    def test_mint_opens_its_own_tools_without_the_model(self):
        ws = self.ctl.workspace
        opened = []
        ws.open_statistics = lambda: opened.append("statistics") or True
        ws.open_search_vars = lambda: opened.append("search")
        self.ask("can you open the stats table?", 'say "no model here"')
        self.ask("how many samples do we have per signal?", 'say "no model here"')
        self.assertEqual(self.said[-1], self.ctl.voice.statistics_opened())
        self.ask("can you open the search variables?", 'say "no model here"')
        self.assertEqual(opened, ["statistics", "statistics", "search"])
        # Three plots in the table and none drawn: the mini-map can't show.
        self.ask("can you enable the mini-map", 'say "no model here"')
        self.assertTrue(self.said[-1].startswith("The mini-map only works when a single plot is visible"),
                        self.said[-1])
        self.assertFalse(self.win.toolBar.minimapAction.isChecked())
        self.ask("what is the mini-map?", 'say "no model here"')
        self.assertTrue(self.said[-1].startswith("The mini-map is a small overview"), self.said[-1])
        self.assertEqual(self.engine.prompts, [])
        del ws.open_statistics
        self.ask("the statistics", 'say "no model here"')
        self.assertEqual(self.said[-1], self.ctl.voice.statistics_nothing_drawn())

    def test_no_take_sdnuda_searches_the_same_again_there(self):
        ws, searched = self.ctl.workspace, []

        def search(words, request="", source=""):
            # As MINT does: a source the words name, else the one chosen, else the default.
            named = [w for w in words if w in ("codacuda", "sdnuda")]
            where = (named or [source or "codacuda"])[0]
            searched.append(([w for w in words if w not in named], where))
            return VariableSearch(where, [("EC-GN-AUX-GCC:FAST-TC0", "")], 1, list(words))

        ws.search_variables = search
        ws.data_source_names = lambda: ["codacuda", "sdnuda"]
        ws.default_data_source = lambda: ("codacuda", None)
        self.ask("search for EC-GN signals", "find EC-GN")
        calls = len(self.engine.prompts)
        self.ask("no take sdnuda", 'say "Sorry, I didn\'t get that."')
        self.assertEqual(len(self.engine.prompts), calls, "MINT searches again itself")
        self.assertEqual(searched[-1], (["EC-GN"], "sdnuda"))
        # The source chosen stays the one searched, until the default is named.
        self.ask("ok can you then filter for the EC-GN*FAST*", "find EC-GN*FAST*")
        self.assertEqual(searched[-1], (["EC-GN*FAST*"], "sdnuda"))
        self.ask("EC-GN in codacuda", "find EC-GN codacuda")
        self.ask("instead of looking in codacuda use sdnuda", 'say "I can\'t look things up."')
        self.assertEqual(searched[-2:], [(["EC-GN"], "codacuda"), (["EC-GN"], "sdnuda")])
        self.assertNotIn("I can't look things up.", self.said)
        # Only right after a search.
        self.ask("smooth pirani 30s", "process r1 moving_average window=30s")
        self.ask("use sdnuda", 'say "Okay."')
        self.assertEqual(self.said[-1], "Okay.")

    def test_the_3_of_them_to_the_models_question_names_them(self):
        self.ask("can you plot the envelope?", 'ask "Sure, which one: the pirani, VAR2 or MT0001?"')
        self.ask("the 3 of them", 'say "Okay."')
        self.assertIn("Request: can you plot the envelope. pirani, MAG-MCTB-F1:VAR2 and CRYO:MT0001",
                      self.engine.prompts[-1][0])

    def test_disabling_a_signal_hides_it_and_keeps_its_row(self):
        ws, hidden = self.ctl.workspace, {}
        ws.is_hidden = lambda uid: hidden.get(uid, False)
        ws.set_hidden = lambda uid, value: hidden.__setitem__(uid, value)
        ws.refresh_plots = lambda: None
        cards = self.ask("can you disable signal pirani", "remove r1")
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].title, "Hide")
        self.ctl.panel.cardActionTriggered.emit(cards[0], ctl.APPLY, [])
        self.assertEqual(list(hidden.values()), [True])
        self.assertEqual(len(self.rows()), 4)

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
            self.ask("what is the mini-map?", 'say "no model here"')
            with open(record.path(), encoding="utf-8") as f:
                lines = [json.loads(line) for line in f]
            self.assertEqual([line["outcome"] for line in lines if "card" in line],
                             ["applied", "applied", "undone", "dismissed", "applied"])
            self.assertEqual(len(lines[0]["workspace"]["rows"]), 4, "the workspace the model saw")
            # Every request too, with its answer, also those no card came of.
            self.assertEqual([(line["request"], line["answer"], line["by"]) for line in lines if "turn" in line],
                             [("smooth pirani 30s", ["process r1 moving_average seconds=30"], "model"),
                              ("abs of the pirani", ["process r1 abs"], "model"),
                              ("remove row 2", ["remove r2"], "model"),
                              ("low-pass the pirani", ["process r1 lowpass"], "model"),
                              ("what is the mini-map?", ["about minimap"], "MINT")])
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
                self.assertEqual(len(f.readlines()), 10, "off: nothing more is kept")

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
                              RowInfo(id="r2", index=1, variable="CRYO-CP-01:MT0001-XI", stack="2.1", plot="p2")],
                        plots=[PlotInfo(id="p1", row=1, col=1), PlotInfo(id="p2", row=2, col=1)])
        self.assertEqual(ctl.suggestions(snap), ["Log scale on the top plot", "Smooth pirani over 10 s",
                                                 "pirani minus MT0001-XI", "Show the last 6 hours"])
        snap.plots[0].log_scale, snap.selected = True, ["r2"]
        self.assertEqual(ctl.suggestions(snap)[0], "Smooth the selected signals over 10 s")
        self.ctl.workspace.data_source_choices = lambda: ["csv", "other"]  # nothing to tell first
        self.ctl.set_visible(True)
        self.assertIn("Smooth pirani over 10 s", [b.text() for b in self.ctl.panel.findChildren(QPushButton)])

    def test_a_number_still_missing_after_an_answer_can_come_alone(self):
        self.ask("low-pass the pirani", "process r1 lowpass")
        self.ask("quite slow", "process r1 lowpass")
        self.assertEqual(self.said[-1], "I still need the number for that. Just the number is enough.")
        calls = len(self.engine.prompts)
        cards = self.ask("2 Hz", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["process r1 lowpass hz=2"])
        self.assertEqual(len(self.engine.prompts), calls, "the number fills in the request it belongs to")

    def test_a_window_asked_again_is_answered_as_people_write(self):
        # A signal archived on change: a sample about every 12 s.
        self.ctl.workspace.sample_period_seconds = lambda row: 11.654
        for reply in ("50s it's okey", "ok", "vale, 50 s"):
            with self.subTest(reply=reply):
                self.ask("smooth the pirani over 10 s", "process r1 moving_average seconds=10")
                self.assertTrue(self.said[-1].endswith("For example 50 s."), self.said[-1])
                calls = len(self.engine.prompts)
                cards = self.ask(reply, 'say "no model here"')
                self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands,
                                 ["process r1 moving_average window=50s"], "the pirani only, over 50 s")
                self.assertEqual(len(self.engine.prompts), calls)

    def test_a_window_that_would_not_show_either_is_explained_again(self):
        self.ctl.workspace.sample_period_seconds = lambda row: 11.654
        self.ask("smooth the pirani over 10 s", "process r1 moving_average seconds=10")
        self.assertEqual(self.ask("12 s", 'say "no model here"'), [])
        self.assertIn("so over 12 s it would stay as it is", self.said[-1])
        self.assertNotIn("I still need", self.said[-1])
        cards = self.ask("ok", 'say "no model here"')
        self.assertEqual(self.ctl._cards[cards[0]]["proposal"].commands, ["process r1 moving_average window=50s"])

    def test_a_window_given_in_an_answer_that_would_not_show_is_explained(self):
        self.ctl.workspace.sample_period_seconds = lambda row: 11.654
        self.ask("smooth it", 'ask "Which signal, and over how long?"')
        self.ask("over 1 second", "process r1 moving_average seconds=1")
        self.assertIn("it would stay as it is", self.said[-1], "the number came: why it doesn't do, not 'I still need'")

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

    def test_a_fixed_prompt_that_fails_stops_the_model_instead_of_leaving_it_starting(self):
        from mint.assistant import engine
        ensure_qapp()
        model = ModelEngine("model.gguf", 1)
        failed = []
        model.failed.connect(lambda *args: failed.append(args))
        model._state = engine.READY  # loaded
        model.prime("prefix")
        model._on_event({"ev": "error", "id": None, "message": "ValueError: prompt longer than the context"})
        self.assertEqual((model.state, failed), (FAILED, [(-1, "ValueError: prompt longer than the context")]))


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

    @unittest.skipUnless(importlib.util.find_spec("llama_cpp"), "the model library is not installed")
    def test_the_model_library_loads_while_the_next_request_is_awaited(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "model.gguf")
            with open(path, "wb") as f:
                f.write(b"GGUF not really")
            with open(path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            proc = self.start()
            try:
                proc.stdin.write(json.dumps({"op": "load", "model": path, "allowed_sha256": [sha]}) + "\n")
                proc.stdin.flush()
                events = []
                reader = threading.Thread(target=lambda: events.extend(json.loads(proc.stdout.readline())
                                                                       for _ in range(3)), daemon=True)
                reader.start()
                reader.join(60)
                # Not a real model, so it ends in an error; what matters is that it ends (it hung on Windows).
                self.assertEqual([e.get("step", e["ev"]) for e in events], ["checking", "loading", "error"])
            finally:
                proc.kill()
                proc.wait(timeout=10)

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
