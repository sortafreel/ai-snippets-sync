---
name: fe-test-audit
description: >-
  Weekly, unattended frontend test-quality audit. Runs inside any FE git repo on
  a schedule (e.g. Claude Code Cloud cron), finds test files added/modified in the
  last ~8 days via a stateless git window, classifies them against a fake-test
  rubric (mock-of-mock, tautologies, hollow render-smoke, snapshot-only,
  implementation-detail, no-op/conditional assertions, etc.), then REWORKS
  salvageable fake tests into meaningful ones or DELETES the unsalvageable, and
  opens a Pull Request with a verdict table. Repo-agnostic and self-contained:
  auto-detects the package manager, test runner(s), and monorepo workspaces
  (pnpm/yarn/npm/bun, Jest/Vitest/Mocha/Jasmine/RTL/Enzyme/Playwright/Cypress,
  nx/turbo/lerna). Never runs the whole test suite, never commits to the default
  branch, and keeps any test it is unsure about. Use when scheduling or running a
  recurring "audit/prune fake frontend tests" job, or when asked to clean up
  low-value FE tests added recently.
---

# Frontend Test-Quality Auditor (`fe-test-audit`)

## Mission

Run **unattended on a weekly schedule** inside an arbitrary frontend git repo.
Find test files that were **added or modified in a recent git window**, read each
one against the fake-test rubric below, and **improve the test suite's signal**:
rework fake-but-salvageable tests into genuine behavioral tests, delete the
unsalvageable ones, and ship the changes as a **Pull Request** that a human
reviews. You are a careful editor, not a bulk deleter.

### Non-goals (read these first — they override any instinct to "be thorough")

- **You do NOT run the whole test suite.** Ever. Only the specific changed/affected
  test files, and only when you need to verify a rework or confirm a deletion is
  safe. Running the full FE suite is forbidden by default.
- **You do NOT touch tests outside the lookback window.** Pre-existing tests that
  were not added/modified recently are out of scope, even if they look fake.
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
Run them in order; the guards (clean-tree, dry-run, shallow-clone, push-failure) are
load-bearing. A few hard rules:

- **Build pathspec/file lists as positional parameters (`set -- …`), never as an
  unquoted string variable.** The environment's default shell is **zsh**, where an
  unquoted `$VAR` does **not** word-split (verified), so a space-separated glob string
  collapses into one literal pathspec that matches nothing and the skill silently finds
  zero files. `set -- a b c` then `-- "$@"` word-splits identically in bash **and** zsh.
- **Always emit a final status line** `AUDIT_RESULT=...` (see Step 7) so the scheduler
  can tell "audited nothing" (healthy) from "broke" (needs a human). Exit non-zero on
  error paths.
- Every command shown is POSIX-`sh`-compatible and verified in **both** bash and zsh.

---

## Configuration (env-overridable knobs)

All knobs are environment variables with safe defaults. Read them once at the start.

```bash
# Lookback window for git discovery. Default 8 days: just above the 7-day cadence
# so weekly scheduling jitter (a run that fires a few hours late) never drops a file.
: "${AUDIT_LOOKBACK:=8.days}"          # any `git log --since` expression, e.g. "8.days", "2025-06-01"

# Base branch for the PR. Empty => auto-detect the repo's default branch (see Step 1).
: "${AUDIT_BASE_BRANCH:=}"

# Branch name prefix for the audit branch.
: "${AUDIT_BRANCH_PREFIX:=chore/fe-test-audit}"

# Dry run: classify + report only. No edits, no deletes, no branch, no PR.
: "${AUDIT_DRY_RUN:=0}"                 # 1 = dry run

# Hard cap on candidate files processed in a single unattended run (bounds blast radius).
: "${AUDIT_MAX_FILES:=25}"

# Per-file verify timeout (seconds). A hard ceiling so a watch-mode runner can never wedge
# the weekly job indefinitely.
: "${AUDIT_VERIFY_TIMEOUT:=180}"

# Extra include/exclude path SUBSTRINGS (space-separated). Matched as plain substrings
# against the candidate path (NOT shell/`**` globs — see Step 2 for why).
: "${AUDIT_INCLUDE_SUBSTR:=}"          # e.g. "apps/web/  packages/ui/"
: "${AUDIT_EXCLUDE_SUBSTR:=}"          # e.g. "/legacy/  /vendor/  .stories."
```

The built-in test-file pathspecs are defined directly in Step 2 as a positional array
(with `:(glob)` magic). Do not move them into a string knob — see the IMPORTANT note above.

> **Optional resilience upgrade (NOT enabled by default):** to survive *missed* runs
> (a skipped week) without re-reviewing the same window, you may persist a single
> "last-reviewed commit" SHA (e.g. in `.fe-test-audit-marker` or a git note) and diff
> from there instead of a time window — but the **default flow is intentionally
> stateless**: no committed state, no marker, just the git time window.

---

## STEP 1 — Preflight, clean-tree gate & detection

**Goal:** confirm we're at the root of a frontend git repo with a clean tree, deepen a
shallow clone, detect tooling, and bail cleanly if there's no FE test runner.

