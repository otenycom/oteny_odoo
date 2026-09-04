/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { FileInput } from "@web/core/file_input/file_input";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Many2ManyBinaryField } from "@web/views/fields/many2many_binary/many2many_binary_field";
import { status } from "@odoo/owl";

// Why this exists:
// A ``many2many_binary`` upload runs in two halves. The FileInput posts the
// file to ``/web/binary/upload_attachment`` through the unprotected ``http``
// service, and only when the response is back does the field link the new
// attachment to the record through the form controller's ORM. That ORM is
// protected: once the controller is destroyed, every call rejects with
// "Component is destroyed". So a wizard dialog that closes while an upload is
// still in flight (the user clicks OK, Send or Escape before the file tile
// appears, or a route change replaces the dialog) crashes with an "Odoo Client
// Error" popup when the response lands, and the file is silently lost. Key
// users hit this on 2026-06-16 (single credential upload), 2026-07-09
// (service email sender) and 2026-09-04 (Document Import).
//
// Two layers, both generic to every ``many2many_binary`` field:
//
//   1. Prevention: the upload blocks the UI from the file pick until the
//      attachment is linked. The BlockUI overlay stops clicks, and the hotkey
//      service ignores Escape and Ctrl+Enter while blocked, so the dialog can
//      no longer be closed under the upload by a user gesture.
//   2. Containment: when the dialog was destroyed anyway (a route change, a
//      second action replacing it), the late upload is reported with a warning
//      notification instead of crashing, and nothing touches the dead record.

// The FileInput that ``Many2ManyBinaryField`` renders. It mirrors the core
// ``onFileInputChange`` with three differences: the UI is blocked while the
// upload is in flight, the ``onUpload`` callback is awaited so the block also
// covers the record link, and a destroyed component writes to no DOM ref.
export class BlockingUploadFileInput extends FileInput {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async onFileInputChange() {
        this.state.isDisable = true;
        this.ui.block();
        try {
            const httpParams = this.httpParams;
            if (this.props.onWillUploadFiles) {
                httpParams.ufile = await this.props.onWillUploadFiles(httpParams.ufile);
            }
            const parsedFileData = await this.uploadFiles(this.props.route, httpParams);
            if (parsedFileData) {
                const input = this.fileInputRef.el;
                await this.props.onUpload(parsedFileData, input ? input.files : []);
                // The input would not fire change again for the same file name,
                // so clear it after the upload is handled (when it still exists).
                if (input) {
                    input.value = null;
                }
            }
        } finally {
            this.ui.unblock();
            this.state.isDisable = false;
        }
    }
}

Many2ManyBinaryField.components = {
    ...Many2ManyBinaryField.components,
    FileInput: BlockingUploadFileInput,
};

patch(Many2ManyBinaryField.prototype, {
    async onFileUploaded(files) {
        if (status(this) === "destroyed") {
            // The dialog that owned this field is gone; its record cannot be
            // linked any more. Tell the user which file was lost instead of
            // raising "Component is destroyed" through the dead controller.
            const names = files
                .map((file) => file.filename)
                .filter(Boolean)
                .join(", ");
            this.notification.add(
                _t(
                    "The window closed before the upload of %s finished, so the file was not attached. Open the window again and attach the file once more.",
                    names
                ),
                { type: "warning", sticky: true }
            );
            return;
        }
        return super.onFileUploaded(...arguments);
    },
});
