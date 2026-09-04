#!/usr/bin/env python3
"""review — independent second-brain review for beads flagged `review:req`.

A reviewer is a CHECKER, not an execution tier (see the `reviewer` block in
models.json): it never owns a bead, it audits what a flagged bead produced.
Model, trigger, and severity policy all live in models.json; `enabled` there is
the master switch (false = the whole review gate is inert).

The controller drives the actual model call (launch models.json reviewer.model
as a subagent); this script owns SCOPE gathering and the severity POLICY:

  review --scope  <bead>   emit the review PACKET (intent + upstream handoff
                           notes + branch diff) for the controller to hand to the
                           reviewer model. Detect/prepare, never auto-run.
  review --record <bead> --severity <nit|minor|major|critical> --summary "..."
                          [--finding "<sev>:<text>"]... [--dry-run]
                           apply policy: findings >= file_beads_from become linked
                           follow-up beads (discovered-from), lesser ones + the
                           summary become notes, and the bead gets review:ok
                           (advisory) or review:block (severity >= block_on) so
                           `gate --close` can enforce it.
  review --gate   <bead>   exit 0 if a review:req bead may close, 1 (with reason)
                           if it must not (unreviewed, or review:block). gate uses
                           this. No-op (0) when the reviewer is disabled.
  review --due    [<bead>...]
                           print flagged beads still awaiting a verdict (open,
                           review:req, no review:ok/review:block). gate and
                           hook-doctor use this to SURFACE a due review.

Severity ladder: nit < minor < major < critical.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SEV = ["nit", "minor", "major", "critical"]


def _rank(s):
    s = (s or "").strip().lower()
    return SEV.index(s) if s in SEV else -1


def _reviewer_cfg():
    p = Path(os.path.realpath(__file__)).parent / "models.json"
    try:
        return json.loads(p.read_text()).get("reviewer", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _enabled():
    return bool(_reviewer_cfg().get("enabled"))


def _bd(args):
    return subprocess.run(["bd", *args], capture_output=True, text=True)


def _git(args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def _die(msg):
    print(f"review: {msg}", file=sys.stderr)
    sys.exit(2)


def _show(bead):
    r = _bd(["show", bead, "--json"])
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(d, list):
        return d[0] if d else None
    return d if isinstance(d, dict) else None


def _labels(issue):
    return issue.get("labels") or []


def _all():
    r = _bd(["list", "--all", "--json"])
    txt = r.stdout
    start = txt.find("[")
    try:
        d = json.loads(txt[start:]) if start != -1 else []
    except json.JSONDecodeError:
        d = []
    return d if isinstance(d, list) else []


# ---- --due -----------------------------------------------------------------
def cmd_due(scope_ids):
    if not _enabled():
        return 0
    scope = set(scope_ids)
    for i in _all():
        labs = i.get("labels") or []
        if "review:req" not in labs:
            continue
        if "review:ok" in labs or "review:block" in labs:
            continue
        if str(i.get("status", "")).lower() in ("closed", "done"):
            continue
        if scope and i.get("id") not in scope:
            continue
        print(f"{i.get('id')}  {i.get('title', '')}")
    return 0


# ---- --gate ----------------------------------------------------------------
def cmd_gate(bead):
    # Exit 0 = may close; 1 = must not. No-op when the reviewer is disabled.
    if not _enabled():
        return 0
    issue = _show(bead)
    if not issue:
        return 0
    labs = _labels(issue)
    if "review:req" not in labs:
        return 0
    if "review:block" in labs:
        print(f"review BLOCK: {bead} has an unresolved finding >= block_on "
              f"(override: gate {bead} --close ... --override-review)", file=sys.stderr)
        return 1
    if "review:ok" not in labs:
        print(f"review REQUIRED: {bead} is flagged review:req but not yet reviewed — "
              f"run: review --scope {bead}", file=sys.stderr)
        return 1
    return 0


# ---- --scope ---------------------------------------------------------------
def cmd_scope(bead):
    issue = _show(bead)
    if not issue:
        _die(f"bead not found: {bead}")
    cfg = _reviewer_cfg()
    if not cfg.get("enabled"):
        print("review: NOTE — reviewer is disabled in models.json (enabled:false); "
              "this packet is advisory only.", file=sys.stderr)
    base = os.environ.get("REVIEW_BASE", "develop")
    mb = _git(["merge-base", "HEAD", base]).strip() or base
    diff = _git(["diff", mb])
    print(f"# REVIEW PACKET — {bead}: {issue.get('title', '')}")
    print(f"# reviewer model: {cfg.get('model', '<unset>')}  "
          f"(launch this model as the reviewer subagent)")
    print(f"# ladder: {' < '.join(SEV)}  |  block_on={cfg.get('block_on', 'critical')}  "
          f"file_beads_from={cfg.get('file_beads_from', 'minor')}")
    print()
    print("## Intent (what this bead was supposed to build)")
    print(issue.get("description") or "(no description)")
    print()
    print("## Notes / upstream handoff")
    print(issue.get("notes") or "(none)")
    print()
    print(f"## Diff to review (git diff {base}...HEAD)")
    print(diff if diff.strip() else "(no diff)")
    print()
    print("## Return the verdict by running:")
    print(f'#   review --record {bead} --severity <nit|minor|major|critical> '
          f'--summary "..." [--finding "<sev>:<text>"]...')
    return 0


# ---- --record --------------------------------------------------------------
def cmd_record(bead, opts):
    issue = _show(bead)
    if not issue:
        _die(f"bead not found: {bead}")
    sev = opts.get("severity")
    if _rank(sev) < 0:
        _die(f"--severity must be one of {', '.join(SEV)}")
    summary = (opts.get("summary") or "").strip()
    findings = opts.get("findings", [])
    cfg = _reviewer_cfg()
    block_on = cfg.get("block_on", "critical")
    file_from = cfg.get("file_beads_from", "minor")
    dry = opts.get("dry")

    for f in findings:
        fsev, _, ftext = f.partition(":")
        fsev = fsev.strip().lower()
        ftext = ftext.strip()
        if _rank(fsev) < 0:
            _die(f"finding severity invalid in {f!r} (use '<sev>:<text>')")
        if _rank(fsev) >= _rank(file_from):
            title = ftext or f"{fsev} finding from review of {bead}"
            if dry:
                print(f"review: would file bead [{fsev}] {title} (discovered-from:{bead})")
            else:
                r = _bd(["create", title, "--type", "task",
                         "--labels", f"review-finding,sev:{fsev}",
                         "--deps", f"discovered-from:{bead}", "--silent"])
                nid = r.stdout.strip().splitlines()[-1] if (r.returncode == 0 and r.stdout.strip()) else "?"
                print(f"review: filed {nid} [{fsev}] {title}")
        else:
            note = f"review nit: {ftext}"
            if dry:
                print(f"review: would note {bead}: {note}")
            else:
                _bd(["update", bead, "--append-notes", note])

    verdict = f"\u21a6 review [{sev}] by {cfg.get('model', 'reviewer')}: {summary or '(no summary)'}"
    if dry:
        print(f"review: would note {bead}: {verdict}")
    else:
        _bd(["update", bead, "--append-notes", verdict])

    outcome = "review:block" if _rank(sev) >= _rank(block_on) else "review:ok"
    if dry:
        print(f"review: would set {outcome} on {bead}")
    else:
        _bd(["update", bead, "--add-label", outcome])
    print(f"review: {bead} -> {outcome} (severity {sev}; block_on {block_on})")
    if outcome == "review:block":
        print(f"review: {bead} is BLOCKED for close until addressed "
              f"(override: gate {bead} --close ... --override-review)", file=sys.stderr)
    return 0


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if a else 2
    if a[0] == "--due":
        return cmd_due(a[1:])
    if a[0] == "--gate":
        if len(a) < 2:
            _die("usage: review --gate <bead>")
        return cmd_gate(a[1])
    if a[0] == "--scope":
        if len(a) < 2:
            _die("usage: review --scope <bead>")
        return cmd_scope(a[1])
    if a[0] == "--record":
        if len(a) < 2:
            _die("usage: review --record <bead> --severity ...")
        bead = a[1]
        opts = {"findings": []}
        i = 2
        while i < len(a):
            t = a[i]
            if t == "--severity":
                opts["severity"] = a[i + 1]; i += 2
            elif t == "--summary":
                opts["summary"] = a[i + 1]; i += 2
            elif t == "--finding":
                opts["findings"].append(a[i + 1]); i += 2
            elif t == "--dry-run":
                opts["dry"] = True; i += 1
            else:
                _die(f"unknown --record option: {t}")
        return cmd_record(bead, opts)
    _die(f"unknown command: {a[0]}")


if __name__ == "__main__":
    sys.exit(main())
