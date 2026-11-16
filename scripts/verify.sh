#!/usr/bin/env bash
# One script a judge can run after a fresh clone. No model, no network beyond pip.
#
#   bash scripts/verify.sh            # rules-only checks (fast, hermetic)
#   FENCEPOST_MODEL=1 bash scripts/verify.sh   # also run the real model path
#
# Every check prints PASS/FAIL and the script exits non-zero on the first failure.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
FAILED=0

say() { printf '%s\n' "$*"; }
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }

say "fencepost verify · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say ""

# ---------------------------------------------------------------- 0. interpreter
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.12 python3.11 python3.13 python3 "py -3.12" "py -3.11"; do
    if command -v ${candidate%% *} >/dev/null 2>&1; then
      if $candidate -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"; break
      fi
    fi
  done
fi
if [ -z "$PY" ]; then
  say "no Python >= 3.11 on PATH"; exit 2
fi
say "interpreter: $($PY -V 2>&1)"

# ------------------------------------------------------------------ 1. install
if [ ! -x "$ROOT/.venv/bin/python" ] && [ ! -x "$ROOT/.venv/Scripts/python.exe" ]; then
  say "creating .venv"
  "$PY" -m venv .venv || { say "venv failed"; exit 2; }
fi
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then VPY="$ROOT/.venv/Scripts/python.exe"; else VPY="$ROOT/.venv/bin/python"; fi

say "installing"
"$VPY" -m pip install -q --upgrade pip >/dev/null 2>&1
"$VPY" -m pip install -q -e . >/dev/null 2>&1 || { say "install failed"; exit 2; }
"$VPY" -m pip install -q pytest >/dev/null 2>&1 || true

VERSION="$("$VPY" -m fencepost.cli --version 2>/dev/null || true)"
if [ -z "$VERSION" ]; then
  VERSION="$("$VPY" -c 'import fencepost; print("fencepost " + fencepost.__version__)')"
fi
case "$VERSION" in
  *0.1.0*) pass "AC-1 installed: $VERSION" ;;
  *) fail "AC-1 version: got '$VERSION'" ;;
esac

# -------------------------------------------------------------------- 2. tests
if "$VPY" -m pytest -q >/tmp/fencepost-pytest.log 2>&1; then
  pass "AC-13 tests: $(tail -1 /tmp/fencepost-pytest.log)"
else
  fail "AC-13 tests failed"; tail -25 /tmp/fencepost-pytest.log
fi

# -------------------------------------------------------- 3. fixtures, rule only
TMP="$(mktemp -d)"
check_fixture() { # name expected_exit expected_high expected_total
  local name="$1" expected_exit="$2" expected_high="$3" expected_total="$4"
  "$VPY" -m fencepost.cli audit "fixtures/$name" --no-model --yes --quiet --out "$TMP/$name" >/dev/null 2>&1
  local code=$?
  local got
  got="$("$VPY" - "$TMP/$name/ledger.json" <<'PY'
import json, sys
ledger = json.load(open(sys.argv[1], encoding="utf-8"))
drift = [f for f in ledger["findings"] if f["verdict"] == "drift"]
high = [f for f in drift if f["severity"] == "high"]
print(f"{len(drift)} {len(high)}")
PY
)"
  local total="${got%% *}" high="${got##* }"
  if [ "$code" -eq "$expected_exit" ] && [ "$total" -eq "$expected_total" ] && [ "$high" -eq "$expected_high" ]; then
    pass "fixture $name: exit $code, drift $total (high $high)"
  else
    fail "fixture $name: expected exit $expected_exit / $expected_total drift ($expected_high high), got exit $code / $total ($high)"
  fi
}

check_fixture clean 0 0 0
check_fixture python-floor 1 1 1
check_fixture missing-dep 1 1 2
check_fixture phantom-command 1 1 1
check_fixture ghost-env 1 1 1
check_fixture multi 1 3 4

