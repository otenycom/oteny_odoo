import { utils, SIZES } from "@web/core/ui/ui_service";
import { cookie } from "@web/core/browser/cookie";

// Force chatter to be always at the bottom
const orgUtilsGetSize = utils.getSize;
utils.getSize = () => {
    let size = orgUtilsGetSize();
    if (size > SIZES.XL) size = SIZES.XL;
    return size;
};

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