<!-- Humans and addon authors. The bot loads SKILL.md, not this file. -->

# Odoo list and form — host Talent

This folder is the Talent for `oteny_bot`. A bot reads it so it can
work a standard Odoo list and form.

Delivery is a talent git path at this directory. Oteny pulls the
commit. The bot never clones.

Point an `hh.talent.source` row at:

- repo: the git that contains this `oteny_bot` module
- `repo_subpath`: `oteny_bot/talents/oteny-odoo-access-talent`
- ref: the same branch or tag the addon is deployed from

The recipe is `SKILL.md`. Operator pages under `.claude/skills`
point here. They are not the runtime copy.

A riverflow bot also needs
`riverflow/talents/riverflow-execute-talent/`. A client Talent is a
third path. That client Talent composes these skills. It does not
copy them.
