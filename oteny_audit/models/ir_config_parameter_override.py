from odoo import models

# Words that mark a system-parameter KEY as holding a credential. The test runs on the key,
# not on the field name, because every system parameter stores its content in the same
# `value` column — `web.base.url` and `ai.anthropic_key` are the same field.
#
# Matched as WORDS, splitting the key on `.` and `_`, not as substrings. A substring test
# over-matched badly: `wilma.llm_max_tokens` (the word is `tokens`), `portal.allow_api_keys`
# (`keys`) and `auth_password_policy.minlength` all looked like credentials.
_SECRET_PARAM_KEY_WORDS = frozenset({
    "key", "token", "secret", "password", "passwd", "credential", "apikey",
})

# Keys whose word says credential but whose value is not one. Only keys measured in a real
# database go here. `auth_signup.reset_password` is a mode (`b2b` / `b2c`) and is exactly the
# security-relevant setting an auditor wants to see change; `recaptcha_public_key` is public
# by design and appears in the page source.
_NOT_SECRET_PARAM_KEYS = frozenset({
    "auth_signup.reset_password",
    "recaptcha_public_key",
})

# A credential is never a flag or a short number. Sparing those shapes costs no credential
# coverage and rescues every remaining false positive — `auth_password_policy.minlength` is
# `8`, `portal.allow_api_keys` is `True`. Eight digits is far below any credential length.
_NON_SECRET_PARAM_VALUES = frozenset({"true", "false", "0", "1", "none", ""})
_MAX_NON_SECRET_DIGITS = 8


def is_secret_param_key(key):
    """True when a system-parameter key names a credential.

    Module-level so the data scrub in `migrations/19.0.1.519/post-migrate.py` can import the
    one definition instead of restating the shape in SQL. Key-only, because the scrub reads
    stored rows whose parameter may since have been deleted.
    """
    lowered = (key or "").lower()
    if not lowered or lowered in _NOT_SECRET_PARAM_KEYS:
        return False
    words = lowered.replace(".", "_").split("_")
    return any(word in _SECRET_PARAM_KEY_WORDS for word in words)


def is_secret_param_value(value):
    """False for a value shape no credential can have — a flag, or a short number."""
    stripped = (value or "").strip()
    if stripped.lower() in _NON_SECRET_PARAM_VALUES:
        return False
    if stripped.isdigit() and len(stripped) <= _MAX_NON_SECRET_DIGITS:
        return False
    return True


class IrConfigParameter(models.Model):
    """Audit-log integration for system parameters.

    `ir.config_parameter` is audited, and must stay audited: a changed system parameter is
    exactly the kind of configuration change an audit trail exists to record. But the column
    that changes is `value`, and for a credential parameter that column IS the credential.
    On test1 on 2026-08-25 the audit log held cleartext values for `ai.anthropic_key`,
    `ai.google_key`, `iap_vies.client_token` and the three `oteny.broker_token*` keys, in
    both the update rows and the create snapshots, going back to 2026-03-02.

    A rotation is worse than a first write, because the update row keeps the OLD value beside
    the new one. So five successive `ai.google_key` rotations left five old keys behind.
    """

    _inherit = "ir.config_parameter"

    def _oteny_audit_redact_record_field(self, field_name, record):
        """Redact `value` when the record's `key` names a credential.

        `key` is this model's `_rec_name`, so it is already in cache at every audit site —
        `record_display_name` is computed from it on the same record, in the same loop. That
        is why this costs no extra query.

        `key` itself is never redacted. The restore detector
        (`base_patch._check_and_disable_on_restore`) matches on `record_display_name ==
        'database.uuid'`, and an auditor needs the parameter name to read the trail at all.

        The value shape is the second gate. It reads the record's CURRENT value, which is the
        new value on a create or a write and the doomed value on an unlink. A parameter does
        not change from a flag to a credential, so one look is enough.
        """
        if field_name != "value":
            return False
        return is_secret_param_key(record.key) and is_secret_param_value(record.value)
