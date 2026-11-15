import argparse


def build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pythonfloor")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("audit", help="audit a path")
    return parser
