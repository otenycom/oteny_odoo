from odoo import models, fields, api, _, Command
from datetime import timedelta, date
from odoo.exceptions import UserError


class Service(models.Model):
    _name = "riverflow.service"
    # no activities 'mail.activity.mixin', we use workflow buttons instead.
    _inherit = [
        # "mail.thread",
        "riverflow.mail.thread.review.mixin",
        "riverflow.state.mixin",
        "riverflow.state.record.tracker.mixin",
    ]
    _description = "Service"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "display_name"  # ensure default search is on display_name.
    # Services are a recursive tree, and in order to show the tree correctly in the flat
    # list view, we assign a sequence numer for all child services. For performance, we don't
    # set the sequence field to all services on any service update, so the root services are not sorted
    # by sequence, but by name.
    _order = "root_name,root_id,sequence"

    DATE_FORMAT = "%d-%b-%y"  # 01-Jan-21

    # auto calculated by Odoo in the form of parent_id/parent_id/self_id/
    # see def _get_domain_locations(self)
    parent_path = fields.Char(index="btree")
    indent_level = fields.Integer("Indent level", compute="_compute_indent_level", store=True, recursive=True)
    parent_id = fields.Many2one("riverflow.service", string="Parent Service", index=True, ondelete="cascade")
    child_ids = fields.One2many("riverflow.service", "parent_id", string="Child Services")
    descendant_ids = fields.One2many(
        "riverflow.service",
        "parent_id",
        string="Descendant Services",
        compute="_compute_descendant_ids",
        store=False,
    )
    created_by_auto_add_service_id = fields.Many2one(
        "riverflow.auto.add.service",
        string="Created by Auto Add Rule",
        help="The auto add rule that created this service. The system can use this to determine if the rule that created the service is still applicable.",
    )

    is_this_a_template = fields.Boolean(
        string="Is This a Template",
        default=False,
        help="Applies to Top-level services only. If checked, this service and its descendants will be used as a template for creating new services",
    )
    is_root_a_template = fields.Boolean(
        string="Is Root a Template",
        compute="_compute_is_root_a_template",
        store=True,
        help="Technical so we always treat the full tree of a service as a template, even if the children are not flagged astemplates themselves",
    )
    email_template_id = fields.Many2one(
        "mail.template",
        string="Email Template",
        domain="[('model_id', '=', 'riverflow.service')]",
        help="The Send Email workflow transition uses this email template. "
        "Templates can be created in Odoo's Email Templates module.",
    )

    # todo: add to rivermen module
    add_operator_as_recipient = fields.Boolean(
        string="Send to operator",
        default=False,
        help="The recipients for the email can also be set by adding followers to the chatter",
    )

    root_id = fields.Many2one("riverflow.service", compute="_compute_root_id", store=True, recursive=True)
    root_name = fields.Char(
        "Top-level service name",
        compute="_compute_root_name",
        help="Name of the top-level service, for sorting the list of services",
        store=True,
        index=True,
        recursive=True,
    )
    name = fields.Char("Service Name", index="trigram", required=True, tracking=True)
    indented_name = fields.Char("Service", compute="_compute_indented_name", store=False, recursive=True)
    display_name = fields.Char(
        "Display Name",
        compute="_compute_display_name",
        store=True,
        index="trigram",
        recursive=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        compute="_compute_company_id",
        inverse="_inverse_company_id",
        recursive=True,
        store=True,
        required=False,
        index=True,
        tracking=True,
    )

    active = fields.Boolean(
        compute="_compute_active",
        inverse="_inverse_active",
        store=True,
        default=True,
        help="Set active to false to archive the service",
        tracking=True,
    )

    days_relative_to_project = fields.Integer(
        "Day",
        help="Number of days before or after the project deadline for this service to be completed, e.g. -1 for the day before",
        required=False,
        tracking=True,
    )

    use_project_deadline_from = fields.Selection(
        [
            ("self", "Self"),
            ("root", "Top-level service"),
        ],
        string="Deadline From",
        required=True,
        tracking=True,
        default="self",
    )

    use_project_deadline_from_options = fields.Json(compute="_compute_use_project_deadline_from_options")

    is_days_relative_to_project_applicable = fields.Boolean(
        "Use relative days",
        compute="_compute_is_days_relative_to_project_applicable",
        help="Whether this service should use relative days to calculate its deadline",
        store=True,
    )

    # This field is either set manually (if use_project_deadline_from is set to 'self')
    # or it is set to the project_deadline of the root service, or some other related entity in an inherited class
    project_deadline = fields.Date(
        "Project deadline",
        help="The services are timed relative to this deadline",
        tracking=True,
        compute="_compute_project_deadline",
        inverse="_inverse_project_deadline",
        store=True,
        recursive=True,
    )
    root_service_deadline = fields.Date(
        "Top-level service deadline",
        related="root_id.deadline",
        help="Deadline of the top-level parent of this service",
        store=False,
        index=True,
        recursive=True,
    )
    deadline = fields.Date(
        "Deadline Date",
        compute="_compute_deadline",
        help="Deadline based on the project-deadline and the relative day of this service",
        store=True,
        index=True,
        recursive=True,
    )
    deadline_formatted = fields.Char("Deadline", compute="_compute_deadline_formatted", store=False)
    timing_json = fields.Json(
        "Timing",
        compute="_compute_timing_json",
        store=False,
        recursive=True,
    )
    sequence = fields.Integer(
        default=1,
        compute="_compute_sequence",
        index=True,
        required=True,
        store=True,
        recursive=True,
    )

    tag_ids = fields.Many2many(
        "riverflow.service.tag",
        "riverflow_service_tag_rel",
        "service_id",
        "tag_id",
        "Tags",
        tracking=True,
        copy=True,
        ondelete="cascade",
    )

    workflow_name_html = fields.Html(
        "Workflow Name",
        related="workflow_id.icon_name_html",
        help="Combination of Icon and name",
        store=False,
    )

    # the container of the service (log_entry, employee, etc)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_id_computed = fields.Integer(
        "Computed Service Subject ID",
        compute="_compute_res_id_computed",
        store=False,
        recursive=True,
        help="Syncs the service's subject reference (ref_id) with the Top-level service. All decendending services reference the same subject.",
    )
    res_name = fields.Char(
        string="Subject of Service",
        compute="_compute_res_name",
        store=True,
        index="trigram",
    )

    # related entity (similar to the one in the mail_message.py in odoo)
    # content fields such as display_name of the related document can be looked
    # up in the riverflow.state.record model
    @api.model
    def _selection_target_model(self):
        return [(model.model, model.name) for model in self.env["ir.model"].sudo().search([])]

    resource_ref = fields.Reference(
        string="Subject Reference",
        selection="_selection_target_model",
        compute="_compute_resource_ref",
        inverse="_set_resource_ref",
    )

    subject_active = fields.Boolean(
        string="Subject Active",
        compute="_compute_subject_active",
        store=True,
        help="Technical field to track if the subject record is active",
    )

    # we take this flag from the workflow, computed field
    is_supply_order = fields.Boolean(
        "Is Supply Order",
        help="Enables data entry for supply order details, such as supplier and supply date. For example, a Taxi Order. This flag is taken from the workflow.",
        required=False,
        tracking=True,
        compute="_compute_is_supply_order",
        store=True,
    )

    has_supplier = fields.Boolean(
        "Has Supplier",
        related="front_office_workflow_id.has_supplier",
        store=True,
    )

    has_legs = fields.Boolean(
        "Has Legs",
        related="front_office_workflow_id.has_legs",
        store=True,
    )

    has_supply_unit_price = fields.Boolean(
        "Has Cost Price",
        related="front_office_workflow_id.has_supply_unit_price",
        store=True,
    )

    supply_unit_price = fields.Monetary("Cost", currency_field="supply_unit_price_currency_id", tracking=True)
    supply_unit_price_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Cost Currency",
        related="company_id.currency_id",
        store=True,
    )

    supplier_partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        help="The partner that is supplying the service",
        required=False,
        tracking=True,
    )

    supply_order_instructions = fields.Text(
        "Instructions for the supplier",
        help="E.g. what to supply, extra information, etc",
        required=False,
        tracking=True,
    )

    leg_ids = fields.One2many(
        "riverflow.service.leg",
        "service_id",
        string="Supply Legs",
        help="The legs of a trip booked using a supply order",
    )

    supply_leg_id = fields.Many2one(
        "riverflow.service.leg",
        "Supply Order Leg",
        readonly=True,
        help="Links back to the 'taxi booking' leg that generated this leg-info service",
    )

    supply_order_service_id = fields.Many2one(
        "riverflow.service",
        "Supply Order",
        related="supply_leg_id.service_id",
        readonly=True,
        recursive=True,
        help="Links back to the 'taxi booking' that generated this leg-info service",
    )

    @api.depends("res_model", "res_id")
    def _compute_resource_ref(self):
        for service in self:
            if not service.res_model or not service.res_id:
                service.resource_ref = False
            else:
                service.resource_ref = "%s,%s" % (
                    service.res_model,
                    service.res_id,
                )

    def _set_resource_ref(self):
        for service in self:
            if service.resource_ref:
                service.res_id = service.resource_ref.id
                service.res_model = service.resource_ref.model
            else:
                service.res_id = False
                service.res_model = False

    @api.depends("root_id.res_id", "root_id.res_model")
    def _compute_res_id_computed(self):
        for service in self:
            service.res_id_computed = service.root_id.res_id

            isRootService = service.id == service.root_id.id
            if not isRootService:
                service.res_id = service.root_id.res_id
                service.res_model = service.root_id.res_model

    @api.depends("front_office_workflow_id.is_supply_order")
    def _compute_is_supply_order(self):
        for service in self:
            service.is_supply_order = service.front_office_workflow_id.is_supply_order

    # inheriting classes can override this method to add their own dependencies, "resource_ref.display_name"
    @api.depends("res_model", "res_id")
    def _compute_res_name(self):
        for service in self:
            if not service.res_id or not service.res_model:
                service.res_name = False
                continue
            if service.res_model not in self.env:
                # Skip if the container model is not yet loaded in the environment
                #  (during upgrades of the module, when the container is a module dependent on riverflow)
                continue
            record = self.env[service.res_model].sudo().browse(service.res_id)
            if not record.exists():
                service.res_name = False
                continue
            name = record.display_name
            service.res_name = name if name else f"{service.res_model}/{service.res_id}"

    @api.depends("root_id", "root_id.name", "name", "deadline")
    def _compute_root_name(self):
        for service in self:
            root_service = service.root_id
            sortable_deadline = (
                root_service.deadline.strftime("%Y-%m-%d") if root_service.deadline else "2000-01-01"
            )
            service.root_name = f"{sortable_deadline} {root_service.name}"

    @api.depends("parent_path")
    def _compute_root_id(self):
        for service in self.sudo():
            try:
                if service.parent_path:
                    path_parts = service.parent_path.split("/")
                    # Assign the first part of the path as the root_id
                    service.root_id = int(path_parts[0])
                else:
                    # If parent_path is empty, use the service's own ID
                    service.root_id = service.id
            except ValueError:
                # Handle the case where conversion to int fails
                service.root_id = service.id  # Or handle as appropriate

    @api.depends(
        "name",
        "parent_id.display_name",
        "supply_leg_id.name",
        "supply_leg_id.service_id.name",
    )
    def _compute_display_name(self):
        for service in self.sudo():
            if service.supply_leg_id:
                name = service.supply_leg_id.name
                if not service.parent_id:
                    name = f"{service.supply_leg_id.service_id.name} | {name}"
                service.name = name

            if service.parent_id:
                service.display_name = "%s | %s" % (
                    service.parent_id.display_name,
                    service.name,
                )
            else:
                service.display_name = service.name

            # service.display_name = ' | '.join(
            #     [service.display_name, self.compute_display_name_suffix(service)])

    @api.depends("child_ids")
    def _compute_descendant_ids(self):
        for service in self:
            descendants = self.env["riverflow.service"].search(
                [
                    ("parent_path", "=like", f"{service.parent_path}%"),
                    ("id", "!=", service.id),
                ],
                order="root_name,root_id,sequence",
            )
            service.descendant_ids = descendants

    @api.depends("parent_path")
    def _compute_indent_level(self):
        for service in self.sudo():
            if service.parent_path:
                # Count the number of slashes in parent_path, subtract 1 for indent level
                service.indent_level = service.parent_path.count("/") - 1
            else:
                service.indent_level = 0

    def _compute_indented_name(self):
        for service in self.sudo():
            service.indented_name = "%s%s" % (
                "\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}"
                * service.indent_level,
                service.name,
            )

    @api.depends(
        "use_project_deadline_from",
        "root_id.deadline",
        "root_id",
        "supply_order_service_id.deadline",
    )
    def _compute_project_deadline(self):
        for service in self:
            if service.supply_order_service_id:
                service.use_project_deadline_from = "self"
                service.project_deadline = service.supply_order_service_id.deadline
            else:
                use_project_deadline_from = service.use_project_deadline_from
                if use_project_deadline_from == "self":
                    service.project_deadline = service.project_deadline
                elif use_project_deadline_from == "root":
                    service.project_deadline = service.root_id.deadline

    def _inverse_project_deadline(self):
        # this is a flag method specifying the user is allowed to store the project_deadline
        pass

    @api.depends("use_project_deadline_from", "root_id")
    def _compute_is_days_relative_to_project_applicable(self):
        for service in self:
            service.is_days_relative_to_project_applicable = (
                service.use_project_deadline_from != "self"
                and not (service.use_project_deadline_from == "root" and service.root_id.ids == service.ids)
            )

    @api.depends(
        "project_deadline",
        "days_relative_to_project",
        "use_project_deadline_from",
        "is_days_relative_to_project_applicable",
        "supply_order_service_id.deadline",
    )
    def _compute_deadline(self):
        for service in self:
            if not service.project_deadline:
                service.deadline = False
            elif service.is_days_relative_to_project_applicable:
                service.deadline = self.project_deadline + timedelta(days=service.days_relative_to_project)
            else:
                service.deadline = service.project_deadline

    @api.depends("deadline")
    def _compute_timing_json(self):
        for service in self:
            relative_days = ""
            if service.is_days_relative_to_project_applicable:
                relative_days = f"{self.relative_to_project_days_prefix()} {'+' if service.days_relative_to_project >= 0 else '-'} {abs(service.days_relative_to_project)}d"

            if not service.deadline:
                date_str = ""
                days_remaining = ""
                is_past = False
                is_today = False
            else:
                today = fields.Date.today()
                days_remaining = (service.deadline - today).days
                date_str = service.deadline.strftime(Service.DATE_FORMAT)

                is_past = service.deadline < today
                is_today = service.deadline == today

            service.timing_json = {
                "relative_days": relative_days,
                "date": date_str,
                "days_remaining": days_remaining,
                "is_past": is_past,
                "is_today": is_today,
                "is_end_state": service.is_end_state,
            }

    def relative_to_project_days_prefix(self):
        if self.use_project_deadline_from == "self":
            return ""
        elif self.use_project_deadline_from == "root":
            return f"Top-level service"
        else:
            return "(unknown: use_project_deadline_from)"

    @api.depends("deadline")
    def _compute_deadline_formatted(self):
        for service in self:
            if service.deadline == False:
                service.deadline_formatted = ""
            else:
                service.deadline_formatted = service.deadline.strftime(Service.DATE_FORMAT)

    def print_compute_sequence_counter(self):
        pass
        # if not hasattr(self.__class__, "_compute_sequence_counter"):
        #     self.__class__._compute_sequence_counter = 0
        # print(
        #     f"_compute_sequence counter: {self.__class__._compute_sequence_counter} - {self.display_name} - id: {self.id} - entry: {self.res_id}"
        # )
        # self.__class__._compute_sequence_counter += 1

    @api.depends(
        "parent_id",
        "root_name",
        "deadline",
    )
    def _compute_sequence(self):
        # if self.env.context.get("computing_sequence"):
        #     return

        if any(isinstance(record.id, models.NewId) for record in self):
            return

        Service = self.env["riverflow.service"].with_context(active_test=False).sudo()

        for record in self:

            # record.print_compute_sequence_counter()

            # self = self.with_context(computing_sequence=True)
            # try:

            # Retrieve all service records with the same root_id as the current record
            # we only set the sequence field of child nodes, the root nodes are sorted
            # by name; as it would become very slow to sequence the entire list of services

            # we use direct sql to avoid recalculation of root_id, which means 'search' would decide
            # to recursively recalculate all records in the table, this overflows the stack
            self.env.cr.execute(
                """
                    SELECT id FROM riverflow_service
                    WHERE root_id = %s AND id != %s
                    """,
                (record.root_id.id, record.id),
            )
            service_ids = [row[0] for row in self.env.cr.fetchall()]
            services = set(Service.browse(service_ids))
            # current record is not included in the search as it can lead to recursive stack overflow
            # as search also recalculates the sequence field
            services.add(record)
            # finally:
            #     self = self.with_context(computing_sequence=False)

            # Dictionary to map service IDs to their corresponding service objects
            service_dict = {service.id: service for service in services}

            # Dictionary to hold the tree structure of services
            service_tree = {}
            # Build the tree structure
            for service in services:
                # Determine the parent ID of the current service
                parent_id = service.parent_id.id if service.parent_id else None

                # Initialize the parent node list if it doesn't exist
                if parent_id not in service_tree:
                    service_tree[parent_id] = []

                # Add the current service to its parent's list of children
                service_tree[parent_id].append(service.id)

            # Initialize the sequence counter
            sequence = 0

            def assign_sequence(service_id, visited):
                nonlocal sequence  # Use the nonlocal keyword to modify the outer scope 'sequence' variable

                # Check for circular references in the hierarchy
                if service_id in visited:
                    raise ValueError(
                        f"Circular reference detected in service hierarchy involving service ID {service_id}"
                    )

                # Add the current service ID to the set of visited nodes
                visited.add(service_id)

                # Retrieve the service object using its ID
                service = service_dict[service_id]

                # Assign the current sequence number to the service
                service.sequence = sequence

                # Increment the sequence number for the next service
                sequence += 1

                if service_id in service_tree:
                    children_ids = service_tree[service_id]
                    # Sort children based on `deadline`, then `name`, then `id`
                    sorted_children_ids = sorted(
                        children_ids,
                        key=lambda child_id: (
                            service_dict[child_id].deadline or date.max,
                            service_dict[child_id].name,
                            service_dict[child_id].id,
                        ),
                    )
                    for child_id in sorted_children_ids:
                        assign_sequence(child_id, visited)

            # Assign sequence numbers to root services (those without parents) and their children
            if None in service_tree:
                visited = set()

                # Sort the root services by `name`, then `id`
                root_ids = sorted(
                    service_tree[None],
                    key=lambda root_id: (
                        service_dict[root_id].name,
                        service_dict[root_id].id,
                    ),
                )
                for root_id in root_ids:
                    assign_sequence(root_id, visited)

    def action_view_parent_service(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "riverflow.service",
            "res_id": self.parent_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def add_child_service(self):
        # Select a start transition for a new service. Can be overridden by child modules
        # to set more default field values
        return {
            "type": "ir.actions.act_window",
            "name": "Add Service to: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.start.service",
            "context": {
                "default_parent_id": self.id,
                "default_company_id": self.company_id.id,
                "default_use_project_deadline_from": "self",
                "default_res_model": self.res_model,
                "default_res_id": self.res_id,
            },
            "target": "new",
        }

    @api.onchange("parent_id")
    def _onchange_parent_id(self):
        if self.parent_id:
            self.res_model = self.parent_id.res_model
            self.res_id = self.parent_id.res_id

    @api.model_create_multi
    def create(self, vals_list):
        # current user is not subscribed to the chatter, because we have the radar-view, the review-count and top-3 external messages
        # this way, a team can keep track of the external messages instead of a single user
        records = super(
            Service,
            self.with_context(
                **{
                    "mail_create_nosubscribe": True,  # At create or message_post, do not subscribe the current user to the record thread
                    "mail_auto_subscribe_no_notify": True,  # Do no notify users set as followers of the mail thread
                }
            ),
        ).create(vals_list)
        for record in records:
            if record.parent_id and not record.res_id:
                record.res_id = record.parent_id.res_id
                record.res_model = record.parent_id.res_model
            elif not record.parent_id and record.res_model == self._name and record.res_id:
                # for auto-adding a child service, they set the parent via res_id
                # Invalidate the recordset to ensure fresh data
                record.parent_id = record.res_id
                record.root_id = record.parent_id.root_id
                record.res_model = record.parent_id.res_model
                record.res_id = record.parent_id.res_id
                # recalculate the parent_id dependent fields
                record.invalidate_recordset(["parent_id", "parent_path", "root_id", "res_model", "res_id"])
                record.parent_id.invalidate_recordset(["child_ids"])
        return records

    def write(self, vals):
        result = super(Service, self).write(vals)
        if "parent_id" in vals:
            for record in self:
                if record.parent_id and not record.res_id:
                    record.res_id = record.parent_id.res_id
                    record.res_model = record.parent_id.res_model
        elif "res_model" in vals and "res_id" in vals:
            for record in self:
                if record.res_model == self._name:
                    record.parent_id = record.res_id
                    record.root_id = record.parent_id.root_id
                    record.res_model = record.parent_id.res_model
                    record.res_id = record.parent_id.res_id
                    record.invalidate_recordset(
                        ["parent_id", "parent_path", "root_id", "res_model", "res_id"]
                    )
                    record.parent_id.invalidate_recordset(["child_ids"])

        return result

    @api.depends("root_id.is_this_a_template", "is_this_a_template")
    def _compute_is_root_a_template(self):
        for service in self:
            service.is_root_a_template = bool(service.root_id.is_this_a_template)

    def _get_default_recipients(self):
        """Get default recipients for email templates based on active followers who receive comments"""
        self.ensure_one()
        # Get followers with comment notification enabled (mail.mt_comment)
        comment_subtype_id = self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_comment")
        recipients = self.message_follower_ids.filtered(
            lambda f: (f.partner_id and f.partner_id.active and comment_subtype_id in f.subtype_ids.ids)
        ).mapped("partner_id")
        if self.is_supply_order and self.supplier_partner_id:
            recipients = recipients.union(self.supplier_partner_id)
        return recipients

    @api.depends("supply_order_service_id.company_id")
    def _compute_company_id(self):
        """Default company is the current user's company, unless overridden"""
        for record in self:
            if record.supply_order_service_id:
                record.company_id = record.supply_order_service_id.company_id
            elif not record.company_id:
                # we do this because the company who is ordering the service
                # is driven by the user's company; not by the subject record (log entry)
                # e.g. Log Entry is for Company Germany with German Employee, but the user is from Company Netherlands
                # the supplier of a third party service will be billing to the user's company, and the user's company
                # will do an intra-company invoice to the German company
                record.company_id = self.env.company

    def _inverse_company_id(self):
        """Allow manual override of computed company"""
        # This is a flag method that allows the field to be written
        pass

    @api.model
    def calculate_use_project_deadline_from_options_for_new_service(
        self, parent_id, res_model, res_id, is_root_a_template
    ):
        """Calculate deadline options for a new service being created
        Used by both the start transition wizard and existing services to determine available options
        """
        options = ["self"]
        # when creating templates, any 'use from' is allowed because we don't know yet which parent service or subject will be selected
        if parent_id or is_root_a_template:
            options.append("root")

        return options

    def _compute_use_project_deadline_from_options(self):
        """Calculate deadline options for existing services"""
        for service in self:

            service.use_project_deadline_from_options = (
                self.calculate_use_project_deadline_from_options_for_new_service(
                    service.parent_id,
                    service.res_model,
                    service.res_id,
                    service.is_root_a_template,
                )
            )

    @api.model
    def _create_service_member_from_template(self, template_service, parent_id=False):
        """Create a new service based on a template service.

        Args:
            template_service: The template service record to clone from
            parent_id: Optional parent service ID for the new service

        Returns:
            The newly created service record
        """
        vals = {
            "name": template_service.name,
            "workflow_id": template_service.workflow_id.id,
            "state_id": template_service.state_id.id,
            "responsible_team_id": template_service.responsible_team_id.id,
            "company_id": template_service.company_id.id,
            "use_project_deadline_from": template_service.use_project_deadline_from,
            "days_relative_to_project": template_service.days_relative_to_project,
            "is_this_a_template": self.env.context.get("default_is_this_a_template", False),
            "email_template_id": template_service.email_template_id.id,
            "add_operator_as_recipient": template_service.add_operator_as_recipient,
            "is_supply_order": template_service.is_supply_order,
            "supplier_partner_id": template_service.supplier_partner_id.id,
            "supply_order_instructions": template_service.supply_order_instructions,
            "tag_ids": [Command.link(tag_id) for tag_id in template_service.tag_ids.ids],
        }
        if parent_id:
            vals["parent_id"] = parent_id

        new_service = (
            self.env["riverflow.service"].with_context(context={"mail_create_nosubscribe": True}).create(vals)
        )

        # Copy the legs from the template
        for leg in template_service.leg_ids:
            self.env["riverflow.service.leg"].create(
                {
                    "service_id": new_service.id,
                    "sequence": leg.sequence,
                    "supply_from": leg.supply_from,
                    "supply_to": leg.supply_to,
                    "supply_cost_amount": leg.supply_cost_amount,
                    "supply_instructions": leg.supply_instructions,
                }
            )

        # Clone direct attachments from the template service
        template_attachments = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "riverflow.service"),
                ("res_id", "=", template_service.id),
            ]
        )

        for attachment in template_attachments:
            attachment.copy(
                {
                    "res_id": new_service.id,
                    "res_model": "riverflow.service",
                }
            )

        # Clone notes (comments) from template
        template_notes = self.env["mail.message"].search(
            [
                ("model", "=", "riverflow.service"),
                ("res_id", "=", template_service.id),
                ("message_type", "=", "comment"),
                ("subtype_id", "=", self.env.ref("mail.mt_note").id),
            ]
        )

        for note in template_notes:
            # First clone the attachments
            new_attachment_ids = []
            if note.attachment_ids:
                for attachment in note.attachment_ids:
                    new_attachment = attachment.copy(
                        {
                            "res_id": new_service.id,
                            "res_model": "riverflow.service",
                        }
                    )
                    new_attachment_ids.append(new_attachment.id)

            self.env["mail.message"].sudo().create(
                {
                    "subject": note.subject,
                    "body": note.body,
                    "message_type": note.message_type,
                    "model": "riverflow.service",
                    "res_id": new_service.id,
                    "subtype_id": note.subtype_id.id,
                    "author_id": note.author_id.id,
                    "email_from": note.email_from,
                    "create_uid": note.create_uid.id,
                    "parent_id": note.parent_id.id,
                    "date": note.date,
                    "starred": note.starred,
                    "starred_partner_ids": [(6, 0, note.starred_partner_ids.ids)],
                    "attachment_ids": [(6, 0, new_attachment_ids)],
                }
            )

        return new_service

    @api.model
    def _create_service_from_template(self, template_service_id):
        """Create a new service from a template, including all child services recursively.

        Args:
            template_service_id: ID of the template service to clone

        Returns:
            The newly created root service record
        """
        template_service = self.env["riverflow.service"].browse(template_service_id)
        if not template_service:
            raise UserError(_("No template service selected."))

        # Create main service from template
        new_service = self._create_service_member_from_template(template_service)

        # Clone children recursively
        def clone_children(template, parent):
            for child in template.child_ids:
                new_child = self._create_service_member_from_template(child, parent.id)
                clone_children(child, new_child)

        clone_children(template_service, new_service)

        return new_service

    @api.model
    def _add_state_record(self, record):
        """We don't want template services in the Radar screen"""
        return not record.is_root_a_template

    @api.depends(
        "workflow_id.is_supply_order",
        "workflow_id.has_supply_quantity",
    )
    def _compute_supply_quantity(self):
        for service in self:
            if (
                service.front_office_workflow_id.is_supply_order
                and service.front_office_workflow_id.has_supply_quantity
            ):
                # keep user supplied value
                pass
            else:
                # If the service has no supply quantity, set it to 1
                # e.g. a flight booking for which we only need the price but not the quantity
                service.supply_quantity = 1

    def _inverse_supply_quantity(self):
        for service in self:
            if (
                service.front_office_workflow_id.is_supply_order
                and service.front_office_workflow_id.has_supply_quantity
            ):
                # Allow manual updates only when has_supply_quantity is True, e.g manual entry of distance for a taxi order
                continue
            else:
                # Reset to 1 if someone tries to change it when has_supply_quantity is False,
                #  e.g. a flight booking for which we only need the price but not the quantity
                service.supply_quantity = 1

    @api.depends("res_model", "res_id")
    def _compute_subject_active(self):
        """Track the active state of the subject record"""
        for service in self:
            if not service.res_model or not service.res_id:
                service.subject_active = True
                continue
            if service.res_model not in self.env:
                service.subject_active = True
                continue
            record = self.env[service.res_model].sudo().browse(service.res_id)
            if not record.exists():
                service.subject_active = True
                continue
            service.subject_active = record.active if "active" in record else True

    @api.depends("subject_active")
    def _compute_active(self):
        """Ensure service is archived when its subject is archived"""
        for service in self:
            if not service.subject_active:
                service.active = False

    def _inverse_active(self):
        """Allow manual override of computed active field"""
        # This is a flag method that allows the field to be written
        pass

    def unlink(self):
        if not self.env.context.get("bypass_user_unlink_check"):
            if self.supply_leg_id.ids and not self.env.user.has_group("base.group_no_one"):
                raise UserError(
                    _(
                        "Cannot delete info-service linked to a supply order leg. Delete the leg from the supply order instead."
                    )
                )

        return super().unlink()


