from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from roqet.extract import SourceRoot, iter_declarations


class ExtractTests(unittest.TestCase):
    def test_extracts_declarations_with_docs_and_comments(self) -> None:
        source = """
(** Addition is commutative. *)
Lemma addnC : commutative addn.
Proof. Admitted.

(* A regular comment should not become docs. *)
Definition double (n : nat) : nat := n + n.

(** A doc comment with (* nested text *) inside. *)
Inductive tree : Type := Leaf | Node of tree & tree.
"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "ssreflect" / "ssrnat.v"
            file_path.parent.mkdir()
            file_path.write_text(source, encoding="utf-8")

            declarations = list(iter_declarations(file_path, SourceRoot(root, "mathcomp")))

        self.assertEqual([decl.name for decl in declarations], ["addnC", "double", "tree"])
        self.assertEqual(declarations[0].docstring, "Addition is commutative.")
        self.assertEqual(declarations[0].kind, "Lemma")
        self.assertEqual(declarations[0].type_signature, "commutative addn")
        self.assertEqual(declarations[0].module_path, "ssreflect.ssrnat")
        self.assertEqual(declarations[0].file_path, "ssreflect/ssrnat.v")
        self.assertEqual(declarations[1].docstring, "")
        self.assertEqual(declarations[1].type_signature, "nat")
        self.assertEqual(declarations[2].kind, "Inductive")


if __name__ == "__main__":
    unittest.main()
