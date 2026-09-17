#!/usr/bin/env python3
"""Migration version gate — pre-merge-commit + pre-commit hook.

Purpose
-------

When a feature branch is merged into ``dev`` or ``main``, this hook
ensures every migration folder added by the merge has a version > the
current dev/main ceiling. Without it, an Odoo migration whose folder
version is ``<= installed_version`` on production silently never runs,
silently breaking data invariants on every environment that already
crossed that version. The classic shape of the bug: a feature branch
sat on ``19.0.3.81/`` while dev kept bumping past it; the merge lands
the migration but production already booted at 19.0.3.85+ so Odoo's
loader skips it.

Behaviour
---------

* **Hook runs on every** ``pre-merge-commit`` or ``pre-commit`` triggered
  while a merge is in progress (``MERGE_HEAD`` exists). Other commits are
  no-ops.
* **Only gates merges whose destination is ``dev`` or ``main``.** Merges
  into a feature branch (e.g. ``git merge dev`` to refresh) cannot
  introduce staleness and are no-ops.
* **Auto-fix path** (preferred): when stale migrations are detected and
  preconditions are safe, the hook calls
  ``MergeManager._apply_renumbering`` directly against the in-progress
  merge's working tree. The renamed folders + bumped manifests are
  re-staged via ``git add``, then the hook exits 0 — letting the
  parent ``git merge`` finalise a single merge commit with the corrected
  content. The user sees a clear console message describing what was
  changed.
* **Fallback path**: when auto-fix can't safely proceed (re-entry from
  merge-branches itself, ambiguous source-branch identification, the
  renumber raises), the hook prints the exact manual command to run and
  exits 1 so the parent merge aborts cleanly.

Logging
-------

All hook output is teed to ``.git/migration-gate.log`` (newest run
appended). The log captures the diagnosis, the renumbering decisions, and
any stack trace if the auto-fix raised — so post-mortem of "why did my
merge produce that commit" is one ``cat`` away.

Re-entry guard
--------------

``riverdeploy merge-branches`` itself produces a merge commit at the end
of its renumber-then-merge flow. That merge would re-trigger this hook
in an infinite loop. The hook short-circuits to a no-op when the env-var
``RIVERDEPLOY_MERGE_BRANCHES_RUNNING=1`` is set; merge-branches is
expected to set it before invoking ``git merge``.

Edge cases
----------

* **Fast-forward merges** don't fire ``pre-merge-commit`` (no merge
  commit is created). Safe by construction: a fast-forward feature → dev
  means the feature branch was already up-to-date with dev, which means
  ``merge-branches`` was used when dev was last pulled into feature.
* **Octopus merges** (≥ 3 parents) — the hook detects multiple
  ``MERGE_HEAD`` entries and falls back to the manual-fix path with a
  clear "Octopus merges not supported" message.
* **``git rebase``** — different stages, no hook fires. Out of scope:
  rebases are dev → feature direction, the safety check happens on the
  *next* merge feature → dev.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Make the riverdeploy package importable when the hook runs from the
# repo root (the usual entrypoint via pre-commit framework). Inserting at
# index 0 means our local copy wins over any system-installed version.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from riverdeploy.module.merge import MergeManager  # noqa: E402


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

GATED_BRANCHES = {"dev", "main"}
# Ad-hoc staging slots. Together with GATED_BRANCHES these are the deploy
# pipeline's infrastructure branches — never a merge's feature side. Keep in
# step with riverdeploy/module/merge.py::INFRA_BRANCHES (canonical); this hook
# runs standalone and cannot import riverdeploy.
STAGING_BRANCHES = {"test1", "test2", "test3"}
RE_ENTRY_GUARD_ENV = "RIVERDEPLOY_MERGE_BRANCHES_RUNNING"
LOG_PATH = _REPO_ROOT / ".git" / "migration-gate.log"

_BOX_LINE = "━" * 68


# --------------------------------------------------------------------------
# Output helpers — every print also tees to .git/migration-gate.log
# --------------------------------------------------------------------------


class _TeeOutput:
    """Print to stderr (so pre-commit framework captures it) AND append
    to ``.git/migration-gate.log`` for post-mortem inspection.

    We flush the log file on every write so a crash mid-hook doesn't lose
    the diagnosis.
    """

    def __init__(self, log_path):
        self.log_path = log_path
        # Best-effort: if .git is missing or read-only we silently skip
        # logging rather than crashing the hook. This can happen in some
        # bare/worktree configurations.
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(log_path, "a", encoding="utf-8")
            self._log.write(f"\n=== {_isoformat_now()} ===\n")
            self._log.flush()
        except OSError:
            self._log = None

    def line(self, s=""):
        sys.stderr.write(s + "\n")
        sys.stderr.flush()
        if self._log is not None:
            try:
                self._log.write(s + "\n")
                self._log.flush()
            except OSError:
                self._log = None

    def close(self):
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None


def _isoformat_now():
    """Best-effort wall-clock timestamp without importing datetime at
    module top level (the hook runs on every commit and we want it lean)."""
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Git plumbing
# --------------------------------------------------------------------------


def _git(*args, check=True):
    """Run ``git <args>`` in the repo root and return stripped stdout.

    Raises ``RuntimeError`` on non-zero exit when ``check=True`` (default);
    pass ``check=False`` for probes that may legitimately fail (e.g.
    ``git rev-parse MERGE_HEAD`` on a non-merge commit).
    """
    result = subprocess.run(
        ["git"] + list(args),
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _is_merge_in_progress():
    """True iff ``MERGE_HEAD`` exists — i.e. ``git merge`` is mid-flight.

    Used by the ``pre-commit`` stage so we only act when the user's
    ``git commit`` is finalising a ``--no-commit`` merge; normal commits
    are no-ops.
    """
    merge_head_file = _REPO_ROOT / ".git" / "MERGE_HEAD"
    return merge_head_file.is_file()


def _current_branch():
    """Branch name that HEAD currently points to (e.g. ``"dev"``).

    Returns ``None`` for detached-HEAD state — in which case the hook is
    a no-op (we can't reason about gated destinations without a branch
    name).
    """
    name = _git("symbolic-ref", "--short", "HEAD", check=False)
    return name or None


def _merge_head_commits():
    """List of commit hashes currently in ``.git/MERGE_HEAD``.

    Returns one entry for a normal 2-way merge; multiple entries indicate
    an octopus merge.
    """
    merge_head_file = _REPO_ROOT / ".git" / "MERGE_HEAD"
    if not merge_head_file.is_file():
        return []
    return [
        line.strip() for line in merge_head_file.read_text().splitlines()
        if line.strip()
    ]


def _identify_source_branch(merge_head_sha):
    """Find the branch name whose tip is ``merge_head_sha``.

    Returns the most-specific name we can derive:
    * Prefer a local non-``origin/`` ref that points exactly at the SHA.
    * Fall back to the first ``origin/<name>`` if no local ref matches.
    * Return ``None`` if no ref points at the SHA (detached commit).

    We do NOT use ``git branch --contains`` (which lists every ancestor
    branch); we want the branch whose TIP is this commit, which is the
    "what we are merging in" identity.
    """
    decoration = _git("log", "-1", "--format=%D", merge_head_sha, check=False)
    if not decoration:
        return None
    # `%D` produces something like "HEAD -> dev, origin/dev, feature/x"
    refs = []
    for chunk in decoration.split(","):
        ref = chunk.strip()
        # Strip leading "HEAD -> " from the "current-HEAD" decoration.
        if ref.startswith("HEAD -> "):
            ref = ref[len("HEAD -> "):]
        # Skip plain "HEAD" and tag refs.
        if not ref or ref == "HEAD" or ref.startswith("tag:"):
            continue
        refs.append(ref)
    # Prefer local refs (no origin/ prefix) — those are what the user
    # would type. Within that group, prefer feature/* over infra branch
    # names so we don't pick "dev" when the source happens to also point
    # at dev's tip.
    locals_ = [r for r in refs if not r.startswith("origin/")]
    feature_locals = [r for r in locals_ if r not in GATED_BRANCHES and r not in STAGING_BRANCHES]
    if feature_locals:
        return feature_locals[0]
    if locals_:
        return locals_[0]
    if refs:
        return refs[0]
    return None


# --------------------------------------------------------------------------
# Diagnosis output
# --------------------------------------------------------------------------


def _print_diagnosis_header(out, source, target):
    out.line("")
    out.line(_BOX_LINE)
    out.line("  ⚠ Migration version gate — stale migrations detected")
    out.line(_BOX_LINE)
    out.line("")
    out.line(f"  Merging  {source}  →  {target}")
    out.line("")
    out.line("  These migrations would be silently skipped on production")
    out.line("  (folder version <= dev/main ceiling):")
    out.line("")


def _print_stale_table(out, analysis):
    for module, info in analysis["modules"].items():
        if not info["stale_migrations"]:
            continue
        for v in info["stale_migrations"]:
            out.line(
                f"    {module}/migrations/{v}/   "
                f"(ceiling: {info['ceiling']})"
            )
    out.line("")


def _print_autofix_plan(out, analysis):
    out.line("  Auto-fix plan:")
    out.line("")
    counter = [0]
    for module, info in analysis["modules"].items():
        if not info["stale_migrations"]:
            continue
        from riverdeploy.module.merge import (
            increment_last_segment,
            parse_version,
            version_to_str,
        )
        ceiling = parse_version(info["ceiling"])
        for i, v in enumerate(info["stale_migrations"]):
            new_v = version_to_str(increment_last_segment(ceiling, i + 1))
            counter[0] += 1
            out.line(
                f"    {counter[0]:>2}. Renumber  {module}/migrations/{v}/  →  "
                f"{module}/migrations/{new_v}/"
            )
        highest = version_to_str(
            increment_last_segment(ceiling, len(info["stale_migrations"]))
        )
        if (info["feature_version"]
                and parse_version(info["feature_version"]) < parse_version(highest)):
            counter[0] += 1
            out.line(
                f"    {counter[0]:>2}. Bump      {module}/__manifest__.py  "
                f"{info['feature_version']}  →  {highest}"
            )
    out.line("")


def _print_autofix_success(out):
    out.line("  ✓ Renumbered files staged into the in-progress merge.")
    out.line("  ✓ Merge will finalise with the corrected content.")
    out.line("  ✓ Inspect with: git log -1 --stat")
    out.line("")
    out.line(_BOX_LINE)
    out.line("")


def _print_fallback(out, source, target, reason):
    out.line("")
    out.line(_BOX_LINE)
    out.line("  ⛔ Migration version gate — auto-fix declined")
    out.line(_BOX_LINE)
    out.line("")
    out.line(f"  Reason: {reason}")
    out.line("")
    out.line("  To resolve manually:")
    out.line("")
    out.line("    git merge --abort")
    out.line(f"    python -m riverdeploy merge-branches {source} {target}")
    out.line("")
    out.line("  After that, the renumbered migrations will land cleanly")
    out.line(f"  and a fresh merge commit on {target} closes out the merge.")
    out.line("")
    out.line(_BOX_LINE)
    out.line("")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main():
    """Entry point invoked by the pre-commit framework.

    Returns 0 on no-op or successful auto-fix; non-zero to abort the
    in-progress merge / commit when the user must take manual action.
    """
    out = _TeeOutput(LOG_PATH)
    try:
        # 1. Re-entry guard: if merge-branches itself is producing a
        #    merge commit, do not re-run the gate (would loop forever).
        if os.environ.get(RE_ENTRY_GUARD_ENV) == "1":
            return 0

        # 2. Only act if a merge is actually in progress. This makes the
        #    same script safely usable for both the pre-merge-commit
        #    stage (always merge-in-progress) and the pre-commit stage
        #    (only merge-in-progress when the user did `git merge --no-commit`
        #    followed by `git commit`).
        if not _is_merge_in_progress():
            return 0

        # 3. Only gate merges into dev or main.
        target_branch = _current_branch()
        if target_branch not in GATED_BRANCHES:
            return 0

        # 4. Reject octopus merges — too unusual to auto-handle.
        merge_heads = _merge_head_commits()
        if len(merge_heads) != 1:
            _print_fallback(
                out,
                "<multiple-sources>",
                target_branch,
                f"Octopus merges ({len(merge_heads)} parents) are not auto-fixable.",
            )
            return 1
        merge_head_sha = merge_heads[0]

        # 5. Identify the source branch (best-effort; detached MERGE_HEAD
        #    falls back to the bare commit hash so analyze() can still
        #    operate via `git show <sha>:<path>`).
        source_branch = _identify_source_branch(merge_head_sha) or merge_head_sha

        # 6. Run the existing analyzer. It auto-discovers radar modules
        #    (Component 1) and computes ceiling = max(dev, main) per module.
        try:
            mgr = MergeManager()
            analysis = mgr.analyze(source=source_branch, target=target_branch)
        except Exception as exc:
            _print_fallback(
                out,
                source_branch,
                target_branch,
                f"Analyzer raised: {exc}",
            )
            return 1

        stale_count = sum(
            len(info["stale_migrations"])
            for info in analysis["modules"].values()
        )
        if stale_count == 0:
            # Clean merge — no diagnosis output, just exit 0 silently.
            return 0

        # 7. Stale migrations found. Print diagnosis + auto-fix plan.
        _print_diagnosis_header(out, source_branch, target_branch)
        _print_stale_table(out, analysis)
        _print_autofix_plan(out, analysis)

        # 8. Apply renumbering in place against the working tree (no
        #    checkout, no commit — the in-progress merge will commit it).
        try:
            changes_made = mgr._apply_renumbering(analysis)
        except Exception as exc:
            out.line(f"  ⛔ Renumber raised: {exc}")
            _print_fallback(
                out,
                source_branch,
                target_branch,
                "Renumber raised an exception. See log for trace.",
            )
            return 1

        if not changes_made:
            # Defensive: stale-count > 0 but renumber did nothing. Should
            # not happen (the analysis just told us there were stale
            # entries) — bail to manual to avoid masking weirdness.
            _print_fallback(
                out,
                source_branch,
                target_branch,
                "Stale migrations reported but renumber made no changes.",
            )
            return 1

        # 9. Re-stage everything the renumber touched. ``git add -u`` picks
        #    up renames + the manifest edits. Newly-renamed folders are
        #    already staged by ``git mv`` inside _safe_rename_migration_dir,
        #    but the manifest edits go through filesystem write so they
        #    need an explicit stage.
        try:
            _git("add", "-u")
        except RuntimeError as exc:
            out.line(f"  ⛔ git add -u failed: {exc}")
            _print_fallback(
                out,
                source_branch,
                target_branch,
                "Could not re-stage renumbered files. See log.",
            )
            return 1

        _print_autofix_success(out)

        # Exit 0 so the parent `git merge` finalises the merge commit
        # with the corrected staged content.
        return 0

    finally:
        out.close()


if __name__ == "__main__":
    sys.exit(main())
