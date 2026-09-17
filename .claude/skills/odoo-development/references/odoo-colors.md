# Odoo Colors Reference

Color integers used in Odoo views (kanban, list decorations, etc.).

## Color List

Based on Odoo 19 `colorlist.js` (COLORS constant):

| Integer | Name | Usage |
|---------|------|-------|
| 0 | No color | Default/unset |
| 1 | Red | Errors, urgent items |
| 2 | Orange | Warnings, attention needed |
| 3 | Yellow | Highlights, pending |
| 4 | Cyan | Information |
| 5 | Purple | Special status |
| 6 | Almond | Neutral/soft |
| 7 | Teal | Success variant |
| 8 | Blue | Primary actions |
| 9 | Raspberry | Accent |
| 10 | Green | Success, completed |
| 11 | Violet | Alternative accent |

## Usage in XML Views

### Kanban Cards

```xml
<kanban>
    <field name="color"/>
    <templates>
        <t t-name="card">
            <div t-attf-class="#{kanban_color(record.color.raw_value)}">
                <!-- Card content -->
            </div>
        </t>
    </templates>
</kanban>
```

### List Row Decoration

```xml
<list decoration-danger="state == 'error'"
      decoration-warning="state == 'pending'"
      decoration-success="state == 'done'">
    <field name="name"/>
    <field name="state"/>
</list>
```

### Color Field Widget

```xml
<field name="color" widget="color_picker"/>
```

## Color Field Definition

```python
color = fields.Integer(
    string="Color",
    default=0,
    help="Color index for kanban cards",
)
```

## Common Color Conventions

| Scenario | Recommended Color |
|----------|-------------------|
| Default/Normal | 0 (No color) |
| Error/Critical | 1 (Red) |
| Warning/Attention | 2 (Orange) |
| Pending/In Progress | 3 (Yellow) or 8 (Blue) |
| Success/Completed | 10 (Green) |
| Cancelled/Archived | 6 (Almond) |
| Special/VIP | 5 (Purple) or 11 (Violet) |
