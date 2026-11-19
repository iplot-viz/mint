"""Each request, its answer and what the user did with each card, kept to retrain the model on.

Each conversation goes to a file of its own, named by when it started and a random id, with nothing in it that tells
who asked. With the public key of the team (MINT_ASSISTANT_RECORD_KEY) the file is encrypted, and only the private key
reads it (see read()). A folder shared by everyone (MINT_ASSISTANT_RECORD set to a folder) is only written encrypted.
"""
import base64
import getpass
import json
import os
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

# The first line of an encrypted file, and what each of its lines is bound to.
FORMAT = "mint-assistant-record-1"
# Past this a conversation is no longer kept: a long one adds little, and a shared folder stays small.
MAX_BYTES = 1024 * 1024
# The name of a record file: when its conversation started and a random id (see Conversation).
NAME = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{32}\.jsonl")
USER = "<user>"
# Folders named after a person: their home, on Linux, at ITER and on Windows.
_HOME_FOLDERS = re.compile(r"((?:^|[\s\"'=:(,])(?:/home/ITER|/home|/mnt/ITER|/Users|[A-Za-z]:\\Users)[/\\])"
                           r"[^/\\\s\"']+")


class RecordError(Exception):
    pass


class Conversation:
    """The record of one conversation, in ``folder``: nothing is written before its first entry, and nothing raises."""

    def __init__(self, folder: str, key_path: str = "", shared: bool = False):
        self.id = uuid.uuid4().hex
        self.folder, self.key_path, self.shared = folder, key_path, shared
        started = datetime.now(timezone.utc)
        self.path = os.path.join(folder, f"{started:%Y%m%dT%H%M%SZ}-{self.id}.jsonl")
        self._seal = None  # (line) -> what is written for it, once the file is made
        # The file made, open until the conversation ends: others can write in a shared folder, and an entry must reach
        # this file whatever is put in its place under its name.
        self._file = None
        self._size = 0
        self._stopped = False

    def write(self, card: str, outcome: str, request: str, snap, commands) -> None:
        """One outcome ("applied", "dismissed", "undone") of a card."""
        self._append({"card": card, "outcome": outcome, "request": request, "commands": list(commands)}, snap)

    def write_turn(self, turn: str, request: str, snap, answer, by: str) -> None:
        """A request and its answer: the model's commands, or what MINT did itself (``by``)."""
        self._append({"turn": turn, "request": request, "answer": list(answer), "by": by}, snap)

    def _append(self, entry: dict, snap) -> None:
        if self._stopped:
            return
        try:
            workspace = asdict(snap)
            workspace.pop("unlisted", None)
            workspace["now"] = snap.now.isoformat()
            line = json.dumps(anonymous({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry,
                                         "workspace": workspace}))
            if self._file is None:
                self._make()
            text = self._seal(line) + "\n"
            if self._size + len(text) > MAX_BYTES:
                self._stopped = True
                logger.info(f"Assistant: this conversation reached {MAX_BYTES} bytes of record; the rest isn't kept")
                self.close()
                return
            self._file.write(text)
            self._file.flush()
            self._size += len(text)
        except Exception as e:
            self._stopped = True
            logger.warning(f"Assistant: this conversation isn't recorded: {e}")
            self.close()

    def close(self):
        """Ends the record of the conversation: nothing more is written to it."""
        self._stopped = True
        if self._file is not None:
            try:
                self._file.close()
            except OSError as e:
                logger.warning(f"Assistant: could not close the record of this conversation: {e}")
            self._file = None

    def _make(self):
        if self.key_path:
            header, seal = _encryption(self.key_path)
        elif self.shared:
            raise RecordError(f"{self.folder} is shared, and only gets encrypted records: set the public key of the "
                              f"team in MINT_ASSISTANT_RECORD_KEY")
        else:
            header, seal = "", (lambda line: line)
        if not self.shared:  # a shared one is made by its admins: a mistyped name makes none
            os.makedirs(self.folder, exist_ok=True)
        # In a shared folder the team reads the files, which only its private key opens. O_EXCL: a new file, never one
        # or a link someone put there first.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644 if self.shared else 0o600)
        self._file = os.fdopen(fd, "w", encoding="utf-8")
        if header:
            self._file.write(header + "\n")
            self._file.flush()
        self._size = len(header) + 1 if header else 0
        self._seal = seal


def anonymous(value):
    """``value`` without the name of the user: theirs, and the folders named after anyone, become <user>."""
    if isinstance(value, dict):
        return {key: anonymous(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [anonymous(item) for item in value]
    if not isinstance(value, str):
        return value
    value = _HOME_FOLDERS.sub(lambda m: m.group(1) + USER, value)
    name = _user_name()
    if len(name) >= 3:
        # As a word, also between underscores as in a file name; case kept: signal names are mostly upper case, and
        # none should lose a part that reads like a user name.
        value = re.sub(rf"(?<![A-Za-z0-9.-]){re.escape(name)}(?![A-Za-z0-9-])", USER, value)
    return value


def _user_name() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _oaep():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    return padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def _encryption(key_path: str):
    """The first line of a file and what encrypts each line after it: a key of its own, which only the private key of
    the team opens."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RecordError("encrypting it needs the Python package cryptography") from None
    with open(key_path, "rb") as f:
        public = serialization.load_pem_public_key(f.read())
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 2048:
        raise RecordError(f"{key_path} isn't an RSA public key of 2048 bits or more")
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)

    def seal(line: str) -> str:
        nonce = os.urandom(12)
        return json.dumps({"nonce": _b64(nonce), "data": _b64(aes.encrypt(nonce, line.encode("utf-8"),
                                                                           FORMAT.encode("ascii")))})

    return json.dumps({"format": FORMAT, "key": _b64(public.encrypt(key, _oaep()))}), seal


def read(path: str, private_key: Optional[str] = None) -> List[dict]:
    """The entries of a record file; an encrypted one needs the private key of the team (the path of its file)."""
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    if not lines:
        return []
    first = _json(lines[0])
    if not isinstance(first, dict) or first.get("format") != FORMAT:
        return [entry for entry in map(_json, lines) if isinstance(entry, dict)]
    if not private_key:
        raise RecordError(f"{path} is encrypted: give the private key of the team")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(private_key, "rb") as f:
        private = serialization.load_pem_private_key(f.read(), password=None)
    aes = AESGCM(private.decrypt(base64.b64decode(first["key"]), _oaep()))
    entries = []
    for sealed in map(_json, lines[1:]):
        if isinstance(sealed, dict):  # a line cut short when MINT stopped
            entries.append(json.loads(aes.decrypt(base64.b64decode(sealed["nonce"]), base64.b64decode(sealed["data"]),
                                                  FORMAT.encode("ascii"))))
    return entries


def _json(line: str):
    try:
        return json.loads(line)
    except ValueError:
        return None


def new_key(folder: str) -> Tuple[str, str]:
    """A key pair for the team, in ``folder``: the private key, readable only by whoever made it, reads the records;
    the public one goes in MINT_ASSISTANT_RECORD_KEY."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    os.makedirs(folder, exist_ok=True)
    private_path = os.path.join(folder, "mint-assistant-record-private.pem")
    public_path = os.path.join(folder, "mint-assistant-record-public.pem")
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    with open(public_path, "wb") as f:
        f.write(private.public_key().public_bytes(serialization.Encoding.PEM,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo))
    return private_path, public_path
