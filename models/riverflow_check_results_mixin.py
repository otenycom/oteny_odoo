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
        # self.env.flush_all()
        return records

    def _refresh_check_results_on_create(self, records):
        pass

    def write(self, vals):
        result = super().write(vals)
        # important: flush the database to ensure that _write is triggered before web_save in models.py
        # captures the current record state
        # see addons/event_crm/models/event_registration.py _write()

        # self.env.flush_all()

        return result

    def write(self, vals):
        before__write_result = self._refresh_check_results_on_before__write(vals)
        result = super().write(vals)
        self._refresh_check_results_on_after__write(before__write_result)
        return result

    def _refresh_check_results_on_before__write(self, vals):
        pass

    def _refresh_check_results_on_after__write(self, before__write_result):
        pass

    def _sync_check_results(self, existing_check_results, new_check_results):
        CheckResult = self.env["riverflow.check.result"]

        to_keep = existing_check_results.filtered(
            lambda r: any(r.compare(new_result) for new_result in new_check_results)
        )
        to_create = [
            result
            for result in new_check_results
            if not any(existing.compare(result) for existing in to_keep)
        ]

        created_results = CheckResult.create(to_create)

        to_unlink = existing_check_results - to_keep
        to_unlink.unlink()  # cascade delete

        return (to_unlink.ids, created_results)

    def base_check_results(self):
        result = self.check_result_ids.filtered(
            lambda r: r.check_type in ["gap", "overlap", "reversed"]
        )
        return result

    def print_check_results(self):
        """
        Debug method to print a table of check results for this log entry.
        """
        print(f"\nCheck Results for Log Entry: {self.name}")
        print(
            "{:<10} {:<12} {:<12} {:<10} {:<50}".format(
                "Type", "Start Date", "End Date", "Severity", "Name"
            )
        )
        print("-" * 94)
        for result in self.check_result_ids:
            print(
                "{:<10} {:<12} {:<12} {:<10} {:<50}".format(
                    result.check_type,
                    (
                        result.start_date.strftime("%Y-%m-%d")
                        if result.start_date
                        else "N/A"
                    ),
                    result.end_date.strftime("%Y-%m-%d") if result.end_date else "N/A",
                    result.severity,
                    (
                        result.name[:47] + "..."
                        if len(result.name) > 50
                        else result.name
                    ),
                )
            )
        print()