```bash
fail()    { echo "AUDIT_RESULT=error: $*" >&2; exit 1; }     # could-not-run -> ALERT (non-zero)
nothing() { echo "AUDIT_RESULT=nothing: $*";   exit 0; }     # legitimately nothing to do (healthy)

# 1a. Must be inside a git work tree, and we must be AT its root.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || nothing "not a git repo"
ROOT="$(git rev-parse --show-toplevel)" || fail "cannot resolve repo root"
cd "$ROOT" || fail "cannot cd to repo root"

# 1b. CLEAN-TREE PRECONDITION. An unattended deleter must NOT run on a dirty tree:
#     post-install lockfile churn, a stray .env.local, or residue from a crashed prior
#     run would otherwise get swept into the PR (secrets / unrelated changes). Refuse.
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean:"; git status --porcelain | head -20
  nothing "dirty working tree; refusing to run unattended (commit/stash/reset first)"
fi

# 1c. Shallow clones are the CI/Cloud norm (actions/checkout depth=1). `git log --since`
#     then only sees the grafted commit -> window under-reported AND every grafted file
#     looks "added". Deepen to cover the window; warn if we cannot.
SHALLOW_WARN=""
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
  git fetch --shallow-since="$AUDIT_LOOKBACK" --quiet 2>/dev/null \
    || git fetch --unshallow --quiet 2>/dev/null \
    || SHALLOW_WARN="WARNING: shallow repo could not be deepened; discovery window may be truncated."
  [ -n "$SHALLOW_WARN" ] && echo "$SHALLOW_WARN"
fi

# 1d. Resolve base branch. Auto-detect the DEFAULT branch; never silently fall back to the
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

# 1e. Confirm this repo contains a JS/TS package SOMEWHERE — root OR a subdirectory. Monorepos
#     often keep the frontend under frontend/, web/, client/, or apps/* with NO root
#     package.json, so do NOT require one at the root; runner detection in 1h is the real gate.
git ls-files -- '*package.json' 2>/dev/null | grep -qv node_modules \
  || nothing "no package.json anywhere in the repo — not a JS/TS project"

# 1f. Ensure a git identity exists (an unattended commit fails without one). Set a
#     fallback author so the commit in Step 6 cannot fail mid-flight.
git config user.email >/dev/null 2>&1 || git config user.email "fe-test-audit@users.noreply.github.com"
git config user.name  >/dev/null 2>&1 || git config user.name  "fe-test-audit bot"
```

**1g. Detect the package manager** and the correct **runner-invocation verb** (these
differ per PM — `bun` has no `bun exec` for local binaries):

```bash
if   [ -f pnpm-lock.yaml ]; then PM=pnpm
elif [ -f yarn.lock ];      then PM=yarn
elif [ -f bun.lockb ] || [ -f bun.lock ]; then PM=bun
elif [ -f package-lock.json ]; then PM=npm
else
  PM="$(node -e "try{const p=require('./package.json').packageManager||'';process.stdout.write(p.split('@')[0]||'npm')}catch(e){process.stdout.write('npm')}" 2>/dev/null || echo npm)"
fi

# Run-a-local-binary verb. Crucial: bun != `bun exec`; npm needs `--` before runner flags.
case "$PM" in
  pnpm) RUN="pnpm exec" ;;
  yarn) RUN="yarn exec" ;;
  npm)  RUN="npm exec --" ;;      # `npm exec -- jest --foo` forwards --foo to jest
  bun)  RUN="bunx" ;;             # `bun x` is equivalent; `bun exec` runs a shell string (wrong)
  *)    RUN="npx" ;;
esac
echo "Package manager: $PM  | run-binary verb: $RUN"
```

**1h. Detect test runner(s) ACROSS THE WHOLE REPO, not just the root package.json.**
A common monorepo shape has a thin root and declares Jest/Vitest/RTL only in workspace
packages; root-only detection would wrongly conclude "no runner" and bail. Aggregate
every non-`node_modules` `package.json` plus config-file presence:

```bash
# Concatenate every tracked package.json (root + workspaces) and list config-file names.
HAY="$(
  git ls-files -- '*package.json' 2>/dev/null | grep -v node_modules | while IFS= read -r p; do cat "$p" 2>/dev/null; done
  git ls-files 2>/dev/null | grep -v node_modules \
    | grep -Ei '(jest\.config|vitest\.config|vitest\.workspace|vite\.config|\.mocharc|jasmine\.json|playwright\.config|cypress\.config)'
)"
have() { printf '%s' "$HAY" | grep -qiE "$1"; }

# NOTE: a bare vite.config is NOT proof of Vitest (every Vite app has one). Require a real
# vitest marker.
USES_VITEST=0;    have '"vitest"|vitest\.config|vitest\.workspace'           && USES_VITEST=1
USES_JEST=0;      have '"jest"|jest\.config|"ts-jest"|"babel-jest"'          && USES_JEST=1
USES_MOCHA=0;     have '"mocha"|\.mocharc'                                   && USES_MOCHA=1
USES_JASMINE=0;   have '"jasmine"|jasmine\.json'                             && USES_JASMINE=1
USES_PLAYWRIGHT=0;have '"@playwright/test"|playwright\.config'              && USES_PLAYWRIGHT=1
USES_CYPRESS=0;   have '"cypress"|cypress\.config'                           && USES_CYPRESS=1
# Library hints (affect rubric calibration, not how files are run):
USES_RTL=0;       have '@testing-library/'                                   && USES_RTL=1
USES_ENZYME=0;    have '"enzyme"'                                            && USES_ENZYME=1

echo "Runners: vitest=$USES_VITEST jest=$USES_JEST mocha=$USES_MOCHA jasmine=$USES_JASMINE playwright=$USES_PLAYWRIGHT cypress=$USES_CYPRESS | rtl=$USES_RTL enzyme=$USES_ENZYME"

if [ $((USES_VITEST+USES_JEST+USES_MOCHA+USES_JASMINE+USES_PLAYWRIGHT+USES_CYPRESS)) -eq 0 ]; then
  nothing "no frontend test runner detected anywhere in the repo"
fi
```

**1i. Detect monorepo layout** (pnpm/yarn/npm/bun workspaces **and** nx/turbo/lerna/rush).
Runners are re-detected **per workspace** at verify time (Step 5), because package A may use
Jest while package B uses Vitest:

