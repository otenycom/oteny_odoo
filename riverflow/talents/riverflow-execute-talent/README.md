<!-- Humans and addon authors. The bot loads SKILL.md, not this file. -->

# Riverflow execute — host Talent

This folder is the Talent for `riverflow`. A bot reads it so it can
list the same transition buttons a person sees, open the same
wizard, and save with the same footer.

Delivery is a talent git path at this directory. Oteny pulls the
commit. The bot never clones.

Point an `hh.talent.source` row at:

- repo: the git that contains this `riverflow` module
- `repo_subpath`: `riverflow/talents/riverflow-execute-talent`
- ref: the same branch or tag the addon is deployed from

Form verbs live in
`oteny_bot/talents/oteny-odoo-access-talent/`. A riverflow bot
needs both paths. A client Talent is a third path. That client
Talent composes these skills. It does not copy them.

The recipe is `SKILL.md`. Operator pages under `.claude/skills`
point here. They are not the runtime copy.
