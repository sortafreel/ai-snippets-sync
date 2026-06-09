---
name: agent-docs-audit
description: >-
  Weekly, unattended documentation-freshness auditor for AGENTS.md and
  ARCHITECTURE.md. Runs inside any git repo on a schedule (e.g. Claude Code Cloud
  cron), discovers the target docs repo-wide (full re-verification every run — NO
  git window), reads every claim in each doc and checks it against the actual repo
  using READ-ONLY, language-agnostic static checks (documented commands defined in
  a manifest, referenced paths exist, stack versions match the authoritative pins,
  the directory/module map matches the real tree, internal links/anchors resolve,
  env vars/config files/ports are real), then EDITS the docs to fix every grounded
  drift it finds and opens a Pull Request with a per-claim verdict table. Polyglot
  and self-contained: auto-detects command-definition sources
  (package.json/Makefile/justfile/pyproject/tox/compose/bin+scripts) for
  JS/TS/Python/Go/Rust/shell monorepos. NEVER executes a documented command, test,
  script, or build (verification is purely static); NEVER edits any non-doc file;
  NEVER creates a doc that does not exist; NEVER commits to the default branch; and
  keeps-and-flags any claim it cannot ground. Use when scheduling or running a
  recurring "keep the agent/architecture docs honest" job, or when asked to audit
  AGENTS.md / ARCHITECTURE.md for drift.
---

# Agent-Docs Freshness Auditor (`agent-docs-audit`)

## Mission

Run **unattended on a weekly schedule** inside an arbitrary git repo. Discover the
project's `AGENTS.md` and `ARCHITECTURE.md` files (and case variants) **repo-wide,
re-verifying them in full every run**, read each one against the verification rubric
below, and **keep the docs honest**: edit every claim that demonstrably drifted from
the repo (a renamed script, a moved directory, a contradicted version pin, a dead
link) to match a concrete, re-checkable repo fact, and ship the changes as a **Pull
Request** that a human reviews. You are a careful, evidence-grounded editor, not a
prose rewriter.

### Non-goals (read these first — they override any instinct to "be thorough")

- **You do NOT execute anything.** Ever. Verification is **purely static and
  read-only** (`git ls-files`, `git grep`, `grep`/`rg`, `test -e/-f/-d`, `jq`,
  TOML/YAML reads, `sed`/`awk` for *reading*). You NEVER run a documented command,
  script, target, recipe, orchestrator task, test suite, build, or service — a
  documented command could deploy, reset a DB, or hang.
- **You do NOT touch any file that is not a target doc.** Source, manifests, config,
  CI, lockfiles are READ-ONLY evidence; the only files you ever edit are the matched
  `AGENTS.md` / `ARCHITECTURE.md` set. You **never create** a doc that does not exist.
- **You do NOT commit to the default/main branch.** All changes land on a dedicated
  branch and go through a PR.
- **You are conservative when unsure.** Shipping a *new* inaccuracy is far more costly
  than leaving an old one. When a claim cannot be grounded in a concrete repo fact, or
  is subjective/aspirational/philosophical, **LEAVE it untouched** and note it in the
  PR as "kept, flagged."
- **You do NOT fabricate.** Every single edit must trace to a concrete, re-checkable
  repo fact (a path that exists/doesn't, a manifest key present/absent, a version
  string literally present in a pin file). No fact => no edit.
- **You do NOT assume any project context.** No CLAUDE.md, no framework, no directory
  layout, no committed state is assumed. Detect everything at runtime.

---

## IMPORTANT — how to run these snippets

The bash blocks below are the **executable contract** for this skill, not illustrations.
Run them in order; the guards (clean-tree, dry-run, push-failure, the nothing-gate, the
stage-only-touched safety-net) are load-bearing. A few hard rules:

- **Never rely on unquoted-`$VAR` word-splitting; normalize to newlines, then read into
  positionals.** The environment's default shell is **zsh**, where an unquoted `$VAR` does
  **not** word-split (verified): `set -- $VAR` and `for x in $VAR` each yield ONE element, so
  a space-separated doc-name/filter string collapses into one literal that matches nothing and
  the skill silently finds zero docs. Build every space/tab-separated knob (doc basenames,
  include/exclude substrings) by `tr ' \t' '\n\n'`-normalizing to newlines and iterating under
  `IFS=<newline>` (or feeding `set -- "$@" "$tok"` per token). This is identical in bash **and**
  zsh (verified). A literal `set -- a b c` splits the same way in both shells, but splitting an
  unquoted *variable* is the zsh trap — Step 2 guards against a regression with a `[ $# -ge 2 ]`
  assertion after building the specs.
- **Always emit a final status line** `AUDIT_RESULT=...` (see Step 7) so the scheduler
  can tell "audited nothing" (healthy) from "broke" (needs a human). Exit non-zero on
  error paths.
- The commands target **bash and zsh** (the documented runtimes) and are verified in both. Most
  are plain POSIX `sh`; the ONE exception is the Step 6 safety-net, which uses a `<(…)` process
  substitution (a bash/zsh feature, not POSIX `sh`) — that guard runs only under bash/zsh.

---

## Configuration (env-overridable knobs)

All knobs are environment variables with safe defaults. Read them once at the start.

```bash
# Target doc basenames to audit. Space-separated; Step 2 NEWLINE-normalizes this before
# reading it into positionals, so it splits identically in bash AND zsh (see Step 2 — an
# unquoted-$VAR split does NOT work in zsh and would silently find 0 docs).
: "${AUDIT_DOC_BASENAMES:=AGENTS.md ARCHITECTURE.md}"

# Base branch for the PR. Empty => auto-detect the repo's default branch (see Step 1).
: "${AUDIT_BASE_BRANCH:=}"

# Branch name prefix for the audit branch.
: "${AUDIT_BRANCH_PREFIX:=chore/agent-docs-audit}"

# Dry run: verify + report only. No edits, no branch, no PR.
: "${AUDIT_DRY_RUN:=0}"                 # 1 = dry run

# Hard cap on target docs processed in a single unattended run (bounds blast radius).
: "${AUDIT_MAX_DOCS:=20}"

# Hard cap on individual edits applied per doc in a single run (bounds an unattended
# edit run; overflow drift is reported but left for the next run / a human).
: "${AUDIT_MAX_EDITS_PER_DOC:=40}"

# Extra include/exclude path SUBSTRINGS (space-separated). Matched as plain substrings
# against the candidate doc path (NOT shell/`**` globs — see Step 2 for why).
: "${AUDIT_INCLUDE_SUBSTR:=}"          # e.g. "backend/  docs/"
: "${AUDIT_EXCLUDE_SUBSTR:=}"          # e.g. "/legacy/  /examples/"

# Opt-in: ADD a neutral stub line for a major undocumented top-level dir/service (best-effort,
# most fabrication-prone op). DEFAULT OFF so the unattended weekly default NEVER writes new
# prose — it only corrects/removes drifted literals. When on, the added line asserts ONLY the
# existence fact + the source of the name (tree/compose key), never a description of purpose.
: "${AUDIT_ADD_UNDOCUMENTED_DIRS:=0}"  # 1 = allow best-effort structural additions
```

The target-doc pathspecs are derived from `AUDIT_DOC_BASENAMES` in Step 2 by newline-normalizing
the knob and reading each basename into a positional array (with `:(glob,icase)` magic so root and
nested, any-case docs are all found). Do not rely on unquoted-`$VAR` splitting — see the IMPORTANT
note above.

> This skill does **FULL re-verification on every run**: there is **no** lookback window,
> no `git log --since`, no `--diff-filter`, no `SINCE_SHA`, and **no** persisted
> last-reviewed marker. Every run re-checks every claim in every target doc against the
> current tree, because doc drift accumulates silently — a doc can go stale from a source
> change that never touched the doc itself, which a git window over the *doc* would miss.

---

## STEP 1 — Preflight, clean-tree gate & detection

**Goal:** confirm we're at the root of a git repo with a clean tree, resolve the base branch,
ensure a git identity, and bail cleanly if there is nothing to audit.

```bash
fail()    { echo "AUDIT_RESULT=error: $*" >&2; exit 1; }     # could-not-run -> ALERT (non-zero)
nothing() { echo "AUDIT_RESULT=nothing: $*";   exit 0; }     # legitimately nothing to do (healthy)

# 1a. Must be inside a git work tree, and we must be AT its root.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || nothing "not a git repo"
ROOT="$(git rev-parse --show-toplevel)" || fail "cannot resolve repo root"
cd "$ROOT" || fail "cannot cd to repo root"

# 1b. CLEAN-TREE PRECONDITION. An unattended editor must NOT run on a dirty tree:
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

# 1d. Ensure a git identity exists (an unattended commit fails without one). Set a
#     fallback author so the commit in Step 6 cannot fail mid-flight.
git config user.email >/dev/null 2>&1 || git config user.email "agent-docs-audit@users.noreply.github.com"
git config user.name  >/dev/null 2>&1 || git config user.name  "agent-docs-audit bot"
```