```bash
[ -f pnpm-workspace.yaml ] && echo "monorepo: pnpm-workspace.yaml"
[ -f nx.json ]             && echo "monorepo: nx (nx.json)"
[ -f turbo.json ]          && echo "monorepo: turbo (turbo.json)"
[ -f lerna.json ]          && echo "monorepo: lerna (lerna.json)"
[ -f rush.json ]           && echo "monorepo: rush (rush.json)"
node -e "try{const w=require('./package.json').workspaces;if(w)console.log('monorepo: package.json workspaces')}catch(e){}" 2>/dev/null
```

A candidate file's **workspace root** = the nearest ancestor directory containing a
`package.json` (fallback: repo root). Step 3 computes this per file.

---

## STEP 2 — Discover candidate test files (STATELESS git window)

**Goal:** purely from git, list test files **added (A) or modified (M)** within the
lookback window. No state file.

```bash
# 2a. Build the test-file pathspecs as POSITIONAL PARAMETERS (word-splits in bash AND zsh).
#     :(glob) magic makes `**` cross directories AND match at depth 0 (so root-level
#     `root.test.ts` is found — default pathspec magic would MISS it). Root-level bare
#     variants are added belt-and-suspenders.
set -- \
  ':(glob)**/*.test.*'    ':(glob)*.test.*' \
  ':(glob)**/*.spec.*'    ':(glob)*.spec.*' \
  ':(glob)**/*.cy.*'      ':(glob)*.cy.*' \
  ':(glob)**/*.e2e.*'     ':(glob)*.e2e.*' \
  ':(glob)**/__tests__/**' \
  ':(glob)**/e2e/**' ':(glob)**/tests/**' ':(glob)**/test/**'

CANDIDATES_RAW="$(git log --since="$AUDIT_LOOKBACK" --diff-filter=AM \
  --name-only --pretty=format: -- "$@" 2>/dev/null | sed '/^$/d' | sort -u)"

# 2b. POST-FILTER to *real* test files. The directory globs (__tests__, tests, e2e, …)
#     also match helpers, fixtures, __snapshots__/*.snap, __mocks__, and setup files —
#     feeding those to the classifier risks deleting a shared fixture other tests import.
#     Keep only basenames that match a test-file suffix; drop snapshots/mocks/coverage/build;
#     apply substring include/exclude knobs.
CANDIDATES=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue                                   # added-then-deleted => gone; skip
  case "$f" in
    */node_modules/*|node_modules/*|*/dist/*|*/build/*|*/.next/*|*/coverage/*|\
    */__snapshots__/*|*/__mocks__/*|*.snap) continue;;
  esac
  base="$(basename "$f")"
  printf '%s' "$base" | grep -qE '\.(test|spec|cy|e2e)\.[mc]?[jt]sx?$' || continue
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

# 2c. SANITY GUARD against the "silent green no-op". If discovery found nothing BUT test
#     files clearly exist in the tree, the discovery itself is likely broken (or the window
#     is genuinely quiet) — warn loudly rather than reporting a clean success that hides a bug.
if [ -z "$CANDIDATES" ]; then
  EXISTING_TESTS="$(git ls-files 2>/dev/null | grep -v node_modules \
    | grep -E '\.(test|spec|cy|e2e)\.[mc]?[jt]sx?$' | head -1)"
  if [ -n "$EXISTING_TESTS" ]; then
    echo "DIAGNOSTIC: 0 candidates in the window, but test files exist (e.g. $EXISTING_TESTS)."
    echo "            This is expected only if no test changed recently. ${SHALLOW_WARN:+($SHALLOW_WARN)}"
  fi
  nothing "no FE test files added/modified in the last window ($AUDIT_LOOKBACK)"
fi

# 2d. Enforce the per-run file cap (bounds an unattended run). Process first N; report rest.
TOTAL="$(printf '%s\n' "$CANDIDATES" | wc -l | tr -d ' ')"
CAPPED_OUT="$(printf '%s\n' "$CANDIDATES" | tail -n +"$((AUDIT_MAX_FILES+1))")"
CANDIDATES="$(printf '%s\n' "$CANDIDATES" | head -n "$AUDIT_MAX_FILES")"
echo "Discovered $TOTAL candidate test file(s); processing up to $AUDIT_MAX_FILES this run:"
printf '%s\n' "$CANDIDATES"
[ -n "$CAPPED_OUT" ] && { echo "Deferred (over cap):"; printf '%s\n' "$CAPPED_OUT"; }
```

