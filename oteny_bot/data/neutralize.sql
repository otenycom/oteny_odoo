-- Disconnect Barney (and any other Oteny business bot) from a restored copy.
-- Odoo runs every installed module's data/neutralize.sql on neutralize; this
-- clears the broker seam and unbinds uplink_ref so a staging/local copy can
-- never keep talking to a production bot or mint login sessions as one.
-- Keep discuss_channel_id + bot_user_id — ensure_bot reuses that seeded shape
-- on the next provision instead of forking a second bot row.
DELETE FROM ir_config_parameter
 WHERE key IN (
       'oteny.broker_base_url',
       'oteny.broker_token',
       'oteny.broker_token_live_watch',
       'oteny.broker_token_replay_view',
       'oteny.portal_login_url',
       'posted_workers_nl_url'
);

UPDATE oteny_bot
   SET uplink_ref = NULL,
       login_dance_until = NULL,
       login_dance_user_id = NULL,
       login_dance_token = NULL;
