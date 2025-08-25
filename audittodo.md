# Todo list for oteny_audit

- [x] basic testers and views for oteny_audit
- [~] make an action record for all models to view their log via their Action menu
  - [x] Audit | Configuration | Install command
  - [ ] hook to do this automatically on install/remove of modules
- [x] writes recorded MANY Times? (did_fly_from_home)
- [x] check results: ignore
- [x] import from excel: disable logging during import using context ignore audit logging flag
  - [ ] some writes during import are still logged, some call method flows clear the context apparenty, not a big deal
- [x] generated entries, state records: ignore audit logging using context flag
- [x] manu2many support: fields_to_check write werkt niet voor user groeps: {'company_ids': 'res.users.company_ids', 'groups_id': 'res.users.groups_id'}
- List changes to sub-models under the log for a parent record, eg service changes listed when viewing the log of a log entry
  - create oteny_audit_ref_log to link descendant log records to their parent log record
- Audit log cleaner cronjob
- List view for parent+child audit log changes in a single list
- highlight of grid based on transaction_id changing between rows, so each single transaction is easily recognized by the user
- audit viewer should show record name als single row (header), with the field changes below; makes the list less wide and helps visual focus
- Add support for translated fields
- Add support for company-dependent fields  