**1e. Inventory the command-DEFINITION sources** present in the repo so documented commands
are checkable **STATICALLY** (never executed). This is the polyglot analog of "runner
detection": instead of a single Python runner, we enumerate every manifest type that can
*define* a command. Read-only `git ls-files` + `test -f`; the project may live in a
subdirectory, so scan the whole non-vendored tree, not just root:

```bash
# ── manifestInventory ─────────────────────────────────────────────────────────
# Inventory the command-definition sources so documented commands are checkable
# STATICALLY (never executed). Read-only. Detect tooling at runtime; the project may
# be in a subdir, so scan the whole non-vendored tree, not just root.

nv() { grep -vE '(^|/)(node_modules|\.venv|venv|vendor|dist|build|target|site-packages)/'; }  # drop vendored
echo "=== Command-definition sources (static inventory) ==="
PKG_JSONS="$(git ls-files -- 'package.json' '*/package.json' 2>/dev/null | nv)"   # npm/pnpm/yarn/bun scripts
MAKEFILES="$(git ls-files -- Makefile makefile GNUmakefile '*/Makefile' 2>/dev/null | nv)"
JUSTFILES="$(git ls-files -- justfile Justfile '*/justfile' '*/Justfile' 2>/dev/null | nv)"
PYPROJECTS="$(git ls-files -- pyproject.toml '*/pyproject.toml' 2>/dev/null | nv)"  # [project.scripts]/[tool.*]
TOXINIS="$(git ls-files -- tox.ini '*/tox.ini' 2>/dev/null | nv)"                   # [tox] envlist
COMPOSES="$(git ls-files -- 'docker-compose*.yml' 'docker-compose*.yaml' 'compose*.yml' '*/docker-compose*.yml' 2>/dev/null | nv)"
BINSCRIPTS="$(git ls-files -- 'bin/*' 'scripts/*' '*/bin/*' '*/scripts/*' 2>/dev/null | nv)"  # callable shims
for label in PKG_JSONS MAKEFILES JUSTFILES PYPROJECTS TOXINIS COMPOSES BINSCRIPTS; do
  eval "v=\$$label"; n="$(printf '%s' "$v" | sed '/^$/d' | wc -l | tr -d ' ')"
  echo "  $label: $n"; printf '%s\n' "$v" | sed 's/^/    /;/^ *$/d'
done
# Monorepo note: a documented command may be defined in a PARENT or a PER-PACKAGE manifest —
# the verifier searches ALL of these (any-match = DEFINED), so cross-package recipes resolve.
```

This inventory feeds the command-verification helper in Step 3 (the haystacks). Nothing here
runs a command. The presence or absence of these sources does **not** gate the run — the
target-doc discovery in Step 2 is the real gate; a repo with no manifests at all simply means
documented-command claims resolve as `EXTERNAL`/unverifiable and are left alone.

---

## STEP 2 — Discover target docs (FULL re-verification, repo-wide, NO git window)

**Goal:** purely from `git ls-files`, list every tracked `AGENTS.md` / `ARCHITECTURE.md` (and
case variants) anywhere in the repo, excluding vendored/generated trees. **No state file, no
time window** — every run re-verifies the full set.

```bash
# ── docDiscovery ──────────────────────────────────────────────────────────────
# FULL re-verification every run — NO --since, NO git window, NO shallow-deepening.
# CRITICAL portability rule: do NOT rely on unquoted-$VAR word-splitting. VERIFIED that
# zsh (the documented default runtime) does NOT split an unquoted variable: `set -- $VAR`
# and `for b in $VAR` each yield ONE element under zsh, collapsing the basenames into a
# single literal that matches nothing — the silent "found 0 docs" no-op. Instead, NORMALIZE
# the space/tab-separated knob to NEWLINES and read each token into the positionals under
# `IFS=<newline>`. This is identical in bash AND zsh (verified). 0-found => clean `nothing`.

# Knob default; normalize to newlines, then load each basename into the positionals.
: "${AUDIT_DOC_BASENAMES:=AGENTS.md ARCHITECTURE.md}"
set --
oldIFS=$IFS; IFS='
'
for b in $(printf '%s' "$AUDIT_DOC_BASENAMES" | tr ' \t' '\n\n' | sed '/^$/d'); do
  # Build CASE-INSENSITIVE, root+nested pathspecs from each basename.
  set -- "$@" ":(glob,icase)**/$b" ":(glob,icase)$b"
done
IFS=$oldIFS
# Regression guard: the default 2 basenames must yield >= 2 specs. If a future change
# re-introduces the word-split bug, this fails LOUD instead of silently auditing nothing.
[ "$#" -ge 2 ] || fail "doc-basename pathspec build collapsed (word-split regression?): $# spec(s)"

RAW="$(git ls-files -- "$@" 2>/dev/null | sort -u)"  # tracked only; NO time filter
# Exclude vendored/generated trees (root-anchored AND nested) — a case-insensitive
# discovery can surface a vendored AGENTS.md/ARCHITECTURE.md inside an excluded tree.
DOCS=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    node_modules/*|*/node_modules/*|.venv/*|*/.venv/*|venv/*|*/venv/*|\
    vendor/*|*/vendor/*|dist/*|*/dist/*|build/*|*/build/*|\
    *site-packages/*|target/*|*/target/*|.git/*|*/.git/*) continue;;
  esac
  # include filter (if set, path must contain at least one include substring).
  # Same zsh non-split trap as the basenames: normalize to newlines and iterate under
  # IFS=<newline> so a multi-token "backend/ docs/" knob is two substrings, not one literal.
  if [ -n "$AUDIT_INCLUDE_SUBSTR" ]; then
    keep=0; fIFS=$IFS; IFS='
'
    for s in $(printf '%s' "$AUDIT_INCLUDE_SUBSTR" | tr ' \t' '\n\n' | sed '/^$/d'); do
      case "$f" in *"$s"*) keep=1;; esac
    done
    IFS=$fIFS
    [ "$keep" = 1 ] || continue
  fi
  # exclude filter (same newline-normalized iteration)
  skip=0; fIFS=$IFS; IFS='
'
  for s in $(printf '%s' "$AUDIT_EXCLUDE_SUBSTR" | tr ' \t' '\n\n' | sed '/^$/d'); do
    case "$f" in *"$s"*) skip=1;; esac
  done
  IFS=$fIFS
  [ "$skip" = 1 ] && continue
  DOCS="$DOCS$f
"
done <<EOF
$RAW
EOF
DOCS="$(printf '%s' "$DOCS" | sed '/^$/d' | sort -u)"
[ -z "$DOCS" ] && nothing "no AGENTS.md/ARCHITECTURE.md tracked (after excluding vendored trees)"

# Per-run cap (bounds an unattended edit run). Process first N; report the rest.
: "${AUDIT_MAX_DOCS:=20}"
TOTAL="$(printf '%s\n' "$DOCS" | wc -l | tr -d ' ')"
DEFERRED="$(printf '%s\n' "$DOCS" | tail -n +"$((AUDIT_MAX_DOCS+1))")"
DOCS="$(printf '%s\n' "$DOCS" | head -n "$AUDIT_MAX_DOCS")"
echo "Found $TOTAL target doc(s); auditing up to $AUDIT_MAX_DOCS:"; printf '%s\n' "$DOCS"
[ -n "$DEFERRED" ] && { echo "Deferred (over cap):"; printf '%s\n' "$DEFERRED"; }
```

> VERIFIED: matched root `AGENTS.md`/`ARCHITECTURE.md`, nested `apps/web/AGENTS.md`, AND case
> variants `docs/Architecture.MD`, `sub/agents.md`; correctly dropped `node_modules/` and
> `vendor/`. Each kept path is read **IN FULL** in the per-doc loop below — there is no git
> diff scope, no "review only changed lines." The whole doc is the audit surface.

---

## STEP 3 — Per-doc verification against the repo (READ-ONLY, STATIC, ZERO-FABRICATION)

Iterate over `$DOCS`. For **each** doc, read it **in full**, extract every concrete claim, and
check each claim against the repo using the read-only helpers below. Track the docs you
actually edit in `TOUCHED` (used by Step 6 — **only these are staged**). Use this scaffold:

