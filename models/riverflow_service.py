from odoo import models, fields, api, _
from datetime import timedelta, date
import json
import re


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
    parent_path = fields.Char(index="btree", unaccent=False)
    indent_level = fields.Integer(
        "Indent level", compute="_compute_indent_level", store=True, recursive=True
    )
    parent_id = fields.Many2one(
        "riverflow.service", string="Parent Service", index=True, ondelete="cascade"
    )
    child_ids = fields.One2many(
        "riverflow.service", "parent_id", string="Child Services"
    )
    descendant_ids = fields.One2many(
        "riverflow.service",
        "parent_id",
        string="Descendant Services",
        compute="_compute_descendant_ids",
        store=False,
    )
    created_by_auto_add_rule_id = fields.Integer(
        string="Created by Auto Add Rule ID",
        default=False,
        help="ID of the auto add rule that created this service. The system can use this to determine if the rule that created the service is still applicable.",
    )

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

    root_id = fields.Many2one(
        "riverflow.service", compute="_compute_root_id", store=True, recursive=True
    )
    root_name = fields.Char(
        "Root service name",
        compute="_compute_root_name",
        help="Name of the root node, for sorting the list of services",
        store=True,
        index=True,
        recursive=True,
    )
    name = fields.Char("Service Name", index="trigram", required=True, tracking=True)
    indented_name = fields.Char(
        "Service", compute="_compute_indented_name", store=False, recursive=True
    )
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
        required=True,
        readonly=False,
        default=lambda self: self.env.company,
        tracking=True,
    )

    active = fields.Boolean(
        default=True, help="Set active to false to archive the service", tracking=True
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
            ("root", "Root Service"),
        ],
        string="Project Deadline From",
        required=True,
        tracking=True,
        default="self",
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
    related_project_deadline = fields.Date(
        "Related deadline",
        related="root_id.deadline",
        help="Deadline of the project at the root of the tree",
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
    deadline_formatted = fields.Char(
        "Deadline", compute="_compute_deadline_formatted", store=False
    )
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
        "riverflow_service_ship_tag_rel",
        "service_tag_id",
        "tag_id",
        "Tags",
        tracking=True,
        copy=True,
    )

    # related entity (similar to the one in the mail_message.py in odoo)
    # content fields such as display_name of the related document can be looked
    # up in the riverflow.state.record model
    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    # the container of the service (log_entry, employee, etc)
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )
    res_name = fields.Char(
        string="Subject of Service",
        compute="_compute_res_name",
        store=True,
        index="trigram",
    )
    resource_ref = fields.Reference(
        string="Subject Reference",
        selection="_selection_target_model",
        compute="_compute_resource_ref",
        inverse="_set_resource_ref",
    )

    @api.depends("res_model", "res_id")  # , "is_unlinked")
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

    res_id_computed = fields.Integer(
        "Computed Service Subject ID",
        compute="_compute_res_id_computed",
        store=False,
        recursive=True,
        help="Syncs the service's subject reference (ref_id) with the root service. All decendending services reference the same subject.",
    )

    @api.depends("root_id.res_id", "root_id.res_model")
    def _compute_res_id_computed(self):
        for service in self:
            service.res_id_computed = service.root_id.res_id

            isRootService = service.id == service.root_id.id
            if not isRootService:
                service.res_id = service.root_id.res_id
                service.res_model = service.root_id.res_model

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

    @api.depends("root_id", "root_id.name", "name")
    def _compute_root_name(self):
        for service in self:
            if service.root_id.id == service.id:
                service.root_name = service.name
            else:
                service.root_name = service.root_id.name

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

    @api.depends("name", "parent_id.display_name")
    def _compute_display_name(self):
        for service in self.sudo():
            if service.parent_id:
                service.display_name = "%s | %s" % (
                    service.parent_id.display_name,
                    service.name,
                )
            else:
                service.display_name = service.name

            # service.display_name = ' | '.join(
            #     [service.display_name, self.compute_display_name_suffix(service)])

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

    @api.depends("use_project_deadline_from", "project_deadline", "root_id.deadline")
    def _compute_project_deadline(self):
        for service in self:
            use_project_deadline_from = service.use_project_deadline_from
            if use_project_deadline_from == "self":
                service.project_deadline = service.project_deadline
            elif use_project_deadline_from == "root":
                service.project_deadline = service.root_id.deadline

    def _inverse_project_deadline(self):
        # this is a flag method specifying the user is allowed to store the project_deadline
        pass

    @api.depends(
        "project_deadline", "days_relative_to_project", "use_project_deadline_from"
    )
    def _compute_deadline(self):
        for service in self:
            project_deadline = self.project_deadline
            if not project_deadline:
                service.deadline = False
            else:
                service.deadline = project_deadline + timedelta(
                    days=service.days_relative_to_project
                )

    @api.depends("deadline")
    def _compute_timing_json(self):
        for service in self:
            if not service.deadline:
                service.timing_json = False
                continue

            relative_days = ""
            if (
                service.use_project_deadline_from != "self"
                and service.days_relative_to_project
            ):

                relative_days = f"{self.relative_to_project_days_prefix()}{service.days_relative_to_project:+02d}d = "

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
                "is_end_state": service.state_id.is_end_state,
            }

    def relative_to_project_days_prefix(self):
        if self.use_project_deadline_from == "self":
            return ""
        elif self.use_project_deadline_from == "root":
            return self.root_name
        else:
            return "(unknown: use_project_deadline_from)"

    @api.depends("deadline")
    def _compute_deadline_formatted(self):
        for service in self:
            if service.deadline == False:
                service.deadline_formatted = ""
            else:
                service.deadline_formatted = service.deadline.strftime(
                    Service.DATE_FORMAT
                )

    def print_compute_sequence_counter(self):
        if not hasattr(self.__class__, "_compute_sequence_counter"):
            self.__class__._compute_sequence_counter = 0
        # print(
        #     f"_compute_sequence counter: {self.__class__._compute_sequence_counter} - {self.display_name}"
        # )
        self.__class__._compute_sequence_counter += 1

    @api.depends(
        "parent_id",
        "root_name",
        "deadline",
    )
    def _compute_sequence(self):
        self.print_compute_sequence_counter()

        if isinstance(self.id, models.NewId):
            return

        # Retrieve all service records with the same root_id as the current record
        # we only set the sequence field of child nodes, the root nodes are sorted
        # by name; as it would become very slow to sequence the entire list of services
        services = self.sudo().search([("root_id", "=", self.root_id.id)])

        # Dictionary to hold the tree structure of services
        service_tree = {}

        # Dictionary to map service IDs to their corresponding service objects
        service_dict = {service.id: service for service in services}

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
                "default_use_project_deadline_from": "root",
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
        records = super(Service, self).create(vals_list)
        for record in records:
            if record.parent_id and not record.res_id:
                record.res_id = record.parent_id.res_id
                record.res_model = record.parent_id.res_model
            elif (
                not record.parent_id
                and record.res_model == self._name
                and record.res_id
            ):
                # for auto-adding a child service, they set the parent via res_id
                # Invalidate the recordset to ensure fresh data
                record.parent_id = record.res_id
                record.root_id = record.parent_id.root_id
                record.res_model = record.parent_id.res_model
                record.res_id = record.parent_id.res_id
                # recalculate the parent_id dependent fields
                record.invalidate_recordset(
                    ["parent_id", "parent_path", "root_id", "res_model", "res_id"]
                )
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
