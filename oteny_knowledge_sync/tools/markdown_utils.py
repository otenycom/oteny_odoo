# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Utilities for parsing and converting markdown skill files to HTML for Knowledge articles.
"""

import re
import yaml
import mistune
from html import escape as html_escape
from pathlib import Path


def parse_frontmatter(content: str) -> dict:
    """
    Parse YAML frontmatter from markdown content.

    Returns a dict with:
    - 'metadata': dict of YAML frontmatter (or empty dict if none)
    - 'body': markdown content without frontmatter
    """
    frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = frontmatter_pattern.match(content)

    if match:
        yaml_text = match.group(1)
        try:
            metadata = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError:
            metadata = {}
        body = content[match.end() :]
    else:
        metadata = {}
        body = content

    return {"metadata": metadata, "body": body}


class OdooHTMLRenderer(mistune.HTMLRenderer):
    """Custom renderer that adds Odoo/Bootstrap classes to HTML elements.

    Odoo Knowledge uses Bootstrap classes for proper styling of tables,
    checklists, and code blocks. Without these overrides, elements render
    as unstyled plain HTML.
    """

    def table(self, text):
        """Render the table with every row in one ``<tbody>`` — ``o_table`` has no ``<thead>``.

        ``.o_table`` is ``display: block`` so wide tables scroll horizontally, and
        it restores ``display: table; width: 100%; table-layout: fixed`` on ``tbody``
        *only* (html_editor/static/src/main/table/table.scss). A ``<thead>`` is
        therefore laid out as its own content-sized anonymous table box — the header
        cells come out narrow and misaligned above the fixed-layout body.

        Odoo's editor never stores a ``<thead>`` either: ``normalizeTableStructure``
        (table_plugin.js) moves its rows into ``<tbody>`` and tags every ``<th>``
        with ``o_table_header``. But that normalization runs only in the editor, not
        in the read-only viewer that renders Knowledge articles and chat messages —
        so we emit the normalized shape up front and both agree.
        """
        return (
            '<table class="table table-bordered o_table">\n<tbody>\n'
            + text
            + '</tbody>\n</table>\n'
        )

    def table_head(self, text):
        """Emit the header row bare — :meth:`table` owns the single ``<tbody>``."""
        return '<tr>\n' + text + '</tr>\n'

    def table_body(self, text):
        """Pass body rows through — :meth:`table` owns the single ``<tbody>``."""
        return text

    def table_cell(self, text, align=None, head=False):
        """Give header cells Odoo's ``o_table_header`` class (grey, bold heading)."""
        tag = 'th' if head else 'td'
        attrs = ' class="o_table_header"' if head else ''
        if align:
            attrs += ' style="text-align:' + align + '"'
        return '<' + tag + attrs + '>' + text + '</' + tag + '>\n'

    def block_code(self, code, info=None):
        """Render code blocks as plain <pre> without inner <code> wrapper.

        Odoo Knowledge uses plain <pre> tags for code blocks. The default
        mistune output nests <code> inside <pre>, which causes double styling
        (both <pre> background and <code> color/font applied).

        Mermaid fenced blocks get class="mermaid" so that client-side JS
        (mermaid_viewer_patch.js) can render them as SVG diagrams.
        """
        escaped = html_escape(code)
        if info and info.strip().lower() == "mermaid":
            return '<pre class="mermaid">' + escaped + '</pre>\n'
        return '<pre>' + escaped + '</pre>\n'

    # Internal marker to signal checklist items to the parent list() method.
    # Stripped from final output; acts as a processing signal between
    # task_list_item() and list() since unchecked items have no distinguishing class.
    _CHECKLIST_MARKER = "<!-- checklist -->"

    def task_list_item(self, text, checked=False):
        """Render task list items in Odoo's checklist format.

        Overrides mistune 3.2.0's task_lists plugin render function. The plugin
        converts '- [ ]' / '- [x]' items into 'task_list_item' tokens with a
        `checked` flag. Mistune dispatches to instance methods before registered
        plugin functions, so this method takes priority.

        Odoo Knowledge expects no <input> elements; instead it uses
        <li class="o_checked"> for checked items, styled via CSS
        pseudo-elements (checkmark in ::before) in list.scss.
        """
        if checked:
            return self._CHECKLIST_MARKER + '<li class="o_checked">' + text + "</li>\n"
        return self._CHECKLIST_MARKER + "<li>" + text + "</li>\n"

    def list(self, text, ordered, **attrs):
        """Add o_checklist class to unordered lists that contain checkbox items.

        Odoo uses class="o_checklist" for native checklist rendering with
        styled checkmarks instead of raw checkbox inputs.
        """
        if not ordered and self._CHECKLIST_MARKER in text:
            text = text.replace(self._CHECKLIST_MARKER, "")
            return '<ul class="o_checklist">\n' + text + '</ul>\n'
        return super().list(text, ordered, **attrs)

    def image(self, text, url, title=None):
        """Render images with Bootstrap's img-fluid so they scale to the article width.

        The relative ``src`` (e.g. ``img/foo.png``) is kept as-is here; the skill
        sync (``SkillSyncService._embed_body_images``) uploads the referenced file
        as an ``ir.attachment`` and rewrites the ``src`` to ``/web/image/<id>`` so
        Knowledge can serve it. The ``o_we_custom_image`` class matches what Odoo's
        editor adds to inserted images.
        """
        html = super().image(text, url, title)
        return html.replace("<img ", '<img class="img-fluid o_we_custom_image" ', 1)


