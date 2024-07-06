from odoo import models, fields, api, _
import json
from datetime import timedelta

class Service(models.Model):
    _name = 'riverflow.service'
    _inherit = ['mail.thread'] # , 'mail.activity.mixin']
    _description = 'Service'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'complete_name'
    _order = "related_project_deadline,root_id,sequence,id" 
    
    DATE_FORMAT = '%d-%b-%y' # 01-Jan-21

    # auto calculated by Odoo in the form of parent_id/parent_id/self_id/
    # see def _get_domain_locations(self)
    parent_path = fields.Char(index='btree', unaccent=False)
    indent_level = fields.Integer('Indent level', compute='_compute_indent_level', store=False, recursive=True)
    parent_id = fields.Many2one('riverflow.service', string='Parent Service', index=True, ondelete='cascade')
    child_ids = fields.One2many('riverflow.service', 'parent_id', string='Child Services')
    root_id = fields.Many2one('riverflow.service', compute='_compute_root_id', store=True, recursive=True)
    name = fields.Char('Name', index='trigram', required=True, tracking=True)
    indented_name = fields.Char('Service', compute='_compute_indented_name', store=False, recursive=True)
    complete_name = fields.Char('Complete Name', compute='_compute_complete_name', store=True, index='trigram', recursive=True)
    internal_remarks = fields.Text('Internal Remarks', tracking=True)
    workflow_transition_buttons_json = fields.Char('Actions', compute='_compute_workflow_transition_buttons_json', store=False)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=False,
        default=lambda self: self.env.company, tracking=True)
    active = fields.Boolean(default=True, help="Set active to false to archive the service", tracking=True)
    days_relative_to_project = fields.Integer(
        'Day', 
        help="Number of days before or after the project deadline for this service to be completed, e.g. -1 for the day before",
        required=False, tracking=True)
    project_deadline = fields.Date('Project deadline', help="The services are timed relative to this deadline", tracking=True)
    related_project_deadline = fields.Date(
        'Related project deadline', 
        related='root_id.project_deadline', 
        help="Deadline of the project at the root of the tree)", 
        store=True, 
        index=True,
        recursive=True)
    deadline = fields.Date(
        'Deadline Date', compute='_compute_deadline', 
        help="Deadline based on the project deadline and the day of this service", 
        store=True, index=True, recursive=True)
    deadline_formatted = fields.Char('Deadline', compute='_compute_deadline_formatted', store=False)
    timing = fields.Char(
        'Timing', compute='_compute_timing', store=False, recursive=True)
    sequence = fields.Integer(default=1, compute='_compute_sequence', index=True, required=True, store=True, recursive=True)

    def action_button_click(self):
        # This is a workflow transition action, for now just one base wizard
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Update Service', # Dialog title
            'res_model': 'riverflow.service.wizard',
            'view_mode': 'form',
            'views': [[False, "form"]],
            'target': 'new',
            'context': {
                'default_service_ids': self.ids,
                'name_readonly': False,
                'internal_remarks_invisible': False,
                'days_relative_to_project_invisible': False,
            },
        }

        return action;

    def _compute_workflow_transition_buttons_json(self):
        for service in self:
            # needs int, for json serialization
            service_id = -1 if isinstance(service.id, models.NewId) else int(service.id)
            
            workflow_transition_buttons = {
                'text': '', # record.indented_name,
                'service_id': service_id,
                'buttons': [
                    {
                        'index': 0,
                        'caption': 'Start',
                        'action': 'action_button_click'
                    },
                    {
                        'index': 1,
                        'caption': 'Cancel',
                        'action': 'action_button_click'
                    }
                ]
            }
            service.workflow_transition_buttons_json = json.dumps(workflow_transition_buttons)

    @api.depends('parent_path')
    def _compute_root_id(self):
        for service in self.sudo():
            try:
                if service.parent_path:
                    path_parts = service.parent_path.split('/')
                    # Assign the first part of the path as the root_id
                    service.root_id = int(path_parts[0])
                else:
                    # If parent_path is empty, use the service's own ID
                    service.root_id = service.id
            except ValueError:
                # Handle the case where conversion to int fails
                service.root_id = service.id  # Or handle as appropriate

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for service in self.sudo():
            if service.parent_id:
                service.complete_name = '%s / %s' % (service.parent_id.complete_name, service.name)
            else:
                service.complete_name = service.name

    def _compute_indent_level(self):
        for service in self.sudo():
            if service.parent_path:
                # Count the number of slashes in parent_path, subtract 1 for indent level
                service.indent_level = service.parent_path.count('/') - 1
            else:
                service.indent_level = 0

    def _compute_indented_name(self):
        for service in self.sudo():
            service.indented_name = '%s%s' % ('\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}' * service.indent_level, service.name)

    def isProject(record):
        # root level services are projects
        return not record.parent_id

    @api.depends('project_deadline', 'related_project_deadline', 'days_relative_to_project')
    def _compute_deadline(self):
        for service in self:
            if Service.isProject(service):
                service.deadline = service.project_deadline
                service.days_relative_to_project = False
            elif not service.related_project_deadline:
                # todo: add checkresults to the service and check for this case
                service.deadline = False
            else:
                service.deadline = service.related_project_deadline + timedelta(days=service.days_relative_to_project)

    def _compute_timing(self):
        for service in self:
            if Service.isProject(service):
                if (service.deadline == False):
                    service.timing = ''
                else:
                    service.timing = service.project_deadline.strftime(Service.DATE_FORMAT)
            else:
                relative_days = f"{service.days_relative_to_project:+02d}d"
                if (service.deadline == False):
                    service.timing = relative_days
                else:
                    today = fields.Date.today() # odoo way to get the current date
                    days_remaining = (service.deadline - fields.Date.today()).days
                    
                    service.timing = f"{relative_days} = {service.deadline.strftime(Service.DATE_FORMAT)} | in {days_remaining:02d}d"

    def _compute_deadline_formatted(self):
        for service in self:
            if (service.deadline == False):
                service.deadline_formatted = ''
            else:
                service.deadline_formatted = service.deadline.strftime(Service.DATE_FORMAT)

    # no need for depends on 'root_id', 'parent_id.sequence',
    # because upon parent_id change, the sequence is recalculated for the entire tree up to the root
    @api.depends('parent_id', 'days_relative_to_project')
    def _compute_sequence(self):
        if isinstance(self.id, models.NewId):
            self.sequence = 0
            return
        
        # Retrieve all service records with the same root_id as the current record
        # we only use the sequence field of child nodes, the root nodes are sorted
        # by project_deadline. 
        services = self.sudo().search([('root_id', '=', self.root_id.id)])

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
                raise ValueError(f"Circular reference detected in service hierarchy involving service ID {service_id}")
            
            # Add the current service ID to the set of visited nodes
            visited.add(service_id)

            # Retrieve the service object using its ID
            service = service_dict[service_id]

            # Assign the current sequence number to the service
            service.sequence = sequence

            # Increment the sequence number for the next service
            sequence += 1

            # If the current service has children, sort them by `days_relative_to_project` and recursively assign sequences to them
            if service_id in service_tree:
                children_ids = service_tree[service_id]
                # Sort children based on `days_relative_to_project`
                sorted_children_ids = sorted(
                    children_ids, 
                    key=lambda child_id: service_dict[child_id].days_relative_to_project
                )
                for child_id in sorted_children_ids:
                    assign_sequence(child_id, visited.copy())  # Use a copy of the visited set to avoid modifying it during recursion

        # Assign sequence numbers to root services (those without parents) and their children
        if None in service_tree:
            visited = set()
            
            # Sort the root services by `project_deadline` and assign sequences
            root_ids = sorted(service_tree[None], key=lambda root_id: service_dict[root_id].project_deadline)
            for root_id in root_ids:
                assign_sequence(root_id, visited)