# ----------------------------------------------------------- 4. exit code ladder
"$VPY" -m fencepost.cli audit fixtures/multi --no-model --yes --quiet --out "$TMP/ladder" --fail-on high >/dev/null 2>&1
[ $? -eq 1 ] && pass "AC-10 --fail-on high -> 1" || fail "AC-10 --fail-on high"
"$VPY" -m fencepost.cli audit fixtures/multi --no-model --yes --quiet --out "$TMP/ladder2" --fail-on none >/dev/null 2>&1
[ $? -eq 0 ] && pass "AC-10 --fail-on none -> 0" || fail "AC-10 --fail-on none"

# ------------------------------------------------------------- 5. ledger honesty
"$VPY" - "$TMP/multi/ledger.json" <<'PY'
import json, sys
from pathlib import Path

ledger = json.load(open(sys.argv[1], encoding="utf-8"))
root = Path("fixtures/multi")
bad = 0
for finding in ledger["findings"]:
    if finding["verdict"] != "drift":
        continue
    text = (root / finding["claim"]["file"]).read_text(encoding="utf-8")
    quote = finding["claim"]["quote"]
    if quote not in text:
        print(f"  FAIL  AC-5 quote missing from file: {finding['id']}")
        bad += 1
    elif text.count("\n", 0, text.find(quote)) + 1 != finding["claim"]["line"]:
        print(f"  FAIL  AC-5 line number wrong: {finding['id']}")
        bad += 1
if ledger["run"]["model_calls"] != 0:
    print("  FAIL  AC-2 rule-only mode made model calls")
    bad += 1
if len(ledger["dropped_quotes"]) != ledger["run"]["claims_dropped"]:
    print("  FAIL  AC-7 dropped_quotes does not match claims_dropped")
    bad += 1
print("  PASS  AC-5 every finding quote is verbatim and line-accurate" if bad == 0 else "")
raise SystemExit(1 if bad else 0)
PY
[ $? -eq 0 ] || fail "AC-5/AC-7 ledger honesty"

# ------------------------------------------------------------- 6. report renders
if [ -f "$TMP/multi/report.html" ] && grep -q "逐字核对拒绝" "$TMP/multi/report.html" \
   && grep -q "pyproject.toml:" "$TMP/multi/report.html"; then
  pass "AC-9 report.html carries citations and the refusal section"
else
  fail "AC-9 report.html"
fi

# -------------------------------------------------------- 7. self audit (AC-14)
"$VPY" -m fencepost.cli audit . --no-model --yes --quiet --out "$TMP/self" --fail-on none >/dev/null 2>&1
SELF="$("$VPY" - "$TMP/self/ledger.json" <<'PY'
import json, sys
ledger = json.load(open(sys.argv[1], encoding="utf-8"))
drift = [f for f in ledger["findings"] if f["verdict"] == "drift"]
high = [f for f in drift if f["severity"] == "high"]
print(f"{len(drift)} {len(high)} {'; '.join(f['id'] for f in drift)}")
PY
)"
say "  INFO  AC-14 self audit: $SELF"

# ------------------------------------------------------------------ 8. optional
if [ "${FENCEPOST_MODEL:-0}" = "1" ]; then
  say ""
  say "model path (this takes minutes on CPU)"
  "$VPY" -m fencepost.cli audit fixtures/multi --yes --out "$TMP/model" >/tmp/fencepost-model.log 2>&1
  "$VPY" - "$TMP/model/ledger.json" <<'PY'
import json, sys
ledger = json.load(open(sys.argv[1], encoding="utf-8"))
run = ledger["run"]
ok = run["mode"] == "model" and bool(run["run_id"]) and run["model_calls"] > 0
print(f"  {'PASS' if ok else 'FAIL'}  AC-6 model path: mode={run['mode']} calls={run['model_calls']} run_id={run['run_id']}")
raise SystemExit(0 if ok else 1)
PY
  [ $? -eq 0 ] || fail "AC-6 model path"
fi

say ""
if [ "$FAILED" -eq 0 ]; then
  say "verify: all checks passed"
  exit 0
fi
say "verify: $FAILED check(s) failed"
exit 1