```bash
TOUCHED=""        # newline-separated list of EDITED target doc paths (the ONLY things staged)
FIXED=""; ADDED=""; KEPT_FLAGGED=""; CURRENT_OK=""    # for the verdict table
ANY_ERROR=0

printf '%s\n' "$DOCS" | while IFS= read -r DOC; do
  [ -z "$DOC" ] && continue
  DOCDIR="$(dirname "$DOC")"               # resolve doc-relative paths against THIS first
  echo "==> $DOC   (doc dir: $DOCDIR)"
  # ... read the doc in full; extract claims; verify each (helpers below); act in Step 4 ...
done
```

> Note: a `while` loop fed by a pipe runs in a subshell in some shells, so variables set
> inside it (`TOUCHED`, counters, `ANY_ERROR`) may not survive. If you need them afterward,
> drive the loop with a here-doc/`for` over `$DOCS`, or append per-claim verdict rows to a
> temp file (`printf '%s\t%s\t...\n' "$DOC" "$claim" >> "$RESULTS"`) and read it back in Step 6.
> Also persist the error flag (e.g. append `printf 'ERROR\t%s\n' "$DOC" >> "$RESULTS"` if a
> verify-after-edit fails) and `grep -q '^ERROR' "$RESULTS"` in Step 7 so a mid-run failure
> can't be silently lost to the subshell. The simplest robust pattern for an agent is to
> **process one doc at a time** and keep the running lists in working memory, writing each
> verdict row (and any error sentinel) to `$RESULTS`.

**For each doc:** read it (don't grep-and-guess — grep *locates* claims; the verdict comes
from reading). Classify each claim as one of:

- **STALE** — contradicts a concrete, re-checkable repo fact (a dead command, a missing path,
  a contradicted version pin, a broken link). Edit it (Step 4) to the fact read back from the
  repo, then verify-after-edit (Step 5).
- **CURRENT** — the claim matches reality. Leave untouched.
- **UNVERIFIABLE** — cannot be confirmed either way from the repo (subjective, external,
  aspirational, ambiguous, secret-omitted). Default action: **LEAVE and flag**.

### ZERO-FABRICATION grounding rules (read these first — they govern every edit)

- **Every edit must cite a concrete, re-checkable repo fact** in the PR verdict row: an exact
  path that does/doesn't exist (the `git ls-files`/`test -e` result), a manifest key
  present/absent (file + key), or a version string literally present in a named pin file. No
  fact => no edit (flag instead).
- **Read-only, never execute.** Verification uses only `git ls-files`, `git grep`, `grep`/`rg`,
  `test -e/-f/-d`, `jq`, TOML/YAML reads, and `sed`/`awk` for *reading*. NEVER run a documented
  command, script, target, recipe, orchestrator task, test, or build — it could deploy, reset a
  DB, or hang. NEVER hit the network (no `curl`/registry/DNS).
- **Only ever assert a value the manifest ACTUALLY states, at the manifest's precision.** Never
  upgrade "Node 20" to "Node 20.11.1" unless a source literally pins 20.11.1; a range
  (`^`,`~`,`>=`,`*`) agreeing with a doc family is *correct*, not stale.
- **Resolve the GOVERNING manifest/scope before judging.** Walk up from the doc's directory to
  the nearest manifest; in a monorepo also consider the workspace package the doc section is
  about, and a parent/root manifest. A command absent at the doc's level but present in a
  parent/root manifest is **DEFINED**, not drift.
- **Map command aliases to their definition correctly before deciding:** `npm test`->scripts.test,
  `npm start`->scripts.start, `npm run X`->scripts.X, `make X`->target X, `just X`->recipe/alias X,
  `pdm run X`->`[tool.pdm.scripts].X`, `cargo run --bin X`->`[[bin]] X`. A missing alias mapping is a
  tool-author convention, not repo drift.
- **Never fabricate a replacement.** Only substitute a documented value with another when an
  **unambiguous** successor exists in the repo (a single clear corresponding key/path/pin). If a
  thing was removed with no clear successor, **flag it** in the PR — do not invent a plausible
  replacement.
- **Built-in language subcommands** (`go build/test/run`, `cargo build/test/run/check`,
  `python -m`) are always valid — only their PATH/target ARGUMENTS are checkable. Never flag a
  built-in subcommand itself as undefined.
- **Tool-swap edits require corroboration from ≥2 independent facts** (dependency + config file +
  script body / lockfile). A single weak signal is not enough to rewrite prose naming a tool.
- **Cross-check the package manager / wrapper tool against the lockfile** present
  (pnpm-lock.yaml, yarn.lock, bun.lock*, package-lock.json, uv.lock, poetry.lock, pdm.lock) and
  any `packageManager`/pin field before correcting a PM verb.
- **Verify-after-edit** (Step 5): after every change, re-run the SAME read-only check against
  the NEW value and confirm it now matches reality. Never ship an edit that introduces a new
  inaccuracy.
- **Exclude vendored/generated trees** (node_modules, .venv, venv, vendor, dist, build,
  site-packages, .next, out, target, coverage, __pycache__, .git) from every tree/manifest
  check so a stale copy under those trees is never used as evidence.

### Read-only verification helpers (the static checks — they NEVER execute the subject)

**Documented command/script/recipe is DEFINED in a manifest** (strip the PM/runner prefix to
the verb, then confirm it is defined somewhere). NEVER run the subject command:

