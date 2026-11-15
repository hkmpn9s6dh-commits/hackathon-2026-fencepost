import yaml


def check(raw: str) -> dict:
    return yaml.safe_load(raw)
