# Plan: unlazy + beads + rtk integration

Date: 2026-08-25
Status: proposal (skill/asset placement settled — Copilot auto-discovers `~/.agents/skills/`)
Location: `~/.agents/unlazy-beads-rtk/beads_unlazy_plan.md` (agent-neutral HOME hub)

End-to-end walkthrough with real command output: [WALKTHROUGH.md](WALKTHROUGH.md)

Plan-placement convention (decided 2026-08-25):
- Actionable plans → beads (epic + Depth Tree + `--acceptance`), not markdown.
- Repo-specific design docs → that repo's `docs/`.
- Cross-repo / personal tooling design (like this) → `~/.agents/`.
- `~/.claude/plans/` is deprecated (stale Claude-Code artifact).

## One-line architecture

**unlazy is the *method* (decompose + write falsifiable gates + verify before
done), beads is the *durable store + scheduler* for the resulting tree, and rtk
is the *global command wrapper* the gate checks run through.** Three layers, no
overlap: unlazy authors the graph, beads persists and schedules it across
repos, rtk makes the verification commands cheap.

```
unlazy  ──produces──▶  a Depth Tree of leaves + acceptance gates
beads   ──stores────▶  that tree as issues (parent-child + blocks + --acceptance)
rtk     ──wraps─────▶  the CHECK commands the gates run (any repo, any agent)
```

---

## How to use it (quickstart)

Read this section to *run* the integration; read the numbered sections below to
understand *why* it is shaped this way.

**Concept:** you agree a plan with the agent, it decomposes it into a tree, you
approve, it becomes beads in one shot, and each bead only closes when a runnable
gate passes.

### Artifacts — how the plan becomes beads

The human-readable plan is *exploded* into the Depth Tree and then *serialized*
as a beads graph. Three distinct artifacts, in order:

```
agreed plan            the outcome of the chat (what to build). Optionally
   │                   captured as unlazy's PLAN.md contract inventory.
   ▼  (unlazy decomposes)
Depth Tree             root → branch → leaf, each leaf with contract, OWNS,
   │                   dependencies, and its acceptance gate. Lives in the head
   │                   / chat / unlazy PLAN.md; not yet machine-consumable.
   ▼  (serialize the approved tree)
plan.json              the SAME tree written as a beads graph (confirmed schema):
   │                   { nodes:[{key,title,type,parent_key,priority,labels,
   │                            description}],
   │                     edges:[{from_key,to_key,type}] }
   │                   Hierarchy is `parent_key` (flat list, NOT nested
   │                   children); `edges` carry `blocks`. Nodes have no
   │                   acceptance field — acceptance lives in the gate ledger.
   ▼  beads_gen plan.json  (wraps `bd create --graph`)
beads                  epic + branch + leaf issues with parent-child / blocks
   │                   edges wired. IDs are flat (`myproj-1xa`), not dotted.
   ▼  review plan.graph.md, then ul_gates_gen plan.json
gate ledgers           one `.beads/gates/<id>.md` per leaf, ready to fill in.
```

