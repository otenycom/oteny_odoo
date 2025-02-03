# Tips for ODOO

## Wizards

- To allow entering lists in Wizards. Quirks are that you loose values that user entered or that are not in the view
  - store=True (to ensure inverted compute values are kept when entered by user)
  - force_save="1" (for round trip values back to service from client), even if they are readonly in the view
  - use hidden fields in the view to ensure they are kept in the client recordset and are posted back to server
  - editable="bottom" (to allow adding new lines), or leave it out for editing in a popup form
