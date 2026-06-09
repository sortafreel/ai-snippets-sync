---
name: be-test-audit-init
description: >-
  One-time INITIAL Python backend test-quality audit — the full-sweep counterpart
  of the scheduled `be-test-audit`. Runs inside any backend git repo and audits ALL
  existing Python test files in the tree (no time window), classifies them against
  a fake-test rubric (mock asserting its own return, patching the subject under
  test, bare assert_called, over-mocked units, re-implemented oracles, hollow
  route-smoke, no-op/conditional assertions, framework-only checks, etc.), then
  REWORKS salvageable fake tests into meaningful ones or DELETES the unsalvageable,
  and opens a Pull Request with a verdict table. Repo-agnostic and self-contained:
  auto-detects the env/dependency manager, the runner (pytest/unittest), and the
  package root even when the project lives in a subdirectory
  (uv/poetry/pdm/hatch/pipenv/pip+venv, pytest collecting unittest too). Never runs
  the whole test suite, never commits to the default branch, and keeps any test it
  is unsure about. Run this ONCE to clear the existing fake-test backlog before
  scheduling the weekly `be-test-audit`; for a large repo, lower AUDIT_MAX_FILES to
  split the work into reviewable PRs and re-run until clean.
---

# Backend Test-Quality Auditor — Initial Full Sweep (`be-test-audit-init`)

## Mission

Run inside an arbitrary Python backend git repo as a **one-time initial pass** —
the full-sweep counterpart of the scheduled `be-test-audit`. Audit **every existing
Python test file in the repo** (no time window), read each one against the fake-test
rubric below, and **improve the test suite's signal**: rework fake-but-salvageable
tests into genuine behavioral tests, delete the unsalvageable ones, and ship the
changes as a **Pull Request** that a human reviews. You are a careful editor, not a
bulk deleter. Run this once to clear the backlog; afterwards the weekly
`be-test-audit` (which only looks at the last ~8 days) keeps the suite clean.

### Non-goals (read these first — they override any instinct to "be thorough")

- **You do NOT run the whole test suite.** Ever. Only the specific changed/affected
  test files, and only when you need to verify a rework or confirm a deletion is
  safe. Running the full backend suite is forbidden by default.
- **You do NOT process more than `AUDIT_MAX_FILES` per run.** For a large repo, lower
  the cap to split the backlog into smaller, reviewable PRs and re-run until clean.
- **You do NOT commit to the default/main branch.** All changes land on a dedicated
  branch and go through a PR.
- **You are conservative when unsure.** Deleting a real test is far more costly than
  leaving a marginal one. When genuinely uncertain whether a test is fake, **KEEP it**
  and note it in the PR as "flagged, left untouched."
- **You do NOT ship red or broken tests.** A reworked test that can't be made to pass
  meaningfully is either fixed or falls back to deletion-with-justification.
- **You do NOT assume any project context.** No CLAUDE.md, no framework, no directory
  layout, no committed state is assumed. Detect everything at runtime.

---

## IMPORTANT — how to run these snippets

The bash blocks below are the **executable contract** for this skill, not illustrations.
Run them in order; the guards (clean-tree, dry-run, push-failure) are
load-bearing. A few hard rules:

- **Build pathspec/file lists as positional parameters (`set -- …`), never as an
  unquoted string variable.** The environment's default shell is **zsh**, where an
  unquoted `$VAR` does **not** word-split (verified), so a space-separated glob string
  collapses into one literal pathspec that matches nothing and the skill silently finds
  zero files. `set -- a b c` then `-- "$@"` word-splits identically in bash **and** zsh.
- **Always emit a final status line** `AUDIT_RESULT=...` (see Step 7) so the scheduler
  can tell "audited nothing" (healthy) from "broke" (needs a human). Exit non-zero on
  error paths.
- The commands target **bash and zsh** (the documented runtimes) and are verified in both. Most
  are plain POSIX `sh`; the ONE exception is the Step 6c safety-net, which uses a `<(…)` process
  substitution (a bash/zsh feature, not POSIX `sh`) — that guard runs only under bash/zsh.

---

## Configuration (env-overridable knobs)

All knobs are environment variables with safe defaults. Read them once at the start.

```bash
# Base branch for the PR. Empty => auto-detect the repo's default branch (see Step 1).
: "${AUDIT_BASE_BRANCH:=}"

# Branch name prefix for the audit branch.
: "${AUDIT_BRANCH_PREFIX:=chore/be-test-audit-init}"

# Dry run: classify + report only. No edits, no deletes, no branch, no PR.
: "${AUDIT_DRY_RUN:=0}"                 # 1 = dry run

# Hard cap on candidate files processed in a single run (bounds blast radius). Defaults high
# for the initial full sweep so it covers everything; LOWER it (e.g. 25) to split a large
# backlog into smaller, reviewable PRs and re-run until the verdict table shows nothing fake.
: "${AUDIT_MAX_FILES:=100000}"

# Per-file verify timeout (seconds). A hard ceiling so a wedged runner can never wedge
# the run indefinitely.
: "${AUDIT_VERIFY_TIMEOUT:=180}"

# Extra include/exclude path SUBSTRINGS (space-separated). Matched as plain substrings
# against the candidate path (NOT shell/`**` globs — see Step 2 for why).
: "${AUDIT_INCLUDE_SUBSTR:=}"          # e.g. "backend/  services/api/"
: "${AUDIT_EXCLUDE_SUBSTR:=}"          # e.g. "/legacy/  /vendor/  /migrations/"
```

The built-in test-file pathspecs are defined directly in Step 2 as a positional array
(with `:(glob)` magic). Do not move them into a string knob — see the IMPORTANT note above.

> **Re-running:** this pass is stateless — it re-enumerates the whole tree each time, so
> already-clean tests are simply re-read and pass as MEANINGFUL. Re-run after merging each
> PR (especially when batching via a lower `AUDIT_MAX_FILES`) until nothing fake remains.

---

## STEP 1 — Preflight, clean-tree gate & detection

**Goal:** confirm we're at the root of a Python backend git repo with a clean tree, detect
tooling, and bail cleanly if there's no backend test runner.

```bash
fail()    { echo "AUDIT_RESULT=error: $*" >&2; exit 1; }     # could-not-run -> ALERT (non-zero)
nothing() { echo "AUDIT_RESULT=nothing: $*";   exit 0; }     # legitimately nothing to do (healthy)

# 1a. Must be inside a git work tree, and we must be AT its root.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || nothing "not a git repo"
ROOT="$(git rev-parse --show-toplevel)" || fail "cannot resolve repo root"
cd "$ROOT" || fail "cannot cd to repo root"

# 1b. CLEAN-TREE PRECONDITION. An unattended deleter must NOT run on a dirty tree:
#     post-install lockfile churn, a stray .env, or residue from a crashed prior
#     run would otherwise get swept into the PR (secrets / unrelated changes). Refuse.
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean:"; git status --porcelain | head -20
  nothing "dirty working tree; refusing to run unattended (commit/stash/reset first)"
fi

# 1c. Resolve base branch. Auto-detect the DEFAULT branch; never silently fall back to the
#     current/feature branch or a detached HEAD.
if [ -z "$AUDIT_BASE_BRANCH" ]; then
  AUDIT_BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
fi
if [ -z "$AUDIT_BASE_BRANCH" ]; then
  for b in main master develop; do
    if git show-ref --verify --quiet "refs/heads/$b" || git show-ref --verify --quiet "refs/remotes/origin/$b"; then
      AUDIT_BASE_BRANCH="$b"; break
    fi
  done
fi
CUR_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"   # "HEAD" if detached
# Refuse to default the PR base to a feature/detached branch — that would target the
# wrong base. Require an explicit AUDIT_BASE_BRANCH instead, but keep the rest of the run
# valid as a "push + report" delivery (Step 6 handles the missing-base case loudly).
if [ -z "$AUDIT_BASE_BRANCH" ] || [ "$AUDIT_BASE_BRANCH" = "HEAD" ]; then
  echo "WARNING: could not resolve a real default branch (current ref: '$CUR_BRANCH')."
  echo "         Set AUDIT_BASE_BRANCH explicitly. Will push the branch + report instead of opening a PR against an unknown base."
  AUDIT_BASE_BRANCH=""
fi
echo "Base branch: ${AUDIT_BASE_BRANCH:-<unresolved>}"

# 1e. Confirm this repo contains a Python project SOMEWHERE — root OR a subdirectory. Repos
#     often keep the backend under backend/, api/, app/, src/, or services/* with NO root
#     pyproject.toml, so do NOT require one at the root; runner detection in 1h is the real gate.
#     Accept any Python-project marker tracked anywhere (non-vendored).
git ls-files -- '*pyproject.toml' '*setup.py' '*setup.cfg' '*requirements*.txt' \
              '*Pipfile' '*tox.ini' '*.py' 2>/dev/null \
  | grep -vE '/(\.venv|venv|site-packages|node_modules)/' | grep -q . \
  || nothing "no Python project anywhere in the repo — not a Python backend project"

# 1f. Ensure a git identity exists (an unattended commit fails without one). Set a
#     fallback author so the commit in Step 6 cannot fail mid-flight.
git config user.email >/dev/null 2>&1 || git config user.email "be-test-audit@users.noreply.github.com"
git config user.name  >/dev/null 2>&1 || git config user.name  "be-test-audit bot"
```

**1g. Detect the env/dependency manager** at the repo root and map it to a **RUN PREFIX**
used to invoke pytest. There is a repo-level **default** here; it is **re-detected per
package root** at verify time (Step 5), because a repo may keep the backend in `backend/`
with its own `uv.lock` while a sibling service uses poetry:

