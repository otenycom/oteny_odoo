---
name: riverflow
description: Riverflow workflow engine for Odoo 19. Covers workflow concepts, state machines, transitions, services, and auto-add rules. Use when creating or modifying workflows, writing workflow XML files, or understanding the state machine architecture.
---

# Riverflow Workflow Engine

Riverflow is a workflow automation engine for Odoo 19. It provides state machines, transitions, services, and auto-add rules for managing business processes.

## When to Use This Skill

- **Developers**: Creating or modifying workflow definitions in XML
- **AI Agents**: Generating workflow XML, understanding state transitions
- **Business Analysts**: Understanding workflow architecture and state machines

## Quick Start

Workflow XML files define three main elements:

1. **Workflow** - The container (e.g., "Taxi Order", "Work Entry")
2. **States** - The stages in the workflow (e.g., "Not Started", "Ordered", "Completed")
3. **Transitions** - The allowed moves between states (e.g., "Order Now", "Cancel")

Basic structure:

```xml
<odoo noupdate="1">
    <!-- 1. Workflow definition -->
    <record id="workflow_example" model="riverflow.workflow">
        <field name="name">Example Workflow</field>
        ...
    </record>

    <!-- 2. States (define all first) -->
    <record id="state_not_started" model="riverflow.state">
        <field name="workflow_id" ref="workflow_example"/>
        <field name="name">Not Started</field>
        <field name="sequence">10</field>
    </record>
    ...

    <!-- 3. Transitions -->
    <record id="trans_to_started" model="riverflow.transition">
        <field name="from_state_id" ref="state_not_started"/>
        <field name="to_state_id" ref="state_started"/>
        ...
    </record>
</odoo>
```

## Core Concepts

### Workflows

A workflow is a state machine attached to an Odoo model. Key fields:

| Field | Purpose |
|-------|---------|
| `model_id` | The Odoo model this workflow applies to |
| `name` | Display name |
| `description` | User-facing description |
| `icon` | FontAwesome icon (e.g., `fa-taxi`, `fa-ship`) |
| `work_status` | For log entries: links to work status type |

### States

States are the stages in a workflow. Key fields:

| Field | Purpose |
|-------|---------|
| `workflow_id` | Parent workflow |
| `name` | Display name |
| `sequence` | Order in statusbar (increment by 10) |
| `color_int` | Color index (0-11, see odoo-colors reference) |
| `is_end_state` | Marks workflow completion |
| `is_cancelled_state` | Marks cancelled items |
| `is_back_office_state` | Requires back-office handling |
| `hide_in_statusbar` | Don't show in status bar |

### Transitions

Transitions define allowed state changes. Key fields:

| Field | Purpose |
|-------|---------|
| `name` | Button label |
| `from_state_id` | Source state (empty for initial) |
| `to_state_id` | Target state |
| `action_id` | Transition action to execute |
| `sequence` | Button order (restart at 10 per from_state) |
| `icon` | FontAwesome icon for button |
| `to_responsible_team_id` | Team assignment after transition |

### Transition Actions

Actions executed when a transition occurs:

| Action | Purpose |
|--------|---------|
| `transition_action_default` | Simple state change |
| `transition_action_email_sender` | Open email composer |
| `transition_action_register_service` | Register for billing |
| `transition_action_supplier_confirmed` | Mark supplier confirmation |

### Services

Services are tasks attached to records (e.g., log entries). They have their own workflow for task management.

### Auto-Add Rules

Rules that automatically create services when conditions are met:

```xml
<record id="auto_add_check_permits" model="riverflow.auto.add.service">
    <field name="name">Check Permits</field>
    <field name="domain">[('work_status', '=', 'work')]</field>
    <field name="service_workflow_id" ref="workflow_check_permits"/>
</record>
```

## Technical Reference

### Key Models

| Model | Purpose |
|-------|---------|
| `riverflow.workflow` | Workflow definitions |
| `riverflow.state` | State definitions |
| `riverflow.transition` | Transition definitions |
| `riverflow.transition.action` | Transition action handlers |
| `riverflow.service` | Service instances |
| `riverflow.auto.add.service` | Auto-add rules |
| `riverflow.state.record` | State tracking per record. State records underpin the 'radar' app view, used by users to query across different models |

### Key Files

```text
riverflow/
├── models/
│   ├── riverflow_workflow.py      # Workflow model
│   ├── riverflow_state.py         # State model
│   ├── riverflow_transition.py    # Transition model
│   └── riverflow_service.py       # Service model
├── data/
│   ├── transition_action_data.xml # Built-in actions
│   ├── riverflow_*_workflow.xml   # Workflow definitions
│   └── riverflow_teams_data.xml   # Team definitions
└── wizards/
    └── riverflow_*_wizard.py      # Transition wizards
```

## References

- [Workflow XML Guide](references/workflow-xml-guide.md) - Detailed XML writing patterns
- [Roadmap](references/roadmap.md) - Development roadmap