> To review only the **new/changed** tests in a *modified* file (not pre-existing ones),
> diff it across the window. `SINCE_SHA` may be empty in a young/shallow repo — guard it:
> ```bash
> SINCE_SHA="$(git rev-list -1 --before="$AUDIT_LOOKBACK" HEAD 2>/dev/null)"
> [ -n "$SINCE_SHA" ] && git diff "$SINCE_SHA" -- "$FILE"   # added/changed lines = review scope
> ```
> For newly-added files, the whole file is in scope. If `SINCE_SHA` is empty (history
> doesn't reach back that far), review the full file but say so in the PR.

---

## STEP 3 — Per-candidate iteration, workspace + runner resolution, classification

Iterate over `$CANDIDATES`. For **each** file resolve its workspace and runner, then read it
against the rubric. Track the set of files you actually change in `TOUCHED` (used by Step 6 —
**only these are staged**). Use this scaffold:

```bash
TOUCHED=""        # newline-separated list of files this run reworked OR deleted
REWORKED=""; DELETED=""; KEPT_FLAGGED=""; KEPT_OK=""   # for the report
ANY_ERROR=0

# Helper: nearest ancestor dir containing package.json (workspace root), fallback ROOT.
ws_root() {
  d="$(dirname "$1")"
  while [ "$d" != "." ] && [ "$d" != "/" ]; do
    [ -f "$d/package.json" ] && { printf '%s' "$d"; return; }
    d="$(dirname "$d")"
  done
  printf '%s' "$ROOT"
}
# Helper: package "name" of a workspace dir (for `pnpm --filter`); empty if none.
ws_name() { node -e "try{process.stdout.write(require('$1/package.json').name||'')}catch(e){}" 2>/dev/null; }

printf '%s\n' "$CANDIDATES" | while IFS= read -r FILE; do
  [ -z "$FILE" ] && continue
  WS="$(ws_root "$FILE")"
  WS_NAME="$(ws_name "$WS")"
  echo "==> $FILE   (workspace: $WS${WS_NAME:+ / $WS_NAME})"
  # ... read + classify (below); record verdict; act in Step 4; verify in Step 5 ...
done
```

> Note: a `while` loop fed by a pipe runs in a subshell in some shells, so variables set
> inside it (`TOUCHED`, counters) may not survive. If you need the lists afterward, either
> drive the loop with a here-doc/`for` over the candidate list, or append per-file results
> to a temp file (`echo "$FILE	reworked" >> "$RESULTS"`) and read it back in Step 6.
> The simplest robust pattern for an agent is to **process one file at a time** and keep the
> running lists in your own working memory, writing each verdict row to `$RESULTS`.

**For each file:** read it (don't grep-and-guess — grep *locates* suspicion; the verdict
comes from reading). Determine the **per-test-type calibration**, then assign each
`it`/`test` block (and the file overall) one of:

- **FAKE** — matches an anti-pattern, no green-flag/false-positive exemption applies.
- **MEANINGFUL** — exercises real code and asserts a real, behavior-sensitive outcome.
- **UNSURE** — genuinely ambiguous after reading. Default action: **KEEP and flag**.

### Strictness calibration by test type (avoid false positives)

- **Unit / component tests that mock** (Jest/Vitest + RTL/Enzyme): the **primary target**.
  Apply the full rubric strictly. Mock-of-mock, hollow render-smoke, tautologies,
  snapshot-only, and implementation-detail tests live here.
- **Integration tests** (real component tree, only the network/boundary mocked): mostly
  legitimate. Only fake if the assertion reads the stub layer back with no app-visible
  effect, or the *subject itself* is mocked. Mocking the network is NOT a red flag.
- **e2e / Playwright / Cypress**: drive a real browser/app; they **almost never** have
  the mock-of-mock problem. Require a **very high bar** before flagging. Intercepting/
  stubbing routes is standard and healthy. Only the rare "asserts the intercepted
  fixture via the network layer (`.its('response.body')`), with zero DOM/URL/state
  assertion" case is fake. When uncertain on e2e: **KEEP-and-flag, never delete.**
- **Unfamiliar runners/DSLs** (Cypress component testing, Storybook play functions,
  custom `render` wrappers, type-level tests): the literal token `expect(` may be absent
  while real assertions exist — `cy.should`/`cy.contains`, `await expect(locator)…`,
  `await expect(canvas…)`, jest-axe `toHaveNoViolations`, `expectTypeOf`/`@ts-expect-error`.
  Recognize the runner's assertion vocabulary **before** concluding "no assertion."

### The rubric — fake-test anti-patterns

For each: what makes it fake, how to spot it, how to salvage, and when deletion is allowed.

1. **Render-smoke with no behavioral assertion.** Mounts a component but asserts only
   that it didn't throw: zero `expect`, or the only assertions target
   `container`/`wrapper`/the render result with always-true matchers
   (`toBeTruthy`, `toBeDefined`, `toBeInTheDocument()` on `container`, `not.toThrow`,
   `toMatchObject({})`). *Salvage:* assert a prop that flows to the DOM, or an
   interaction outcome (`expect(screen.getByRole('heading',{name:user.name})).toBeVisible()`).
   *Delete only if* there is genuinely no user-visible output AND an integration test
   already covers it.

2. **Asserting on a mocked child (mock-of-mock).** A sibling child component is replaced
   by a `jest.mock`/`vi.mock` stub, then the test asserts the stub appeared or received
   props (`getByTestId('chart')` where the mock emits `data-testid="chart"`;
   `toHaveBeenCalledWith(objectContaining(...))` on a stub that renders null). It only
   verifies the mock you wrote. *Salvage:* stop mocking the child if cheap/deterministic
   and assert its real user-visible output; if the child is genuinely heavy (canvas/WebGL/
   maps), keep the mock but move the assertion to the parent's own DOM / callbacks /
   transforms. *Delete only if* the sole purpose is "stub rendered/received props" and a
   higher-level test already covers the composition.

3. **Snapshot-only test.** `toMatchSnapshot`/`toMatchInlineSnapshot`/`toMatchImageSnapshot`
   as the **only** assertion in the block. Encodes no intent; gets blindly `--updated`.
   *Salvage:* replace with explicit assertions on the meaningful parts
   (`expect(screen.getByText('$9.99')).toBeVisible()`); keep at most one small, reviewed
   snapshot **paired with** a real behavioral assertion. *Delete* a redundant snapshot-only
   test when an explicit test for the same component exists; if it's the component's only
   test, rework instead. (Playwright `toHaveScreenshot` visual snapshots are out of scope.)

4. **Testing implementation details / internal state.** Reaching into `.instance()`,
   `.state(`, `.setState`, `spyOn(*.prototype`, asserting on `result.current` properties
   the component never renders. Passes even when the UI is broken; breaks on harmless
   refactors. Enzyme `shallow` + state/instance access is a strong signal. *Salvage:*
   rewrite as a user flow — `await userEvent.click(getByRole('button',{name:/toggle/i}))`
   then `expect(getByRole('menu')).toBeVisible()`. *Delete only if* the internal behavior
   has no user-visible manifestation at all (usually means dead code) and is covered elsewhere.

5. **Test-id-only behavioral void.** Every query is `getByTestId`/`queryByTestId` and the
   only assertion is existence/truthiness, especially when the test-id is a code-ish slug
   mirroring a handler/component name. *Salvage:* re-query by accessible role/name or
   visible text and assert real content/interaction. Keep a test-id only when there is no
   accessible handle, paired with a real assertion. *Delete only if* the node's existence
   is irrelevant and duplicated by a stronger test.

6. **Mocking the very subject under test (or its core logic).** The spec mocks the same
   module it imports as the subject (`Button.test.tsx` → `jest.mock('./Button')`), or mocks
   the hook/util that *is* the behavior, then asserts a literal that originated entirely in
   the mock factory. The real code can never fail. *Salvage:* remove the mock of the SUT and
   render real; for a "mocked core hook," mock only its I/O dependency and let the real hook
   compute. *Almost never delete* — un-mock instead; delete only if the un-mocked test
   exactly duplicates an existing one.

7. **"Mock was called" as the ONLY assertion (spy-existence tautology).** Only
   `toHaveBeenCalled`/`toHaveBeenCalledTimes`/`toBeCalled` on a `jest.fn()`/`vi.fn()`/spy,
   with no meaningful `toHaveBeenCalledWith` args and no DOM/screen assertion. Bare
   `toHaveBeenCalled()` is the key signal; worse when the spy is invoked directly in the
   test rather than through a real interaction. *Salvage:* assert the **arguments** when the
   contract is the callback shape AND/OR the user-visible consequence (spinner→rows, route
   change, toast). *Delete only if* the call has no meaningful args, no visible effect, and
   an integration test already covers the interaction.

8. **Re-implementing the SUT's logic to build the expectation (the oracle is the code).**
   The expected value is computed in the test with the **same** algorithm/format the source
   uses (`.toFixed`, `.reduce`, the same template literal/regex), or imports the SUT's own
   transform on both sides (`expect(slugify(x)).toBe(slugify(x))`). It can't fail for a logic
   bug. *Salvage:* replace with a **hand-verified hardcoded literal** oracle
   (`expect(getByText('$1,234.50')).toBeVisible()`); pick boundary/rounding/locale cases.
   *Delete only if* every case is tautological AND the function is trivial/covered elsewhere.

9. **Conditional / swallowed / skipped assertions (may never run).** `expect` guarded by
   `if (queryBy...)` (skipped when null), inside `try` with an empty/log-only `catch`,
   after an early return, or `it.skip`/`xit`/`test.todo`. Also `it.only`/`fit`/`fdescribe`
   (silently drops siblings — a CI-poisoning bug, always flag). *Salvage:* set up the state
   deterministically and assert unconditionally; for async add `await`+`findBy` and/or
   `expect.assertions(n)`; for expected throws use `expect(fn).toThrow()` /
   `await expect(p).rejects.toThrow()`; un-skip and fix; **always remove `.only`**. *Delete*
   permanently-rotted `skip`/`todo` shells referencing removed APIs.

10. **Trivially-true / self-equality matchers.** `expect(true).toBe(true)`,
    `expect(1).toEqual(1)`, `expect(user).toEqual(user)`, `expect(props.title).toBe(props.title)`,
    `typeof handler).toBe('function')` on a known fn prop, `toBeDefined`/`toBeTruthy` on a
    value assigned a literal in the same block, or LHS textually identical to RHS. *Salvage:*
    recover the intended check and assert it against an independent expected value or real DOM
    outcome. *Delete* if the block contains only vacuous matchers with no recoverable intent.

11. **Asserting the mock's own return / fixture round-trip.** `mockReturnValue(V)` /
    `mockResolvedValue(V)` then `expect(mocked(...)).toBe(V)` with the **same** `V` and no real
    transformation between, or a component stubbed to echo the mock verbatim. *Salvage:* put
    REAL code between mock and assertion — mock only the boundary (network/store), let the real
    component format/branch/filter, assert the **transformed** result (differs from the raw
    fixture). *Delete* if it only round-trips a mock with no production code in the path and
    can't be restructured.

12. **No-op / unconditional waits with no following assertion.** `await waitFor(() => {})`,
    `await waitFor(() => expect(true).toBe(true))`, `page.waitForTimeout(ms)`, `cy.wait(<number>)`
    (fixed ms, not an aliased route) as the last meaningful statement. *Salvage:* replace fixed
    sleeps with assertion-based waits — `await screen.findByText(...)`,
    `await waitFor(() => expect(...))`, Playwright `await expect(locator).toBeVisible()`,
    Cypress `cy.intercept().as('x'); cy.wait('@x')` **then a DOM assertion**. *Delete* the wait
    line (not necessarily the test); delete the test only if nothing assertable remains.

13. **Over-mocked unit (no real code path runs).** Children, primary hook(s), router, and store
    are all mocked, and every assertion target is a string defined inside a mock factory in the
    same file (high mock-count file whose only assertions reference mock-produced testids).
    *Salvage:* unmock the layers you actually want to test; keep mocks only at true boundaries;
    assert real composed output. *Delete* if, after unmocking, it duplicates a child's own unit
    test or is a redundant smoke shell.

14. **Asserting framework/library behavior instead of app behavior.** Verifying that React/the
    router/`<a href>` faithfully renders a constant prop, with no app logic deciding the value
    (prop literal === asserted literal, no conditional logic around it). *Salvage:* re-target at
    the app's own decision logic (computed `disabled`, role-based routing). *Delete* if the
    component is a pure passthrough with no logic of its own.

### Green flags — NEVER flag these as fake

- Queries by accessible role/name/label/visible text **and** asserts perceivable
  content/visibility/state. `toBeInTheDocument()`/`toBeVisible()` on a `getByRole`/`getByText`
  result is a **real** assertion (the query throws if absent).
- A real user interaction (`userEvent` preferred, or `fireEvent`/`page.click`/`cy.get().click`)
  **followed by** an assertion on a **changed** user-visible outcome (text appears/disappears,
  `aria-expanded`/`disabled` flips, route/toast/modal changes). Cause→effect = real behavior.
- `toHaveBeenCalledWith(...)` where the asserted **arguments carry domain meaning** and are
  **derived** by the subject from its inputs (ids, payloads, formatted/merged/validated values) —
  a legitimate collaborator-contract test, even though the callback is a mock.
- Mocks confined to true **boundaries** (network: fetch/axios/MSW/nock; timers; `Date`;
  randomness/UUID; router; global store; analytics; heavy canvas/WebGL/map widgets) while the
  subject and its presentational children render for real. MSW/network fixtures asserted via the
  **rendered, transformed** result (formatting/filtering/sorting by real code).
- Independently-derived/hardcoded expected values (golden literals), not recomputed with the
  source's algorithm or imported from the SUT.
- Async correctness via `findBy*`/`waitFor` (with a real `expect` inside) and often
  `expect.assertions(n)`/`expect.hasAssertions()` — these are **safeguards**, never count them
  as vacuous.
- Discriminating negative/edge assertions: `queryBy...().not.toBeInTheDocument()` after a
  removing action; error/empty/loading states asserted via visible messaging.
- a11y/behavioral matchers tied to perception: `toBeDisabled`, `toBeVisible`,
  `toHaveAccessibleName`, `toHaveTextContent(specific)`, `toHaveValue`, `toBeChecked`, `aria-*`.
- `renderHook` asserting on `result.current` values/handlers that are part of the hook's
  **public return contract**.
- A trivial pure-presentational component covered by a single render + one text/role assertion —
  **proportionate**, keep.
- Parameterized `it.each`/`test.each` mapping distinct inputs to distinct **independent** expected
  outputs.
- **e2e/Playwright/Cypress** driving real navigation, real forms, asserting post-action UI/URL.

### False-positive traps — looks fake, is actually fine (check before flagging)

- **Mocking the network ≠ mock-of-mock.** If *any* assertion targets DOM/URL/store/visible effect,
  the real component, router, reducers, selectors, and rendering ran. Judge by the **assertion
  target**, not by the presence of a stub. Stub = input boundary (fine); fake only if the assertion
  also reads the stub layer back with zero app-visible effect.
- **`toHaveBeenCalledWith` with meaningful, derived args is real** (analytics/navigation/`onSubmit`
  side-effects with no observable return). Only bare `toHaveBeenCalled()` with no args and no UI
  effect — or a verbatim echo of a value the test just passed in with no logic between — is fake.
- **`getByTestId` is the correct escape hatch** when there's no accessible role/stable text
  (decorative container, virtualized row, third-party widget). Test-id + a **real** content/
  interaction assertion is fine; only test-id + existence-only is suspect.
- **A single small, reviewed snapshot paired with explicit assertions** can be acceptable. Flag
  snapshot-**only** blocks. A small curated `toMatchInlineSnapshot` may be intentionally pinning a
  regression (even an empty/`[]` one) — check history/comments before deleting.
- **`expect.assertions(n)`/`hasAssertions()` are quality safeguards** — never count as fake; their
  presence is a green flag.
- **`renderHook` asserting public-return properties is valid;** only truly internal, non-returned
  state is the implementation-detail anti-pattern.
- **Re-implementation-looking code that builds INPUT fixtures is fine** (computing a date to feed as
  a prop). The anti-pattern is computing the **expected OUTPUT** with the source's own algorithm —
  confirm the duplicated logic is on the **assertion** side.
- **`it.each` with golden expected values is valid;** only flag when the table's expected column is
  derived by calling the SUT's transform.
- **Integration tests rendering a parent with several real children** exercise real composition —
  high-value, keep — unless a child is actually stubbed and asserted on.
- **No literal `expect(` ≠ hollow.** Cypress `cy.should`/`cy.contains`, Playwright
  `await expect(locator)…`, Storybook play `await expect(canvas…)`, jest-axe, custom assertion
  helpers, and type-level tests all assert without a bare `expect(`. Resolve helpers/snapshot/await
  forms first.
- **Faking `Date`/timers/random is required** for determinism; fake only if the assertion reads the
  faked primitive straight back, real if it asserts a downstream computed effect.
- **Setup/wiring is not a test.** Never count a `beforeEach`/factory/`render` helper's lack of
  `expect()` against an `it()` block, and **never remove a shared fixture/mock another test imports**
  — verify no other test references it first (Step 4).

### Grep starters (to LOCATE suspicion — never to decide a verdict)

```bash
F="$FILE"
grep -nE 'toMatchSnapshot|toMatchInlineSnapshot' "$F"                 # snapshot-only candidates
grep -nE '\.(skip|only|todo)\(|\bxit\(|\bfit\(|\bxdescribe\(|\bfdescribe\(' "$F"  # skipped/focused
grep -nE 'toHaveBeenCalled\b|toHaveBeenCalledTimes' "$F"             # spy-existence (check for args)
grep -nE 'mockReturnValue|mockResolvedValue|mockImplementation' "$F" # round-trip / re-impl candidates
grep -nE '\.instance\(|\.state\(|\.setState|spyOn\([^,]*\.prototype' "$F"  # impl-detail (Enzyme)
grep -nE 'getByTestId|queryByTestId' "$F"                            # test-id-only candidates
grep -nE 'jest\.mock\(|vi\.mock\(|jest\.doMock\(' "$F"               # mock targets (boundary vs sibling/SUT)
grep -nE 'waitForTimeout|cy\.wait\([0-9]|setTimeout' "$F"           # fixed-time no-op waits
grep -nE 'expect\((true|false|[0-9]+|null|undefined)\)\.(toBe|toEqual)' "$F"  # tautologies
grep -c 'expect(' "$F"                                               # 0 => possible no-assertion (or a DSL — verify!)
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
  - Swap hollow/test-id queries for accessible role/name/text queries.
  - Replace existence/truthiness with a behavior- or content-sensitive assertion.
  - Trigger a real interaction and assert the changed user-visible outcome.
  - Replace computed/echoed expectations with **hand-verified hardcoded** oracles.
  - Un-mock the SUT or a mocked sibling when cheap/deterministic; keep mocks only at boundaries.
  - Upgrade `toHaveBeenCalled()` to assert derived arguments and/or the visible effect.
  - Convert snapshot-only into explicit assertions (keep at most one small snapshot + a real assert).
  - Replace fixed sleeps with assertion-based waits; add `await`/`return`/`expect.assertions(n)` to
    async; convert try/catch into `toThrow`/`rejects.toThrow`; remove `.only`; un-skip and fix.
  - After editing, append the path to `TOUCHED` and **verify** (Step 5).
- **FAKE & unsalvageable** → **delete** the block (or the whole file if it becomes empty),
  allowed only when **all** the deletion safety checks below pass.

### Pre-deletion safety checks (ALL must pass; on ANY uncertainty → keep-and-flag)

```bash
# (a) Does the file EXPORT anything beyond test blocks? If so it doubles as a shared module
#     (fixtures/mocks/helpers) — deleting it can break importers. Prefer keep-and-flag.
if grep -qE '^\s*export\b' "$FILE"; then
  echo "  $FILE exports symbols — may be a shared module. KEEP-and-flag instead of delete."
  # record as keep (flagged): "exports shared symbols"; do NOT delete.
fi

# (b) Is the file imported anywhere else? Match import/require by path stem AND by directory.
#     This is a heuristic; alias/tsconfig-path imports may be missed, so it only *raises*
#     caution — it never authorizes a delete on its own.
REL_NOEXT="${FILE%.*}"                          # e.g. src/foo.test
STEM="$(basename "$REL_NOEXT")"                 # e.g. foo.test
if git grep -nE "from ['\"][^'\"]*${STEM}['\"]|require\(['\"][^'\"]*${STEM}['\"]" \
     -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' 2>/dev/null | grep -v ":$FILE:" | grep . ; then
  echo "  $FILE appears to be imported elsewhere — KEEP-and-flag instead of delete."
  # record as keep (flagged): "imported by other files"; do NOT delete.
fi
```

Deletion is allowed **only** when (a) it exports nothing shared, (b) nothing imports it, **and**
one of:
- there is genuinely nothing user-visible/behavioral to assert, **or**
- the test is fundamentally redundant (a stronger/integration/e2e test already covers it), **or**
- a meaningful rework is impossible (e.g. a rotted permanently-skipped stub).

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

**Re-detect the runner from the FILE's workspace** (mixed monorepos), and run with a hard
timeout, `CI=true`, no watch, and exact-file flags (a watch-mode hang would otherwise wedge the
weekly job forever):

```bash
# Re-detect runner for THIS file's workspace ($WS from Step 3).
WHAY="$( [ -f "$WS/package.json" ] && cat "$WS/package.json"; ls -1 "$WS" 2>/dev/null )"
whave() { printf '%s' "$WHAY" | grep -qiE "$1"; }
T=""        # the verify command, scoped to exactly one file
RUNCTX="env CI=true CYPRESS_CRASH_REPORTS=0 timeout ${AUDIT_VERIFY_TIMEOUT}"

# Path RELATIVE to the workspace we cd into. $FILE is repo-root-relative (e.g.
# frontend/src/Foo.test.tsx); we run from $WS (e.g. frontend/), so strip the leading "$WS/" —
# otherwise the runner looks for frontend/frontend/src/... and fails. When $WS is the repo root
# there is no prefix to strip and REL == FILE.
REL="${FILE#"$WS"/}"

# Re-detect the PACKAGE MANAGER for THIS workspace — a monorepo subdir may use a different PM
# than the repo root. Check the workspace dir first, then the repo root; fall back to the
# repo-level $RUN from Step 1g.
WRUN="$RUN"
for d in "$WS" "$ROOT"; do
  if   [ -f "$d/pnpm-lock.yaml" ];                    then WRUN="pnpm exec";   break
  elif [ -f "$d/yarn.lock" ];                         then WRUN="yarn exec";   break
  elif [ -f "$d/bun.lockb" ] || [ -f "$d/bun.lock" ]; then WRUN="bunx";        break
  elif [ -f "$d/package-lock.json" ];                 then WRUN="npm exec --"; break
  fi
done

if   whave '"vitest"|vitest\.config|vitest\.workspace'; then
  # `run` = no watch; pass the workspace-relative path. (Bare `vitest <name>` is a substring
  # FILTER, not a file — `run <path>` plus --no-watch keeps it to the one file.)
  T="$WRUN vitest run --no-watch \"$REL\""
elif whave '"jest"|jest\.config'; then
  T="$WRUN jest --runTestsByPath \"$REL\" --ci --watchAll=false --silent"     # exact file
elif whave '"@playwright/test"|playwright\.config'; then
  T="$WRUN playwright test \"$REL\""        # needs a running app/server; see note below
elif whave '"cypress"|cypress\.config'; then
  case "$(basename "$REL")" in
    *.cy.tsx|*.cy.jsx) T="$WRUN cypress run --component --spec \"$REL\"" ;;    # component spec
    *)                 T="$WRUN cypress run --e2e --spec \"$REL\"" ;;          # e2e spec (needs app)
  esac