So yes: **`plan.json` is the Depth Tree in beads-graph form** — the machine
input to `bd create --graph`. Do not confuse it with unlazy's own `PLAN.md`
template (a human contract/tree doc); `plan.json` is the serialized,
create-ready projection of that tree. (This file is named `beads_unlazy_plan.md`
precisely to avoid colliding with unlazy's `PLAN.md` artifact.)

**Two separate tools, do not confuse them:**
- **Creation** = `beads_gen plan.json` (wraps `bd create --graph`) — builds ALL
  beads + all edges (`parent-child`, `blocks`) from one plan file, writes a
  manifest sidecar, and renders a mermaid review chart. `--dry-run` via bd
  previews. Re-runnable: a second run deletes the manifest's beads and recreates.
- **Verification** = `gate <bead-id>` — runs a bead's CHECK and gates `bd close`.
  `gate` never creates beads.

### What YOU do (three touchpoints)

1. **Approve the tree in chat.** Describe the task (optionally `tree N` to hint
   depth). The agent replies with a bulleted tree — leaves, ownership,
   dependencies, and its merge/split rationale. You say "yes" or adjust. No file
   and no bead exists yet; this conversation *is* the human gate.
2. **Approve the CHECK commands once** (`gate <id> --approve`) — a security
   confirmation before any command runs. Can be batched.
3. **Read the final report.**

### What the AGENT does

4. On your "yes", serialize the approved tree to `plan.json` (`nodes` +
   `edges`) and materialize in two reviewable steps:

   ```bash
   beads_gen plan.json      # bd create --graph + manifest + plan.graph.md chart
   #   → you open plan.graph.md (mermaid: dotted = parent-child, solid = blocks)
   #     and confirm the tree looks right
   ul_gates_gen plan.json   # scaffold .beads/gates/<id>.md for each LEAF bead
   ```

   The mermaid chart is a **review checkpoint** between graph-create and
   ledger-scaffold; nothing is gated until you approve it.
5. Per leaf: implement → `gate <id> --lint` → `gate <id> --approve` →
   `gate <id> --close` (reverify; `bd close` iff all gates pass, else HANDOFF).
6. `bd epic status` rolls completion up to the root, then reports.

### The `gate` verbs (agent-facing, per leaf)

```bash
gate <id> --new       scaffold a ledger (from template, or from the bead's acceptance)
gate <id> --lint      catch un-failable / fixed-output oracles
gate <id> --approve   approve + run the CHECK commands the first time
gate <id>             reverify (re-execute the checks)
gate <id> --close     reverify; bd close iff all pass, else HANDOFF
```

> Not yet built: a `materialize plan.json` helper that does `bd create --graph`
> **and** scaffolds every gate ledger in one command — the literal version of
> "one command turns the plan into gated beads." Ask to add it when wanted.

That is the entire day-to-day surface. Everything else in this file is rationale.

---

## 1. Why unlazy fits a beads architecture

beads already gives you the *shape* unlazy needs, but nothing that fills it well:

| unlazy artifact | beads primitive it maps to | grounded fact |
|---|---|---|
| Depth Tree (root → branch → leaf) | `--parent` parent-child edges (arbitrary depth) | `bd create --parent` |
| Leaf dependencies | `bd dep add --type blocks` | dep types: `blocks\|tracks\|related\|parent-child\|discovered-from\|until\|caused-by\|validates\|relates-to\|supersedes` |
| Acceptance gate (`CHECK:`/`EXPECT:`) | `bd create --acceptance` | native field |
| Leaves-upward verification | `bd epic status`, `bd epic close-eligible` | closes parent when all children complete |
| Root reconcile / report | epic roll-up + reread | — |

So unlazy is not a competitor to beads — it is the **authoring and
verification discipline** that beads lacks. beads is a persistent,
dependency-aware issue graph; unlazy is the procedure that decides *what the
nodes are* and *how you prove each one is done*.

unlazy's own artifacts (`PLAN.md`, `GATES.md`, `.unlazy/<scope>/`) are
**session-scoped and ephemeral**. beads gives the same tree **durability,
cross-session recovery, multi-repo reach, and multi-agent coordination**. That
is the fit: unlazy produces the structure; beads is where the structure lives.

## 2. Why beads benefits from unlazy (honest version)

beads does **not** need unlazy to function. The benefit is narrow but real:

- **`--acceptance` stops being prose nobody checks.** Today an acceptance
  criterion is a sentence. unlazy turns it into a runnable `CHECK:` with a
  success-only `EXPECT:`, linted by `gate_lint.py` so an oracle that *cannot
  fail* is caught at authoring time, and re-run by `gate_check.py --reverify`
  before `bd close`. Acceptance becomes *enforced*, not aspirational.
- **Decomposition quality.** beads lets you nest anything; unlazy's
  "contract before fan-out" + "merge tiny adjacent leaves / split hidden
  outcomes" gives a principled reason for each node.
- **Honest completion.** unlazy distinguishes a *legitimate stop* (owner
  decision / handoff) from a *lazy stop* (confident done over unmet gates).
  beads' `close` gets a gate in front of it.

**When beads does NOT benefit:** trivial beads (a one-line fix, a factual
note). unlazy itself says do not gate a trivial edit. Keep the discipline for
work where quiet incompleteness is costly.

## 3. Where rtk fits

rtk is **orthogonal and global**. It wraps the commands agents run — including
the commands unlazy uses as gate oracles — to cut token cost. It is an
"any repo" requirement, configured once in `~/.config/rtk/`, no per-repo files.

Rules that matter for this integration:
- **Route CHECK commands through rtk** where a wrapper exists:
  `rtk cargo test …` (Rust repos), `rtk npm …` / `rtk vitest …` (JS repos).
- **rtk hooks do NOT fire under Copilot/Cursor** — the rewrite hook is
  Claude-Code-only. So gate `CHECK:` lines must write `rtk …` *explicitly*;
  do not rely on transparent rewriting.
- **Approval stability:** unlazy binds an approval to the *exact* command
  string + PATH + cwd. `rtk cargo test` and `cargo test` are different
  approvals. Pick one convention (prefer `rtk`) and keep it, or you re-approve
  constantly.

---

## 4. File layout — general (HOME) vs repo-specific

Guiding principle: **anything identical across repos lives once in HOME and is
referenced; only intrinsically per-repo state lives in a repo.**

### Global — the "any repo" machinery (HOME)

```
~/.local/bin/            bd, rtk, dolt                     (already present)
~/.config/rtk/           config.toml, filters.toml         (already present)
~/.beads/
    shared-server/       Dolt sql-server, port 3306        (already present)
    (beads_global db)    cross-repo epics via `bd --global`
~/.unlazy/
    approved/            gate approvals — MUST be outside any repo (enforced)
~/.agents/skills/unlazy/ CANONICAL unlazy skill: scripts/, references/,
                         templates/, SKILL.md, SECURITY.md
~/.agents/unlazy-beads-rtk/
    beads_unlazy_plan.md this design doc
    gate                 wrapper (also symlinked to ~/.local/bin/gate)
    GATES.template.md    generic leaf-gate template
                         (rtk/approval conventions are inline in gate + template)
```

Why `~/.agents/skills/unlazy/` for the canonical copy: it matches the documented
global-skill convention (`~/.agents/skills/<name>/`, same pattern as the beads
skill). **VS Code Copilot auto-discovers `~/.agents/skills/` globally** (verified:
the copied unlazy skill loads from there with no per-repo wiring), so no symlink
is needed. A per-repo `.cursor/skills -> ~/.agents/skills` symlink is a
**Cursor-only** workaround for Cursor's project-local discovery; not used here.

### Repo-specific — only what is intrinsically per-repo

```
<repo>/.beads/                    per-repo Dolt db + config.yaml + hooks
                                  (exists in the primary repo; `bd init` elsewhere on demand)
<repo>/.beads/gates/<id>.md       per-bead gate ledgers (durable record is the bead)
```

The **only genuinely repo-specific content is the CHECK commands**, because
build/test differ per repo:

| Repo family | Gate CHECK convention |
|---|---|
| Monorepo (Rush) | `rush build`, `rushx test`, `rushx <script>` |
| Rust repos | `rtk cargo test …`, `rtk cargo build` |
| JS repos | `rtk npm …` / `rtk vitest …` |

These live in each leaf's `plan.json` acceptance and its gate ledger. Nothing
repo-specific needs to live in HOME.

---

## 5. Multi-repo and outside-the-workspace beads

A common case: a single logical effort spans more than one git repo, sometimes
repos not in the current workspace.

Two supported modes:

- **Per-repo tracking (default):** each repo has its own `.beads/` (like
  the primary repo). Independent trees, synced through the shared server. Use when work
  is contained in one repo.
- **Cross-repo tracking:** use the **global beads db** (`bd --global`, the
  `beads_global` database on the shared server). One epic/tree can hold leaves
  that belong to different repos; each leaf records its repo via
  `--external-ref` (e.g. `gh-…`) or a `repo:<name>` label, and its `OWNS:`
  paths are written repo-relative. Use for a Depth Tree whose branches cross
  repo boundaries or reach a repo outside the workspace.

Recommendation: **default to per-repo `.beads`; escalate a specific tree to the
global db only when its branches genuinely span repos.** Keep the shared server
(`~/.beads/shared-server`) as the single sync point either way — it already
works on this machine.

---

## 6. End-to-end workflow (corrections from discussion baked in)

```
1. Agree on the plan                      (conversation)
2. unlazy builds Contract inventory       (unlazy PLAN.md — every omittable outcome)
3. unlazy GENERATES the Depth Tree        (the intellectual step; details each
                                           leaf: contract, OWNS, deps, gates)
4. HUMAN GATE — you approve the tree       (conversational, BEFORE any bead;
   ┌─ iterate 3⇄4 until leaves make        you say YES to unlazy, not to beads)
   │  sense to you, incl. merge choices
5. Serialize tree → plan.json, then        (mechanical: root→epic,
   │  bd create --graph plan.json          branch→intermediate parent bead,
   │                                        leaf→task bead, edges→parent-child/blocks,
   │                                        gate→acceptance)
6. Work each leaf in 4 passes
7. gate <id> --close (reverify → bd close) (gate in front of close)
8. bd epic status / close-eligible         (leaves-upward reconcile → report)
```

Decisions settled in discussion, encoded here so the plan is self-contained:

- **The human approval gate is conversational and lives at step 4, before
  materialization.** You approve *unlazy*, not beads. Do **not** create a
  `gate-plan` blocking bead in the default flow — the beads created at step 5
  are by definition already approved, so a gate bead is redundant ceremony. (A
  blocking gate bead only earns its place in a *materialize-then-approve*, an
  *async/second-reviewer*, or a *mid-flight amendment* flow.)
- **leaf ↔ bead is not strictly 1:1.** Default 1:1, but merge tiny adjacent
  leaves and split a leaf hiding several outcomes. The invariant that stays
  1:1 is **leaf ↔ acceptance gate**.
- **CHECK commands always prefix `rtk`.** Every gate CHECK is written `rtk …`
  (`rtk cargo test`, `rtk npm …`, `rtk rush build`), never raw. rtk's rewrite
  hook does not fire under Copilot/Cursor, so the prefix must be explicit; a
  uniform prefix also keeps approvals stable (approvals bind the exact command
  string, so raw-vs-rtk drift would fragment them). rtk still tracks savings on
  light commands via pass-through, so there is no downside to always using it.
- **No new bead hierarchy type.** beads depth is edge-based (`--parent` nests
  arbitrarily; an epic can parent an epic). A "branch" is a *role*
  (intermediate parent bead carrying an *integration* gate), not a rank
  between task and epic. Mark it with a label like `role:branch` if you want
  to query them; do not add a schema tier.

---

## 7. Setup steps

DONE:
1. ✅ Canonical skill installed at `~/.agents/skills/unlazy/` (Copilot
   auto-discovers it globally — no symlink needed).
2. ✅ Generic assets under `~/.agents/unlazy-beads-rtk/`: `gate` wrapper (also
   symlinked to `~/.local/bin/gate`) and `GATES.template.md`. Smoke-tested.
3. ✅ Approvals stay at `~/.unlazy/approved/` (default; outside every repo).

Per repo, on demand only:
4. `bd init` if the repo needs its own tracking.
5. Author gates with repo-appropriate CHECK commands routed through `rtk`,
   then `gate <bead-id> --new` / `--lint` / `--approve` / `--close`.

ALSO DONE (materialize helpers, generic in HOME, symlinked to `~/.local/bin`):
6. ✅ `beads_gen <plan.json> [--no-wbs]` — `bd create --graph` + `<plan>.beads.json`
   manifest + `<plan>.graph.md` mermaid chart (dotted = parent-child, solid =
   blocks). Re-runnable overwrite via the manifest. Renderer: `render_mermaid.py`.
   By default injects a WBS prefix into each title (`[E1]`, `[E1.T1]`,
   `[E1.T1.T1]`) + a `wbs:` label, derived from the `parent_key` tree, so a flat
   `bd list` reads like an outline (flat IDs are unavoidable; titles/labels are
   ours). Injector: `wbs_prefix.py`; never mutates your `plan.json`.
7. ✅ `ul_gates_gen <plan.json>` — scaffolds a leaf gate ledger per manifest
   leaf (leaves detected via parent-child edges, since graph IDs are flat).
   Slash-command wrappers `/beads_gen` and `/ul_gates_gen` call these.

## 9. Development trace (git-time) — DONE

The trace is not "keep every bead forever": you **close** beads (Dolt keeps them
queryable with history), and gate ledgers under `.beads/gates/` are committed
evidence. On top of that, a thin git integration writes a human index:

- `devlog_update --trailer` — prints a "Beads closed" summary (id, title, passing
  gate CHECKs) for beads closed since a watermark; no side effects.
- `devlog_update --commit <sha>` — appends that summary (with sha/date/subject)
  to `.beads/DEVLOG.md` and advances the watermark (`.beads/.devlog-mark`, kept
  git-ignored; first run defaults to HEAD's date).
- Hooks: `prepare-commit-msg` appends the summary as a **commit-message trailer**
  (so `git log` becomes a verified trace); `post-commit` writes the `DEVLOG.md`
  entry. Installed per-repo, chain-safe, via `install-devlog-hooks [repo]`.
- Hooks only *annotate* commits you make — they never create/amend/auto-commit.
  The `DEVLOG.md` change lands with your next commit (one-commit lag, by design).

## 8. Open decisions for you

- **Cross-repo default:** ~~per-repo `.beads` everywhere, or one global tree for
  multi-repo efforts?~~ **SETTLED (2026-08-27).** Per-repo `.beads/` is the
  default: each repo keeps its own Dolt db, config, and gates under `.beads/`,
  synced through the shared server. The cross-repo *view* is not lost — it comes
  from bd's multi-repo hydration (`repos.additional` in config.yaml) plus the
  `beads_global` db, so no physical centralization is needed. Names don't grow:
  the `<prefix>-<id>` prefix is intrinsic to every ID regardless of storage, so
  cross-repo attribution costs zero extra characters (given a pinned
  `issue-prefix`, which `beads_gen` now enforces).
- **Gate ledger location:** **SETTLED.** Gates live next to their beads under
  `<repo>/.beads/gates/<id>.md` (the `gate` default, override via `GATE_DIR`).
  Invariant: **gates follow the beads** — if beads ever move to `~/.beads`,
  `GATE_DIR` moves the gates with them; they never split.

