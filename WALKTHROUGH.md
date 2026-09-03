# unlazy + beads + rtk — Walkthrough

End-to-end guide to the plan→beads→gates→close→trace pipeline, with the exact
commands and observed output from a smoke test (2026-08-27).

- Design rationale & open decisions: [beads_unlazy_plan.md](beads_unlazy_plan.md)
- unlazy methodology skill: `~/.agents/skills/unlazy/`

---

## 1. What this is

Three things wired together:

| Piece   | Role                                                                    |
|---------|-------------------------------------------------------------------------|
| **unlazy** | Completion discipline: write acceptance **gates** before executing, verify evidence before reporting. |
| **beads (`bd`)** | Durable, Dolt-backed issue tracker. Hierarchical work + dependency edges. |
| **rtk** | Token-optimized CLI wrapper. All gate `CHECK:` commands route through `rtk`. |

One line: **a plan becomes a beads graph; every leaf gets an evidence gate;
a leaf only closes when its gate CHECK passes; closures are traced into a devlog;
everything persists in Dolt.**

---

## 2. Pipeline

```
plan.json ──beads_gen──▶ beads graph (Dolt)  +  plan.graph.md (mermaid review)
                             │
                       ul_gates_gen
                             ▼
              .beads/gates/<leaf-id>.md  (one ledger per leaf)
                             │
                 gate <id> --lint / --approve / (reverify) / --close
                             ▼
                  bd close <id>   (only if all gates PASS and no open blockers)
                             │
              prepare-commit-msg + post-commit hooks
                             ▼
                     .beads/DEVLOG.md   (closures + CHECK evidence)

  ── at every session end ──────────────────────────────────────────────
     stop-gate (VS Code Stop hook): refuses a clean stop while any
     in-progress bead has an unsatisfied gate; warns on stale beads;
     writes a heartbeat so hook-doctor can prove it fired.
```

## 3. Tools (all in `~/.agents/unlazy-beads-rtk/`, symlinked into `~/.local/bin`)

