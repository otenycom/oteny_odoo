"""Schema-only: riverflow.state.bot_login_hold (default False).

Odoo adds the column on ``-u``. Existing rows stay False until a client
module sets the flag on its login-park states. No data rewrite here —
riverflow must not name another module's xmlids.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        "riverflow 19.0.1.1203: bot_login_hold column is ORM-owned; no row rewrite"
    )
