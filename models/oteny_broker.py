"""Shared Oteny cloud-browser broker client (login-handoff, live-watch, replay).

One AbstractModel so Bot Activity (Watch/Replay) and domain wizards (MFNL login)
share the same fenced POST helper. Tokens are purpose-scoped on the public lane
(``otci_``); a dog-food ``otmt_`` in ``oteny.broker_token`` still works against a
tailnet broker base URL. Bearer URLs returned by the broker are ephemeral (R3) —
callers open them and must never persist them.
"""

from odoo import _, models
from odoo.exceptions import UserError

try:
    import requests
except ImportError:  # pragma: no cover — Odoo runtime always has requests
    requests = None

BASE_PARAM = "oteny.broker_base_url"
# Default / login-gate token. Live-watch and replay-view prefer their dedicated
# params and fall back to this for dog-food (otmt_ over the tailnet).
TOKEN_PARAM = "oteny.broker_token"
TOKEN_LIVE_WATCH_PARAM = "oteny.broker_token_live_watch"
TOKEN_REPLAY_VIEW_PARAM = "oteny.broker_token_replay_view"

_PURPOSE_TOKEN_PARAMS = {
    "login-gate": TOKEN_PARAM,
    "live-watch": TOKEN_LIVE_WATCH_PARAM,
    "replay-view": TOKEN_REPLAY_VIEW_PARAM,
}


class OtenyBrokerClient(models.AbstractModel):
    _name = "oteny.broker.client"
    _description = "Oteny Cloud-Browser Broker Client"

    def _broker_token(self, purpose=None):
        """Resolve the bearer for ``purpose``. Dedicated purpose params win.

        Dog-food fall-back to ``oteny.broker_token`` is only for a metering
        ``otmt_`` token (tailnet broker). A purpose-scoped ``otci_`` login-gate
        token must never be reused for live-watch / replay-view — that yields
        401 ``unknown or inactive token`` while the chip still said Replay was
        available."""
        icp = self.env["ir.config_parameter"].sudo()
        if purpose:
            dedicated = _PURPOSE_TOKEN_PARAMS.get(purpose)
            if dedicated:
                tok = (icp.get_param(dedicated) or "").strip()
                if tok:
                    return tok
            # login-gate's dedicated slot IS TOKEN_PARAM (already checked above).
            if purpose == "login-gate":
                return ""
            fallback = (icp.get_param(TOKEN_PARAM) or "").strip()
            if fallback.startswith("otmt_"):
                return fallback
            return ""
        return (icp.get_param(TOKEN_PARAM) or "").strip()

    def _broker_purpose_configured(self, purpose):
        """True when a mint for ``purpose`` has a usable bearer (honest UI gate)."""
        return bool(self._broker_token(purpose))

    def _broker_post(self, path, payload=None, *, purpose=None):
        """POST to the Oteny cloud-browser broker. Fenced on base URL + token
        (unset → a clear error, so nothing calls out off-prod). The token is used
        in the header only — never logged; broker errors carry no bearer URL."""
        if requests is None:
            raise UserError(_("The requests library is not available in this Odoo."))
        icp = self.env["ir.config_parameter"].sudo()
        base = (icp.get_param(BASE_PARAM) or "").rstrip("/")
        token = self._broker_token(purpose)
        if not base or not token:
            purpose_hint = {
                "live-watch": _("oteny.broker_token_live_watch"),
                "replay-view": _("oteny.broker_token_replay_view"),
            }.get(purpose) or _("oteny.broker_token")
            raise UserError(_(
                "The Oteny cloud-browser broker is not configured on this environment "
                "(%(base)s / %(token)s). Ask an administrator to wire the broker seam.",
                base=_("oteny.broker_base_url"),
                token=purpose_hint,
            ))
        try:
            resp = requests.post(
                f"{base}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=payload or {},
                # login-handoff landing may retry Steel CDP 503s for ~28 s
                # (plus create); 30 s was cutting the mint off mid-retry.
                timeout=45,
            )
            if not resp.ok:
                detail = ""
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                if isinstance(body, dict):
                    detail = (
                        body.get("message")
                        or body.get("error")
                        or ""
                    )
                    if body.get("error") == "bad_login_url":
                        detail += _(
                            " — fix the CrewRadar system parameter "
                            "oteny.portal_login_url"
                        )
                    elif body.get("error") == "login_page_unreachable":
                        detail = detail or _(
                            "Could not open the portal sign-in page — "
                            "click Open login browser again."
                        )
                if not detail and (resp.text or "").strip():
                    detail = (resp.text or "").strip()[:200]
                raise UserError(_(
                    "The Oteny cloud-browser broker refused the request (%(status)s): "
                    "%(detail)s",
                    status=resp.status_code,
                    detail=detail or _("no detail"),
                ))
            return resp.json()
        except requests.RequestException as exc:
            raise UserError(
                _("Could not reach the Oteny cloud-browser broker: %s") % exc
            )