```bash
# ── envManagerDetection ───────────────────────────────────────────────────────
# Detect the Python dependency/environment manager AT A GIVEN DIRECTORY and map it
# to a RUN PREFIX used to invoke pytest. Mirrors the per-package PM detection
# (Step 5): there is a repo-level DEFAULT, and it is RE-RUN per package root at
# verify time (a repo may keep the backend in backend/ with its own uv.lock while a
# sibling service uses poetry).
#
# The universal, most-portable single-file invocation is `python -m pytest` — pytest
# also collects and runs unittest.TestCase classes, so one prefix covers BOTH styles.
#
# detect_env_at <dir> echoes the RUN PREFIX for that dir. It checks markers IN <dir>,
# then (caller-controlled) falls back to the repo root, then to a bare `python -m`.
# grep -qs silences "no such file" when pyproject.toml is absent. No shell globs are
# expanded directly (find -maxdepth 1 is used for requirements*.txt) so it never
# aborts under zsh's nomatch — verified in bash AND zsh.
#
# CRITICAL — a venv is returned as the OPAQUE MARKER 'venv:<dir>', NOT as a
# `. activate &&` fragment. A `&&`-bearing prefix CANNOT be wrapped by
# `env CI=1 timeout N …` in Step 5 (the shell would run `env`/`timeout` against the
# `.` source builtin -> `env: .: Permission denied`, rc 126, and the `&&` short-circuits
# so pytest NEVER runs). Step 5 decodes the marker and points pytest directly at the
# venv interpreter (`<dir>/bin/python -m pytest`), which composes cleanly under env/timeout.

detect_env_at() {
  D="$1"
  # requirements*.txt presence, glob-safe in zsh+bash (no bare-glob nomatch abort):
  _has_reqs() { [ -n "$(find "$1" -maxdepth 1 -name 'requirements*.txt' -print -quit 2>/dev/null)" ]; }

  if   [ -f "$D/uv.lock" ]     || grep -qsE '^\[tool\.uv\]'      "$D/pyproject.toml"; then
    printf '%s' 'uv run'                                  # uv
  elif [ -f "$D/poetry.lock" ] || grep -qsE '^\[tool\.poetry\]'  "$D/pyproject.toml"; then
    printf '%s' 'poetry run'                              # poetry
  elif [ -f "$D/pdm.lock" ]    || grep -qsE '^\[tool\.pdm\]'     "$D/pyproject.toml"; then
    printf '%s' 'pdm run'                                 # pdm
  elif grep -qsE '^\[tool\.hatch'                                "$D/pyproject.toml"; then
    printf '%s' 'hatch run'                               # hatch
  elif [ -f "$D/Pipfile" ] || [ -f "$D/Pipfile.lock" ]; then
    printf '%s' 'pipenv run'                              # pipenv
  elif [ -d "$D/.venv" ]; then
    printf '%s' "venv:$D/.venv"                           # plain pip + .venv (opaque marker; see Step 5)
  elif [ -d "$D/venv" ]; then
    printf '%s' "venv:$D/venv"                            # plain pip + venv  (opaque marker; see Step 5)
  elif _has_reqs "$D"; then
    printf '%s' 'python -m'                               # requirements.txt, no venv dir -> use ambient python
  else
    printf '%s' ''                                        # no marker here; caller falls back to repo root / 'python -m'
  fi
}

# Resolve the RUN PREFIX for a package root, falling back to the repo root, then to a
# bare 'python -m'. (ROOT is the repo top-level; PKG is this file's package root, which
# callers pass as a RELATIVE path — '.' or 'backend' — so compare against BOTH '.' and
# $ROOT before re-detecting at the repo root.)
run_prefix_for() {  # run_prefix_for <pkg_root>
  RP="$(detect_env_at "$1")"
  if [ -z "$RP" ] && [ "$1" != "." ] && [ "$1" != "$ROOT" ]; then RP="$(detect_env_at "$ROOT")"; fi
  [ -z "$RP" ] && RP='python -m'        # universal fallback; `python -m pytest` runs pytest + unittest
  printf '%s' "$RP"
}

# Repo-level DEFAULT (logged once in preflight):
RUN_PREFIX_DEFAULT="$(run_prefix_for "$ROOT")"
echo "Env manager (repo default): RUN_PREFIX='$RUN_PREFIX_DEFAULT' | universal invocation: python -m pytest"
```

**1h. Detect test runner(s) ACROSS THE WHOLE REPO, not just the root config.**
A common backend shape keeps the Python project in a subdirectory (`backend/`, `api/`,
`app/`, `src/`) with **no** config at the repo root; root-only detection would wrongly
conclude "no runner" and bail. Aggregate every non-vendored pytest-config file plus the
dependency declarations, and treat `conftest.py` anywhere as a strong pytest signal:

```bash
# ── runnerDetection ───────────────────────────────────────────────────────────
# Detect pytest vs unittest ACROSS THE WHOLE REPO (not just a root config). The Python
# project is OFTEN in a subdirectory (backend/, api/, app/, src/) with NO config at the
# repo root, so root-only detection would wrongly bail. Default to pytest — it collects
# and runs unittest.TestCase tests too, so it is the single runner for both styles.
# Bail cleanly with `nothing` if there is no Python test setup anywhere.
# (`nothing()` / `fail()` are the Step 1 helpers; reuse them verbatim.)

# Aggregate every tracked, NON-VENDORED pytest-config file body + the dependency decls.
CFG_HAY="$(
  git ls-files -- '*pyproject.toml' '*pytest.ini' '*tox.ini' '*setup.cfg' \
                  '*requirements*.txt' '*Pipfile' 2>/dev/null \
    | grep -vE '/(\.venv|venv|site-packages|\.tox|\.mypy_cache|\.pytest_cache|node_modules|build|dist)/' \
    | while IFS= read -r p; do cat "$p" 2>/dev/null; echo; done
)"
have_cfg() { printf '%s' "$CFG_HAY" | grep -qiE "$1"; }

# conftest.py ANYWHERE (non-vendored) is a strong pytest signal (config-file presence).
HAS_CONFTEST="$(git ls-files -- '*conftest.py' 2>/dev/null \
  | grep -vE '/(\.venv|venv|site-packages|\.tox|node_modules)/' | head -1)"

# pytest if: a pytest config section exists, conftest.py exists, or 'pytest' is a dep.
USES_PYTEST=0
have_cfg '\[tool\.pytest\.ini_options\]|\[pytest\]|\[tool:pytest\]|(^|[^a-z])pytest([^a-z]|$)' && USES_PYTEST=1
[ -n "$HAS_CONFTEST" ] && USES_PYTEST=1

# unittest if any tracked .py imports unittest / subclasses TestCase (covers stdlib-only repos).
USES_UNITTEST=0
git grep -lE '^[[:space:]]*import[[:space:]]+unittest|^[[:space:]]*from[[:space:]]+unittest|unittest\.TestCase|\(TestCase\)' \
  -- '*.py' 2>/dev/null \
  | grep -vE '/(\.venv|venv|site-packages|\.tox|node_modules)/' | grep -q . && USES_UNITTEST=1

echo "Runners: pytest=$USES_PYTEST unittest=$USES_UNITTEST | conftest=${HAS_CONFTEST:-none}"

# No Python test setup at all -> clean exit (healthy 'nothing').
if [ "$USES_PYTEST" = 0 ] && [ "$USES_UNITTEST" = 0 ]; then
  nothing "no Python test setup detected anywhere in the repo (no pytest config/conftest, no unittest tests)"
fi
# Default runner is ALWAYS pytest — it runs unittest.TestCase tests too, so a single
# `python -m pytest <file>` invocation covers both. (unittest signal only calibrates
# strictness; it does not change how files are run.)
RUNNER="pytest"
echo "Runner (default; also executes unittest tests): $RUNNER"
```

**1i. Detect multi-package layout** (a repo with several Python package roots — `backend/`,
`services/*`, `libs/*`). Env managers are re-detected **per package root** at verify time
(Step 5), because package A may use uv while package B uses poetry:

```bash
echo "Python package roots detected (markers anywhere, non-vendored):"
git ls-files -- '*pyproject.toml' '*setup.py' '*setup.cfg' '*tox.ini' '*Pipfile' '*requirements*.txt' 2>/dev/null \
  | grep -vE '/(\.venv|venv|site-packages|node_modules)/' \
  | while IFS= read -r p; do printf '  %s\n' "$(dirname "$p")"; done | sort -u
```

A candidate file's **package root** = the nearest ancestor directory containing a Python
project marker (`pyproject.toml`/`setup.cfg`/`setup.py`/`requirements*.txt`/`Pipfile`/
`tox.ini`); fallback: repo root. Step 3 computes this per file (see `pkg_root` below).

```bash
# ── packageRootRule ───────────────────────────────────────────────────────────
# The Python PACKAGE ROOT is the analog of the FE 'workspace root' / ws_root (Step 3).
# It is the nearest ANCESTOR directory of a test file containing any of:
#   pyproject.toml | setup.cfg | setup.py | requirements*.txt | Pipfile | tox.ini
# fallback: the repo root ($ROOT). We `cd` into it before running the test so the
# correct venv/manager AND the nearest conftest.py resolve — essential when the project
# lives in backend/ rather than at the repo root.
#
# pkg_root <file> echoes the package root dir (relative path, or '.' meaning repo root).
# requirements*.txt is matched with find -maxdepth 1 (no bare glob) so it never aborts
# under zsh's nomatch. Verified identical in bash AND zsh.

pkg_root() {  # pkg_root <repo-relative test path>
  d="$(dirname "$1")"
  while [ "$d" != "." ] && [ "$d" != "/" ]; do
    if [ -f "$d/pyproject.toml" ] || [ -f "$d/setup.cfg" ] || [ -f "$d/setup.py" ] \
       || [ -f "$d/Pipfile" ] || [ -f "$d/tox.ini" ] \
       || [ -n "$(find "$d" -maxdepth 1 -name 'requirements*.txt' -print -quit 2>/dev/null)" ]; then
      printf '%s' "$d"; return
    fi
    d="$(dirname "$d")"
  done
  printf '%s' "."          # fallback: repo root (we cd to $ROOT for '.')
}

# REL = the test path RELATIVE to the package root we cd into, so
# `cd <pkgroot> && python -m pytest <REL>` resolves even when the project is in backend/.
# $FILE is repo-root-relative (e.g. backend/tests/test_x.py); strip the leading "PKG/".
# When PKG is '.' (repo root) there is nothing to strip and REL == FILE.
rel_to_pkg() {  # rel_to_pkg <file> <pkg_root>
  if [ "$2" = "." ]; then printf '%s' "$1"; else printf '%s' "${1#"$2"/}"; fi
}
```

---

## STEP 2 — Discover candidate test files (ALL tracked test files)

**Goal:** list **every** Python test file tracked in the repo (no time window). No state file.

