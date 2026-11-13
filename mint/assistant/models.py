"""Model files the assistant has been evaluated with, by SHA-256."""

from mint.assistant.prompt import FORMATS

KNOWN_MODELS = {
    "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597": {
        "name": "Qwen3-4B-Instruct-2507 Q4_K_M", "format": "chatml"},
    "364de16769a552bd4d35b755adaa76ec60188594e84beecd60ccf22970cbd3d8": {
        "name": "MINT assistant (Qwen3-1.7B trained for MINT) Q4_K_M", "format": "qwen3-nothink", "few_shot": False},
    "a5fc9c66a5aa463cefe6ccd3f117844c8e3b343db56668124d1f031314002c29": {
        "name": "MINT assistant (Qwen3-1.7B trained for MINT) Q4_K_M v12", "format": "qwen3-nothink", "few_shot": False,
        "files": True},
}


def chat_format(sha256: str, declared: dict = None) -> str:
    known = KNOWN_MODELS.get((sha256 or "").lower())
    if known:
        return known["format"]
    # A model trained for MINT says in its own file how it was trained (see mint/tools/assistant_train.py).
    if (declared or {}).get("mint.assistant.format") in FORMATS:
        return declared["mint.assistant.format"]
    return "chatml"


def few_shot(sha256: str, declared: dict = None) -> bool:
    """Whether the model needs the worked examples in its prompt (a model trained for MINT does not)."""
    known = KNOWN_MODELS.get((sha256 or "").lower())
    if known and "few_shot" in known:
        return known["few_shot"]
    return str((declared or {}).get("mint.assistant.few_shot", "true")).lower() != "false"


def reads_files(sha256: str, declared: dict = None) -> bool:
    """Whether the model was trained on the variables and times of an attached file (see prompt.render_file)."""
    known = KNOWN_MODELS.get((sha256 or "").lower())
    if known and "files" in known:
        return known["files"]
    return str((declared or {}).get("mint.assistant.files", "false")).lower() == "true"
