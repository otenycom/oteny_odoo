# Todo list for oteny_audit

- [~] make an action record for all models to view their log
  - [x] Audit | Configuration | Install command
  - [ ] hook to do this automatically on install/remove of modules
- [x] writes recorded MANY Times? (did_fly_from_home)
- [x] check results: ignore
- [x] import from excel: igore using context ignore audit logging flag
- [x] generated entries, state records: ignore audit logging using context flag
- [x] manu2many support: fields_to_check write werkt niet voor user groeps: {'company_ids': 'res.users.company_ids', 'groups_id': 'res.users.groups_id'}
- List changes to sub-models under the log for a parent record: create oteny_audit_ref_log to link descendant log records to their parent log record
- List view for parent+child audit log changes
- highlight of grid based on transaction_id changing between rows
- audit viewer should show record name als single row (header), with the field changes below; less wide