```bash
# ── discoveryPathspecs ────────────────────────────────────────────────────────
# 2a. Build the Python test-file pathspecs as POSITIONAL PARAMETERS (`set -- …`), never a
#     space-separated string variable — zsh does NOT word-split an unquoted $VAR, so a glob
#     string collapses into one literal pathspec that matches nothing. `set -- a b c` then
#     `-- "$@"` word-splits identically in bash AND zsh.
#
#     :(glob) magic makes `**` cross directories AND match at depth 0, so a root-level
#     test_foo.py / foo_test.py is found (default pathspec magic would MISS it). Bare
#     root-level variants are added belt-and-suspenders. Covers test_*.py, *_test.py, and
#     everything under tests/ and test/ directories (unittest layouts live there).
#     Verified: finds root-level, api/test_bar.py, and backend/tests/test_foo.py.
set -- \
  ':(glob)**/test_*.py'   ':(glob)test_*.py' \
  ':(glob)**/*_test.py'   ':(glob)*_test.py' \
  ':(glob)**/tests/**'    ':(glob)**/test/**' \
  ':(glob)tests/**'       ':(glob)test/**'

CANDIDATES_RAW="$(git ls-files -- "$@" 2>/dev/null | sed '/^$/d' | sort -u)"

# ── postFilter ────────────────────────────────────────────────────────────────
# 2b. POST-FILTER to *real* test files. The tests/ and test/ directory globs sweep in
#     conftest.py, __init__.py, fixtures, and factories — feeding those to the classifier
#     risks DELETING a shared module other tests import. So:
#       KEEP only basenames matching ^test_.*\.py$  OR  ^.*_test\.py$
#       DROP conftest.py, __init__.py, setup.py, fixtures*.py, factories*.py, factory*.py
#            (the Python analog of FE's shared src/test/* modules — NEVER delete these)
#       DROP anything under vendored/generated trees.
#     conftest.py is the Python analog of FE shared fixtures and is dropped here so it is
#     never even a candidate (the Step-4 export/import checks are the second line of defense).
CANDIDATES=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue                                   # added-then-deleted => gone; skip
  # Drop vendored / generated / cache / build / migration paths:
  case "$f" in
    */.venv/*|.venv/*|*/venv/*|venv/*|*/site-packages/*|*/__pycache__/*|\
    */.tox/*|*/.mypy_cache/*|*/.pytest_cache/*|*/build/*|*/dist/*|\
    */migrations/*|migrations/*|*/node_modules/*|node_modules/*) continue;;
  esac
  base="$(basename "$f")"
  # Drop shared helpers/config that must never be deleted (conftest = FE shared fixtures).
  # Includes the conventional shared base-class / helper / util module names that are
  # frequently imported by sibling tests (`from tests.test_base import BaseTestCase`); these
  # match ^test_.*\.py$ and would otherwise become deletion candidates. Pre-excluding them is
  # the first line of defense; the Step-4 import-check (b) is the second.
  case "$base" in
    conftest.py|__init__.py|setup.py) continue;;
    fixtures*.py|factories*.py|factory*.py) continue;;
    test_base.py|base_test.py|test_helpers.py|test_helper.py|helpers_test.py|test_utils.py|test_util.py|utils_test.py) continue;;
  esac
  # KEEP only real test-file basenames (covers pytest test_*.py and *_test.py + unittest):
  printf '%s' "$base" | grep -qE '^test_.*\.py$|^.*_test\.py$' || continue
  # include filter (if set, path must contain at least one include substring)
  if [ -n "$AUDIT_INCLUDE_SUBSTR" ]; then
    keep=0; for s in $AUDIT_INCLUDE_SUBSTR; do case "$f" in *"$s"*) keep=1;; esac; done
    [ "$keep" = 1 ] || continue
  fi
  # exclude filter
  skip=0; for s in $AUDIT_EXCLUDE_SUBSTR; do case "$f" in *"$s"*) skip=1;; esac; done
  [ "$skip" = 1 ] && continue
  CANDIDATES="$CANDIDATES$f
"
done <<EOF
$CANDIDATES_RAW
EOF
CANDIDATES="$(printf '%s' "$CANDIDATES" | sed '/^$/d' | sort -u)"

# 2c. No test files at all => nothing to audit. For the initial sweep, an empty list after
#     filtering means the repo genuinely has no Python test files matching the patterns.
if [ -z "$CANDIDATES" ]; then
  nothing "no Python test files found in the repo"
fi

# 2d. Enforce the per-run file cap (bounds an unattended run). Process first N; report rest.
TOTAL="$(printf '%s\n' "$CANDIDATES" | wc -l | tr -d ' ')"
CAPPED_OUT="$(printf '%s\n' "$CANDIDATES" | tail -n +"$((AUDIT_MAX_FILES+1))")"
CANDIDATES="$(printf '%s\n' "$CANDIDATES" | head -n "$AUDIT_MAX_FILES")"
echo "Discovered $TOTAL candidate test file(s); processing up to $AUDIT_MAX_FILES this run:"
printf '%s\n' "$CANDIDATES"
[ -n "$CAPPED_OUT" ] && { echo "Deferred (over cap):"; printf '%s\n' "$CAPPED_OUT"; }
```

> For this initial sweep the **entire content of each test file is in scope** — there is no
> "since" baseline, so read and classify every test in the file.

---

## STEP 3 — Per-candidate iteration, package-root + runner resolution, classification

Iterate over `$CANDIDATES`. For **each** file resolve its package root and run prefix, then read it
against the rubric. Track the set of files you actually change in `TOUCHED` (used by Step 6 —
**only these are staged**). Use this scaffold:

```bash
TOUCHED=""        # newline-separated list of files this run reworked OR deleted
REWORKED=""; DELETED=""; KEPT_FLAGGED=""; KEPT_OK=""   # for the report
ANY_ERROR=0

printf '%s\n' "$CANDIDATES" | while IFS= read -r FILE; do
  [ -z "$FILE" ] && continue
  PKG="$(pkg_root "$FILE")"                 # nearest ancestor with a Python marker, else '.'
  REL="$(rel_to_pkg "$FILE" "$PKG")"        # path to pass to pytest after cd
  PKG_ABS="$ROOT"; [ "$PKG" != "." ] && PKG_ABS="$ROOT/$PKG"   # absolute dir to cd into
  echo "==> $FILE   (package root: $PKG  | REL: $REL)"
  # ... read + classify (below); record verdict; act in Step 4; verify in Step 5 ...
done
```

> Note: a `while` loop fed by a pipe runs in a subshell in some shells, so variables set
> inside it (`TOUCHED`, counters, `ANY_ERROR`) may not survive. If you need them afterward,
> either drive the loop with a here-doc/`for` over the candidate list, or append per-file
> results to a temp file (`echo "$FILE	reworked" >> "$RESULTS"`) and read it back in Step 6.
> If you use the `$RESULTS`-file pattern, also persist the error flag (e.g. append a sentinel
> row `printf 'ERROR\t%s\n' "$FILE" >> "$RESULTS"` whenever a rework verify returns
> `ASSERTION-FAILURE`) and `grep -q '^ERROR' "$RESULTS"` in Step 7 so a mid-run failure can't be
> silently lost to the subshell. The simplest robust pattern for an agent is to **process one
> file at a time** and keep the running lists in your own working memory, writing each verdict
> row (and any error sentinel) to `$RESULTS`.

**For each file:** read it (don't grep-and-guess — grep *locates* suspicion; the verdict
comes from reading). Determine the **per-test-type calibration**, then assign each
`test_*` function / `TestCase` method (and the file overall) one of:

- **FAKE** — matches an anti-pattern, no green-flag/false-positive exemption applies.
- **MEANINGFUL** — exercises real code and asserts a real, behavior-sensitive outcome.
- **UNSURE** — genuinely ambiguous after reading. Default action: **KEEP and flag**.

### Strictness calibration by test type (avoid false positives)

- **Mock-heavy unit tests** (`unittest.mock`/`pytest-mock` patching collaborators): the
  **primary target**. Apply the full rubric strictly. Round-trip mock tautologies, patching
  the subject under test, bare `assert_called`, over-mocked units, re-implemented oracles,
  and framework-only checks live here.
- **Integration tests** (real service composing several real collaborators, only the
  network/boundary mocked): mostly legitimate. Only fake if the assertion reads the stub
  layer back with no app-visible effect, or the *subject itself* is mocked. Mocking the
  network/clock is NOT a red flag.
- **Functional / integration tests that need a DB or live services** (real Postgres/Redis,
  testcontainers, docker-compose, a transactional fixture): apply a **very high bar** before
  flagging — they exercise the real persistence/query path and are high-value. A test that
  ERRORS on a connection/fixture/service problem during verification is **unverified, not
  proven-fake**; mark it `reworked (unverified: needs DB/services)` and **never delete on the
  basis of an unrunnable verify**. When uncertain here: **KEEP-and-flag, never delete.**
- **Unfamiliar assertion vocabularies** the literal token `assert` may be absent while real
  assertions exist — `pytest.raises(...)`/`assertRaises` as a context manager, unittest
  `self.assertEqual`/`assertIn`/`assertRaises`, mock `.assert_called_with(...)`, Django
  `assertContains`/`assertJSONEqual`/`assertQuerySetEqual`, DRF helpers, syrupy `snapshot`,
  Hypothesis invariants, or a custom helper (`assert_valid(resp)`). Recognize the runner's
  assertion vocabulary **before** concluding "no assertion."

### The rubric — fake-test anti-patterns

For each: what makes it fake, how to spot it, how to salvage, and when deletion is allowed.

1. **Mock asserting its own configured return value (round-trip tautology).** The test
   configures a Mock to return V (`return_value`/`side_effect`), then asserts the same V
   comes back, with NO production code transforming it in between — it calls the **mock**,
   not the SUT. Cannot fail for any real bug. Spot: a `.return_value = X` followed in the same
   test by `assert <same mock>(...) == X` with the literal X repeated and the call target the
   mock itself. *Salvage:* mock only the boundary (DB row / HTTP body), call the actual
   service/function, assert the **transformed** output (formatting, branching, validation,
   aggregation) — `assert UserService(repo).display_name(1) == "Ann (#1)"`. *Delete only if*
   there is no production symbol to place between mock and assert (pure echo) AND an existing
   test already covers the real path AND the safety checks pass.

2. **Patching/monkeypatching the SUBJECT under test itself.** The test patches the very
   function/class/method it is supposed to verify (`monkeypatch.setattr(billing,
   "compute_total", lambda items: 42)` then `assert compute_total([]) == 42`), so the real
   implementation never runs and the test passes even if the SUT is deleted/broken. Spot:
   `@mock.patch`/`patch.object`/`mocker.patch`/`monkeypatch.setattr` whose target resolves to
   the SUT (matches the test name stem or the asserted symbol). *Salvage:* remove the patch on
   the SUT; if it depends on heavy I/O, patch ONLY that dependency (DB client, HTTP call,
   `time`/`uuid`), not the SUT, and assert the SUT's real computed result. *Almost never
   delete* — un-patch instead; delete only if, after un-patching, it exactly duplicates an
   existing meaningful test.

3. **`assert_called` / `.called` as the ONLY assertion (spy-existence tautology).** The sole
   assertion is that a mock was called (`assert_called`, `assert_called_once`, `assert
   mock.called`, `assert mock.call_count == 1`) with no meaningful argument check and no real
   effect. *Salvage:* assert the **arguments** when the collaborator contract is the point
   (`assert_called_once_with(to=user.email, subject=f"…")` with **derived** values), AND/OR
   assert the user-visible/state consequence (a row written, a returned DTO, a status
   transition). FAKE when args are absent/trivial/echoed; REAL when args are domain-meaningful
   values **derived** by the SUT. *Delete only if* the call has no meaningful args, no
   observable effect, AND an integration test already covers the interaction.

