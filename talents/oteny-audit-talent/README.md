# oteny-audit-talent

The Talent a bot reads to answer "who changed which field, and when" from the
`oteny_audit` trail, read-only, through the Odoo connection the project bound.
`SKILL.md` is the runtime copy the bot reads; `agent-profile.yaml` declares the
one tool it needs (`odoo_client`). The module `oteny_audit` in this repository
is what writes the trail; this Talent only reads it.

A client Talent loads this bundle beside its own; it does not copy the recipe.
