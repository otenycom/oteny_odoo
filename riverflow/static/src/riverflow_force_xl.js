import { cookie } from "@web/core/browser/cookie";

// The XL size cap below was used to force the chatter to always render below
// the form sheet instead of beside it. Commented out because it also prevents
// the o_attachment_preview sidebar (PDF/image preview) from rendering — that
// component only activates at the XXL breakpoint (>= 1400px). With the cap
// removed, wide screens get the standard Odoo XXL layout: chatter beside the
// form on regular forms, or attachment preview beside the form + chatter below
// on forms with o_attachment_preview (e.g. credentials, invoices).
//
// import { utils, SIZES } from "@web/core/ui/ui_service";
// const orgUtilsGetSize = utils.getSize;
// utils.getSize = () => {
//     let size = orgUtilsGetSize();
//     if (size > SIZES.XL) size = SIZES.XL;
//     return size;
// };

// --- HACK to set default companies on first load ---
// On initial load, this checks if the 'cids' cookie is present.
// If not, it sets a hardcoded list of company IDs.
if (!cookie.get("cids")) {
    // Note: Company IDs in Odoo usually start from 1. The ID 0 may be ignored by Odoo.
    const hardcodedCompanyIds = Array.from({ length: 3 }, (_, i) => i + 1).join("-"); // "1-2-3"

    // The cookie is set for a year, which is the default for Odoo's cookie utility.
    // The company service will pick this up when the application starts.
    cookie.set("cids", hardcodedCompanyIds);
}