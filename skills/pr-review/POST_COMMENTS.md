---
name: validate-and-post-pr-review
description: >
  Take an existing AI-generated PR-review report, validate each finding against
  the actual code (keep production-real ones, drop theoretical/wrong ones), then
  optionally post the kept findings to the PR as threaded inline diff comments
  (reviewer voice) + agent-written author replies. Use when you have a review
  report JSON/MD and want a verified, posted review.
---

# Validate & post a PR review

Three phases. Phase 1 is mandatory; phase 3 is opt-in (it writes to a live PR).

## Inputs
- A review report with discrete findings (id, priority, file/lines, issue, suggested fix).
- The target repo checked out at the PR's head branch (so agents read the real code).
- `owner/repo` + PR number, and `gh` authenticated with `repo` scope (only for phase 3).

---

## Phase 1 — Validate each finding (Workflow, ultracode)

One validator + one adversarial verifier **per finding** (catches false-keeps *and*
false-drops). Pipeline, not barrier. The bar is the load-bearing part:

> KEEP if it "makes sense and could happen" in production. Lean toward keeping plausible
> problems; do NOT over-drop. DROP only if the finding is technically **wrong about the
> code**, already handled, or a true 1-in-a-million edge.

```js
// meta omitted for brevity — see Workflow tool docs
const results = await pipeline(
  ISSUES,                                   // [{id, title, priority, location, issue, fix}]
  (it)    => agent(validatePrompt(it),  {label:`validate:${it.id}`, phase:'Validate', schema:V}),
  (v, it) => agent(verifyPrompt(v, it), {label:`verify:${it.id}`,   phase:'Verify',   schema:VV}),
)
return results.filter(Boolean)
```

Validator must: (1) read the cited files + trace real behavior, (2) verify/correct line
numbers, (3) set `claimAccurate` (is the review even right about the code?), (4) keep/drop
against the bar, (5) set severity, (6) write a `reviewerComment` (issue + fix, reviewer
voice) and (7) an `authorReply` (realistic author response — concede, defer, or rebut,
grounded in code + the repo's design docs). Verifier re-reads independently, can overturn,
and produces polished `reviewerComment`/`authorReply` + `overturned`.

Schema fields worth forcing: `id, claimAccurate, finalVerdict(keep|drop), overturned,
severity(must_fix|should_fix|nice_to_have|n/a), category, location, reviewerComment,
authorReply, rationale`.

**Tip:** point validators at the repo's own architecture/design docs — many "findings" are
already acknowledged-by-design (deferred-item lists, prod checklists). That's what flips a
`must_fix` to `should_fix` or a keep to a drop.

## Phase 2 — Assemble the report

Group kept by severity (should_fix → nice_to_have), then id. For each: **Location**
(verified files+lines), **Review comment**, **Author's assessment**. Add a "Validator note"
line wherever `overturned` is true (severity change / line fix / relocation). List dropped
findings with the why. Write it as a repo-root artifact — but **don't commit it** (it's a
review artifact, same class as scratch docs).

---

## Phase 3 — Post to the PR (opt-in, writes to a live PR)

Decisions to confirm with the user first:
- **Identity:** every comment is attributed to the token owner. You cannot post "as a
  separate reviewer" vs "as the author" — both voices are the same account. The split is
  purely textual. (Self-approve/request-changes is blocked on your own PR; plain comments
  are fine.)
- **Label the reply "Agent response", not "Author response".** The reply text is drafted by
  the validation agent, not the human PR author — labelling it "Author response" is unfair
  and misleading (they never wrote or even saw it). Use **Agent response** and say so in the
  summary comment.
- **Format:** inline diff comments (most authentic) vs one-comment-per-finding vs one
  consolidated comment. Inline only works on lines **inside the PR's diff**.
- **Scope** and whether to include the dropped findings as a closing note.

### Gotchas (the reason this needs a script, not 40 hand calls)
1. **Inline comments require an in-diff line.** Parse `GET /pulls/{n}/files[].patch`: a line
   is anchorable on `side:RIGHT` if it's an added (`+`) or context (` `) line; track the
   *new-file* line number from each `@@ -a,b +c,d @@` header. Snap each finding to the
   nearest valid line in its file; keep the precise refs in a footer. Fall back to a
   conversation comment only if the file isn't in the diff at all.
2. **commit_id must be the PR head SHA** (`GET /pulls/{n}` → `head.sha`) — diff line numbers
   are relative to it.
3. **Threading:** post the reviewer comment via `POST /pulls/{n}/comments`
   (`{body, commit_id, path, line, side:"RIGHT"}`), grab its `id`, then post the author
   reply via `POST /pulls/{n}/comments/{id}/replies` `{body}`.
