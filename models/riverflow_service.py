from odoo import models, fields, api, _
from datetime import timedelta, date
import re


class Service(models.Model):
    _name = "riverflow.service"
    # no activities 'mail.activity.mixin', we use workflow buttons instead
    _inherit = ["mail.thread", "riverflow.state.mixin"]
    _description = "Service"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "display_name"  # ensure default search is on display_name.
    # Services are a recursive tree, and in order to show the tree correctly in the flat
    # list view, we assign a sequence numer for all child services. For performance, we don't
    # set the sequence field to all services on any service update, so the root services are not sorted
    # by sequence, but by name.
    _order = "root_name,sequence"

    DATE_FORMAT = "%d-%b-%y"  # 01-Jan-21

    # auto calculated by Odoo in the form of parent_id/parent_id/self_id/
    # see def _get_domain_locations(self)
    parent_path = fields.Char(index="btree", unaccent=False)
    indent_level = fields.Integer(
        "Indent level", compute="_compute_indent_level", store=False, recursive=True
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

    @api.depends("child_ids")
    def _compute_descendant_ids(self):
        for service in self:
            descendants = self.env["riverflow.service"].search(
                [
                    ("parent_path", "=like", f"{service.parent_path}%"),
                    ("id", "!=", service.id),
                ],
                order="root_name, sequence",
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
        related="root_id.project_deadline",
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
    timing = fields.Char(
        "Timing", compute="_compute_timing", store=False, recursive=True
    )
    sequence = fields.Integer(
        default=1,
        compute="_compute_sequence",
        index=True,
        required=True,
        store=True,
        recursive=True,
    )
    latest_messages = fields.Html(
        string="Latest Messages",
        compute="_compute_latest_messages",
        store=True,
        tracking=False,
        index="trigram",
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

    @api.depends("root_id", "root_id.name", "name")
    def _compute_root_name(self):
        for service in self:
            if service.root_id.id == service.id:
                service.root_name = service.name
            else:
                service.root_name = service.root_id.name

    @api.depends("message_ids.body")
    def _compute_latest_messages(self):
        for record in self:
            # this finds any edited body in the orm cache, which a direct
            # sql query would not find
            messages = self.env["mail.message"].search(
                [
                    ("res_id", "=", record.id),
                    ("model", "=", self._name),
                    ("message_type", "=", "comment"),
                ],
                order="date DESC",
                limit=2,
            )
            # Concatenate the bodies of the latest two messages, marking them up as safe HTML
            # todo: add a css class to the <p> tag, as the default css has too big a margin
            # p {   margin-top: 0;    margin-bottom: 1rem; }
            latest_messages = ""
            for message in messages:
                # trim the Markup wrapper class from the body value
                body = str(message.body)
                # Replace <p> tags with <p> tags that have inline styles
                body = body.replace("<p>", '<p style="margin-bottom: 0rem;">')
                latest_messages += body

            record.latest_messages = latest_messages

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

    @api.depends("use_project_deadline_from", "root_id.project_deadline")
    def _compute_project_deadline(self):
        for service in self:
            use_project_deadline_from = service.use_project_deadline_from
            if use_project_deadline_from == "self":
                service.project_deadline = service.project_deadline
            elif use_project_deadline_from == "root":
                service.project_deadline = service.root_id.project_deadline

    def _inverse_project_deadline(self):
        # this is a flag method specifying the user is allowed to store the project_deadline
        pass

    @api.depends("project_deadline", "days_relative_to_project")
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
    def _compute_timing(self):
        for service in self:
            if service.deadline == False:
                service.timing = ""
                continue

            relative_days = ""
            if (
                self.use_project_deadline_from != "self"
                and service.days_relative_to_project
            ):
                relative_days = f"{service.days_relative_to_project:+02d}d = "

            today = fields.Date.today()  # odoo way to get the current date
            days_remaining = (service.deadline - fields.Date.today()).days

            service.timing = f"{relative_days}{service.deadline.strftime(Service.DATE_FORMAT)} | in {days_remaining:02d}d"

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
        print(
            f"_compute_sequence counter: {self.__class__._compute_sequence_counter} - {self.display_name}"
        )
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
        # Select a start transition for a new service
        return {
            "type": "ir.actions.act_window",
            "name": "Add Service to: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.start.service",
            "context": {
                "default_parent_id": self.id,
                "default_company_id": self.company_id.id,
                "default_use_project_deadline_from": "root",
            },
            "target": "new",
        }
