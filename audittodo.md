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
- ! List changes to sub-models under the log for a parent record, eg service changes listed when viewing the log of a log entry
  - create oteny_audit_ref_log to link descendant log records to their parent log record
  - create a model to merge join the audit log records with the audit log parent ref table

    ```py
    from odoo import models, fields
    from odoo.tools import sql

    class MyCustomReport(models.Model):
        """
        This model provides a read-only view of aggregated data from another model.
        """
        _name = 'my.custom.report'
        _description = 'My Custom Report'
        _auto = False  # This is crucial for a view-based model

        # Define the fields that will be available in the view
        # The field names must match the column names in the SELECT query
        tag_id = fields.Many2one('my.tag.model', string='Tag', readonly=True)
        total_quantity = fields.Integer(string='Total Quantity', readonly=True)
        
        @property
        def _table_query(self):
            """
            Defines the SELECT query for the view.
            """
            return """
                SELECT
                    tag.id as id,
                    tag.id as tag_id,
                    SUM(child.quantity) as total_quantity
                FROM
                    my_child_model AS child
                JOIN
                    my_child_model_my_tag_model_rel AS rel ON rel.my_child_model_id = child.id
                JOIN
                    my_tag_model AS tag ON tag.id = rel.my_tag_model_id
                GROUP BY
                    tag.id
            """
      ```

- ! Audit log cleaner cronjob
- Globally disable Odoo's Tracking mixin when oteny_audit is installed/active; cleans up the Chatter and saves performance and space
- List view for parent+child audit log changes in a single list
    Log Entry ABC PIETJE PUG 10/10/25 10:00:11
    Veld A van X naar Y
    Veld B van Z naar W
- highlight of grid based on transaction_id changing between rows, so each single transaction is easily recognized by the user
- audit viewer should show record name als single row (header), with the field changes below; makes the list less wide and helps visual focus
- Add support for translated fields
- Add support for company-dependent fields  
