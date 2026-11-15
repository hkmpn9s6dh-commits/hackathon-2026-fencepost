import tomllib


def load(data: bytes) -> dict:
    return tomllib.loads(data.decode())
