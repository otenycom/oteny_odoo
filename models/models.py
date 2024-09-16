from odoo import api, models, tools, _
from typing import Dict, List

import logging

_logger = logging.getLogger(__name__)

"""

class BaseModel(models.AbstractModel):
    _inherit = "base"

    def web_save(
        self, vals, specification: Dict[str, Dict], next_id=None
    ) -> List[Dict]:
        if self:
            self.write(vals)
        else:
            self = self.create(vals)
        if next_id:
            self = self.browse(next_id)

        # HACK: Workaround for client not receiving updates on check results after create/write
        # TODO: fix in code so that web_read sees invalidated fields and does the recompute 
        # .... See also riverflow_check_results_mixin.py _write()
        self.env.flush_all()

        return self.with_context(bin_size=True).web_read(specification)
"""
