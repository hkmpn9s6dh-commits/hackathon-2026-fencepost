# clean

## Install

Requires Python 3.11+.

## Configure

Set `CLEAN_TOKEN` before running the CLI.

## Use

Run `clean audit .` to write the ledger.

## What the checker looks for

This table is documentation about the tool: every cell written in code is a
specimen, not a promise this repository makes.

| Kind | The promise | Where the reality is |
|---|---|---|
| `env_var` | "set `SOMETHING_API_KEY`" | `os.environ[...]` |
| `python_requires` | `Python 3.9+` in prose | `requires-python` |
| `command` | `clean something` | `add_parser("something")` |

Set `YOUR_API_KEY` in your shell before configuring anything else.
