"""riverflow's seed data names no business: the one team row a business seeded here
moves to that business's module before this update, so the update does not
delete it as an orphan of riverflow's data. The business's module declares the
same record under its own xmlid from now on."""


def migrate(cr, version):
    cr.execute(
        "UPDATE ir_model_data SET module = %s WHERE module = 'riverflow' AND name = %s",
        ("crewradar", "team_cuneus_yangon"),  # customer-template: allow
    )