class ServiceLeg(models.Model):
    _name = "riverflow.service.leg"
    _description = "Supply Order Leg"
    _order = "sequence,id"

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
    )

    service_id = fields.Many2one(
        "riverflow.service",
        required=True,
        ondelete="cascade",
        index=True,
        help="Supply Order",
    )

    sequence = fields.Integer(default=10)
    supply_from = fields.Char("From")
    supply_to = fields.Char("To")
    supply_cost_amount = fields.Monetary("Cost", currency_field="supply_cost_currency_id")
    supply_cost_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Cost Currency",
        related="service_id.company_id.currency_id",
        store=True,
    )
    supply_instructions = fields.Text(
        "Instructions",
        help="Instructions to the supplier about this leg of the supply order",
    )
    is_reviewed_for_invoicing = fields.Boolean(
        string="Reviewed for Invoicing",
        default=False,
        help="If True, the leg is considered for invoicing",
    )

    @api.depends("supply_from", "supply_to", "service_id.deadline", "service_id.name")
    def _compute_name(self):
        for leg in self:
            name_parts = []

            if leg.supply_from and leg.supply_to:
                name_parts.append(f"{leg.supply_from} → {leg.supply_to}")
            elif leg.supply_from:
                name_parts.append(leg.supply_from)
            elif leg.supply_to:
                name_parts.append(leg.supply_to)

            if leg.service_id.deadline:
                name_parts.append(leg.service_id.deadline.strftime(Service.DATE_FORMAT))

            leg.name = " | ".join(name_parts)
