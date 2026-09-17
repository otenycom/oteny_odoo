"""Two roots, two trees; an unchanged run writes nothing; a removed root unpublishes."""
import tempfile
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


def _root(base, name, skill, extra_line=""):
    root = Path(base) / name
    skills = root / ".claude" / "skills"
    (skills / skill / "references").mkdir(parents=True)
    (skills / "SKILL.MD").write_text(f"# {name} skills\n\nIndex of {name}.\n")
    (skills / skill / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: The {skill} skill.\n---\n# {skill}\n\n"
        f"See [the notes](references/notes.md).{extra_line}\n")
    (skills / skill / "references" / "notes.md").write_text(f"# Notes of {skill}\n\nBody.\n")
    return root


@tagged("post_install", "-at_install", "oteny_knowledge_sync")
class TestRoots(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root_a = _root(self.tmp.name, "alpha", "alpha-skill")
        self.root_b = _root(self.tmp.name, "beta", "beta-skill")
        self.Article = self.env["knowledge.article"]
        self.Sync = self.env["oteny.knowledge.sync"]
        self.Param = self.env["ir.config_parameter"].sudo()

    def _configure(self, *roots):
        self.Param.set_param("oteny_knowledge_sync.roots", "\n".join(f"{n}={p}" for n, p in roots))

    def _tree(self, label):
        return self.Article.search([("x_skill_is_managed", "=", True), ("x_skill_root", "=", label)])

    def test_two_roots_make_two_trees_and_links_resolve_inside_each(self):
        self._configure(("Alpha", self.root_a), ("Beta", self.root_b))
        out = self.Sync.sync_skills_to_knowledge()
        self.assertEqual(out["roots"], {"Alpha": 3, "Beta": 3})
        for label, skill in (("Alpha", "alpha-skill"), ("Beta", "beta-skill")):
            tree = self._tree(label)
            self.assertEqual(len(tree), 3, label)
            root = tree.filtered(lambda a: not a.parent_id)
            self.assertEqual(root.name, f"{label} Skills")
            skill_article = tree.filtered(lambda a: a.x_skill_file_path == f"skills/{skill}/SKILL.md")
            notes = tree.filtered(lambda a: a.x_skill_file_path == f"skills/{skill}/references/notes.md")
            self.assertEqual(skill_article.parent_id, root)
            self.assertEqual(notes.parent_id, skill_article)
            self.assertIn(f'href="/knowledge/article/{notes.id}"', skill_article.body)

    def test_an_unchanged_run_writes_nothing(self):
        self._configure(("Alpha", self.root_a))
        self.Sync.sync_skills_to_knowledge()
        before = {a.id: a.write_date for a in self._tree("Alpha")}
        self.env.flush_all()
        self.Sync.sync_skills_to_knowledge()
        after = {a.id: a.write_date for a in self._tree("Alpha")}
        self.assertEqual(before, after)

    def test_a_root_that_leaves_the_list_is_unpublished(self):
        self._configure(("Alpha", self.root_a), ("Beta", self.root_b))
        self.Sync.sync_skills_to_knowledge()
        self.assertEqual(len(self._tree("Beta")), 3)
        self._configure(("Alpha", self.root_a))
        self.Sync.sync_skills_to_knowledge()
        self.assertFalse(self._tree("Beta"))
        self.assertEqual(len(self._tree("Alpha")), 3)

    def test_a_root_without_skills_is_skipped_not_fatal(self):
        empty = Path(self.tmp.name) / "empty"; empty.mkdir()
        self._configure(("Alpha", self.root_a), ("Empty", empty))
        self.assertEqual([label for label, _p in self.Sync._skill_roots()], ["Alpha"])