def markdown_to_html(content: str) -> str:
    """
    Convert markdown content to HTML using mistune.

    Supports:
    - Tables (with Odoo/Bootstrap styling classes)
    - Strikethrough
    - Code blocks with syntax highlighting markers

    Output is wrapped in a <div class="o_skill_content"> scope so that
    an app's SCSS can override Odoo's default checklist styling (which
    applies strikethrough + opacity to checked items, making them hard to
    read as documentation).
    """
    renderer = OdooHTMLRenderer()
    md = mistune.create_markdown(renderer=renderer, plugins=["table", "strikethrough", "task_lists"])
    return '<div class="o_skill_content">' + md(content) + '</div>'


def parse_skill_file(file_path: Path) -> dict:
    """
    Parse a complete skill markdown file.

    Returns a dict with:
    - 'name': from frontmatter or derived from filename
    - 'heading': the first ``# heading`` in the body (user-friendly article title), or None
    - 'description': from frontmatter or empty string
    - 'body_html': converted HTML from markdown body
    - 'icon': emoji from frontmatter or default
    - 'file_path': relative path for tracking
    - 'sync_to_knowledge': whether this file should be published to Knowledge (default True).
      Set ``sync_to_knowledge: false`` in YAML front matter for agent-only / internal tooling skills.
    """
    content = file_path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(content)

    metadata = parsed["metadata"]
    body_md = parsed["body"]

    # First # heading — preferred article title (friendlier than the frontmatter
    # ``name`` slug). Computed here from the already-read body so callers don't
    # need to re-read the file just to extract it.
    heading_match = re.search(r"^#\s+(.+)$", body_md, re.MULTILINE)
    heading = heading_match.group(1).strip() if heading_match else None

    # Get title from frontmatter or filename
    name = metadata.get("name") or metadata.get("title")
    if not name:
        # Derive from filename: "SKILL.md" or "glossary.md"
        name = file_path.stem.replace("-", " ").title()
        if name.upper() == "SKILL":
            # Use parent directory name for SKILL.md files
            name = file_path.parent.name.replace("-", " ").title()

    # Only explicit YAML false opts out; missing key defaults to publishing to Knowledge.
    _sk = metadata.get("sync_to_knowledge", True)
    sync_to_knowledge = False if _sk is False else True

    return {
        "name": name,
        "heading": heading,
        "description": metadata.get("description", ""),
        "body_html": markdown_to_html(body_md),
        "icon": metadata.get("icon", "📚"),
        "file_path": str(file_path),
        "sync_to_knowledge": sync_to_knowledge,
    }
