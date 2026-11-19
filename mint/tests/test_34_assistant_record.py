"""What the assistant keeps to retrain the model on: a file per conversation, named by when it started and a random id,
with nothing that tells who asked, encrypted for the team; and a new conversation started from the panel."""
import argparse
import json
import os
import re
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest import mock

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.assistant import controller as ctl
from mint.assistant import record
from mint.assistant.config import AssistantConfig, record_place, state_dir
from mint.assistant.prompt import ChatFormat
from mint.assistant.voice import Voice
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp
from mint.tests.test_30_assistant_actions import build_window
from mint.tests.test_31_assistant_panel import ChatPanel, StubEngine, wait_until

try:
    import cryptography  # noqa: F401
except ImportError:
    cryptography = None

NAME = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{32}\.jsonl$")


@dataclass
class Snap:
    now: datetime = field(default_factory=lambda: datetime(2026, 11, 19, 13, 33, tzinfo=timezone.utc))
    rows: list = field(default_factory=list)
    unlisted: list = field(default_factory=list)


class WhereTheRecordsGoTest(unittest.TestCase):

    def config(self, **variables):
        names = ("MINT_ASSISTANT_RECORD", "MINT_ASSISTANT_RECORD_KEY")
        with mock.patch.dict(os.environ, {name: variables.get(name, "") for name in names}):
            return AssistantConfig.from_environment()

    def test_on_this_computer_with_1(self):
        config = self.config(MINT_ASSISTANT_RECORD="1")
        self.assertTrue(config.record)
        self.assertEqual(record_place(config), (os.path.join(state_dir(), "records"), False))

    def test_in_a_folder_shared_by_everyone(self):
        config = self.config(MINT_ASSISTANT_RECORD="/team/records", MINT_ASSISTANT_RECORD_KEY="~/team.pem")
        self.assertTrue(config.record)
        self.assertEqual(record_place(config), ("/team/records", True))
        self.assertEqual(config.record_key, os.path.expanduser("~/team.pem"))

    def test_nowhere_without_it(self):
        for value in ("", "0", "off"):
            with self.subTest(value=value):
                self.assertFalse(self.config(MINT_ASSISTANT_RECORD=value).record)


class ConversationRecordTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(self.tmp.name, "records")

    def keys(self):
        return record.new_key(os.path.join(self.tmp.name, "keys"))

    def test_a_file_for_each_conversation_named_by_its_start_and_a_random_id(self):
        first, second = record.Conversation(self.folder), record.Conversation(self.folder)
        self.assertEqual(os.listdir(self.tmp.name), [], "nothing before the first entry")
        first.write_turn("t1", "smooth the pirani", Snap(), ["process r1 smooth"], "model")
        second.write_turn("t1", "zoom on the last hour", Snap(), ["range last 1 hours"], "model")
        names = sorted(os.listdir(self.folder))
        self.assertEqual(len(names), 2)
        self.assertTrue(all(NAME.match(name) for name in names), names)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual([entry["request"] for entry in record.read(first.path)], ["smooth the pirani"])

    def test_nothing_in_it_tells_who_asked(self):
        rows = [{"variable": "CRYO-CP-03:MT0021-XI",
                 "pulse": "imas:hdf5?path=/home/ITER/someone/public/imasdb/test/105027/pf_active_5k"},
                {"variable": "pf_active/coil[1]/current/data", "file": "C:\\Users\\someone\\Documents\\coils.csv"},
                {"variable": "CRYO:JDOE01-XI", "file": "pressures_jdoe.xlsx"}]
        conversation = record.Conversation(self.folder)
        with mock.patch.object(record.getpass, "getuser", return_value="jdoe"):
            conversation.write_turn("t1", "plot what jdoe asked for", Snap(rows=rows), ["add r1"], "model")
        with open(conversation.path, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("jdoe", text)
        self.assertNotIn("someone", text)
        entry = record.read(conversation.path)[0]
        self.assertEqual(entry["request"], "plot what <user> asked for")
        self.assertEqual(entry["workspace"]["rows"][0], {
            "variable": "CRYO-CP-03:MT0021-XI",
            "pulse": "imas:hdf5?path=/home/ITER/<user>/public/imasdb/test/105027/pf_active_5k"})
        self.assertEqual(entry["workspace"]["rows"][1]["file"], "C:\\Users\\<user>\\Documents\\coils.csv")
        self.assertEqual(entry["workspace"]["rows"][2], {"variable": "CRYO:JDOE01-XI", "file": "pressures_<user>.xlsx"},
                         "a signal name keeps its upper case letters")

    @unittest.skipIf(cryptography is None, "cryptography is not installed")
    def test_only_the_team_reads_a_record_encrypted_with_its_key(self):
        private, public = self.keys()
        os.makedirs(self.folder)
        conversation = record.Conversation(self.folder, public, shared=True)
        conversation.write_turn("c1-t1", "smooth the pirani 30s", Snap(), ["process r1 moving_average window=30s"],
                                "model")
        conversation.write("c1-1", "applied", "smooth the pirani 30s", Snap(), ["process r1 moving_average window=30s"])
        with open(conversation.path, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("pirani", text)
        with self.assertRaises(record.RecordError):
            record.read(conversation.path)
        self.assertEqual([entry.get("outcome") for entry in record.read(conversation.path, private)], [None, "applied"])
        # What retrains the model is read with the private key.
        from mint.tools.assistant_train import cmd_feedback
        out = os.path.join(self.tmp.name, "feedback.jsonl")
        cmd_feedback(argparse.Namespace(records=[conversation.path], out=out, key=private))
        with open(out, encoding="utf-8") as f:
            self.assertEqual([json.loads(line)["request"] for line in f], ["smooth the pirani 30s"])

    @unittest.skipUnless(cryptography is not None and hasattr(os, "getuid"), "POSIX permissions")
    def test_the_private_key_is_only_for_whoever_made_it(self):
        private, _ = self.keys()
        self.assertEqual(os.stat(private).st_mode & 0o077, 0)

    def test_a_shared_folder_gets_nothing_unencrypted(self):
        os.makedirs(self.folder)
        conversation = record.Conversation(self.folder, "", shared=True)
        conversation.write_turn("t1", "smooth the pirani", Snap(), ["process r1 smooth"], "model")
        self.assertEqual(os.listdir(self.folder), [])

    @unittest.skipIf(cryptography is None, "cryptography is not installed")
    def test_a_shared_folder_that_isnt_there_is_not_made(self):
        _, public = self.keys()
        conversation = record.Conversation(self.folder, public, shared=True)
        conversation.write_turn("t1", "smooth the pirani", Snap(), ["process r1 smooth"], "model")
        self.assertFalse(os.path.exists(self.folder))

    def test_a_long_conversation_stops_being_kept(self):
        conversation = record.Conversation(self.folder)
        with mock.patch.object(record, "MAX_BYTES", 2000):
            for turn in range(40):
                conversation.write_turn(f"t{turn}", "smooth the pirani", Snap(), ["process r1 smooth"], "model")
        self.assertLessEqual(os.path.getsize(conversation.path), 2000)
        self.assertGreater(len(record.read(conversation.path)), 1)


@unittest.skipIf(ChatPanel is None, "iplotWidgets has no chat panel")
class NewConversationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patched = mock.patch.dict(os.environ, {"IPLOT_DUMP_PATH": self.tmp.name})
        patched.start()
        self.addCleanup(patched.stop)
        self.win = build_window()
        self.engine = StubEngine()
        self.ctl = ctl.AssistantController(self.win, AssistantConfig(enabled=True, record=True), ChatPanel,
                                           engine=self.engine)
        self.ctl.format = ChatFormat("chatml")
        self.ctl.workspace.draw = lambda: None
        self.said = []
        show = self.ctl.panel.add_assistant_message
        self.ctl.panel.add_assistant_message = lambda text: (self.said.append(text), show(text))[1]

    def tearDown(self):
        self.ctl.panel.deleteLater()
        self.win.close()

    def ask(self, request, answer):
        self.engine.answer = answer
        before = set(self.ctl._cards)
        self.ctl.panel.messageSubmitted.emit(request)
        self.assertTrue(wait_until(lambda: self.ctl._inflight is None))
        return [card for card in self.ctl._cards if card not in before]

    def records(self):
        folder = os.path.join(self.tmp.name, "assistant", "records")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_panel_says_that_what_is_asked_is_kept(self):
        self.ctl.set_visible(True)
        self.assertEqual(self.said[0], Voice.RECORDED)
        self.said.clear()
        self.ctl.config.record = False
        self.ctl.new_conversation()
        self.assertNotIn(Voice.RECORDED, self.said)

    def test_a_new_conversation_starts_afresh_in_a_file_of_its_own(self):
        self.ctl.set_visible(True)
        cards = self.ask("smooth pirani 30s", "process r1 moving_average seconds=30")
        self.ctl.on_card_action(cards[0], ctl.APPLY, [])
        self.assertEqual(len(self.records()), 1)
        panel = self.ctl.panel
        self.assertTrue(panel.new_button.isVisible() and panel.new_button.isEnabled())
        self.said.clear()
        panel.new_button.click()
        self.assertEqual(self.ctl._cards, {})
        self.assertEqual(self.ctl._last_action, "", "nothing said before is carried into the next answers")
        self.assertEqual(len(self.ctl.workspace.table()), 5, "the change applied stays")
        # As on opening the panel: that it is kept, and why a row isn't drawn.
        self.assertEqual(self.said[0], Voice.RECORDED)
        self.assertIn("uses the data source other", self.said[1])
        self.assertEqual(panel.message_count(), 2)
        self.ask("abs of the pirani", "process r1 abs")
        names = self.records()
        self.assertEqual(len(names), 2)
        requests = [[entry["request"] for entry in record.read(os.path.join(self.tmp.name, "assistant", "records",
                                                                            name))] for name in names]
        self.assertIn(["abs of the pirani"], requests)


if __name__ == "__main__":
    unittest.main()
