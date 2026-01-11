# Workflow XML Guide

Detailed patterns for writing riverflow workflow XML files.

## File Structure

```xml
<?xml version="1.0"?>
<odoo noupdate="1">
    <!-- 1. Workflow definition -->
    
    <!-- 2. All states (define before transitions to prevent forward references) -->
    
    <!-- 3. All transitions (grouped by from_state with comments) -->
</odoo>
```

## Workflow Record

```xml
<record id="workflow_service_taxi_order" model="riverflow.workflow">
    <field name="model_id" ref="riverflow.model_riverflow_service"/>
    <field name="name">Taxi Supply Order</field>
    <field name="description">Workflow for managing taxi orders</field>
    <field name="icon">fa-taxi</field>
    <!-- Service-specific fields -->
    <field name="is_supply_order">True</field>
    <field name="has_supplier">True</field>
    <field name="has_legs">True</field>
</record>
```

For log entry workflows:

```xml
<record id="log_entry_workflow_crew_change" model="riverflow.workflow">
    <field name="model_id" ref="crewradar.model_crewradar_log_entry"/>
    <field name="name">Work</field>
    <field name="description">Placement of an employee on a ship</field>
    <field name="icon">fa-ship</field>
    <field name="work_status">work</field>
    <field name="billing_sequence">10</field>
</record>
```

## State Records

### Sequence Convention

States have sequences that increment by **10**:

```xml
<!-- State sequence: 10, 20, 30, 40... -->
<record id="state_not_started" model="riverflow.state">
    <field name="sequence">10</field>
    ...
</record>

<record id="state_ordered" model="riverflow.state">
    <field name="sequence">20</field>
    ...
</record>

<record id="state_confirmed" model="riverflow.state">
    <field name="sequence">30</field>
    ...
</record>
```

### Common State Patterns

**Initial state:**

```xml
<record id="state_not_started" model="riverflow.state">
    <field name="workflow_id" ref="workflow_example"/>
    <field name="name">Not Started</field>
    <field name="sequence">10</field>
    <field name="color_int">7</field>  <!-- Teal -->
</record>
```

**End state (completed):**

```xml
<record id="state_completed" model="riverflow.state">
    <field name="workflow_id" ref="workflow_example"/>
    <field name="name">Completed</field>
    <field name="sequence">50</field>
    <field name="is_end_state">True</field>
    <field name="is_back_office_state">True</field>
    <field name="color_int">10</field>  <!-- Green -->
</record>
```

**Cancelled state:**

```xml
<record id="state_cancelled" model="riverflow.state">
    <field name="workflow_id" ref="workflow_example"/>
    <field name="name">Cancelled</field>
    <field name="sequence">60</field>
    <field name="is_end_state">True</field>
    <field name="is_cancelled_state">True</field>
    <field name="hide_in_statusbar">True</field>
    <field name="color_int">1</field>  <!-- Red -->
</record>
```

**State with review service:**

```xml
<record id="state_in_progress" model="riverflow.state">
    <field name="workflow_id" ref="workflow_example"/>
    <field name="name">In Progress</field>
    <field name="sequence">20</field>
    <field name="add_review_service_on_change">True</field>
    <field name="review_on_change_max_days_in_future">60</field>
    <field name="color_int">8</field>  <!-- Blue -->
</record>
```

### State Color Reference

| Color Int | Name | Typical Use |
|-----------|------|-------------|
| 1 | Red | Cancelled, Error |
| 2 | Orange | Warning, Registered |
| 4 | Cyan | Arranging, Attention |
| 7 | Teal | Initial, Not Started |
| 8 | Blue | Working, In Progress |
| 10 | Green | Completed, Success |
| 11 | Violet | Planning, Draft |

## Transition Records

### Sequence Convention

Transitions restart sequence at **10** for each `from_state`, incrementing by **10**:

```xml
<!-- Transitions from Not Started -->
<record id="trans_not_started_to_ordered" model="riverflow.transition">
    <field name="from_state_id" ref="state_not_started"/>
    <field name="sequence">10</field>  <!-- First transition from this state -->
    ...
</record>

<record id="trans_not_started_to_confirmed" model="riverflow.transition">
    <field name="from_state_id" ref="state_not_started"/>
    <field name="sequence">20</field>  <!-- Second transition from this state -->
    ...
</record>

<!-- Transitions from Ordered (sequence restarts) -->
<record id="trans_ordered_to_confirmed" model="riverflow.transition">
    <field name="from_state_id" ref="state_ordered"/>
    <field name="sequence">10</field>  <!-- First transition from Ordered -->
    ...
</record>
```

### Grouping with Comments

Always add comments to group transitions by from_state:

```xml
<!-- Transitions from Not Started -->
<record id="trans_not_started_to_ordered" model="riverflow.transition">
    ...
</record>

<!-- Transitions from Ordered -->
<record id="trans_ordered_to_confirmed" model="riverflow.transition">
    ...
</record>

<!-- Transitions from Confirmed -->
<record id="trans_confirmed_to_completed" model="riverflow.transition">
    ...
</record>
```

### Initial Transition (No from_state)

The initial transition has an empty `from_state_id`:

```xml
<record id="trans_initial_to_not_started" model="riverflow.transition">
    <field name="name">Create</field>
    <field name="from_state_id" ref=""/>  <!-- Empty = initial transition -->
    <field name="to_state_id" ref="state_not_started"/>
    <field name="action_id" ref="riverflow.transition_action_default"/>
    <field name="sequence">10</field>
</record>
```

### Common Transition Actions

| Action ID | Purpose |
|-----------|---------|
| `riverflow.transition_action_default` | Simple state change, no wizard |
| `riverflow.transition_action_email_sender` | Opens email composer wizard |
| `riverflow.transition_action_register_service` | Marks for billing/registration |
| `riverflow.transition_action_supplier_confirmed` | Records supplier confirmation |

For crewradar log entries:

| Action ID | Purpose |
|-----------|---------|
| `crewradar.log_entry_transition_action_new_prospect` | New planning entry |
| `crewradar.log_entry_transition_action_validate_employee_sign_on` | Validate sign-on |
| `crewradar.log_entry_transition_action_set_actual_start_date` | Set actual start |

### Transition Examples

**Simple transition:**

```xml
<record id="trans_not_started_to_ordered" model="riverflow.transition">
    <field name="name">Order Now</field>
    <field name="from_state_id" ref="state_not_started"/>
    <field name="to_state_id" ref="state_ordered"/>
    <field name="action_id" ref="riverflow.transition_action_email_sender"/>
    <field name="icon">fa-taxi</field>
    <field name="sequence">10</field>
    <field name="to_responsible_team_id" ref="riverflow.partner_team_logistics"/>
</record>
```

**Cancel transition:**

```xml
<record id="trans_ordered_to_cancelled" model="riverflow.transition">
    <field name="name">Cancel</field>
    <field name="from_state_id" ref="state_ordered"/>
    <field name="to_state_id" ref="state_cancelled"/>
    <field name="action_id" ref="riverflow.transition_action_default"/>
    <field name="icon">fa-times</field>
    <field name="sequence">40</field>
</record>
```

**Self-transition (stay in same state):**

```xml
<record id="trans_ordered_to_ordered" model="riverflow.transition">
    <field name="name">Re-order</field>
    <field name="from_state_id" ref="state_ordered"/>
    <field name="to_state_id" ref="state_ordered"/>  <!-- Same state -->
    <field name="action_id" ref="riverflow.transition_action_email_sender"/>
    <field name="icon">fa-refresh</field>
    <field name="sequence">30</field>
</record>
```

**Return/undo transition:**

```xml
<record id="trans_completed_to_in_progress" model="riverflow.transition">
    <field name="name">Return to In Progress</field>
    <field name="from_state_id" ref="state_completed"/>
    <field name="to_state_id" ref="state_in_progress"/>
    <field name="action_id" ref="riverflow.transition_action_default"/>
    <field name="icon">fa-undo</field>
    <field name="sequence">10</field>
</record>
```

## Updating Existing Workflows

When modifying workflows:

1. **Re-number sequences** if states/transitions are inserted or deleted
2. **Keep existing flags** (`is_end_state`, `is_back_office_state`) unless there's a reason to change
3. **Test transitions** ensure all paths work correctly

### Adding a State

Insert with appropriate sequence, renumber subsequent states:

```xml
<!-- Before: 10, 20, 30 -->
<!-- After: 10, 20, 25 (new), 30 -->
<!-- Or: 10, 20, 30 (new), 40 (renumbered) -->
```

### Adding a Transition

Add with appropriate sequence for its from_state group:

```xml
<!-- Existing transitions from state_ordered: 10, 20 -->
<!-- Add new: sequence 30 -->
```

## Complete Example

See `/riverflow/data/riverflow_taxi_order_workflow.xml` for a complete workflow example with:

- Workflow definition with service-specific fields
- Five states (Not Started → Ordered → Confirmed → Registered → Cancelled)
- Multiple transitions per state
- Team assignments
- Action contexts

## Prompt Notation

When describing workflows in prompts, use arrow notation:

```
a -> b -> c
```

This indicates:

- 3 states: a, b, c
- 2 transitions: a→b, b→c

More complex:

```
Plan -> Arrange -> Working -> Completed
           ↓
       Cancelled
```