| Tool | Purpose |
|------|---------|
| `beads_gen <plan.json>` | Create the beads graph from a plan; render `plan.graph.md`; write `plan.beads.json` manifest. **Pre-create hard gate: runs `beads_lint` first and refuses to create/delete anything on a malformed graph (`--no-gate` overrides).** **Emits two review gates on every run: the mermaid chart + an inline `beads_verify` blocks table.** These two outputs are a **human stop point**, not a status print — present them and get explicit WBS/ordering sign-off before proposing or starting any implementation (see §10). Re-runnable (overwrites prior beads via manifest). Preflight refuses to run unless `issue-prefix` is pinned. |
| `beads_lint <plan.json>` | **Structural integrity gate** (pure plan.json analysis, no bd): flags cycles (deadlock), danglers, self-deps, bad parent_key, string priorities, unstartable graphs; warns on redundant/lineage-crossing edges. Also validates the optional `gate` field (errors on an invalid value; warns on an ungated leaf or a gated container/epic) and the optional `model` tier (errors on an unknown/disabled tier; warns when a manual gate is delegated off-lead or a delegated task has no run gate). Exit 3 on error, 0 clean. Auto-invoked by `beads_gen` before creation; also standalone. Checks **integrity, not intent**. |
| `beads_verify <plan.json>` | Print the WBS-sorted **blocks** table for the plan's beads (scoped via the manifest): each bead's blocked-by set, a `GATE` column (`run`/`manual`/`—`), a single-letter `M` tier column (`w`/`m`/`l`), a `WHY` column (per-bead justification from the plan's `why`, else the tier default), `← READY` flags, and cross-plan anomalies — followed by an embedded tier legend. Auto-invoked by `beads_gen`; also runnable standalone. `bd ready` stays authoritative. |
| `ul_gates_gen <plan.json>` | Scaffold a gate ledger for each **leaf** (node with no children), detected via parent-child edges. |
| `gate <id> [verb]` | Gate lifecycle: `--new`, `--lint`, `--approve`, reverify (default), `--close [--note "how it was built"]`. On a passing `--close`, stores the note on the master as `bd close --reason` and mirrors it onto each open bead this one was blocking (via `handoff_note.py`); the note is **required when the bead unblocks others** (refuses before closing without it). |
| `handoff_note.py <closed-id> <note>` / `--deps <id>` / `--reconcile [<id>...]` | Helper invoked by `gate --close`. Write mode appends the closing agent's handoff note to the open **blocking-dependents**, so the successor reads *how* its dependency was built in `bd show` (§12); `--deps` lists those dependents (gate's pre-close "note required?" check); `--reconcile` delivers handoffs a raw `bd close` skipped (mirrors a closed master's `close_reason` to open dependents that lack it; no id scans all closed beads; exit 1 + flags any master closed with only a generic reason). Additive — never fails a close; `HANDOFF_DRY_RUN=1` prints without writing. |
| `render_mermaid.py <manifest>` | Render the review chart (helper) — edge colours + gate badges (🔒/👁) + model-tier tags (`[w]`/`[m]`; none = lead). |
| `wbs_prefix.py <plan.json>` | Add `[E1.T1.T1]` WBS codes to titles + `wbs:` labels, `gate:` labels from each node's `gate` field, and `model:` labels from each node's `model` field (helper, used by beads_gen). |
| `devlog_update --trailer` / `--commit <sha>` | Devlog trace: trailer summary (read-only) / append DEVLOG.md entry + advance watermark. |
| `install-devlog-hooks [repo]` | Chain-safe symlink of prepare-commit-msg + post-commit hooks. |
| `hooks/stop-gate` | VS Code **Stop** hook (fires at session end): gate-enforce (blocks a clean stop, `exit 2`), staleness warn, heartbeat. Not called directly. |
| `install-stop-hook` [`--disarm`] | Arm/disarm the Stop hook (default **ON**): write `agent-hooks.json`, register it in VS Code user settings, record the durable "armed" trace. |
| `hook-doctor` | Report Stop-hook health (OK / UNCONFIRMED / INACTIVE / NOT-ARMED) + stale beads + undelivered handoff notes (detect-only `handoff_note.py --reconcile` scan). Run at session start. |
| `ul_allowlist_check` [`--print`] | Preflight VS Code's `chat.tools.terminal.autoApprove` before an autonomous run: verifies the curated allows (`rtk`, `bd`, …) and the mandatory `git push` **deny** are present. Exit 1 on a critical gap (stop and ask the user); `--print` emits the recommended JSON block to paste. |
| `stale-beads [path]` / `--install-view` | List in-progress beads older than `UNLAZY_STALE_HOURS` (default 2h); `--install-view` adds a live `stale_beads` view to the repo's Dolt DB. |

Every tool supports `-h`/`--help`, which prints its own header block — per-tool
flag details live with the code, this file covers how the pieces fit together.

Absolute paths in generated files come from **`UNLAZY_HOME`** (defaults to `$HOME`).
Pin it in `env.sh` (git-ignored); commit `env.sh.example` instead. The scripts
themselves carry no personal path — only `$UNLAZY_HOME`.

## 4. plan.json schema (confirmed `bd create --graph`)

```json
{
  "nodes": [
    {"key": "root", "title": "Add CSV export", "type": "epic"},
    {"key": "a", "title": "Parse CSV schema", "parent_key": "root", "type": "task"},
    {"key": "b", "title": "Handle quoting rules", "parent_key": "a", "type": "task"},
    {"key": "c", "title": "Write exporter", "parent_key": "root", "type": "task"}
  ],
  "edges": [{"from_key": "c", "to_key": "a", "type": "blocks"}]
}
```

- Flat `nodes`; hierarchy via **`parent_key`** (not nested children).
- `key` is a local ref only — **not** the persisted ID. `bd create --graph` mints
  flat random IDs (`myproj-1x9`), not dotted ones.
- Edge `{from_key: c, to_key: a, type: blocks}` means **c depends on a** (a must
  finish first; a blocks c).
- Accepted node fields: `key, title, type, parent_key, priority, labels, description`.
  **Nodes carry no acceptance field** — acceptance lives in the gate ledger.
- `priority` is an **integer** (0–4, 0 = highest); a JSON string fails to parse.
- Optional **`gate`** per node declares verification *intent*: `"run"` (a runnable
  CHECK), `"manual"` (a human EVIDENCE gate), or `"none"` (deliberately ungated).
  `beads_gen` consumes it (bd never sees it) and stamps a `gate:<kind>` label,
  surfaced as a chart badge (🔒/👁) and a `GATE` column in the blocks table.
  `beads_lint` errors on an invalid value and *warns* (never blocks) on a leaf
  with no gate or a container/epic carrying a runnable gate. Intent only — the
  ledger still decides whether a gate actually passes.
- Optional **`model`** per node declares the **execution tier**: a tier name from
  [`models.json`](../models.json) (e.g. `"worker"`, `"mid"`), or `"lead"`/`"none"`/
  absent for the controller itself. `beads_gen` consumes it and stamps a
  `model:<tier>` label, surfaced as a chart tag (`[w]`/`[m]`; none = lead) and a
  single-letter `M` column (`w`/`m`/`l`) in the blocks table. `beads_lint` errors
  on an unknown/disabled tier and warns on unsafe delegation (manual gate
  off-lead, or a delegated task with no run gate). See §4a.
- Optional **`why`** per node is a short, review-only justification for the tier
  choice. `wbs_prefix` consumes it (bd never sees it — prose isn't a tag); the
  original plan is read by `beads_verify` to fill the `WHY` column. If omitted,
  the column falls back to the tier's default reason (`reason` in `models.json`).

## 4a. Model tiers & delegation

Run-gated mechanical work can be delegated to a cheaper model; judgment and
manual gates stay with the lead. Tiers live in
[`models.json`](../models.json) (JSON, user-owned):

```json
{
  "tiers": [
    {"tag": "w", "name": "worker", "model": "Claude Haiku 4.5", "vendor": "copilot", "enabled": true,  "reason": "mechanical, run-gated bulk", "desc": "…"},
    {"tag": "m", "name": "mid",    "model": "Claude Sonnet 4.5", "vendor": "copilot", "enabled": false, "reason": "substantial non-architectural coding", "desc": "…"}
  ]
}
```

- **`lead` is implicit** — never listed; a node with no `model` (or `model:"lead"`)
  runs on the controller.
- **Data-driven depth:** ships two tiers (`lead` + `worker`); enable the `mid`
  entry to get a third. That toggle *is* the "choose your tiers" setting.
- **Your responsibility:** `model`/`vendor` must match your Copilot picker. A
  subagent is dispatched as `"{model} ({vendor})"`. If the model does not
  respond, the lead **falls back to `lead`** (does it itself) and warns you that
  `models.json` needs attention.
- Charts/tables show the **tier tag** (`[w]`/`[m]`), not the model name — so a
  swapped-out model never makes the chart lie.

Delegation rule (see [docs/POLICY.md](POLICY.md) §4): **delegate the mechanical
bulk, the lead keeps the one-liners and the judgment calls.** run-gated leaf →
worker/mid; manual-gated/design → lead; literal one-liners → lead.

### Governance (set in stone) — [docs/POLICY.md](POLICY.md)

- **Commit — two modes:** interactive chat → *ask* before each commit;
  autonomous agent/subagent work → *commit freely on the branch* at checkpoints.
- **Push — never:** the lead never `git push`es in any context. Humans push.
- **Deletes — guarded:** git-aware deletes and `rm -f <file>` are fine; `rm -rf`
  only on a relative in-tree subpath that avoids `.git/`, `.beads/`, absolute
  paths, `~`, and bare `*`.
- **Allowlist preflight:** before a fan-out or long loop, run `ul_allowlist_check`;
  stop on a critical gap. Re-verify before each bead; treat an unexpected prompt
  as drift → stop and re-check.

---

## 5. Chart legend (mermaid)

- **parent-child (kin):** thin **blue** line, **circle** head — `parent --o child`
- **blocks:** fat **red** line, **arrow** head — `blocker ==> blocked`
- **gate badge (node prefix):** 🔒 = runnable gate · 👁 = manual (EVIDENCE) gate · no badge = ungated
- **model tag (node prefix):** `[w]` = worker · `[m]` = mid · no tag = lead (controller)

Shape + colour + weight all differ, so the chart reads without a legend.

---

## 6. Smoke test — observed run (2026-08-27)

Test plan: epic *Add CSV export* → tasks *Parse CSV schema* / *Write exporter*,
subtask *Handle quoting rules*; edge *Write exporter* **blocks-depends-on**
*Parse CSV schema*.

### Step 1 — create the graph

```bash
beads_gen /tmp/ultest/plan.json
```

Minted (WBS-prefixed titles, flat IDs):

```
myproj-1x9 | [E1]      Add CSV export        (epic)
myproj-2ys | [E1.T1]   Parse CSV schema      (task)
myproj-7rl | [E1.T1.T1] Handle quoting rules (leaf)
myproj-nru | [E1.T2]   Write exporter        (leaf, blocks-depends-on 2ys)
```

### Step 2 — scaffold leaf gates

```bash
ul_gates_gen /tmp/ultest/plan.json
```

Only the two true leaves got ledgers; the epic and the branch (`E1.T1`) correctly
did not:

```
.beads/gates/myproj-7rl.md
.beads/gates/myproj-nru.md
```

### Step 3 — the evidence-gated close cycle

A real, deterministic gate in `myproj-7rl.md`:

```
- [ ] G1: a field with a comma and embedded quotes round-trips through CSV unchanged
  CHECK: python3 -c "import csv,io; s=io.StringIO(); csv.writer(s).writerow(['a,b','he said \"hi\"']); r=list(csv.reader(io.StringIO(s.getvalue()))); assert r==[['a,b','he said \"hi\"']], r; print('QUOTING_OK')"
  EXPECT: QUOTING_OK
```

```bash
gate myproj-7rl --lint      # LINT OK (0 warnings)
gate myproj-7rl --approve   # APPROVED + PASS G1  (approval binds the exact command)
gate myproj-7rl             # ALL MET
gate myproj-7rl --close     # reverify → bd close → ✓ Closed myproj-7rl
```

Two safety nets, both observed:

- **Evidence gate:** the CHECK does not execute until you `--approve` the exact
  command string (`PENDING APPROVAL` until then) — tamper-proofing.
- **Blocks gate:** `bd close myproj-nru` was **refused** —
  `cannot close myproj-nru: blocked by open issues [myproj-2ys]`.

### Step 4 — devlog trace (the two git hooks)

```bash
devlog_update --trailer        # read-only; what prepare-commit-msg appends
```
```
Beads closed in this commit:
- myproj-7rl  [E1.T1.T1] Handle quoting rules  ✓ python3 -c "...print('QUOTING_OK')"
```

```bash
devlog_update --commit <sha>   # what post-commit runs; writes DEVLOG.md, advances watermark
```
`.beads/DEVLOG.md`:
```
## <commit-date>  60939f6e3  fix(proxy-configuration) ... (#3564)
- myproj-7rl  [E1.T1.T1] Handle quoting rules  ✓ python3 -c "...print('QUOTING_OK')"
```

Evidence in the devlog is the leaf's passing `CHECK:` line. Neither hook ever
commits, amends, or pushes. `--commit` prints nothing to stdout on success (writes
to the file), so a `| grep` filter returning exit 1 is a no-match, not a failure.

### Step 5 — Dolt persistence

`bd` commits **every operation as its own Dolt commit**:

```
bd: graph-apply 4 nodes
bd: close myproj-7rl
bd: delete myproj-1x9 ... myproj-nru
```

After `bd delete` of all four beads, the working set is empty — but the same query
`AS OF` the pre-delete commit returns them all, including the closed one. Deletion
only advances the tip; history is immutable.

---

## 7. Stop-hook enforcement (default ON)

unlazy's job is to make skipping a gate impossible. `gate --close` already refuses
to close a bead whose CHECK fails — but only if the agent *calls* it. The
**Stop hook** closes that gap: it runs when a session ends, whether or not the
agent asked.

**Arm it once (default ON):**

```bash
install-stop-hook            # writes agent-hooks.json + VS Code settings + trace
                             # (reload the VS Code window afterwards)
install-stop-hook --disarm   # undo
```

It registers `hooks/stop-gate` under `chat.hookFilesLocations` (by **absolute**
path — VS Code strips `~/` keys) and sets `chat.useHooks: true`, in
`~/.vscode-server/data/User/settings.json`.

**What stop-gate does at session end:**

1. **Heartbeat** — records that it fired (`~/.unlazy/.stop-heartbeat`).
2. **Gate-enforce** — for each in-progress bead with a ledger, runs the checker;
   if any is unsatisfied it **blocks the stop** (`exit 2`) and lists them, forcing
   a handoff instead of a silent exit.
3. **Staleness** — warns (non-blocking) about in-progress beads older than
   `UNLAZY_STALE_HOURS` (default **2h**).

**The durable trace (survives even if hooks are blocked).** VS Code agent hooks
are Preview and can be disabled by org policy. So the machinery proves its own
liveness:

| Signal | Where | Meaning |
|--------|-------|---------|
| `armed` | `~/.unlazy/hook-status.log` | install ran — the "it was tried" record |
| heartbeat | `~/.unlazy/.stop-heartbeat` | the hook actually fired |
| verdict | `hook-doctor` | OK / UNCONFIRMED / **INACTIVE** / NOT-ARMED |

`hook-doctor` (run at session start — an always-on instruction does this) infers
**INACTIVE** when a previous session started but left no heartbeat: that is the
signal that the hooks feature is blocked/unsupported and enforcement is **not**
running. The install trace remains either way, so a silently-disabled hook can't
masquerade as a passing one.

### How hook-doctor computes its verdict

`hook-doctor` runs at **session start** — the always-on instruction
`hook-health.instructions.md` (`applyTo: '**'`) tells the agent to. It reads three
markers under `~/.unlazy/` and **never needs the hook itself to run**, which is
exactly what lets it detect a dead hook:

| Marker | Written by | Meaning |
|--------|-----------|---------|
| `hook-status.log` (`armed` line) | `install-stop-hook` | the hook was installed |
| `.stop-heartbeat` | `stop-gate` (when it fires) | the hook last fired, and when |
| `.session-start` | `hook-doctor` (each run) | this session started, and when |

Verdicts:

- **NOT-ARMED** — no `armed` line → `install-stop-hook` never ran.
- **UNCONFIRMED** — armed, but no heartbeat yet → not observed firing.
- **OK** — a heartbeat exists and is newer than the previous session-start marker
  → the hook fired at the last session end.
- **INACTIVE** — a previous session started but no heartbeat came after it
  (`heartbeat < last session-start`) → the hook did **not** fire; the feature is
  likely policy-disabled or unsupported, and enforcement is **not** running.

Crucially, `hook-doctor` advances `.session-start` to *now* **last** — after
reading the old value — so every run compares against the *previous* session.
That makes "two session starts with no heartbeat between them" the INACTIVE tell,
and a silently disabled hook surfaces at the very next session start instead of
passing unnoticed. Each verdict is also appended to `hook-status.log`, giving a
durable timeline (`armed → doctor → fired → doctor …`).

A healthy timeline (once a build actually executes hooks and stop-gate fires)
looks like:

```
14:00:00  armed                  ← install-stop-hook
14:00:10  doctor  UNCONFIRMED    ← turn start, no heartbeat yet
14:03:22  fired   Stop           ← stop-gate ran at a turn end (heartbeat written)
14:05:00  doctor  OK             ← next turn start: heartbeat present
```

> **VS Code Copilot 1.135 does NOT execute file hooks (verified 2026-08-28,
> WSL/remote).** This build *discovers/lists* hooks (the `/hooks` picker shows
> them) but never *runs* them. Every turn end logs
> `[ToolCallingLoop] Stop hook result: shouldContinue=false, reasons=undefined`
> — zero external hooks collected — and the "GitHub Copilot Chat Hooks" output
> channel log is never created (definitive proof `ChatHookService` executed 0
> hooks). All four documented locations were tested with the extension host
> restarted and a clean config, and all produced no heartbeat:
> `chat.hookFilesLocations` (edit-approval only), `~/.copilot/hooks` (that's the
> Copilot **CLI** home), `~/.claude/settings.json` + `chat.useClaudeHooks`, and
> `<repo>/.github/hooks/`. Our hook JSON schema is valid; the limitation is the
> Preview build, not our config.
>
> The Stop hook remains configured in `~/.claude/settings.json` (all workspaces,
> inert today) so it **auto-activates** if a future build fixes execution.
> **Re-test signal:** enforcement is live the moment a "GitHub Copilot Chat
> Hooks" output channel appears / a `~/.unlazy/.stop-heartbeat` is written after
> a turn end. Until then, `hook-doctor` at session start is the active trace and
> will honestly report **INACTIVE/UNCONFIRMED**. Notes: the `Stop` event is
> evaluated at **agent turn end**, not on window close; in WSL, config changes
> that affect hook discovery need **Developer: Restart Extension Host**, not just
> Reload Window.

**Staleness keeps going until close.** The same check runs at both ends of every
session (hook-doctor at start, stop-gate at end) and re-emits until the bead
leaves `in_progress`. Ping out-of-band any time with `stale-beads`, or add a live
Dolt view (next section).

---

## 8. Seeing Dolt content

### Embedded vs server — how unlazy relates to the mode

unlazy never picks or detects the Dolt mode. The whole gate / close / hook /
devlog path shells out to **`bd`**, which resolves embedded vs `sql-server`
itself from the repo's `.beads/` config — so those tools work identically either
way and neither know nor care which mode a repo uses.

The **one exception** is `stale-beads` (and `hook-doctor`, which calls it): to
power a live Dolt Workbench view it reads staleness with a *direct* SQL
connection instead of through `bd`. It decides what to do purely from
`.beads/dolt-server.port`:

- **file present with a port** → it connects to that running Dolt **sql-server**
  (`dolt --port <port> --host 127.0.0.1`) and runs the queries below.
- **no `dolt` binary, no port file, or an empty port** (i.e. pure embedded with
  no server) → it **stands down (exits 0, no-op)**. Staleness reporting and the
  `stale_beads` view are simply unavailable; gate, close, and the devlog hooks
  are unaffected because they route through `bd`.

So the only "embedded vs server" question unlazy ever asks is *"does
`.beads/dolt-server.port` point at a live server?"*, and only `stale-beads` asks
it. A repo running embedded with no (or an empty) port file just makes
`stale-beads` a no-op while everything else works normally.

### Querying the server directly

The shared Dolt SQL server hosts one database per project (`myproj`, plus a
`beads_global`). Port is in `.beads/dolt-server.port`.

```bash
P="--port $(cat .beads/dolt-server.port) --host 127.0.0.1 --no-tls"

# current issues
dolt $P sql -q "select id,title,status from myproj.issues order by id"

# commit history (each bd op = one commit)
dolt $P sql -q "select left(commit_hash,10) as commit, message from myproj.dolt_log order by date desc limit 10"

# time-travel: state as it was at an earlier commit
dolt $P sql -q "select id,title,status from myproj.issues as of '<commit_hash>' order by id"

# what changed between two commits
dolt $P sql -q "select * from dolt_diff('<old_hash>','<new_hash>','issues')"

# stale in-progress beads — started_at is stored in UTC, so compare to
# utc_timestamp() (not now(), which is local). `stale-beads --install-view`
# saves this as a live `stale_beads` view you can open in Dolt Workbench.
dolt $P sql -q "select id, timestampdiff(HOUR, started_at, utc_timestamp()) as h, title from myproj.issues where status='in_progress' and started_at is not null and started_at < utc_timestamp() - interval 2 hour"
```

A `bd delete` / cleared local `.beads` therefore **still persists in Dolt** — the
rows live in history and are recoverable via `as of` or `dolt_diff`.

---

## 9. Prefixing on the shared server (important)

The `<prefix>-<id>` prefix is auto-detected from the **directory basename** unless
`issue-prefix` is pinned in `.beads/config.yaml`. Auto-detection is fragile
(basename collisions, rename drift). Since gate ledgers are named `<bead-id>.md`,
their uniqueness rides entirely on the prefix.

**Pin it per repo** before onboarding to the shared server:

```bash
bd config set issue-prefix <name>     # e.g. myproj, webapp, api
```

`beads_gen` enforces this — its preflight refuses to run when the prefix is unset:

```
beads_gen: issue-prefix is not pinned for this repo — beads would take a fragile
auto-detected prefix. Pin it first: bd config set issue-prefix <name>
```

With a pinned prefix, both beads **and** their gate ledgers are guaranteed
attributable whether gates stay per-repo (`$repo_root/.beads/gates/`) or move to a
global `~/.beads`.

**Gotcha — a `--stealth` re-init can reset `beads.role` to `contributor`.** In
that state `bd` hydrates reads from a *different* store than the one it writes to,
so `bd list`/`bd ready` can look stale or empty while the real DB is fine. Re-pin
after any `--stealth` init:

```bash
git config --local beads.role maintainer   # restore read/write against the real DB
bd list                                     # confirm the graph is visible again
```

---

## 10. Conventions

- Run `bd` only in the integrated terminal (never MCP).
- **On claim, `bd show <id>` before working** — it renders the bead's `NOTES`,
  where a closed dependency left its handoff note (§12). `bd ready` alone does
  not show notes.
- **After `beads_gen`, stop at the review gate.** Show the mermaid chart + the
  `beads_verify` blocks table, ask for explicit approval of the WBS/ordering, and
  do **not** propose or begin implementation in the same breath — generating the
  gate is not satisfying it. This is the semantic counterpart to `beads_lint`'s
  automated integrity gate.
- **Never let a filter pipe hide an interactive prompt.** `bd init`/`bootstrap`
  can prompt; piping them through `grep`/`sed`/`head` swallows the prompt and
  looks like a silent hang. Run interactive `bd` commands unpiped; to still drop
  the 0777 warning, redirect to a file and `grep` the file afterward rather than
  filtering inline. (The toolkit's own scripts are non-interactive and safe to
  filter.)
- Filter beads' 0777 permission warning (emitted on some systems): `... | grep -vE "permissions 0777|chmod 700"`.
- All CHECK commands prefix `rtk` explicitly (its rewrite hook does not fire under Copilot/Cursor).
- Never auto-commit/push; the devlog hooks annotate only.
- Personal absolute paths live only in `env.sh` (git-ignored) via `UNLAZY_HOME`;
  scripts and `env.sh.example` carry none. Generated `agent-hooks.json` is
  git-ignored and regenerated by `install-stop-hook`.
- After `install-stop-hook`, reload the VS Code window; approve the hook if prompted.

## 10b. Browser-UI projects & CI-as-enforcement

The CHECK contract ("process exit 0 + EXPECT marker in stdout") assumes the
project offers a *shell-runnable* verifier (`cargo test`, `npm test`). Two cases
break that assumption — worth knowing before you trust a green gate:

- **No CLI test runner / in-browser suite.** Some apps verify behaviour in the
  browser against a live build (e.g. a map/UI app whose tests run *inside* the
  running page), not via a shell command. Driving that from an agent's browser
  tools works live but **evaporates when the session ends and CI can't replay
  it** — it is not a durable CHECK. To make it one, commit a small harness
  (e.g. Node + Playwright) that launches the app headless, runs the in-app suite,
  and maps DOM pass/fail → exit code + a success-only marker. Only then does
  `CHECK: rtk node run-suite.js` become durable and CI-runnable. Verification the
  project can't express as a check, the gate can't enforce — e.g. visual/3D
  fidelity or a placeholder data URL stays a **manual EVIDENCE gate**.
- **The runner doesn't fire Stop hooks (VS Code / Copilot).** There the local
  `gate --close` is *self-run* — compliance, not fail-closed enforcement — and
  `hook-doctor` only *detects* lapses after the fact. The un-bypassable wall then
  has to be **CI running the same CHECK commands** on the PR (or a CLI runner
  that executes Stop hooks). Treat the local gate as a fast pre-flight that
  *mirrors* CI; if no CI mirrors it, the gates are advisory structure, not a
  guarantee.

## 11. Full vs light usage

The two halves of this repo are independent, so you pick per project.

**Full usage** (both halves) — best for long, agent-driven work:

- Track work as beads, *and* enforce completion: a bead closes via
  `gate <id> --close`, which reverifies the acceptance CHECK and runs
  `bd close` **only if it passes** (refuses otherwise). The Stop hook blocks a
  clean session-stop while any in-progress bead has unmet gates.
- Nothing closes a bead by itself — even here it is *you* running `gate --close`;
  the automation is a *verified* close, not a *background* one.

**Light usage** (beads only) — best for small, chat-only work:

- **Decompose the work into beads** (`bd create`, `bd ready`, `bd close`) so the
  work is *remembered* across sessions, and let that bead trail shape meaningful
  commit messages that convey *how* things were actually built.
- **Keep the commit-trace automation** — run `install-devlog-hooks` and every
  commit still gets the "Beads closed" trailer + a rolling `.beads/DEVLOG.md`.
  This half only *reads* bd's closed list, so it needs nothing from the gates.
- **Drop the gate/enforcement half** — no `GATES.md`, no `gate`, no Stop hook.
  You close beads with a plain `bd close <id>`, trusting your own review instead
  of a reverified `gate <id> --close`. What you give up is *verified* close and
  Stop-hook enforcement — both matter most for long, agent-driven work, and
  little when you review each step yourself in chat.

**Seeing when to intervene is pull, not push.** The only push is the Stop hook
firing, and it fires only in runners that execute Stop hooks (Claude Code,
Codex) — **not VS Code / Copilot**. Everywhere else, poll `hook-doctor` at
session start (armed / heartbeat / stale beads / unmet gates) plus `bd ready` /
`bd list --status in_progress`. Treat it like a manual daemon you check
periodically.

The gate layer is **additive and per-repo** — you can drop a `GATES.md` into a
project later, the day a task grows big enough to want fail-closed checks,
without changing anything you have already done.

## 12. The blackboard framing (and a proposed handoff note)

Thoughtworks' [*An Accidental Blackboard*](https://martinfowler.com/articles/exploring-gen-ai/an-accidental-blackboard.html)
(Edwards-Alexander, Sep 2026) describes ten agents in a monorepo that
*accidentally* began coordinating through plans linked to numbered spec sections
— re-deriving the **blackboard / tuple-space** pattern (Hearsay-II, 1980;
Gelernter, 1986): a schema-light shared memory where autonomous agents drop
labelled partial solutions and other agents pick them up. The piece lands on two
conclusions — you want that channel **intentional**, not emergent, and **sitting
independently of source control** (they drove it with a frequent push cycle,
which overloaded CI; backing off starved the signal).

This toolkit already implements the intentional version:

| Blackboard concept | Mechanism here |
|--------------------|----------------|
| Shared tuple space | **beads** = Dolt-backed shared issue store |
| "Minimum structure + any extra fields, no schema" | bead = `id` + `status` + `blocked-by`, plus arbitrary labels (`gate:run`, `model:worker`) and the plan's free-text `why` |
| Plans linked to numbered spec sections | `plan.json` → **WBS** (`E1.T2`, …) |
| Integration points / "wait for the verifier to land" | **`blocked-by`** edges (a first-class constraint, not a convention) |
| "Mark in-progress so no one else takes it" | **`bd update --claim`** (atomic tuple-take) |
| "Drop a labelled solution, other searchers pick it up" | **gates + model tiers** — a worker picks up *ready ∧ run-gated ∧ `[w]`* beads (§4a) |
| Opportunistic control / scheduler | **`bd ready`**; delegate-by-gate is the policy for *which tier* takes *which* bead |

Crucially, the channel is **off-VCS by construction**: `.beads/` is git-ignored
and Dolt sync rides `refs/dolt/data`, separate from `refs/heads/*` (§9, §8). So
coordination flows over the Dolt channel, **not over commits** — sidestepping the
CI-overload trap that forced the article's team to back off. This is the same
separation the never-push / two-mode-commit policy enforces: git carries code,
beads carries coordination ([docs/POLICY.md](POLICY.md)).

**Handoff notes on unblock.** The article's team observed one more behaviour:
when an agent finished a line, the dependent agent received, *at the moment it
unblocked*, notes on **how** that line was implemented. Beads already
auto-unblocks dependents (their `blocked-by` clears on close); this toolkit adds
the delivered-note half. On a passing close:

```
gate <id> --close --note "how it was built"
```

The note is authored by the **closing agent** (what it built, gotchas) — not the
human; it's the finishing agent leaving a breadcrumb for its successor, the same
spirit as the gate forcing evidence. `handoff_note.py` (invoked by `gate --close`
after `bd close` succeeds) reads the closed bead's `dependents`
(`bd show --json --include-dependents`), keeps the open ones joined by a `blocks`
edge, and appends the note to each via `bd note` — so it lands on the **dependent**
bead, and the successor agent reads "↩ handoff: dependency `<id>` closed. `<how>`"
in `bd show <its-own-bead>` when it claims (see §10). The same text is also stored
on the **closed bead itself** as its `bd close --reason` (the single authored
source / audit trail); the dependent copy is the passive-delivery mirror. A bead
with several blockers accumulates one handoff line per blocker as each closes, so
by the time it is actually ready (all blockers closed) every predecessor's note
is already in its context; the `blocks`-vs-`parent-child` filter keeps the parent
epic from being treated as a blocker. The note is **required whenever the bead
unblocks others**: `gate --close` runs `handoff_note.py --deps` first and refuses
(before closing) if a dependent exists and no `--note` was given — no dependents,
no note needed. Enforcement lives in `gate --close`: `bd` exposes no
close-lifecycle hook (its `hooks` are git hooks), so a bead closed via raw
`bd close` bypasses this — the same trust boundary as every other gate. It is
deliberately **additive and fail-safe**: it runs only after the close, mutates
only dependents' notes, and never fails the close (soft-warns on any `bd` error).
`HANDOFF_DRY_RUN=1` prints targets without writing. This makes the article's
*directly delivered notes* an intentional part of the pipeline.

**Detector / repair for bypassed closes.** Because enforcement lives in
`gate --close`, a master closed via raw `bd close` skips the mirror. `handoff_note.py
--reconcile [<id>...]` catches that after the fact: for each closed master with
open blocking-dependents, it mirrors the master's `close_reason` to any dependent
that lacks the note (idempotent — it checks for the `↩ handoff: dependency <id>`
marker first). With no id it scans every closed bead. It **cannot fabricate** a
missing "how": a master closed with no real reason (bd's generic auto-`Closed`
counts as none) is **flagged, not repaired**, and the scan exits 1. `hook-doctor`
runs this scan detect-only (`HANDOFF_DRY_RUN=1`) at session start and surfaces
anything outstanding with the fix command.