4. **Over-mocked unit — DB session, external clients, AND the service all mocked.** Every
   collaborator AND the service/repository under test are replaced by mocks, so no production
   line executes; every assertion references values defined in the mocks' `return_value`/
   `side_effect` in the same test. Spot: high count of `patch(`/`mocker.patch(`/`MagicMock(`
   in one test (3+), **including** a patch of the service/handler whose behavior is the
   subject. *Salvage:* un-mock the layer you actually want to test (the service); keep mocks
   ONLY at true boundaries (network, DB driver, clock, randomness); use a real in-memory
   DB/SQLite/session fixture so the repository code runs; assert the real composed output.
   *Delete only if*, after un-mocking, it duplicates an existing test of the same unit or is an
   irreducible smoke shell.

5. **Bare `Mock`/`MagicMock` without autospec — every attribute access silently succeeds.** An
   unspecced `Mock()`/`MagicMock()`/`AsyncMock()` answers ANY attribute/method call with a
   fresh auto-mock, so the test passes even when the SUT calls a method that doesn't exist or
   was renamed (the typo'd `svc.proccess_order.assert_called()` still "passes"). It cannot
   catch interface drift. Spot: a double for a concrete collaborator built with NO
   `spec=`/`spec_set=`/`autospec=`/`create_autospec`. **This AGGRAVATES the `assert_called` and
   over-mock patterns — flag in combination, not alone.** *Salvage:* add `autospec=True` or
   `create_autospec(RealClass)`/`spec=RealClass` so attribute typos and wrong arity raise;
   better, assert a real outcome. *Do not delete for lack of autospec alone* — rework by adding
   the spec.

6. **No assertion and no `pytest.raises` (executes code, checks nothing).** The test calls the
   SUT but has zero assertions, no `pytest.raises`/`assertRaises`/`self.assert*`/`.assert_*`. It
   only proves the code didn't raise. *Salvage:* add a behavior-sensitive assertion on the real
   result (a field value, a length, a status, a raised error via
   `pytest.raises(SpecificError)`). **BEWARE false positives:** parametrized smoke tests that
   intentionally just construct, custom helpers (`assert_valid(x)`), and `pytest.raises` used
   as a context manager — resolve helpers and context managers before concluding "no
   assertion." *Delete only if* there is genuinely nothing observable to assert AND it is
   redundant — prefer adding an assertion.

7. **Re-implementing the SUT computation to build the expected value (the oracle is the
   code).** The expected value is computed with the SAME algorithm/format the source uses
   (same `.format`, `round`, `Decimal`, regex, comprehension), or the SUT's own transform is
   called on both sides (`expected = name.lower().replace(" ", "-"); assert slugify(name) ==
   expected`). A logic bug changes both sides identically. Spot: the assertion's RHS recomputes
   with the same operations, or imports the SUT transform onto both sides. *Salvage:* replace
   with a **hand-verified hardcoded literal** oracle (`assert slugify("Hello World") ==
   "hello-world"`) at boundary/rounding/locale/edge cases. *Delete only if* every case is
   tautological AND the function is trivial/covered elsewhere. Distinguish from building INPUT
   fixtures (fine) — the smell is duplicated logic on the EXPECTED-OUTPUT side.

8. **Trivially-true / self-equality assertions.** `assert True`, `assert 1 == 1`, `assert obj
   == obj`, asserting a literal just assigned, `assert isinstance(x, T)` on a value the test
   constructed as `T`, or LHS textually identical to RHS. *Salvage:* recover the intended check
   and assert it against an INDEPENDENT expected value or a real outcome produced by the SUT
   (not the literal the test just set). *Delete* the block if it contains only vacuous matchers
   with no recoverable intent; delete the whole file only if every block is vacuous and safety
   checks pass.

9. **Asserting a mocked collaborator's echoed/round-tripped fixture through the SUT with no
   transformation.** A boundary is mocked to return V, the SUT is called, but the SUT is a pure
   passthrough (or the asserted field equals the raw fixture), so the assertion just confirms
   the mock's value survived an identity hop — no branching/formatting/validation is exercised
   even though real code is nominally on the path. Spot: `patch(..., return_value=V)` then
   `assert sut_call(...) == V`/`[key] == V[key]` unchanged. *Salvage:* mock only the boundary,
   assert the **transformed** result (a derived field, a filtered subset, a formatted string,
   an error branch); if the SUT genuinely has no logic, move the assertion to where logic
   exists or test the boundary contract via args. *Delete only if* the SUT is a trivial
   passthrough and the boundary contract is covered elsewhere.

10. **Conditional / swallowed / skipped assertions and focused tests (may never run).**
    Assertions guarded by an `if` that can be false (so they silently skip — `if row: assert
    row.name == "Ann"`), inside a `try` whose `except` only logs/passes, after an early
    `return`, or marked `@pytest.mark.skip`/`@unittest.skip`/`@pytest.mark.xfail` (without
    `strict`). Also unconditional `xfail` masking real failures. Spot:
    `@pytest.mark.skip`/`@unittest.skip`/`@pytest.mark.xfail`/`pytest.skip(`, `if .*:` enclosing
    the only `assert`, `try:` with a bare/`pass`/log-only `except`. *Salvage:* set up state
    deterministically and assert UNCONDITIONALLY; for expected exceptions use
    `pytest.raises(SpecificError)`/`assertRaises`; for async `await` the coroutine and assert;
    make `xfail` strict or fix and un-skip; remove dead `if` guards by arranging the
    precondition. *Delete* permanently-rotted skip/xfail shells referencing removed APIs, after
    safety checks.

11. **Patching where the symbol is DEFINED rather than where it is USED (mock never
    intercepts) plus asserting on the unintercepted result.** `@mock.patch` targets the module
    where a name is defined, but the SUT did `from x import y`, so the SUT's local reference is
    never replaced; the assertion then either tests real code accidentally or tests the
    leftover mock object directly. Spot: `@mock.patch("<module-where-defined>…")` while the SUT
    uses `from <module> import <name>` (target should be `<sut_module>.<name>`); the assert
    compares against the patch's `return_value` object identity. *Salvage:* patch at the point
    of use (`patch("app.svc.now")`) so the SUT sees the double, then assert the SUT's real
    output; OR drop the patch and assert real behavior. Prefer `autospec=True`. **Rework (fix
    the patch target) — do not delete for this reason.**

12. **Time/sleep-based or unconditional-wait tests with no following assertion.** The test
    relies on `time.sleep(...)`/`asyncio.sleep(...)`/a fixed delay then asserts nothing
    discriminating (or asserts a value the mock was told to return). Spot: `time.sleep(`/
    `asyncio.sleep(` followed by end-of-test or only a vacuous/mock-echo assertion. *Salvage:*
    replace fixed sleeps with deterministic synchronization (poll a condition with a bounded
    wait that ASSERTS the awaited state, await the real coroutine/future, use a fake clock and
    advance it) and add a behavior assertion on the resulting state/output. *Delete* the sleep
    line (not necessarily the test); delete the test only if nothing assertable remains.

13. **Asserting framework/library behavior instead of application logic.** Verifying that a
    library (Pydantic validation, SQLAlchemy mapping, the ORM, Flask/FastAPI routing,
    dataclasses) faithfully stores/returns a constant the test passed in, with no application
    decision logic between input and asserted output (`User(name="Ann"); assert u.name ==
    "Ann"`). Spot: construct-then-read-back with the asserted value identical to the
    constructor literal and no SUT method invoked between. *Salvage:* re-target at the app's own
    decision logic — a custom validator that rejects bad input
    (`pytest.raises(ValidationError)`), a computed property, a serializer that transforms, a
    default-derivation rule. Distinguish from testing a real custom validator/`__post_init__`/
    computed property (that IS app logic — keep). *Delete only if* the model is a pure
    passthrough with no custom logic.

#### Endpoint / route-level anti-patterns (FastAPI / Flask / Django / DRF)

14. **Hollow route-smoke: status-code-only on a trivial route.** Asserts only that a request
    returned 200/201/204 (sometimes plus a constant body) on a health/ping/static-constant
    route with no branching/validation/DB/serialization — it proves the framework can route a
    URL, not that any logic is correct. Spot: assertions ONLY on `resp.status_code`/`.status`
    with no assertion on `resp.json()`/`resp.text`/headers/DB; route handler is a one-line
    constant `return`; route path matches `/(health|ping|status|live|ready|version)`.
    *Salvage:* re-point at a route with real logic, or assert the response **body** the handler
    computed/serialized, validation behavior (422 + error detail on bad input), or a real side
    effect (a row now exists). A single proportionate status+body assert on a genuinely static
    route is fine. *Delete only if* the endpoint is a pure static constant AND an equivalent
    smoke test exists elsewhere AND safety checks pass.

15. **Mocking the ORM/session and asserting the mock instead of real DB state.** The database
    layer (SQLAlchemy `Session`/`Query`, Django `Model.objects`, a repository) is replaced by a
    `MagicMock`/`patch`, told what to return, and the test asserts the route returned the mock's
    value or that the mocked query was called. No SQL runs — wrong filter, missing commit,
    constraint violation, wrong column are invisible. Spot: `patch`/`MagicMock` of a DB symbol
    (`.session`/`Session`/`db`/`engine`/`query`/`objects`/`get_db`/`SessionLocal`,
    `mock_session`/`mock_db`/`mock_query`/`mock_repo`), chained
    `.return_value.filter.return_value…`, assertion target is the mock. *Salvage:* swap the ORM
    mock for a REAL test database/session (a `db_session`/transactional fixture, in-memory
    SQLite, or disposable Postgres), seed real rows, hit the route, assert BOTH the response AND
    the DB state. Assert against state, never against the mock. *Prefer un-mocking;* if no test
    DB exists and one cannot be wired, mark `reworked (unverified: needs DB)` and keep — never
    delete on an unrunnable verify.

16. **Mocking the outbound HTTP client and asserting the mock's return, not the client/parse
    path.** An outbound call (`requests`/`httpx`/`aiohttp`/an SDK) is mocked to return a canned
    payload and the test asserts that payload came back out — with no real URL/param building,
    status handling, JSON parsing, error mapping, retry, or response-model validation between.
    (Mocking the EXTERNAL HTTP boundary is legitimate — but only when REAL parsing/validation/
    business logic runs on the result.) Spot: `patch` of an HTTP symbol (or
    `responses`/`respx`/`httpx_mock`/`requests_mock`/`aioresponses`) with the function output
    `==` the exact configured `return_value`, byte-identical, no transform. *Salvage:* configure
    the mock with a RAW upstream shape and assert the TRANSFORMED result (renamed/snake_cased
    fields, parsed `datetime`, computed/aggregated values, mapped error → domain exception via
    `pytest.raises(UpstreamError)` on a 500, Pydantic validation on a malformed payload, or the
    correct URL/headers/auth your code BUILT from inputs). *Delete only if* the function is a
    pure passthrough with no parsing/validation of its own AND covered elsewhere.

17. **Asserting a stubbed response body the test itself injected (no transform).** A dependency
    override / monkeypatched service / fixture returns a fixed object, the endpoint is called,
    and the test asserts the response equals that exact object — but the handler does no work
    (no serialization difference, no field selection, no computed field, no status logic). Spot:
    `app.dependency_overrides[...] = lambda: V` (FastAPI) or `monkeypatch.setattr(service,
    "get", lambda: V)` where the asserted `resp.json()`/return `==` V verbatim. **Dependency
    overrides themselves are a legitimate pattern — never flag the override, only the echo
    assertion.** *Salvage:* inject a richer raw input and assert the handler's TRANSFORM
    (`response_model` dropping internal fields, a computed/derived field, role-based filtering,
    403 when the injected user lacks a permission, a pagination envelope). *Delete only if* the
    route is a pure identity passthrough AND covered elsewhere.

18. **Testing the serializer/framework faithfully echoes a constant.** Verifies that a Pydantic
    model / DRF serializer / marshmallow schema serializes a hardcoded input to the obvious
    output with no logic in the schema (`UserSchema(**data).model_dump() == data` where the
    schema has no validators, computed fields, aliases, or transforms). Spot:
    `.model_dump()`/`.dict()`/`.data` compared `==` to the SAME literal passed into the
    constructor, no `@validator`/`@field_validator`/`@computed_field`/`alias=`/
    `SerializerMethodField`/custom `to_representation`. *Salvage:* re-target at the schema's
    actual LOGIC — a validator rejecting bad input (`pytest.raises(ValidationError)`), an
    `alias`/`by_alias` rename, a `@computed_field`/`SerializerMethodField` derived value,
    coercion (`str → datetime`/`Decimal`), excluded write-only/internal fields, default
    injection. *Delete only if* the schema has zero validators/computed/alias logic AND is
    exercised through an endpoint test elsewhere.

19. **Validation/error path asserted only by status code, body unread.** Bad input expecting a
    4xx asserts only `status_code == 422/400` without asserting WHICH field failed or the error
    message — so any 4xx (wrong field, unrelated validation, even an auth 401 misfire) passes.
    Borderline (a 422-on-bad-input IS some signal), so flag only when paired with a trivially
    invalid input and no body assertion. Spot: POST/PUT with malformed input then ONLY
    `status_code in 4xx` with no assertion on `resp.json()['detail']`/`errors`/field name.
    *Salvage:* assert the specific failing field and/or message (`resp.json()['detail'][0]
    ['loc'][-1] == 'email'`), and add a positive counterpart (valid input → 201 + created row).
    *Rarely delete* — these guard real validation; only delete if it duplicates a stronger
    validation test.

20. **Async coroutine asserted but never awaited (test passes vacuously).** An async endpoint/
    service is called but the returned coroutine is never awaited (or the test fn is `async` but
    not marked, so pytest skips/never runs the body), so the assertion compares a coroutine
    object or never executes. Common with `httpx.AsyncClient`/`asyncpg`/SQLAlchemy async. Spot:
    `async def test_` without a nearby `@pytest.mark.asyncio` AND no `asyncio_mode = auto` in
    pyproject/pytest.ini/setup.cfg; or `assert <coro>` / an async call result with no `await`.
    *Salvage:* add `@pytest.mark.asyncio` (or set `asyncio_mode = auto`), `await` every
    coroutine, use the project's async client/session fixture, and assert the awaited result.
    **Never delete on this basis alone — it is almost always a fixable wiring bug;** if the
    async harness cannot be wired in-environment, mark `reworked (unverified: needs async
    harness)` and keep.

> Endpoint anti-patterns (14–20) co-occur with the unit ones (1–13): a route test can be both
> over-mocked (4) and hollow-route-smoke (14). Apply all that match.

### Green flags — NEVER flag these as fake

- Mocks confined to TRUE boundaries (DB driver / SQLAlchemy engine, network:
  requests/httpx/aiohttp/responses/respx/vcr, the clock via freezegun or a fake `now`,
  randomness/`uuid`, message brokers, S3/cloud SDKs, third-party APIs) while the SUT and its
  pure logic run for REAL and the assertion targets the SUT's computed/transformed output.
- `assert_called_once_with(...)` / `assert_has_calls([...])` / `assert_awaited_with(...)` where
  the asserted ARGUMENTS carry domain meaning AND are DERIVED by the SUT from its inputs (ids,
  formatted payloads, merged/validated values, query parameters, built URL/headers/auth) — a
  legitimate collaborator-contract test even though the callee is a mock.
- Independently-derived, hand-verified hardcoded expected values (golden literals) — NOT
  recomputed with the source's own algorithm and NOT obtained by calling the SUT's transform on
  the expected side.
- `pytest.raises(SpecificError, match='regex')` / `assertRaises(SpecificError)` /
  `assertRaisesRegex(...)` (with a specific exception type, ideally `match=` on the message, or
  asserting `exc.value` attributes) — a real negative-path assertion, never count as vacuous.
- `create_autospec(...)` / `patch(..., autospec=True)` / `spec=`/`spec_set=` doubles — these
  strengthen tests by making attribute typos and wrong arity raise; their presence is a quality
  signal, not a smell.
- Real DB/integration via a transactional fixture, in-memory SQLite, `testcontainers`, or a
  docker-compose service where the actual repository/query/migration code executes and the
  assertion checks persisted state (row count, a refreshed column, a cascade delete, an
  IntegrityError on a constraint).
- `@pytest.mark.parametrize` mapping DISTINCT inputs to DISTINCT, independently-specified expected
  outputs (golden table), including explicit edge/boundary/error rows.
- FastAPI/Flask/Django/DRF `TestClient`/`APIClient`/test-client calls that hit a real route, run
  the real view/handler, and assert on the status code AND the response body content / a DB side
  effect; auth/permission outcomes (401 on missing token, 403 on wrong role, 404/403 for a
  non-owner) driven through the real auth dependency/middleware.
- Async tests that `await` the real coroutine (pytest-asyncio / anyio / `asyncio.run`) and assert
  the resolved value or resulting state, using `AsyncMock` only at boundaries.
- Property-based tests (Hypothesis `@given`) that assert an invariant/round-trip property over
  generated inputs against an independent oracle, not the SUT's own recomputation.
- `assert_not_called()` / `call_count == 0` used as a DISCRIMINATING negative assertion (proving
  the SUT did NOT take a path under a given condition), paired with the positive case.
- Celery/background tasks run for real (`task_always_eager=True` or calling the task body
  directly) with the test asserting the task's DB/side-effect, not just that it was scheduled.
- unittest `assertEqual`/`assertTrue`/`assertIn`/`assertRaises`/`assertContains`/`assertJSONEqual`
  etc., Django `assertRedirects`/`assertQuerySetEqual`, `caplog`/`capsys` assertions on specific
  output, and custom assertion helpers — all assert without a bare `assert` token.
- Fixtures/factories (`@pytest.fixture`, factory_boy/model-bakery) that build realistic input data
  which then flows through real SUT code before an assertion on transformed output — setup is not
  the test; judge the `assert`.

### False-positive traps — looks fake, is actually fine (check before flagging)

- **A `def test_*` with no literal `assert` is NOT automatically hollow:** the assertion may be
  `pytest.raises(...)`/`assertRaises` as a context manager, a `self.assert*` unittest method, an
  `.assert_called_with(...)` on a mock, a custom helper (`assert_valid(resp)`,
  `assert_response_ok(r)`), Django `assertContains`/`assertRedirects`/`assertQuerySetEqual`, a
  syrupy `snapshot`, or a Hypothesis invariant. Resolve helpers, context managers, and unittest
  assert methods before concluding "no assertion."
- **conftest.py is the Python analog of shared FE fixtures** — it defines fixtures, hooks, and
  plugins for a whole directory tree. NEVER delete a conftest.py, and never treat its lack of
  `assert`/`test_` functions as "fake." Same for shared `fixtures*.py`, `factories*.py`,
  `factory*.py`, `setUp`/`setUpClass`/`tearDown`/`@pytest.fixture` providers, and any module other
  tests import. These contain no assertions **by design**.
- **Mocking the NETWORK/DB driver/clock/queue is not "mock-of-mock."** If ANY assertion targets the
  SUT's real transformed output, persisted state, a status code, a raised domain exception, or a
  derived call-arg, the real service/model/serializer/query-builder ran. Judge by the assertion
  TARGET, not by the presence of a `patch`/`Mock`. A stub at the input boundary is fine; only fake
  if the assertion ALSO reads that stub's value straight back with no app-visible effect.
- **`assert_called_once_with(...)` with meaningful DERIVED arguments is a real contract test**
  (analytics events, outbound API payloads, `on_commit` callbacks, enqueued jobs, fire-and-forget
  email/webhook side effects whose contract IS the args) — only BARE `assert_called`/`.called`
  with no/echoed args and no effect is fake.
- **`app.dependency_overrides[...]` (FastAPI) and `monkeypatch.setattr`/`setenv` are STANDARD,
  healthy DI/config patterns.** Flag only the specific assertion that echoes the injected literal
  verbatim — never flag the override mechanism itself, and never the override of a DB/auth
  dependency that is then exercised by real handler logic.
- **`response is not None` / `obj is not None` on a value from a DB QUERY or an endpoint** (which
  could legitimately be absent) is a real existence check — NOT vacuous. Only `is not None` on a
  literal assigned in the same block is fake.
- **Re-implementation-LOOKING code that builds INPUT fixtures** (computing a date/id/payload to
  FEED the SUT) is fine. The anti-pattern is computing the EXPECTED OUTPUT with the source's own
  algorithm — confirm the duplicated logic sits on the assertion (expected) side, not the input
  side.
- **`@pytest.mark.parametrize` with hardcoded golden expected values is valid and high-value;**
  only flag when the table's `expected` column is produced by calling the SUT's own transform.
- **Faking `Date`/`time`/`uuid`/random (freezegun, `time-machine`, `monkeypatch.setattr`) is
  REQUIRED for determinism;** fake only if the assertion reads the faked primitive straight back,
  real if it asserts a downstream computed effect (an expiry date derived, a deterministic token
  in the persisted row).
- **`skipif`/`skipUnless`/`importorskip` with a REAL condition** (`sys.platform`, missing optional
  dependency, Python version, env/service gate) are legitimate environment guards — NOT rotted
  shells. `xfail(strict=True, reason='<issue>')` is a CORRECT pin of a known bug. Only
  unconditional/reasonless skip/xfail, or bodies referencing removed APIs, are the anti-pattern.
- **`pytest.raises`/`assertRaises` is the CORRECT way to assert an expected exception** — do NOT
  confuse it with a try/except that swallows failures. `raises` ASSERTS an exception occurred (and
  fails if it doesn't); a bare `except/pass` DISCARDS a failure. The presence of `raises` is a
  green flag.
- **Integration tests that mock ONLY the external boundary and let a real parent service compose
  several real collaborators** are high-value composition coverage — keep, unless a collaborator
  that IS the subject is itself stubbed and asserted on.
- **`assert_not_called()` / `call_count == 0`** can be a meaningful negative assertion (the SUT
  correctly skipped a side effect) — read whether it discriminates a real branch.
- **A small pure function/model/thin endpoint covered by a single construct/request + one specific
  value/body assertion is PROPORTIONATE** — do not demand elaborate behavior for trivial code;
  keep it. Only flag when the SINGLE assertion is itself vacuous or echoes a stub.
- **A test that ERRORS on a DB/Redis/connection/fixture/service problem during verification is
  UNVERIFIED, not proven-fake.** Mark such a rework `unverified: needs DB/services` and NEVER
  delete on the basis of an unrunnable verify — only an assertion-level pass proves a rework and
  only a clean run proves a deletion is safe.
- **A migration test, a conftest plugin, a `setup.py`/`__init__.py`, or a factories module under
  tests/ is NOT a fake test** — the post-filter drops these; if one slips through, exclude it
  rather than delete it. Status-only on a 204 DELETE / 304 / 302-redirect-with-Location can be
  legitimate — assert the side effect or the header rather than deleting.

### Grep starters (to LOCATE suspicion — never to decide a verdict)

```bash
F="$FILE"
grep -nE '\.return_value\b|return_value=|side_effect' "$F"                   # round-trip / over-mock candidates
grep -nE '\.assert_called\b|\.called\b|\.call_count|assert_called_once' "$F" # spy-existence (check for derived args)
grep -nE '@(mock\.)?patch\(|patch\.object\(|mocker\.patch|monkeypatch\.setattr' "$F"  # patch targets (boundary vs SUT)
grep -cE 'patch\(|MagicMock\(|Mock\(|AsyncMock\(' "$F"                       # high count => possible over-mock
grep -nE 'MagicMock\(|Mock\(|AsyncMock\(' "$F"; grep -nE 'autospec|spec=|create_autospec' "$F"  # unspecced doubles
grep -nE '@pytest\.mark\.(skip|xfail)|@(unittest\.)?skip|@expectedFailure|pytest\.skip\(' "$F"  # skipped/xfail
grep -nE 'except[^:]*:\s*(pass|\.\.\.)|^\s*if .*:\s*$' "$F"                  # swallowed / conditional assertions
grep -nE 'time\.sleep\(|asyncio\.sleep\(' "$F"                              # fixed-time no-op waits
grep -nE 'assert\s+True\b|assert\s+1\s*==\s*1|assertTrue\(True\)' "$F"       # tautologies
grep -nE '\.status_code\b' "$F"                                             # status-only route-smoke candidates
grep -nE '\.model_dump\(\)|\.dict\(\)|\.data\b|dependency_overrides' "$F"    # serializer-echo / injected-stub candidates
grep -nE 'async def test_' "$F"; grep -nE 'asyncio_mode|@pytest\.mark\.asyncio' "$F"  # un-awaited async hazard
grep -cE 'assert |assertRaises|pytest\.raises|self\.assert|\.assert_called' "$F"  # 0 => possible no-assertion (or a DSL — verify!)
```

---

## STEP 4 — Act (rework, else delete; keep-and-flag when unsure)

**DRY-RUN GATE — first executable line of the action phase. Do not edit/delete past this
point when previewing:**

```bash
if [ "$AUDIT_DRY_RUN" = "1" ]; then
  echo "DRY RUN: classification only — no edits, no deletes, no branch, no PR."
  # emit the verdict report (Step 6 body builder) and stop.
  echo "AUDIT_RESULT=ok (dry-run): classified $TOTAL file(s); no changes made."
  exit 0
fi
```

**Action bias: REWORK first; DELETE only when nothing real can be tested.** For each
block/file:

- **MEANINGFUL** → leave untouched.
- **UNSURE** → leave untouched, record in the PR table as `keep (flagged)` with the reason.
- **FAKE & salvageable** → **rework** following the rubric's *Salvage* guidance:
  - Put REAL code between a mock and the assertion — mock only the boundary, let the real
    service format/branch/validate, and assert the **transformed** result (differs from the raw
    fixture).
  - Un-patch the SUT (or a mocked sibling/service) when feasible; keep mocks only at boundaries;
    fix patch targets to the point of USE; add `autospec=True`/`spec=` so attribute typos raise.
  - Replace existence/echo with a behavior- or content-sensitive assertion on the real result,
    persisted DB state, status code AND body, or a derived call-arg.
  - Replace computed/echoed expectations with **hand-verified hardcoded** oracles.
  - Upgrade `assert_called()` to `assert_called_once_with(<derived args>)` and/or assert the
    user-visible/state consequence.
  - Narrow over-broad `pytest.raises(Exception)` to a specific exception subclass + `match=`.
  - Replace fixed sleeps with deterministic waits/eager task execution; add
    `@pytest.mark.asyncio` + `await` to async; convert try/except-pass into
    `pytest.raises`/`assertRaises`; make `xfail` strict or fix and un-skip.
  - After editing, append the path to `TOUCHED` and **verify** (Step 5).
- **FAKE & unsalvageable** → **delete** the block (or the whole file if it becomes empty),
  allowed only when **all** the deletion safety checks below pass.

### Pre-deletion safety checks (ALL must pass; on ANY uncertainty → keep-and-flag)

```bash
# (a) Does the file define a SHARED symbol other tests can consume? If so it doubles as a
#     shared module and a whole-file delete can break importers/siblings — prefer keep-and-flag.
#     Two distinct cases, both gated here (mirrors FE's "ANY shared export => keep" intent):
#
#   (a1) A module-scope @pytest.fixture (or @fixture) — a fixture in a test_*.py is injectable
#        into SIBLING tests by NAME (pytest fixture name-injection, NO import statement), so it
#        CANNOT be proven unused by an import grep. Keep-and-flag REGARDLESS of whether the file
#        also contains test_ functions, and NEVER whole-file `git rm` a fixture-defining file —
#        at most edit out an individual dead test BLOCK, never the file.
if grep -qE '^[[:space:]]*@(pytest\.)?fixture' "$FILE"; then
  echo "  $FILE defines a @pytest.fixture — sibling tests may consume it by name-injection (no import). KEEP-and-flag; never whole-file delete."
  # record as keep (flagged): "defines a shared fixture (sibling name-injection)"; do NOT git rm the file.
  # (If individual NON-fixture test blocks are fake+unsalvageable, you may edit THOSE out, but the file stays.)
fi

#   (a2) Other shared definitions with NO own test_ functions (a pure helpers/factories module
#        that slipped past the discovery post-filter) — also keep-and-flag.
if grep -qE '^[[:space:]]*def [a-z_]+\(|^[[:space:]]*class [A-Z][A-Za-z0-9_]*\(|import factory|factory\.Factory|DjangoModelFactory|pytest_plugins' "$FILE" \
   && ! grep -qE '^[[:space:]]*def test_|^[[:space:]]*async def test_|class Test' "$FILE"; then
  echo "  $FILE looks like a shared module (factories/helpers/plugins, no test_ functions). KEEP-and-flag instead of delete."
  # record as keep (flagged): "exports shared symbols"; do NOT delete.
fi

# (b) Is the file imported anywhere else? Match `from <pkg.>stem import` / `import <stem>`
#     by the module stem (filename without .py), INCLUDING the stem as a non-first item in a
#     multi-name `from <pkg> import a, stem` list. This is a heuristic; conftest/fixture name
#     injection and alias/namespace-package imports may be missed, so it only *raises* caution —
#     it never authorizes a delete on its own. (Shared base-class/helper modules conventionally
#     named test_base.py / test_helpers.py / test_utils.py are protected primarily by THIS check;
#     they are also pre-dropped from candidacy in the Step 2 post-filter.)
STEM="$(basename "${FILE%.py}")"                 # e.g. test_user  (module name)
if git grep -nE "(from[[:space:]]+[A-Za-z0-9_.]*${STEM}[[:space:]]+import|import[[:space:]]+[A-Za-z0-9_.]*${STEM}([[:space:]]|$|,)|,[[:space:]]*${STEM}([[:space:]]|$|,))" \
     -- '*.py' 2>/dev/null | grep -v ":$FILE:" | grep . ; then
  echo "  $FILE appears to be imported elsewhere — KEEP-and-flag instead of delete."
  # record as keep (flagged): "imported by other files"; do NOT delete.
fi

# (c) Belt-and-suspenders for fixture name-injection (caught primarily by (a1) above): if the
#     file defines any @pytest.fixture, grep sibling test files in the SAME directory for the
#     fixture's NAME used as a test parameter before allowing any whole-file deletion. A match
#     means a sibling consumes it by injection with no import -> KEEP-and-flag, never delete.
# Extract each fixture's function name: the `def <name>(` on the line after an @fixture decorator.
FIXNAMES="$(awk '/^[[:space:]]*@(pytest\.)?fixture/{f=1;next} f&&/^[[:space:]]*def /{sub(/^[[:space:]]*def[[:space:]]+/,"");sub(/\(.*/,"");print;f=0} f&&!/^[[:space:]]*@/{f=0}' "$FILE" 2>/dev/null)"
if [ -n "$FIXNAMES" ]; then
  SIBDIR="$(dirname "$FILE")"
  for fn in $FIXNAMES; do
    # NOTE: git grep's POSIX -E does NOT honor `\b`; delimit the name with a non-word class
    # instead. Restrict to sibling .py files in the same directory. A hit => a sibling test
    # takes the fixture as a parameter (name-injection) -> KEEP-and-flag, never delete.
    if git grep -nE "def[[:space:]]+test_[A-Za-z0-9_]*\([^)]*[^A-Za-z0-9_]?${fn}[^A-Za-z0-9_]" \
         -- "${SIBDIR}/*.py" 2>/dev/null | grep -v ":$FILE:" | grep . ; then
      echo "  $FILE fixture '$fn' is consumed by a sibling test (name-injection) — KEEP-and-flag; never delete."
    fi
  done
fi
```

Deletion is allowed **only** when (a) it exports nothing shared, (b) nothing imports it, **and**
one of:
- there is genuinely nothing user-visible/behavioral to assert, **or**
- the test is fundamentally redundant (a stronger/integration/functional test already covers it), **or**
- a meaningful rework is impossible (e.g. a rotted permanently-skipped stub referencing a removed API).

To delete: use `git rm -f -- "$FILE"` (the `-f` is required if you had already edited the file
in the working tree before deciding to delete; plain `git rm` refuses on a modified file). For
removing a dead *block* (not the whole file), edit it out. Append `$FILE` to `TOUCHED`, then
**run the importer/sibling files (Step 5) — this verification is MANDATORY and gating for
deletions.** If the importers can't be verified green, **revert the deletion
(`git checkout -- "$FILE"` / `git restore "$FILE"`) and keep-and-flag** instead.

---

## STEP 5 — Verify (ONLY the affected file(s) — never the whole suite)

After every rework, run **only** that test file. After every deletion, run the **sibling files
in the same directory** and the files that imported the removed file — never the whole suite.
A reworked test must **pass and be meaningful**; a deletion must leave importers green. If a
rework can't be made to pass meaningfully, fix it or fall back to deletion-with-justification —
**never ship red**.

**Re-detect the env manager from the FILE's package root** (mixed multi-package repos), and run
with a hard timeout, `CI=1`, no watch, and an exact-file path that is **package-root-relative**
(after `cd` into the package root — never a repo-root-relative path). pytest has no watch mode by
default (good); if a project's `test` script wraps `pytest-watch`/`ptw`, IGNORE it and invoke
pytest directly. `python -m pytest` runs pytest AND unittest tests, so this single form covers
both:

```bash
# ── verifyCommands ────────────────────────────────────────────────────────────
# Verify exactly ONE file, from its package root (re-detect manager per package; hard
# timeout; CI=1; no watch). `python -m pytest` runs pytest + unittest, so this single form
# covers both. Verified in bash AND zsh, incl. the rc=124 timeout path.

# Per-candidate (PKG/REL from packageRootRule, computed in Step 3):
PKG="$(pkg_root "$FILE")"
REL="$(rel_to_pkg "$FILE" "$PKG")"
PKG_ABS="$ROOT"; [ "$PKG" != "." ] && PKG_ABS="$ROOT/$PKG"
RUN_PREFIX="$(run_prefix_for "$PKG")"            # RE-DETECT manager for THIS package root

# Portable hard-timeout binary: GNU `timeout`, brew `gtimeout`, or none (macOS often
# lacks it — verified absent on the dev box). The timeout is the backstop that keeps a
# wedged runner from hanging the run forever.
if   command -v timeout  >/dev/null 2>&1; then TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_BIN="gtimeout"
else TIMEOUT_BIN=""; fi

# Build the pytest invocation. -p no:cacheprovider keeps the run side-effect-free; -q quiet.
#
# CRITICAL — venv handling. detect_env_at returns a plain venv as the opaque marker
# 'venv:<dir>'. We must NOT splice a `. activate &&` fragment into a string that then gets
# prefixed by `env`/`timeout`: the shell would run `env`/`timeout` against the `.` source
# builtin (env: .: Permission denied, rc 126) and the `&&` would short-circuit so pytest
# never runs. Instead, point pytest DIRECTLY at the venv interpreter
# (<dir>/bin/python -m pytest) — it composes cleanly under `env CI=1 timeout N …` and needs
# no activation. All other prefixes (uv/poetry/pdm/hatch/pipenv run, or bare `python -m`)
# are single command tokens that wrap cleanly as-is.
case "$RUN_PREFIX" in
  venv:*)
    # Resolve the venv interpreter as an ABSOLUTE path so it composes under env/timeout and
    # is independent of cwd. The marker dir is package-relative ('backend/.venv', './.venv')
    # when the package itself has the venv, or absolute ('$ROOT/.venv') when run_prefix_for
    # fell back to the repo-root venv. Make it absolute against $ROOT if relative — this also
    # avoids the 'backend/backend/.venv' double-prefix bug, since we never re-prefix PKG_ABS.
    VENV_DIR="${RUN_PREFIX#venv:}"
    case "$VENV_DIR" in /*) ;; ./*) VENV_DIR="$ROOT/${VENV_DIR#./}";; *) VENV_DIR="$ROOT/$VENV_DIR";; esac
    PYBIN="$VENV_DIR/bin/python"
    [ -x "$PYBIN" ] || PYBIN="$VENV_DIR/Scripts/python"     # POSIX or Windows layout
    CORE="\"$PYBIN\" -m pytest \"$REL\" -p no:cacheprovider -q" ;;
  "python -m")
    CORE="python -m pytest \"$REL\" -p no:cacheprovider -q" ;;                # avoid 'python -m python -m'
  *)
    CORE="$RUN_PREFIX python -m pytest \"$REL\" -p no:cacheprovider -q" ;;
esac

# Wrap with env CI=1 + timeout (if available). Run FROM the package root so the right
# venv/manager and the nearest conftest.py resolve. The env/timeout wrapper now always
# wraps ONLY the pytest process (no `&&` source step in CORE), so the hard-timeout backstop
# is never bypassed.
if [ -n "$TIMEOUT_BIN" ]; then
  VERIFY="env CI=1 $TIMEOUT_BIN \"$AUDIT_VERIFY_TIMEOUT\" $CORE"
else
  VERIFY="env CI=1 $CORE"     # no portable timeout available; rely on pytest finishing
fi

echo "Verifying: ( cd \"$PKG_ABS\" && $VERIFY )"
VERIFY_OUT="$( cd "$PKG_ABS" && eval "$VERIFY" 2>&1 )"
VERIFY_RC=$?
printf '%s\n' "$VERIFY_OUT" | tail -40        # keep the tail for the classifier + PR notes
# rc 124 (GNU timeout) => timed out => UNVERIFIED. rc handling continues below.
[ "$VERIFY_RC" = 124 ] && echo "  TIMED OUT after ${AUDIT_VERIFY_TIMEOUT}s — treat as UNVERIFIED (never delete on this)."
```

**Distinguish a REAL ASSERTION FAILURE from a collection/import/DB/connection/fixture error**
(the analog of the FE "e2e needs a running app" nuance). Many backend integration tests need a
live DB/Redis/external service (the repo may ship docker-compose the unattended runner doesn't
have). The rule, applied to `($VERIFY_RC, $VERIFY_OUT)`:

> **ONLY an ASSERTION-level pass (rc 0) proves a rework. ONLY a clean run proves a deletion is
> safe. NEVER delete on an unrunnable verify.**

```bash
# ── dbServicesHandling ────────────────────────────────────────────────────────
# pytest exit codes: 0=all passed, 1=tests ran & some failed (assertions executed),
#   2=interrupted, 3=internal error, 4=usage error, 5=no tests collected; 124=timeout.
# Verified in bash AND zsh.

classify_verify() {   # classify_verify <rc> <output>; echoes a verdict token
  rc="$1"; out="$2"
  [ "$rc" = 0 ]   && { echo "PASS"; return; }                        # rework proven / deletion-safe
  [ "$rc" = 124 ] && { echo "UNVERIFIED:timeout"; return; }          # hung runner -> never delete
  [ "$rc" = 5 ]   && { echo "UNVERIFIED:no-tests-collected"; return; }
  # Infra / collection / import / DB / connection / fixture errors => UNVERIFIED.
  # These are NOT assertion failures; treat as 'reworked (unverified: needs DB/services)'
  # and NEVER delete on the basis of an unrunnable verify. Includes connection-pool
  # TimeoutError (dressed as a failure but really a DB/service problem) and a
  # missing-pytest / command-not-found environment.
  if printf '%s' "$out" | grep -qiE \
    'errors during collection|ERROR collecting|ModuleNotFoundError|ImportError|cannot import name|No module named (pytest|pip)|command not found|fixture .* not found|error: fixture .* not found|ConnectionError|ConnectionRefusedError|Connection refused|could not connect|OperationalError|psycopg|sqlalchemy\.exc|asyncpg|pymongo\.errors|redis\.exceptions|socket\.gaierror|getaddrinfo|Name or service not known|Address already in use|docker|testcontainers|InternalError|InterfaceError|TimeoutError|QueuePool|pool .*timed out|connection pool|pool limit|usage:|unrecognized arguments|file or directory not found'; then
    echo "UNVERIFIED:needs-DB/services-or-collection-error"; return
  fi
  # rc 1 with a genuine assertion signal and NO infra marker => real failure (true signal).
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -qiE 'AssertionError|^E +assert|[0-9]+ failed'; then
    echo "ASSERTION-FAILURE"; return
  fi
  echo "UNVERIFIED:unknown-rc-$rc"                                    # interrupted/internal -> unverified
}

VERDICT="$(classify_verify "$VERIFY_RC" "$VERIFY_OUT")"
case "$VERDICT" in
  PASS)
    # Rework: only a PASS proves it. Deletion safety: only a clean run authorizes the delete
    # (and, for a deletion, the importer/sibling run must also be PASS).
    echo "  VERIFY: pass — rework verified / deletion safe." ;;
  ASSERTION-FAILURE)
    # A reworked test that fails on a real assertion must be FIXED — never ship red.
    # If it cannot be made to pass meaningfully, fall back to deletion-with-justification
    # (only after the pre-deletion safety checks AND a clean importer/sibling run).
    echo "  VERIFY: assertion failure — fix the rework; do not ship red." ; ANY_ERROR=1 ;;
  UNVERIFIED:*)
    # DB/services/collection/import/timeout. Mark the change
    # 'reworked (unverified: needs DB/services)'. NEVER delete on this — an unrunnable
    # verify proves nothing. If this was a DELETION candidate, REVERT
    # (git restore -- "$FILE") and downgrade to keep-and-flag.
    echo "  VERIFY: $VERDICT — mark 'reworked (unverified: needs DB/services)'; never delete on an unrunnable verify." ;;
esac
```

Notes:
- **Project-script fallback (`$PM test`, `make test`, a `test` console-script) is DANGEROUS —
  use only if you have confirmed it (1) accepts a single-file path AND (2) runs once (no
  watch).** A script that wraps `pytest-watch`/`ptw` or runs the whole suite ignores a file arg
  and hangs or over-runs. When in doubt, invoke `python -m pytest <REL>` directly as above. The
  `timeout` wrapper is the backstop.
- **Functional/e2e tests need a live DB/Redis/external service** that an unattended runner
  usually lacks. If verification errors on a connection/fixture/service problem, mark the change
  `reworked (unverified: needs DB/services)` and **never delete on the basis of an unrunnable
  verify.** Only an `AssertionError` proves fakeness; only a clean pass proves a deletion is safe.
- **For a deletion:** run the sibling/importer files (from Step 4's grep) the same way, from
  their own package root. ONLY a clean `PASS` (rc 0) on the importer/sibling run authorizes the
  deletion. A real assertion failure means the deletion broke something → **revert and
  keep-and-flag.** An importer run that returns rc 5 (no tests collected) is
  `UNVERIFIED:no-tests-collected` — it is NOT a clean pass and therefore does **not** authorize
  the deletion either → **revert and keep-and-flag.** Same for any `UNVERIFIED:*` (collection/
  import/DB/services/timeout) on the importer run: never delete on an unrunnable verify.

---

## STEP 6 — Deliver via Pull Request (never to main)

First, if nothing was reworked or deleted, stop here with a clean status. Otherwise create the
branch, stage only the touched files, commit, push, and open the PR.

```bash
# 6·pre. If you reworked or deleted NOTHING (every candidate was meaningful or kept-and-flagged),
#        there is nothing to deliver — an audit DID run, so this is success, not an error. Emit a
#        clean `nothing` status and STOP before creating any branch. (TOUCHED is the explicit list
#        of reworked+deleted paths from Steps 4–5; if you tracked it in your own working memory
#        instead of the shell var, apply the same check to that list.)
if [ -z "$(printf '%s' "$TOUCHED" | sed '/^$/d')" ]; then
  nothing "audited $TOTAL test file(s); 0 fake found — nothing to rework, delete, or ship"
fi

# 6a. Create the audit branch BEFORE relying on it. (Branch was ideally created before edits;
#     if you instead edited on the base checkout, create it now — deletions are still only in
#     the working tree, not committed, so switching carries them onto the new branch.)
STAMP="$(date +%Y%m%d-%H%M%S)"
BRANCH="${AUDIT_BRANCH_PREFIX}/${STAMP}-$$"           # PID suffix avoids same-second collisions
n=0
until git switch -c "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" 2>/dev/null; do
  n=$((n+1)); BRANCH="${AUDIT_BRANCH_PREFIX}/${STAMP}-$$-$n"
  [ "$n" -gt 5 ] && fail "could not create a unique audit branch"
done
echo "Audit branch: $BRANCH"

# 6b. Stop if nothing actually changed.
if [ -z "$(git status --porcelain)" ]; then
  git switch "${CUR_BRANCH:-$AUDIT_BASE_BRANCH}" 2>/dev/null || true
  nothing "no changes produced (all candidates kept/flagged)"
fi

# 6c. Stage ONLY the files this run touched — NEVER `git add -A` (an unattended checkout can be
#     dirty with lockfile churn / .env / generated artifacts, which must not enter the PR).
#     TOUCHED is the explicit list from Steps 4–5 (reworked + deleted paths). Stage adds AND
#     deletions of exactly those paths.
printf '%s\n' "$TOUCHED" | sed '/^$/d' | sort -u | while IFS= read -r p; do
  [ -z "$p" ] && continue
  git add -A -- "$p"        # `-A -- <path>` stages a modification OR a deletion of that path
done
# Safety net: if anything outside TOUCHED is somehow staged, abort rather than ship it.
if git diff --cached --name-only | grep -vxF -f <(printf '%s\n' "$TOUCHED" | sed '/^$/d' | sort -u) | grep . ; then
  echo "Refusing to commit: staged paths outside the touched-file set:"; git diff --cached --name-only
  fail "unexpected staged paths (possible dirty tree) — aborting before commit"
fi

# 6d. Commit (identity guaranteed in Step 1f).
git commit -m "chore(test): initial audit & prune of fake backend tests ($STAMP)" -m "$(cat <<'BODY'
Initial full-sweep Python backend test-quality audit (all existing test files).
Reworked fake-but-salvageable tests into behavioral tests; deleted unsalvageable ones.
Only the specific affected test files were run; the full suite was NOT executed.
See the verdict table in the PR body.
BODY
)" || fail "commit failed"

# 6e. Push — capture success; do NOT assume it worked.
PUSHED=0
git push -u origin "$BRANCH" && PUSHED=1
```

**Build the PR body** containing a verdict table — one row per processed candidate, plus
`keep (flagged)` rows and any files deferred over the cap:

```bash
PR_BODY_FILE="$(mktemp)"
cat > "$PR_BODY_FILE" <<HDR
## Backend test-quality audit (initial full sweep)

Initial one-time run. Scope: **ALL existing Python test files** in the repo (no time window).
**The full test suite was NOT run** — only the specific affected files were executed.
Conservative by design: anything ambiguous was kept and flagged, not deleted.

| File | Type | Verdict | Action | Rationale |
|------|------|---------|--------|-----------|
HDR
# Append one row per processed file:
#   type    = unit | integration | functional | endpoint
#   verdict = fake | meaningful | unsure
#   action  = reworked | reworked (unverified: needs DB/services) | deleted | kept (flagged) | skipped (cap)
# Include the contents of $RESULTS here.
```

**Delivery ladder — always end in a clearly-reported state, gated on `PUSHED`:**

```bash
# Resolve owner/repo for a real compare URL (only if origin is a GitHub remote).
REMOTE="$(git remote get-url origin 2>/dev/null)"
SLUG="$(printf '%s' "$REMOTE" | sed -E 's#^git@github\.com:##; s#^https?://github\.com/##; s#\.git$##')"

if [ "$PUSHED" = 1 ] && [ -n "$AUDIT_BASE_BRANCH" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh pr create --base "$AUDIT_BASE_BRANCH" --head "$BRANCH" \
       --title "chore(test): initial prune & rework of fake backend tests ($STAMP)" \
       --body-file "$PR_BODY_FILE"; then
    echo "AUDIT_RESULT=ok: PR opened against $AUDIT_BASE_BRANCH (branch $BRANCH)."
  else
    echo "AUDIT_RESULT=error: gh pr create failed; branch $BRANCH is pushed. Verdict report:"
    cat "$PR_BODY_FILE"; exit 1
  fi
elif [ "$PUSHED" = 1 ]; then
  echo "gh unavailable/unauthenticated OR base branch unresolved — branch pushed, open the PR manually."
  case "$REMOTE" in
    *github.com*) [ -n "$AUDIT_BASE_BRANCH" ] \
        && echo "Compare: https://github.com/${SLUG}/compare/${AUDIT_BASE_BRANCH}...${BRANCH}?expand=1" \
        || echo "Compare: https://github.com/${SLUG}/tree/${BRANCH} (choose a base manually)";;
  esac
  echo "--- Verdict report ---"; cat "$PR_BODY_FILE"
  echo "AUDIT_RESULT=error: delivery incomplete — PR not opened, human action required."
  exit 1
else
  echo "PUSH FAILED (no remote/creds). Local branch '$BRANCH' holds the changes."
  echo "--- Verdict report ---"; cat "$PR_BODY_FILE"
  echo "AUDIT_RESULT=error: push failed — delivery incomplete, human action required."
  exit 1
fi
```

**Never** merge, never force-push, never `--delete-branch`, never commit to the default branch.

---

## STEP 7 — Final status (so the scheduler knows what happened)

Every run MUST end on exactly one machine-grep-able status line so the caller can
distinguish healthy idleness from a silent break:

- `AUDIT_RESULT=nothing: <reason>` — legitimately nothing to do OR an audit ran and found
  nothing to change: no repo / no runner / no test files / all candidates meaningful
  (0 reworked, 0 deleted). Exit 0. Healthy. **No PR is opened in this case.**
- `AUDIT_RESULT=ok: <summary>` — audited AND delivered changes: a PR was opened (or a dry-run
  completed). `ok` implies a PR exists except for dry-run; do NOT use it when nothing changed.
  Exit 0.
- `AUDIT_RESULT=error: <reason>` — could NOT run or could NOT deliver (broken discovery,
  push/PR failure, unexpected staged paths). **Exit non-zero so the caller alerts a human.**

For Claude Code Cloud, surface the `error` path as a notification rather than swallowing it.
A `AUDIT_RESULT=nothing` on a repo you know contains test files is itself a signal to
investigate discovery (re-check the Step 2 pathspecs and post-filter).

---

## SAFETY (read this — it governs every step)

- **Conservative by default.** When genuinely unsure a test is fake, **KEEP it** and flag it in
  the PR. The cost of deleting a real test >> the cost of leaving a marginal one.
- **Action bias is rework, not delete.** Delete only when there is nothing real to test, the test
  is fundamentally redundant, or a meaningful rework is impossible — and only after the
  pre-deletion safety checks pass and the importer/sibling verify is green.
- **Clean-tree precondition.** Refuse to run on a dirty working tree; only ever stage the explicit
  touched-file set. Never `git add -A`.
- **Never run the whole suite.** Only the specific affected file(s), with `CI=1`, no watch, and
  a hard `timeout` so a runner can never hang the job.
- **Never ship a red/broken test.** Fix it, or fall back to deletion-with-justification.
- **Never commit to the default/main branch.** All changes go through a dedicated branch + PR; a
  human reviews and merges.
- **`AUDIT_DRY_RUN=1`** classifies and reports only — zero edits, deletes, branches, or PRs. The
  guard is the first executable line of Step 4. Use it to preview on a new/unknown repo.
- **`AUDIT_MAX_FILES`** caps the blast radius of any single run; overflow files are reported as
  `skipped (cap)`, not silently dropped.
- **Don't remove shared fixtures/factories/helpers** — conftest.py, `fixtures*.py`, `factories*.py`,
  `factory*.py`, `__init__.py`, `setup.py`, and conventional shared modules (`test_base.py`,
  `test_helpers.py`, `test_utils.py`, …) are excluded at discovery; the fixture/export check and
  import check in Step 4 downgrade anything that slips through to keep-and-flag. **A test_*.py that
  defines a module-scope `@pytest.fixture` is NEVER whole-file deleted** — sibling tests can consume
  it by pytest name-injection (no import), which an import grep cannot see; at most edit out an
  individual dead non-fixture test block, never the file.
- **Calibrate by type:** strict on mock-heavy unit; **high bar** on integration/functional that
  need a DB/services (prefer keep-and-flag over deletion). An unrunnable verify (DB/services/
  collection error/timeout) is `unverified`, never proof of fakeness.
- **Fail loud.** Error paths exit non-zero with `AUDIT_RESULT=error`; only true idleness is a
  green `nothing`.

---

## What this skill deliberately does NOT do

- Does **not** run, modify, or report on the entire test suite or non-test source code.
- Does **not** use a time window — it reviews **all** existing test files (this is the one-time initial pass).
- Does **not** commit to or merge into the default branch; it only opens a PR for human review.
- Does **not** `git add -A`, stage a dirty tree, or run on an unclean working tree.
- Does **not** chase coverage numbers, add new tests for untested code, or refactor production code.
- Does **not** delete on a hunch — uncertainty resolves to **keep-and-flag**, not removal.
- Does **not** persist any state; it audits the current working tree once (re-run after merging to continue).
- Does **not** delete conftest.py / shared fixtures / factories, and does **not** delete a test on an
  unrunnable verify — integration/functional tests that need a DB or live services require a very high
  bar and default to keep-and-flag.