```bash
# ── commandVerification ───────────────────────────────────────────────────────
cmd_defined() {            # echoes where it's defined; 0=defined, 1=not, 2=unverifiable/external
  raw="$1"
  # TRAP: one-off EXTERNAL package runners (npx/bunx/pnpx/pnpm dlx/uvx) invoke a package that is
  # intentionally NOT defined in any local manifest — never flag these as a dead command. If the
  # runner targets a LOCAL package.json script it is covered by the script lookup below, so here
  # we treat a runner + non-empty arg as EXTERNAL/unverifiable rather than NOT-DEFINED.
  case "$raw" in
    npx\ *|bunx\ *|pnpx\ *|uvx\ *|*pnpm\ dlx\ *|*pnpm\ exec\ *)
      echo "EXTERNAL-runner:$(printf '%s' "$raw" | sed -E 's/[[:space:]]+/ /g')"; return 2;;
  esac
  # Strip a leading package-manager / runner / task invocation down to the verb (first token).
  verb="$(printf '%s' "$raw" | sed -E \
    -e 's/^[[:space:]]*(npm|pnpm|yarn|bun|pdm|poetry|uv)[[:space:]]+(run|exec|--|tool)?[[:space:]]*//' \
    -e 's/^[[:space:]]*(make)[[:space:]]+//' \
    -e 's/^[[:space:]]*(just)[[:space:]]+//' \
    -e 's/^[[:space:]]*(tox)[[:space:]]+-e[[:space:]]+//' \
    -e 's/^[[:space:]]*(docker[[:space:]]+compose|docker-compose)[[:space:]]+(run|up|exec)[[:space:]]+//' \
    -e 's/[[:space:]].*$//; s/[`$].*$//')"
  [ -z "$verb" ] && verb="$raw"
  # TRAP: ignore bare binaries that aren't project recipes (built-ins / external tools).
  case "$verb" in node|git|ls|cd|echo|cat|sh|bash|cargo|go|python|python3|pip|rustc|tsc) echo "EXTERNAL-binary:$verb"; return 2;; esac

  # 1) package.json scripts (root + per-package, any match = defined — covers monorepos)
  for pj in $(git ls-files -- 'package.json' '*/package.json' 2>/dev/null | grep -v node_modules); do
    [ "$(jq -r --arg k "$verb" '.scripts[$k] // empty' "$pj" 2>/dev/null)" != "" ] && { echo "DEFINED npm-script:$verb @ $pj"; return 0; }
  done
  # 2) Makefile target (verb at col 0 then ':')
  for mk in $(git ls-files -- Makefile makefile GNUmakefile '*/Makefile' 2>/dev/null | grep -v node_modules); do
    grep -qE "^${verb}[[:space:]]*:" "$mk" && { echo "DEFINED make:$verb @ $mk"; return 0; }
  done
  # 3) justfile recipe (verb [args] ':')
  for jf in $(git ls-files -- justfile Justfile '*/justfile' 2>/dev/null | grep -v node_modules); do
    grep -qE "^${verb}([[:space:]].*)?:" "$jf" && { echo "DEFINED just:$verb @ $jf"; return 0; }
  done
  # 4) pyproject [project.scripts]/[tool.poetry.scripts]/[tool.pdm.scripts] / tox env / compose service
  for pp in $(git ls-files -- pyproject.toml '*/pyproject.toml' 2>/dev/null | grep -v node_modules); do
    grep -qE "^[[:space:]]*${verb}[[:space:]]*=" "$pp" && { echo "DEFINED pyproject-script:$verb @ $pp"; return 0; }
  done
  for tx in $(git ls-files -- tox.ini '*/tox.ini' 2>/dev/null); do grep -qE "(^|[,= ])${verb}([,]|$)" "$tx" && { echo "DEFINED tox-env:$verb @ $tx"; return 0; }; done
  for dc in $(git ls-files -- 'docker-compose*.yml' 'compose*.yml' 2>/dev/null); do grep -qE "^[[:space:]]{2,}${verb}:" "$dc" && { echo "DEFINED compose-service:$verb @ $dc"; return 0; }; done
  # 5) a bin/ or scripts/ shim of that name
  for s in $(git ls-files -- "bin/$verb" "bin/$verb.*" "scripts/$verb" "scripts/$verb.*" 2>/dev/null); do echo "DEFINED bin-script:$verb @ $s"; return 0; done
  echo "NOT-DEFINED:$verb (from: $raw)"; return 1
}
```

> NEVER run `cmd_defined`'s subject command; it only inspects manifests. A `NOT-DEFINED`
> documented command is a grounded drift fact (dead command). `EXTERNAL-binary` (return 2) is
> left unflagged — a generic `node`/`git` usage is not a project recipe to verify.

**Referenced path exists in the current tree** (skip the false-positive traps before testing):

```bash
# ── pathVerification ──────────────────────────────────────────────────────────
path_exists() {  # 0=exists, 1=missing(grounded drift), 2=skip(trap — never flag)
  p="$1"; p="$(printf '%s' "$p" | sed -E 's/^[`"'"'"' ]+//; s/[`"'"'"' ]+$//')"  # strip quotes/backticks/space
  case "$p" in
    ''|http://*|https://*|ftp://*|git@*|ssh://*|mailto:*) echo "SKIP-url-or-empty:$p"; return 2;;
    *'<'*'>'*|*'...'*|*'$'*|*'{'*'}'*|*'*'*|*'?'*|*'['*']'*|'~'*) echo "SKIP-placeholder/glob:$p"; return 2;;
  esac
  pp="${p#./}"; pp="${pp%/}"                       # normalize ./ prefix and trailing /
  git ls-files --error-unmatch -- "$pp" >/dev/null 2>&1 && { echo "EXISTS-tracked-file:$pp"; return 0; }
  [ -n "$(git ls-files -- "$pp/" 2>/dev/null | head -1)" ] && { echo "EXISTS-tracked-dir:$pp"; return 0; }
  [ -e "$pp" ] && { echo "EXISTS-untracked:$pp"; return 0; }   # generated-but-present (e.g. dist/) still real
  echo "MISSING:$pp"; return 1
}
```

> Resolve a doc-relative path against `$DOCDIR` FIRST, then the doc's parent, then `$ROOT`,
> before declaring it missing. A `MISSING` result backs a dead-path edit. ENV/CONFIG sub-check
> reuses this: documented `.env`/config files and `.env.example` keys are confirmed with
> `path_exists` + `grep -q '^KEY=' .env.example`; documented ports are checked against compose
> `ports:`/Dockerfile `EXPOSE` (grep), and an unverifiable port is LEFT and noted, never guessed.

**Tech-stack/version claim vs the authoritative pin** (conservative: a doc version is wrong
only when a pin states a DIFFERENT concrete value for the same tool):

```bash
# ── versionVerification ───────────────────────────────────────────────────────
# MATCH HAYSTACK = AUTHORITATIVE PINS ONLY. Do NOT feed lockfiles (pnpm-lock.yaml/yarn.lock/
# package-lock.json/Cargo.lock) into the MATCH search: lockfiles pin TRANSITIVE deps, so a
# doc's version string will spuriously appear for an unrelated package and mask real drift.
# Lockfiles are used elsewhere only to corroborate the package-manager VERB, never as a
# version-claim haystack.
VSRC="$(printf '%s\n' .tool-versions .nvmrc .node-version package.json go.mod Cargo.toml \
  pyproject.toml runtime.txt; \
  git ls-files -- Dockerfile '*/Dockerfile' 'docker-compose*.yml' 'compose*.yml' \
    '.github/workflows/*' '*.tool-versions' 2>/dev/null \
  | grep -vE '(^|/)(node_modules|vendor|dist|build)/' )"
VSRC="$(printf '%s\n' "$VSRC" | sed '/^$/d' | sort -u)"

# TOKEN-BOUNDED match: the version must appear as a whole numeric token, NOT a bare substring.
# WHY: a bare `grep -qF "$ver"` makes "node 2" MATCH a pin of "20.11.1" and "react 1"/"react 8"
# MATCH "18" (verified), masking genuine drift. We escape dots and require non-digit/non-dot
# boundaries so `2` does not match inside `20.11.1` and `1` does not match inside `18`.
ver_token_re() { printf '%s' "$1" | sed 's/[.]/[.]/g'; }   # escape dots for a literal-ish ERE

version_present() {  # tool ver -> MATCH (claim ok) | MISMATCH (pin differs) | UNVERIFIABLE
  tool="$1"; ver="$2"; hits=""; authoritative=""; re="$(ver_token_re "$ver")"
  while IFS= read -r f; do [ -f "$f" ] || continue
    # whole-token match (segment-bounded), NOT a bare substring
    grep -qE "(^|[^0-9.])${re}([^0-9]|$)" "$f" 2>/dev/null && hits="$hits $f"
    case "$f:$tool" in
      .nvmrc:node|.node-version:node) authoritative="$f";;
      .tool-versions:*) grep -qiE "^[[:space:]]*$tool([[:space:]]|$)" "$f" 2>/dev/null && authoritative="$f";;
      go.mod:go)        grep -qE '^go[[:space:]]+[0-9]' "$f" 2>/dev/null && authoritative="$f";;
    esac
  done <<EOF