4. **Rate limits:** sleep ~2s between writes; retry once on a 403/429 "secondary rate limit"
   after ~30s.
5. **Sanitize bodies:** strip stray C0 control bytes (BEL/ESC can sneak in from findings that
   *discuss* control chars) → render them as `\xNN`.
6. **Dry-run first.** Resolve every anchor and print the plan (exact / snapped / fallback)
   without posting; only `--post` after it looks clean. 40+ posts are only deletable one by
   one — keep every returned `html_url` and the (sequential) discussion IDs for a possible
   `gh api -X DELETE` sweep.

### Reusable poster (stdlib only; reads the validated findings JSON)
```python
import json, re, sys, time, subprocess, urllib.request, urllib.error
OWNER, REPO, PULL = "ORG", "REPO", 0
JSON_PATH = "validated_findings.json"      # [{id, finalVerdict, severity, category, title, location, reviewerComment, authorReply}]
ANCHORS = { "1-1-1": ("path/to/file.ts", 13), }   # primary (file, line) per kept id
DRY = "--post" not in sys.argv
tok = subprocess.check_output(["gh","auth","token"]).decode().strip()

def api(m, p, d=None):
    body = json.dumps(d).encode() if d is not None else None
    r = urllib.request.Request("https://api.github.com"+p, data=body, method=m)
    for k,v in {"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}.items(): r.add_header(k,v)
    if body: r.add_header("Content-Type","application/json")
    for a in range(3):
        try:
            with urllib.request.urlopen(r) as x: return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            t=e.read().decode()
            if e.code in (403,429) and "secondary rate" in t.lower() and a<2: time.sleep(30); continue
            return e.code, t
def clean(s): return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', lambda x:'\\x%02x'%ord(x.group()), s)
def valid_right(patch):
    out=set(); nl=None
    for ln in (patch or "").split("\n"):
        if ln.startswith("@@"): m=re.search(r'\+(\d+)',ln); nl=int(m.group(1)) if m else None
        elif nl is None: pass
        elif ln.startswith("+"): out.add(nl); nl+=1
        elif ln.startswith("-") or ln.startswith("\\"): pass
        else: out.add(nl); nl+=1
    return out

_,pr = api("GET",f"/repos/{OWNER}/{REPO}/pulls/{PULL}"); head=pr["head"]["sha"]
files={}; pg=1
while True:
    _,b = api("GET",f"/repos/{OWNER}/{REPO}/pulls/{PULL}/files?per_page=100&page={pg}")
    if not b: break
    for f in b: files[f["filename"]]=f.get("patch","")
    if len(b)<100: break
    pg+=1
vmap={p:valid_right(q) for p,q in files.items()}
def snap(path,line):
    if path not in files or not vmap[path]: return None,"FALLBACK"
    if line in vmap[path]: return line,"exact"
    return min(vmap[path],key=lambda x:abs(x-line)),f"snap<-{line}"

kept={f["id"]:f for f in json.load(open(JSON_PATH)) if f["finalVerdict"]=="keep"}
rank={"should_fix":0,"nice_to_have":1}
order=sorted(kept.values(),key=lambda f:(rank.get(f["severity"],9),f["id"]))
for f in order:
    p,l=ANCHORS[f["id"]]; rl,how=snap(p,l); print(f'{f["id"]:7}{f["severity"]:13}{p}:{l} -> {rl} [{how}]')
if DRY: print("DRY RUN"); sys.exit()

for f in order:
    p,l=ANCHORS[f["id"]]; rl,how=snap(p,l)
    note="" if how=="exact" else "\n\n<sub>⚠︎ anchored to nearest in-diff line</sub>"
    rbody=f'**`{f["severity"]}` · {f["category"]} · {f["id"]}** — {f["title"]}\n\n{clean(f["reviewerComment"])}{note}\n\n<sub>📍 {clean(f["location"])}</sub>'
    if rl is None:
        api("POST",f"/repos/{OWNER}/{REPO}/issues/{PULL}/comments",{"body":rbody+"\n\n---\n\n**Agent response**\n\n"+clean(f["authorReply"])}); time.sleep(2); continue
    st,c=api("POST",f"/repos/{OWNER}/{REPO}/pulls/{PULL}/comments",{"body":rbody,"commit_id":head,"path":p,"line":rl,"side":"RIGHT"})
    print(f["id"],st,c.get("html_url") if isinstance(c,dict) else c); time.sleep(2)
    if st in (200,201):
        api("POST",f'/repos/{OWNER}/{REPO}/pulls/{PULL}/comments/{c["id"]}/replies',{"body":"**Agent response**\n\n"+clean(f["authorReply"])}); time.sleep(2)
```

Also post one conversation comment (`POST /issues/{n}/comments`) as a summary: methodology,
keep/drop counts + table, and the dropped findings with reasons.

