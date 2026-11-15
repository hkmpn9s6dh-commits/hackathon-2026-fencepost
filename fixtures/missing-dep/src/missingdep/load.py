from pathlib import Path

import yaml


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())
