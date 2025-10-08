/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class DetachementWarningTooltip extends Component {
    static template = "hr_detachement.DetachementtWarningTooltip";
    static props = { ...standardWidgetProps };
    get tooltipInfo() {
        return JSON.stringify({
            "text" : _t("Calendar Mismatch: The employee's calendar does not match this detachement's calendar. This could lead to unexpected behaviors."),
        })
    }
}

export const detachementtWarningTooltip = {
    component: DetachementWarningTooltip,
};
registry.category("view_widgets").add("detachement_warning_tooltip", DetachementWarningTooltip);
