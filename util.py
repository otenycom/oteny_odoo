# -*- coding: utf-8 -*-

from odoo.http import request
import ipaddress


def is_neutralized_or_development():
    """
    Returns true if the current database is neutralized or if the request is coming from localhost.
    """
    if not request:
        return False

    # only true if the script to neutralize the database was run,
    # not true if Db was created from blank during development
    is_neutralized = (
        request.env["ir.config_parameter"]
        .sudo()
        .get_param("database.is_neutralized", False)
    )

    # Check if the request is coming from local net (normally only in a development environment)
    is_development_network = ipaddress.ip_address(
        request.httprequest.remote_addr
    ).is_private

    return is_neutralized or is_development_network
