# Todo list for oteny_audit

- [x] basic testers and views for oteny_audit
- [~] make an action record for all models to view their log via their Action menu
  - [x] Audit | Configuration | Install command
  - [ ] hook to do this automatically on install/remove of modules
  - [ ] v2: also inject a panel in form views that have chatter or a notebook for immediate access to log. Action menu is not too bad so maybe leave it
- [x] writes recorded MANY Times? (did_fly_from_home)
- [x] check results: ignore
- [x] import from excel: disable logging during import using context ignore audit logging flag
  - [ ] some writes during import are still logged, some call method flows clear the context apparenty, not a big deal
- [x] generated entries, state records: ignore audit logging using context flag
- [x] manu2many support: fields_to_check write werkt niet voor user groeps: {'company_ids': 'res.users.company_ids', 'groups_id': 'res.users.groups_id'}
- [~] List changes to sub-models under the log for a parent record, eg service changes listed when viewing the log of a log entry
  - [x] create oteny_audit_parent_ref to link descendant log records to their parent log record
  - [x] create a model to merge join the audit log records with the audit log parent ref table
    - [ ] mem leak check: Cleanup all fields we stuffed in the cr if the tx changes; store the tx id in the cr as well (only needed if cr is pooled)
    - [~] when inserting a log entry, some updates done after the insert are shown before the insert in the log, see if we can fix; fixed by ordering on create_date of the audit log record?
    - [~] the aggregated view does not show the primary record name; this is an issue if you view the log for multiple records from the list
    - [ ] Add more parent_field_names to other models, currently:
        [x] service.log_entry_id (or better via res_model,res_id)
        [ ] mail.message via res_model,res_id
        [ ] service travel leg (to service, which should recursively log to entry)
    - Computed fields seem to be logged for services when we change the state/date for a parent log entry (end_date_for_calendar,project_deadline)
      - they probably have an inverse so it makes sense to log them so the change can be accont for between users and computed changes
    - Top 3 External Messages: for services not logged, but Top 3 Internal messages is actually logged for Entries. why?

- ! Audit log cleaner cronjob
- Globally disable Odoo's Tracking mixin when oteny_audit is installed/active; cleans up the Chatter and saves performance and space
- List view for parent+child audit log changes in a single list
    Log Entry ABC PIETJE PUG 10/10/25 10:00:11
    Veld A van X naar Y
    Veld B van Z naar W
- [x] highlight_row of grid based on transaction_id changing between rows, so each single transaction is easily recognized by the user
- audit viewer should show record name als single row (header), with the field changes below; makes the list less wide and helps visual focus
- Add support for translated fields
- Add support for company-dependent fields  