elif whave '"mocha"|\.mocharc'; then
  T="$WRUN mocha \"$REL\""
elif whave '"jasmine"|jasmine\.json'; then
  T="$WRUN jasmine \"$REL\""
fi

if [ -n "$T" ]; then
  echo "Verifying: ( cd $WS && $RUNCTX $T )"
  ( cd "$WS" && eval "$RUNCTX $T" )
  VERIFY_RC=$?
  [ "$VERIFY_RC" = 124 ] && echo "  TIMED OUT (watch mode / hung runner?) — treat as UNVERIFIED."
else
  echo "  No single-file command for this workspace's runner — treat as UNVERIFIED."
  VERIFY_RC=99
fi
```

Notes:
- **Project-script fallback (`$PM test -- "$FILE"`) is DANGEROUS — use only if you have
  confirmed the package's `test` script (1) forwards args to the runner AND (2) runs once
  (no watch).** A bare `vitest`, `react-scripts test`, or `cypress open` script ignores
  `-- "$FILE"` and stays in watch mode, hanging the run. When in doubt, invoke the runner
  binary directly as above. The `timeout` wrapper is the backstop.
- **Playwright/Cypress e2e need a running app/server** that an unattended runner usually lacks.
  If verification needs an app you don't have, mark the change `reworked (unverified: needs
  running app)` and **never delete on the basis of an unrunnable verify.**
- **For a deletion:** run the sibling/importer files (from Step 4's grep) the same way. A
  non-zero result means the deletion broke something → **revert and keep-and-flag.**
- For nx/turbo monorepos you may alternatively scope via `nx test <project> --testFile=<path>`
  or `turbo run test --filter=<pkg> -- <path>` — but the per-workspace direct-binary form above
  is the portable default.

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
- **Commit ONLY the files this run changed** (the reworked/deleted test files you tracked in Steps 4–5). NEVER `git add -A`, and never
  sweep in unrelated or untracked files (lockfile churn, `.env`, build artifacts). If anything
  outside your changed set would be staged, stop and report instead of committing.
- **Never commit to, push to, or merge into the default/main branch.** It changes only through a
  human-reviewed PR.
- **Never force-push, never delete branches, and never merge the PR yourself.**

**PR description** — include a verdict table — one row per processed file (`file | type | verdict | action | rationale`) — the note that the full suite was NOT run (only the specific affected files were executed) and that anything ambiguous was kept and flagged rather than deleted, plus any files deferred over the cap.

---

## STEP 7 — Final status

End on exactly one machine-grep-able status line so the caller can tell healthy idleness from a
silent break:

- `AUDIT_RESULT=nothing: <reason>` — nothing to do, OR an audit ran and found nothing to change
  (no repo / no runner / no candidates / all candidates meaningful). Exit 0. Healthy. **No PR in this case.**
- `AUDIT_RESULT=ok: <summary>` — audited AND delivered changes for review: a PR was opened, or —
  in an environment that manages PRs for you — your changes were committed and pushed to the working
  branch. Exit 0.
- `AUDIT_RESULT=error: <reason>` — could NOT run or could NOT deliver. **Exit non-zero so the caller
  alerts a human.**

For Claude Code Cloud, surface the `error` path as a notification rather than swallowing it.

---


## SAFETY (read this — it governs every step)

- **Conservative by default.** When genuinely unsure a test is fake, **KEEP it** and flag it in
  the PR. The cost of deleting a real test >> the cost of leaving a marginal one.
- **Action bias is rework, not delete.** Delete only when there is nothing real to test, the test
  is fundamentally redundant, or a meaningful rework is impossible — and only after the
  pre-deletion safety checks pass and the importer/sibling verify is green.
- **Clean-tree precondition.** Refuse to run on a dirty working tree; only ever stage the explicit
  touched-file set. Never `git add -A`.
- **Never run the whole suite.** Only the specific affected file(s), with `CI=true`, no watch, and
  a hard `timeout` so a runner can never hang the job.
- **Never ship a red/broken test.** Fix it, or fall back to deletion-with-justification.
- **Never commit to the default/main branch.** All changes go through a dedicated branch + PR; a
  human reviews and merges.
- **`AUDIT_DRY_RUN=1`** classifies and reports only — zero edits, deletes, branches, or PRs. The
  guard is the first executable line of Step 4. Use it to preview on a new/unknown repo.
- **`AUDIT_MAX_FILES`** caps the blast radius of any single run; overflow files are reported as
  `skipped (cap)`, not silently dropped.
- **Don't remove shared fixtures/mocks/helpers** — the export check and import check in Step 4
  downgrade those to keep-and-flag.
- **Calibrate by type:** strict on mock-heavy unit/component; **high bar** on e2e (prefer
  keep-and-flag over deletion).
- **Fail loud.** Error paths exit non-zero with `AUDIT_RESULT=error`; only true idleness is a
  green `nothing`.

---

## What this skill deliberately does NOT do

- Does **not** run, modify, or report on the entire test suite or non-test source code.
- Does **not** review tests outside the git lookback window (pre-existing tests are off-limits).
- Does **not** commit to or merge into the default branch; it only opens a PR for human review.
- Does **not** `git add -A`, stage a dirty tree, or run on an unclean working tree.
- Does **not** chase coverage numbers, add new tests for untested code, or refactor production code.
- Does **not** delete on a hunch — uncertainty resolves to **keep-and-flag**, not removal.
- Does **not** persist committed state by default (stateless git window); the last-reviewed-marker is
  an optional upgrade only.
- Does **not** touch Playwright/Cypress visual `toHaveScreenshot` baselines or aggressively prune e2e
  tests — those require a very high bar and default to keep-and-flag.