import { utils, SIZES } from "@web/core/ui/ui_service";

// Force chatter to be always at the bottom
const orgUtilsGetSize = utils.getSize;
utils.getSize = () => {
    let size = orgUtilsGetSize();
    if (size > SIZES.XL) size = SIZES.XL;
    return size;
};