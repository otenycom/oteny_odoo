from odoo import api, models


class CheckResultsMixin(models.AbstractModel):
    _name = "riverflow.check.results.mixin"
    _description = "Check Results Mixin"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._refresh_check_results_on_create(records)
        # important: flush the database to ensure that _write is triggered before web_save in models.py
        # captures the current record state
        self.env.flush_all()
        return records

    def _refresh_check_results_on_create(self, records):
        pass

    def write(self, vals):
        result = super().write(vals)
        # important: flush the database to ensure that _write is triggered before web_save in models.py
        # captures the current record state
        # see addons/event_crm/models/event_registration.py _write()
        self.env.flush_all()
        return result

    def _write(self, vals):
        before__write_result = self._refresh_check_results_on_before__write(vals)
        result = super()._write(vals)
        self._refresh_check_results_on_after__write(before__write_result)
        return result

    def _refresh_check_results_on_before__write(self, vals):
        pass

    def _refresh_check_results_on_after__write(self, before__write_result):
        pass
