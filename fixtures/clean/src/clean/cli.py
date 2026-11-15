import argparse
import os


def token() -> str:
    return os.environ["CLEAN_TOKEN"]


def build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clean")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("audit", help="audit a path")
    return parser