$VSRC
EOF
  # DOC-FAMILY tolerance is intended (a doc "Node 20" is satisfied by a pin "20.11.1"). Implement
  # it as an explicit PREFIX/family rule when needed (the doc value is a numeric prefix of the
  # authoritative pin's value for the SAME tool), NOT as an accidental substring side-effect.
  if [ -n "$hits" ]; then echo "MATCH $tool $ver in:$hits"; return 0
  elif [ -n "$authoritative" ]; then echo "MISMATCH $tool: doc says $ver; authoritative pin: $authoritative"; return 1
  else echo "UNVERIFIABLE $tool $ver (no authoritative pin) -> LEAVE + note"; return 2; fi
}
```

> Only a `MISMATCH` (a concrete pin states a different value) authorizes a version edit; the
> corrected value is read back FROM that pin (zero fabrication). When sources disagree with
> *each other*, do NOT pick one — flag the inconsistency for a human.

**Documented directory/module map vs the actual tree** (both directions):

```bash
# ── structureVerification ─────────────────────────────────────────────────────
# Exclude vendored/generated trees AND conventional, intentionally-undocumented dirs (an
# architecture doc legitimately omits docs/scripts/tests/config/CI/tooling dirs). Keeping these
# out of the "undocumented" set holds the addition noise floor down.
actual_topdirs() {
  git ls-files 2>/dev/null | awk -F/ 'NF>1{print $1}' | sort -u \
    | grep -ivE '^(node_modules|\.venv|venv|vendor|dist|build|out|coverage|target|tmp|__pycache__|\.next|\.git|\.github|\.gitlab|\.circleci|\.devcontainer|\.husky|\.changeset|\.idea|\.vscode|docs|doc|scripts|bin|tests|test|examples|example|config|fixtures)$'
}
documented_dirs() {  # $1 = doc file; first path segment of any `foo/...` token in the doc
  grep -oE '(`|"|^|[[:space:](])[A-Za-z0-9._-]+/' "$1" 2>/dev/null \
    | grep -oE '[A-Za-z0-9._-]+/' | sed 's:/$::' | sort -u \
    | grep -vE '^(http|https|node_modules|\.\.|\.)$'
}
# A dir is a MAJOR (worth-documenting) dir only if it holds real first-party SOURCE, not just
# config/docs/assets. Heuristic, read-only: it contains at least one tracked code-ish file.
is_major_dir() {  # $1 = top-level dir; 0 = major (has source), 1 = not major
  git ls-files -- "$1/" 2>/dev/null \
    | grep -qiE '\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|php|c|cc|cpp|h|hpp|cs|swift|scala|ex|exs|sql)$'
}
ACT="$(actual_topdirs)"
# Per-doc (inside the Step 3 loop):
#   DOCD="$(documented_dirs "$DOC")"
#   documented-but-MISSING (objective dead-structure; may be removed/corrected):
#     comm -23 <(printf '%s\n' "$DOCD" | sort -u) <(printf '%s\n' "$ACT" | sort -u)
#       | while read -r d; do [ -n "$d" ] && { git ls-files -- "$d/" | grep -q . || echo "  dead: $d"; }; done
#   exists-but-UNDOCUMENTED MAJOR top-level dir (BEST-EFFORT, OPT-IN, low-confidence):
#     [ "$AUDIT_ADD_UNDOCUMENTED_DIRS" = 1 ] || skip   # default OFF: never writes new prose
#     comm -13 <(printf '%s\n' "$DOCD" | sort -u) <(printf '%s\n' "$ACT" | sort -u)
#       | while read -r d; do [ -n "$d" ] && is_major_dir "$d" && echo "  undocumented-major: $d"; done
# docker-compose SERVICES are part of the module map too — cross-check documented services vs
# compose `services:` keys; an undocumented real service is a best-effort (opt-in) add.
```

> `documented-but-missing` is objectively verifiable (the dir has no tracked files) and may be
> removed/corrected. `exists-but-undocumented` is a **BEST-EFFORT, OPT-IN** addition
> (`AUDIT_ADD_UNDOCUMENTED_DIRS=1`; default OFF — the unattended default writes no new prose). When
> enabled, it fires ONLY for a MAJOR dir (real first-party source) or a real compose service, and
> the added line asserts ONLY the EXISTENCE FACT + the source of the NAME — e.g.
> `` `payments/` — present in tree, undocumented (auto-added, please describe) `` (or for a service,
> `` `worker` — docker-compose service, undocumented (auto-added, please describe) ``). It MUST NOT
> contain any agent-authored description of the dir's role/contents/architecture. Verify-after-edit
> can confirm the path resolves but CANNOT confirm prose accuracy, so the contract forbids prose:
> the human reviewer writes the description. Prose describing WHY/philosophy is never touched here.

**Internal markdown links & heading anchors resolve** (skip external URLs — never fetch):

```bash
# ── linkVerification ──────────────────────────────────────────────────────────
# CRITICAL: the slugifier MUST emit a trailing newline (printf '%s\n') or `grep -qxF` matches
# nothing and every anchor falsely reports broken (verified).
# GitHub slug: lowercase, drop ` and punctuation, trim, then ONE hyphen PER space. Do NOT
# collapse hyphen runs: GitHub keeps the empty token left by a dropped `&` so "Setup & Install"
# -> "setup--install" (verified). Collapsing (s/ +/-/g) would mis-slug it to "setup-install".
slug() { printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/`//g; s/[^a-z0-9 _-]//g; s/^[[:space:]]+//; s/[[:space:]]+$//; s/ /-/g'; }  # GitHub-style
anchors_of() { grep -nE '^#{1,6}[[:space:]]' "$1" 2>/dev/null \
  | sed -E 's/^[0-9]+:#{1,6}[[:space:]]+//' | while IFS= read -r h; do slug "$h"; done; }

check_links() {  # $1 = doc file
  DOC="$1"; base="$(dirname "$DOC")"
  grep -oE '\]\([^) ]+\)' "$DOC" | sed -E 's/^\]\(//; s/\)$//' | while IFS= read -r tgt; do
    case "$tgt" in http://*|https://*|mailto:*|ftp://*) echo "SKIP-external:$tgt"; continue;; esac
    file="${tgt%%#*}"; frag=""; case "$tgt" in *#*) frag="${tgt#*#}";; esac
    file="${file#./}"
    if [ -z "$file" ]; then   # same-file anchor
      [ -z "$frag" ] && { echo "OK-self:$tgt"; continue; }
      anchors_of "$DOC" | grep -qxF "$frag" && echo "OK-self-anchor:#$frag" || echo "BAD-self-anchor:#$frag in $DOC"
      continue
    fi
    rp="$base/$file"; rp="${rp#./}"
    if git ls-files --error-unmatch -- "$rp" >/dev/null 2>&1 || [ -e "$rp" ]; then
      if [ -n "$frag" ]; then
        case "$rp" in *.md|*.markdown|*.MD) anchors_of "$rp" | grep -qxF "$frag" \
            && echo "OK-file+anchor:$rp#$frag" || echo "BAD-anchor:$rp#$frag";;
          *) echo "OK-file(non-md, anchor unchecked):$rp#$frag";; esac
      else echo "OK-file:$rp"; fi
    else echo "BAD-file:$rp (target missing)"; fi
  done
}
```

> `BAD-file`/`BAD-anchor` are grounded drift facts. A fix points the link at the file/heading
> that actually exists (read back from `git ls-files`/`anchors_of`); if no correct target can
> be identified from the tree, LEAVE it and note in the PR — never guess a destination.
> Duplicate-heading anchors get occurrence-indexed suffixes (`#setup`, `#setup-1`, …) that
> cannot be derived from the slug alone — treat a `#foo-1` cautiously.
> `check_links` only locates inline `](target)` links. Reference-style links (`[text][ref]` +
> `[ref]: target`) and bare autolinks (`<https://…>`) are NOT located, so a broken reference-style
> internal link is conservatively left as UNVERIFIABLE (never auto-edited), not flagged as drift.

### The verification rubric — what to check, the false-positive traps, the do-NOT-edit list

For each claim type below: **what it claims**, **how to verify it (read-only)**, the **drift
signal**, and the **fix approach**. The detailed cross-language rubric (npm/pnpm/yarn/bun
scripts, Makefile targets, justfile recipes, pyproject entry-points, uv/poetry/pdm/hatch
wrappers, tox envs, docker-compose services/ports, Go subcommands/module path, Cargo
bins/aliases, shell scripts, tool-swap drift, flag/argument drift, monorepo/workspace
invocations, directory/module map both directions, component/service lists, data-flow
anchors, file-path references, tech-stack/version pins, internal links/anchors, env
vars/config/ports) is embodied by the helpers above. Apply them as follows.

1. **Documented command / script / recipe.** *Claims:* `npm run build`, `pnpm test:unit`,
   `make migrate`, `just deploy`, `yarn dev`, `poetry run pytest`, `uv run lint`, `tox -e py312`,
   `docker compose up app`, `nx test web`, `pdm run X`, `cargo run --bin server`, `go run
   ./cmd/server`, `./scripts/setup.sh` resolve to something the project defines. *Verify:*
   `cmd_defined` for manifest-defined recipes; `path_exists` for script files and for
   built-in-subcommand path arguments (`./cmd/server`, `--bin server` -> `[[bin]]`/`src/bin`).
   *Drift:* `NOT-DEFINED` from every candidate manifest (root + the doc's package + a parent
   monorepo manifest), or a path argument that is `MISSING`. *Fix:* substitute the exact
   defined key/path string when an **unambiguous** successor exists; if removed with no
   successor, flag as removed (do not invent). Built-in `go build`/`cargo test`/`python -m`
   subcommands are always valid — only their arguments are checkable.

2. **Referenced file / directory / path.** *Claims:* `tsconfig.json`, `src/components/`,
   `cmd/server/main.go`, `config/app.yaml`, a doc-to-doc path. *Verify:* `path_exists`,
   resolving doc-relative first (`$DOCDIR`), then parent, then `$ROOT`. *Drift:* `MISSING`
   under every plausible base. *Fix:* if a single unambiguous current path matches the same
   basename/role (rename/move evidenced in the tree), correct it; if genuinely gone, remove the
   single reference. Never point at a path you have not confirmed; multi-candidate => leave + flag.

3. **Tech-stack & version claims.** *Claims:* "Node 20", "React 18", "Python 3.12", "Go 1.22",
   "Postgres 17", "pnpm 9". *Verify:* `version_present tool ver` against the authoritative pin.
   *Drift:* `MISMATCH` (a pin literally states a different value at the doc's precision). *Fix:*
   edit to the value the pin LITERALLY states, at matching precision; ranges agreeing with a doc
   family are correct. Sources disagreeing with each other => flag, don't pick a winner.

4. **Directory / module / service map (both directions).** *Verify:* `structureVerification`
   (vendored + conventional non-architectural dirs excluded; `is_major_dir` = has first-party
   source) + compose `services:` keys. *Drift:* documented-but-missing dir (objective: zero
   tracked files), or a MAJOR undocumented top-level dir/service with real source. *Fix:*
   remove/relabel a dead entry (objective). ADDING a line for a major undocumented dir/service is
   **OPT-IN** (`AUDIT_ADD_UNDOCUMENTED_DIRS=1`, default OFF); when enabled, add ONE neutral
   existence-only stub (`` `dir/` — present in tree, undocumented (auto-added, please describe) ``),
   best-effort/low-confidence/flagged. Never invent purpose/design narrative.

5. **Internal doc links & anchors.** *Verify:* `check_links`. *Drift:* `BAD-file`/`BAD-anchor`.
   *Fix:* repoint a moved file / renamed section when exactly one unambiguous candidate exists;
   else leave + flag. External URLs are out of scope — never fetch.

6. **Env vars / config files / ports (where statically checkable).** *Verify:* `path_exists`
   for config files; `.env.example` LHS keys (`grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | sed
   's/=.*//'` — commented `# KEY=` is NOT a declared key); ports vs compose `ports:`/Dockerfile
   `EXPOSE`. *Drift:* a config file that doesn't exist; a var absent from `.env.example` AND all
   tracked code/compose/CI; a port contradicting the only configured value. *Fix:* correct a
   moved config path or a contradicted port; for env vars prefer flagging over deletion (secrets
   are intentionally omitted; vars are read indirectly). Never print/invent secret VALUES.

#### Do NOT edit — these are never drift, never "improve" them

- **WHY/philosophy/rationale prose** ("we chose X because…", "favor composition", "keep the
  domain layer framework-agnostic") — opinion/intent, not a checkable fact. Leave verbatim even
  if you'd have chosen differently.
- **Aspirational / roadmap / future / TODO / planned / proposed / vision** notes, or anything
  hedged with "will", "plans to", "eventually", "intended to", "we may". A path/service/command
  mentioned ONLY as planned is NOT drift if absent.
- **Illustrative / example / pedagogical snippets** explicitly framed as samples ("for example",
  "e.g.", "such as", `npm run <your-script>`, placeholder values) — not live claims.
- **Subjective guidance / conventions / opinions** (style preferences, "prefer small PRs", "ask
  before refactoring", review etiquette, commit-message conventions, tone) — unfalsifiable.
- **Human-authored cautions / gotchas / "don't do X" warnings** — intentional operator guidance.
- **Prose naming a tool historically/comparatively** ("migrated away from Jest", "unlike
  Webpack, we…") — the manifest's absence of that tool is consistent, not drift.
- **External commands not owned by the repo** (`brew install node`, `rustup`, `apt-get`,
  CI-provider commands, a dependency's own docs) — not defined in THIS repo's manifests.
- **Conceptual/logical architecture diagrams** describing LAYERS/RESPONSIBILITIES (Domain,
  Infrastructure, Presentation) rather than literal directories — only edit a node that names a
  literal, now-broken path.
- **Internal inconsistencies between two authoritative sources** (engines vs CI matrix, compose
  vs Dockerfile, both jest.config and vitest.config present) — do NOT pick a winner; flag.
- **Any claim genuinely ambiguous after read-only checking, and any wording/style/formatting of
  otherwise-correct prose** — leave it; quality/altitude prose edits are out of scope.
- **Any file that is NOT a target doc** — source, manifests, config, CI, lockfiles are read-only
  evidence; never edit them, and never create a doc that doesn't exist.

#### False-positive traps — looks like drift, is actually fine (check before flagging)

- **Lifecycle aliases** look undefined but aren't: `npm test`/`npm start`/`npm run build` map to
  `scripts.test/start/build`; `make`/`tox`/`cargo build` with no arg run the default
  target/envlist/build. Map the alias before flagging.
- **Parent/root or workspace-orchestrator commands** in a monorepo: a script absent from a
  subpackage's manifest may live in the root package.json, a parent Makefile `include`, a
  turbo/nx pipeline, or a sibling workspace. Check ancestors + orchestrator config + the doc's
  OWN package before flagging.
- **Aliased commands**: a justfile `alias b := build`, a `.cargo/config.toml [alias]`, an
  npm-script that calls another script, a synonym Makefile target — a valid alias, not missing.
- **Placeholders / globs / template tokens are NOT dead paths or commands**: `<your-key>`,
  `<service>`, `$VAR`, `${ENV}`, `...`, `path/to/<thing>`, `**/*.ts`, `foo/*`, `~/…`,
  `example.com`, `YOUR_TOKEN`. The helpers skip these; never resolve them as concrete targets.
- **Built-in toolchain subcommands** (`go build`, `cargo test`, `python -m pytest`, `docker
  compose up` with no service = all services) are valid even though no manifest "defines" them —
  only explicit path/target args are checkable.
- **One-off external package runners** (`npx <pkg>`, `bunx <pkg>`, `pnpm dlx <pkg>`, `uvx <pkg>`,
  `pnpx <pkg>`) invoke an EXTERNAL package that is intentionally NOT defined in this repo's
  manifests — `cmd_defined` returns `EXTERNAL-runner` (unverifiable), never `NOT-DEFINED`. Never
  flag a one-off runner as a dead command. (A runner pointed at a LOCAL package.json script is
  still verified via the script lookup.)
- **Globs/wildcards in a command** (`go test ./...`, `eslint .`, `pytest tests/`) are valid —
  `./...`/`.` are not missing paths. Only resolve concrete, non-glob path arguments.
- **Factor-expanded tox envs** (`tox -e py311` valid when envlist has `py3{9,10,11}`) — expand
  factors before concluding the env is missing.
- **Config present ≠ tool in use; two configs can coexist**: a bare `vite.config` doesn't prove
  Vitest; jest.config + vitest.config can coexist during a migration. Require dependency +
  config + script-body corroboration; when ambiguous, flag rather than swap.
- **Case / separator / extension variance**: `Makefile` vs `makefile`, `compose.yaml` vs
  `docker-compose.yml`, `src/Components` vs `src/components`, `main` for `main.ts`. Match
  case-insensitively for the manifest FILE before declaring it missing; a basename match
  elsewhere usually means a path nuance, not a missing dir.
- **Version range operators are NOT drift**: `^18.3.1`/`~5.4.0`/`>=20`/`*` satisfies a doc family
  claim "React 18"/"Node 20+". Only a true major/explicit mismatch is drift, not a caret/tilde.
- **Version matches are TOKEN-bounded and pin-sourced, not substring/lockfile**: `version_present`
  matches the version as a whole numeric token against AUTHORITATIVE PINS ONLY (`.nvmrc`/`go.mod`/
  `engines`/`.tool-versions`/Dockerfile FROM tag/compose image tag), never as a bare substring and
  never against lockfiles (a lockfile pins transitive deps, so the doc's number would spuriously
  appear and mask drift). A doc "Node 20" is satisfied by pin "20.11.1" via the family/prefix rule.
- **Commented-out / optional / secret-omitted env keys**: `# OPTIONAL=` is not a declared key;
  secrets like `API_SECRET` are legitimately absent from `.env.example`. Absence is WEAK
  evidence — flag, don't delete. Env vars are also read indirectly (loaders, prefix scans).
- **A documented port is not "contradicted" just because compose/Dockerfile omit it**: an app's
  default port is often set in source or via an env default (`${PORT:-8000}`), or lives in a code
  constant or a port RANGE. Only treat a port as drift when compose/Dockerfile configure a
  DIFFERENT explicit value for the same service; an env-default/source-set port that is simply
  absent from compose is UNVERIFIABLE — leave and flag, never delete.
- **Commands gated behind a documented prerequisite** ("after running setup", "in the dev
  container") or **dynamically generated** (postinstall/codegen) may not appear in the committed
  manifest — flag-and-note rather than delete.
- **Conceptual layer names vs literal dirs**, **decorative ASCII-tree branches/labels**, and
  **a `.gitkeep`/README-only placeholder dir** are not paths/major services to add or test.
- **Vendored/generated matches are not evidence**: a path found only inside
  node_modules/dist/vendor/.venv does not satisfy a first-party source claim, and source under
  those trees is never "undocumented."
- **Renamed-but-equivalent is ONE fix, not two drifts**: if `lib/` became `packages/core/`,
  update the path once — don't both flag the old path missing AND the new path undocumented.
- **Anchor-slug formatting**: GitHub slugs lowercase, drop punctuation, hyphenate spaces, and
  occurrence-index duplicates (`#setup-1`) — compute the slug the same way and treat duplicate
  suffixes cautiously before declaring an anchor broken.
- **Git submodule / sibling-repo paths**: a path that lives in a `git submodule` (listed in
  `.gitmodules`) may be present-but-uninitialized (an empty dir) locally and read as MISSING even
  though it is a real, tracked submodule. A command/path that belongs to a SIBLING repo in a
  multi-repo setup is also not this repo's drift. When a missing path coincides with a `.gitmodules`
  entry or an out-of-repo reference, flag-and-note rather than delete.
- **Doc location**: a nested doc describes its own subtree — resolve paths against the doc's own
  directory before flagging. External http(s) URLs are never fetched or "verified."

### Grep starters (to LOCATE claims — never to decide a verdict)

```bash
D="$DOC"
grep -nE '`[^`]+`' "$D"                                              # code spans: commands, paths, versions
grep -nE 'npm |pnpm |yarn |bun |make |just |tox |poetry |uv |pdm |docker compose|docker-compose' "$D"  # commands
grep -nE '[A-Za-z0-9._-]+/' "$D"                                     # path-ish tokens (dirs/files)
grep -nEi 'node|python|go|rust|react|next|postgres|redis|typescript|pnpm|java' "$D"  # version/stack claims
grep -nE '\]\([^) ]+\)' "$D"                                         # markdown links (file + #anchor)
grep -nE '\$\{?[A-Z_][A-Z0-9_]*\}?|[A-Z_]{3,}=' "$D"                 # env vars / config keys
grep -nE ':[0-9]{2,5}\b|port' "$D"                                   # ports
grep -nE '^#{1,6} ' "$D"                                             # headings (for anchor slugs)
```

---

## STEP 4 — Act (EDIT the docs to fix grounded drift; keep-and-flag when unsure)

**DRY-RUN GATE — first executable line of the action phase. Do not edit past this point when
previewing:**

```bash
if [ "$AUDIT_DRY_RUN" = "1" ]; then
  echo "DRY RUN: per-doc verdict report only — no edits, no branch, no PR."
  # emit the verdict report (Step 6 body builder) and stop.
  echo "AUDIT_RESULT=ok (dry-run): audited $TOTAL doc(s); no changes made."
  exit 0
fi
TOUCHED=""   # newline-separated list of edited TARGET DOC paths (the ONLY things staged later)
```

**Action: fix ALL detected drift, every edit grounded in a concrete repo fact.** For each
claim:

- **CURRENT** → leave untouched.
- **UNVERIFIABLE** → leave untouched, record in the PR table as `kept (flagged)` with the reason.
- **STALE & objectively correctable** (dead command with an unambiguous successor key, dead path
  with a single rename candidate, contradicted version with a literal pin value, broken link with
  one unambiguous target) → **edit** the doc in place: replace the exact wrong literal with the
  correct one **read from the repo**. Apply the edit ONLY to the target doc file; NEVER edit a
  non-doc file. After editing, append the doc path to `TOUCHED` and **verify-after-edit** (Step 5).
- **STALE & best-effort structural** (a major undocumented dir/service to add, a
  rename-vs-deleted judgment call) → a rename/relabel of an existing literal is fine when one
  unambiguous successor exists. **ADDING a new line for an undocumented dir/service is OPT-IN**
  (`AUDIT_ADD_UNDOCUMENTED_DIRS=1`; default OFF) and, when enabled, the added line asserts ONLY
  the existence fact + the source of the name (a neutral `auto-added, please describe` stub) —
  never an agent-authored description of purpose/contents. **Mark every such edit low-confidence
  in the PR body** for human scrutiny. Never author a design narrative or invent purpose/data-flow.
- **STALE but no unambiguous successor** (removed with no clear replacement, multiple candidate
  targets, sources contradicting each other) → **keep and flag** in the PR; do not guess.

**PREFERRED EDIT MECHANISM: the harness `Edit` tool.** Apply each grounded edit by matching the
**exact unique surrounding context** (the wrong literal plus enough adjacent text to be unique in
the doc) and replacing only that occurrence, on the matched target doc only. This is the path for
EVERY edit — both objective literal fixes and best-effort structural lines — because it changes
exactly the located occurrence and nothing else. The shell helper below is a fallback for batch
contexts; it is a TRUE-LITERAL, SINGLE-OCCURRENCE replace (never a regex `gsub`) and it self-aborts
if it changed more than the one intended hunk.

```bash
# ── editAndSelfCheck (apply) ────────────────────────────────────────────────────
# LITERAL, SINGLE-OCCURRENCE in-place replace. Do NOT use `awk gsub` / `sed s///`: those treat
# `old` as a regex and `new`'s `&`/`\` as specials, so a literal containing metacharacters
# (paths `src/app.config.js`, globs `**/*.ts`, versions `^18.3.1`, `pytest -k 'a or b'`, `[tool.uv]`)
# would over-match, edit UNRELATED lines, or corrupt the text — a "new inaccuracy" that the
# per-claim verify-after-edit (which only re-checks the ONE changed value) would NOT catch.
apply_fix() { DOC="$1"; old="$2"; new="$3"   # never edit non-doc files; only $DOC
  # EXACT-LINE membership (not a substring test): $DOC must be an exact entry in $DOCS, so a
  # path that is merely a substring of a listed path (AGENTS.md vs app/AGENTS.md) cannot pass.
  printf '%s\n' "$DOCS" | grep -qxF -- "$DOC" || { echo "REFUSE: $DOC not a target doc"; return 1; }
  grep -qF -- "$old" "$DOC" || { echo "skip(not present): $old"; return 1; }
  before="$(git diff --quiet -- "$DOC" 2>/dev/null; echo $?)"   # 0=clean,1=already dirty
  # Replace ONLY the FIRST literal occurrence across the whole doc via index()/substr() (no regex).
  tmp="$(mktemp)"
  awk -v o="$old" -v n="$new" '
    BEGIN{done=0}
    { if(!done){ i=index($0,o); if(i){ $0=substr($0,1,i-1) n substr($0,i+length(o)); done=1 } } print }
  ' "$DOC" > "$tmp" && mv "$tmp" "$DOC"
  # POST-EDIT HUNK GUARD: the diff for this doc must be exactly ONE added line (one in-place
  # change). If more lines changed (collateral edit / corruption), revert and bail — never ship it.
  if [ "$before" = 0 ]; then
    n_add="$(git diff --unified=0 -- "$DOC" | grep -cE '^\+[^+]')"
    n_del="$(git diff --unified=0 -- "$DOC" | grep -cE '^-[^-]')"
    if [ "$n_add" != 1 ] || [ "$n_del" != 1 ]; then
      echo "REFUSE: edit touched more than the one intended hunk ($DOC: +$n_add/-$n_del) — reverting"
      git checkout -- "$DOC" 2>/dev/null || git restore -- "$DOC" 2>/dev/null
      return 1
    fi
  fi
  case "$TOUCHED" in *"$DOC"*) :;; *) TOUCHED="$TOUCHED$DOC
";; esac; }
```

> The `before`-clean check scopes the one-hunk assertion to a doc that was clean before THIS edit;
> when applying several edits to the same doc in one run, prefer the harness `Edit` tool (each call
> is a reviewed, exactly-located replacement) over re-running `apply_fix` against an already-dirty
> doc, so every individual change is independently confined to its located occurrence.

- **NEVER create a doc that does not exist** — fixing a doc by adding the missing file it
  references is out of scope; the only editable files are the matched target docs.
- **Respect `AUDIT_MAX_EDITS_PER_DOC`** — if a doc has more grounded drift than the cap, apply
  the cap's worth (prefer objective fixes over best-effort), and report the overflow as
  `deferred (edit cap)` in the PR so it is not silently dropped.
- **Keep-and-flag (in the PR body) anything unverifiable** — never delete a claim you cannot
  ground, and never "improve" correct prose.

---

## STEP 5 — Verify-after-edit (re-run the SAME static check on the NEW value — NEVER execute)

After **every** edit, re-run the same read-only check that detected the drift, now against the
NEW text, and confirm it matches reality. This replaces the test-execution of a code-audit:
**documented commands are NEVER run; no test suite, no build, no service is started.** If the
re-check does NOT pass, **REVERT that doc hunk** (`git checkout -- "$DOC"` / `git restore
"$DOC"`) and downgrade the claim to `kept (flagged)` — never ship a new inaccuracy.

```bash
# ── editAndSelfCheck (verify) ─────────────────────────────────────────────────
# Each CHANGED claim must now pass its detector against the NEW value:
#   new command -> cmd_defined "$new"      == DEFINED   (return 0)
#   new path    -> path_exists "$new"      == EXISTS    (return 0)
#   new version -> version_present t "$new"== MATCH     (return 0)
#   new link    -> check_links "$DOC"      == no BAD- for that target
#   structural  -> the added dir/service path resolves via path_exists / compose services
# If a re-check does NOT pass, REVERT that doc hunk and record keep/flag:
verify_after() { kind="$1"; shift
  case "$kind" in
    cmd)   cmd_defined "$1"          | grep -q '^DEFINED' ;;
    path)  path_exists "$1"          | grep -q '^EXISTS'  ;;
    ver)   version_present "$1" "$2" | grep -q '^MATCH'   ;;
    # FIXED-STRING link re-check: filter to BAD lines, then match the new target LITERALLY
    # (grep -F). Interpolating $1 into a regex (BAD-.*$1) could match a DIFFERENT BAD line
    # (false revert) or miss the intended one (false safe) when the target has metachars.
    link)  ! check_links "$DOC" | grep '^BAD-' | grep -qF -- "$1" ;;
    # struct: the added dir/service must actually exist — path resolves OR it's a compose service.
    struct) path_exists "$1" | grep -q '^EXISTS' \
              || git ls-files -- 'docker-compose*.yml' 'compose*.yml' 2>/dev/null \
                   | xargs -r grep -qE "^[[:space:]]{2,}$1:" ;;
    *) return 1 ;;   # FAIL CLOSED: an unknown kind is never silently "verified"
  esac
}
# Usage after each apply_fix (one line per kind so arg order is copy-pasteable):
#   if verify_after path "$new_path";        then echo "  ok: $new_path exists";
#   elif ...                                                                       fi
#   if verify_after cmd  "$new_cmd";         then ...                              fi
#   if verify_after ver  "$tool" "$new_ver"; then ...                              fi
#   if verify_after link "$new_target";      then ...                             fi
#   if verify_after struct "$new_dir";       then ...                             fi
# On a FAILED re-check: revert and keep-flag (NOT an error status — the edit was unsafe):
#   echo "  re-check FAILED — reverting $DOC"; git checkout -- "$DOC" 2>/dev/null || git restore -- "$DOC"
#   # (do NOT set ANY_ERROR here; a reverted unsafe edit is not a run failure — only
#   #  discovery/push/PR failures are 'error'. Optionally bump a separate REVERTED tally.)
```

> Notes:
> - **NEVER execute a documented command to "check" it.** Verification is the static
>   `cmd_defined`/`path_exists`/`version_present`/`check_links` re-check ONLY. A documented
>   command could deploy, reset a DB, or hang — running it is forbidden in every code path.
> - **A re-check failure is the editor's own mistake** (the "successor" wasn't real). Revert the
>   hunk and keep-and-flag the original claim; do not leave the doc in a worse state and do not
>   escalate to `error` for this — only push/PR/discovery failures are `error`.
> - **Best-effort structural additions** are re-checked too: the added dir/service path must
>   resolve via `path_exists` / a compose `services:` key, or the addition is reverted.

---

## STEP 6 — Deliver the changes for review (never the default branch)

**If you changed nothing this run, stop here.** Emit `AUDIT_RESULT=nothing` — an audit ran and
found nothing to change, which is success, not an error — and do not create a branch or open a PR.

Otherwise, open a Pull Request with your changes for a human to review. **You are Claude Code — use
whatever branch / commit / PR flow is correct for the environment you are running in; do not follow a
rigid script.** For example: in Claude Code Cloud you are already on a dedicated working branch, so
commit there and let the platform surface or open the PR (and honor any standing "don't open PRs"
rule — the platform handles it); in a plain checkout, create a short-lived branch off the default
branch and open a PR (e.g. `gh pr create`), or, if `gh` is unavailable, push the branch and report
that a PR should be opened.

**Non-negotiable rules — these are safety policy, NOT mechanics; never relax them:**
- **Commit ONLY the files this run changed** (the target doc files you edited in Step 4). NEVER `git add -A`, and never
  sweep in unrelated or untracked files (lockfile churn, `.env`, build artifacts). If anything
  outside your changed set would be staged, stop and report instead of committing.
- **Never commit to, push to, or merge into the default/main branch.** It changes only through a
  human-reviewed PR.
- **Never force-push, never delete branches, and never merge the PR yourself.**

**PR description** — include a per-claim verdict table (`doc | claim | status (current/stale/unverifiable) | action (fixed/added/kept-flagged) | evidence`), the note that verification was read-only and static (no documented command, test, or build was executed), that every edit is grounded in a concrete repo fact, and that anything unverifiable was left and flagged.

---

## STEP 7 — Final status

End on exactly one machine-grep-able status line so the caller can tell healthy idleness from a
silent break:

- `AUDIT_RESULT=nothing: <reason>` — nothing to do, OR an audit ran and found nothing to change
  (no repo / no runner / no candidates / all documented claims current). Exit 0. Healthy. **No PR in this case.**
- `AUDIT_RESULT=ok: <summary>` — audited AND delivered changes for review: a PR was opened, or —
  in an environment that manages PRs for you — your changes were committed and pushed to the working
  branch. Exit 0.
- `AUDIT_RESULT=error: <reason>` — could NOT run or could NOT deliver. **Exit non-zero so the caller
  alerts a human.**

For Claude Code Cloud, surface the `error` path as a notification rather than swallowing it.

---


## SAFETY (read this — it governs every step)

- **Conservative by default.** When a claim cannot be grounded in a concrete repo fact, **LEAVE
  it** and flag it in the PR. The cost of shipping a new inaccuracy >> the cost of leaving an
  old one.
- **ZERO FABRICATION.** Every edit is backed by a concrete, re-checkable repo fact — a path that
  exists/doesn't, a manifest key defined/not, a version literally present in a pin. No fact => no
  edit (flag instead). The corrected value is always read back FROM the repo.
- **NEVER execute anything.** Verification is purely static and read-only. NEVER run a documented
  command, script, target, recipe, orchestrator task, test suite, build, or service — it could
  deploy, reset a DB, or hang. NEVER hit the network. Verify-after-edit re-runs only the static
  checks.
- **ONLY edit the target docs.** The matched AGENTS.md/ARCHITECTURE.md set is the only thing ever
  written; source, manifests, config, CI, lockfiles are read-only evidence. **Never create a doc
  that does not exist.**
- **Clean-tree precondition.** Refuse to run on a dirty working tree; only ever stage the explicit
  touched-doc set. Never `git add -A`.
- **Never ship a new inaccuracy.** If a verify-after-edit re-check fails, revert that hunk and
  keep-and-flag the claim.
- **Never commit to the default/main branch.** All changes go through a dedicated branch + PR; a
  human reviews and merges.
- **`AUDIT_DRY_RUN=1`** verifies and reports only — zero edits, branches, or PRs. The guard is the
  first executable line of Step 4. Use it to preview on a new/unknown repo.
- **`AUDIT_MAX_DOCS` / `AUDIT_MAX_EDITS_PER_DOC`** cap the blast radius of any single run; overflow
  is reported as `deferred (cap)` / `deferred (edit cap)`, not silently dropped.
- **`AUDIT_ADD_UNDOCUMENTED_DIRS` defaults OFF** — the unattended weekly default NEVER writes a new
  prose line; it only corrects/removes drifted literals. When opted in, an added line is a neutral
  existence-only stub (name + source), never an agent-authored description, and always flagged.
- **Every edit changes only its one located occurrence.** Edits go through the harness `Edit` tool
  (exact unique context) or the literal single-occurrence `apply_fix`, which self-aborts and
  reverts if the diff is more than the one intended hunk — no unbounded/regex replacement.
- **Don't touch philosophy/aspirational/subjective prose.** WHY/rationale, roadmap/future/TODO,
  conventions, opinions, illustrative examples, conceptual layer diagrams, and external
  commands/URLs are never "corrected" — only objective, manifest/tree/pin-checkable drift is in
  scope.
- **Distinguish objective from best-effort.** Objective fixes (dead path, undefined command,
  contradicted pin, broken link with one target) vs best-effort/structural (added dir/service,
  rename-vs-deleted judgment) must be VISIBLY distinguished in the verdict table; every
  best-effort/low-confidence edit is flagged for human scrutiny.
- **Fail loud.** Error paths (discovery/push/PR failure, unexpected staged paths) exit non-zero
  with `AUDIT_RESULT=error`; only true idleness is a green `nothing`.

---

## What this skill deliberately does NOT do

- Does **not** execute any documented command, script, target, recipe, test suite, build, or
  service, and does **not** touch the network — verification is purely static and read-only.
- Does **not** edit, create, or report on any non-doc file (source, manifests, config, CI,
  lockfiles are read-only evidence); the ONLY editable files are the matched target docs.
- Does **not** create a doc that does not exist, and does **not** use a git window or persisted
  state — it re-verifies the full set of target docs on every run.
- Does **not** commit to or merge into the default branch; it only opens a PR for human review.
- Does **not** `git add -A`, stage a dirty tree, or run on an unclean working tree.
- Does **not** fabricate a replacement — uncertainty (no unambiguous successor, contradicting
  sources, subjective/aspirational/external claims) resolves to **keep-and-flag**, never a guess.
- Does **not** "improve" correct prose, restructure sections, or touch WHY/philosophy,
  roadmap/aspirational notes, conventions, opinions, illustrative examples, or external
  references — only objective, repo-checkable factual drift is in scope.
- Does **not** ship a new inaccuracy — every edit is re-verified after editing, and any hunk that
  fails its re-check is reverted and the claim kept-and-flagged.
