from __future__ import annotations

import unittest

from knoarbor.core.evidence_alignment import align_evidence_quote, canonical_evidence_text


class EvidenceAlignmentTests(unittest.TestCase):
    def test_cjk_layout_break_maps_to_original_raw_slice(self) -> None:
        raw = "适用于智能制造、工\n业4.0场景。"

        self.assertEqual(canonical_evidence_text(raw), "适用于智能制造、工业4.0场景。")
        alignment = align_evidence_quote(raw, "适用于智能制造、工业4.0场景")

        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment.excerpt, "适用于智能制造、工\n业4.0场景")
        self.assertEqual(raw[alignment.raw_start : alignment.raw_end], alignment.excerpt)

    def test_non_cjk_layout_break_projects_to_one_space(self) -> None:
        raw = "smart\nmanufacturing"

        self.assertEqual(canonical_evidence_text(raw), "smart manufacturing")
        self.assertIsNotNone(align_evidence_quote(raw, "smart manufacturing"))
        self.assertIsNone(align_evidence_quote(raw, "smartmanufacturing"))

    def test_hard_break_and_horizontal_whitespace_are_not_normalized(self) -> None:
        self.assertIsNone(align_evidence_quote("第一段。\n\n第二段。", "第一段。第二段。"))
        self.assertIsNone(align_evidence_quote("a\tb", "a b"))
        self.assertIsNone(align_evidence_quote("a  b", "a b"))

    def test_punctuation_ocr_and_unicode_variants_are_rejected(self) -> None:
        self.assertIsNone(align_evidence_quote("工业4，0。", "工业4.0。"))
        self.assertIsNone(align_evidence_quote("O型密封圈", "0型密封圈"))
        self.assertIsNone(align_evidence_quote("ＡＩ平台", "AI平台"))

    def test_repeated_quote_uses_first_source_occurrence(self) -> None:
        raw = "北极光常呈绿色。北极光常呈绿色。"

        alignment = align_evidence_quote(raw, "北极光常呈绿色。")

        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment.raw_start, 0)


if __name__ == "__main__":
    unittest.main()
