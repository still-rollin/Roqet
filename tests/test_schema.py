import unittest

from roqet.embedder import HashEmbedder
from roqet.enrich import enrich_declarations
from roqet.schema import normalize_declaration


class SchemaTests(unittest.TestCase):
    def test_normalizes_old_phase_one_shape(self) -> None:
        declaration = normalize_declaration(
            {
                "name": "addnC",
                "kind": "Lemma",
                "type": "commutative addn",
                "doc": "Addition is commutative.",
                "module": "ssreflect.ssrnat",
                "library": "mathcomp",
                "file": "ssreflect/ssrnat.v",
                "line": 10,
            }
        )

        self.assertEqual(declaration["type_signature"], "commutative addn")
        self.assertEqual(declaration["docstring"], "Addition is commutative.")
        self.assertEqual(declaration["module_path"], "ssreflect.ssrnat")
        self.assertEqual(declaration["line_number"], 10)

    def test_enrichment_fills_missing_docstrings(self) -> None:
        enriched = enrich_declarations(
            [
                {
                    "name": "map_id",
                    "kind": "Lemma",
                    "type_signature": "forall xs, map id xs = xs",
                    "library": "stdlib",
                    "file_path": "Lists/List.v",
                    "line_number": 1,
                }
            ]
        )
        self.assertTrue(enriched[0]["docstring"])
        self.assertTrue(enriched[0]["docstring_generated"])

    def test_hash_embedder_is_deterministic(self) -> None:
        embedder = HashEmbedder()
        first = embedder.embed(["commutativity of addition"])[0]
        second = embedder.embed(["commutativity of addition"])[0]

        self.assertEqual(first, second)
        self.assertEqual(len(first), embedder.dim)


if __name__ == "__main__":
    unittest.main()
