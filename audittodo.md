# Todo list for oteny_audit

- [~] make an action record for all models to view their log
  - [x] Config | Install command
  - [ ] hook to do this automatically on install/remove of modules

- List changes to sub-models under the log for a parent record: create oteny_audit_ref_log to link descendant log records to their parent log record
- [x] updates recorded MANY Times? (did_fly_from_home)
- [x] check results: ignore
- import from excel: igore using context flag?
- generated entries: ignore write/unlink using context flag?
- highlight of grid based on transaction_id changing
- audit viewer should show record name als single row, with the field change below; less wide

- bug: fields_to_check write werkt niet voor user groeps: {'company_ids': 'res.users.company_ids', 'groups_id': 'res.users.groups_id'}
