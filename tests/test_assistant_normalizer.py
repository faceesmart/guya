import unittest

from guya.assistant.normalizer import (
    filename_match_score,
    normalize_spoken_filename,
)


class AssistantFilenameNormalizerTests(unittest.TestCase):
    def test_english_number_and_docx_homophones_are_equivalent(self):
        variants = (
            "test six docks",
            "test 6 docs file",
            "test6 docx",
            "test6.docx",
        )
        normalized = {normalize_spoken_filename(item) for item in variants}
        self.assertEqual({"test 6 docx", "test6 docx"}, normalized)
        for item in variants:
            score, exact = filename_match_score(item, "test6.docx")
            self.assertEqual(1.0, score)
            self.assertTrue(exact)

    def test_persian_numbers_and_digits_are_equivalent(self):
        score, exact = filename_match_score(
            "گزارش شش ورد",
            "گزارش ۶.docx",
        )
        self.assertEqual(1.0, score)
        self.assertTrue(exact)

    def test_compound_numbers_work_in_both_languages(self):
        self.assertEqual(
            "report 21 docx",
            normalize_spoken_filename("report twenty one.docx"),
        )
        self.assertEqual(
            "گزارش 21 docx",
            normalize_spoken_filename("گزارش بیست و یک.docx"),
        )
        self.assertEqual(
            "report 21 docx",
            normalize_spoken_filename("report twenty one word file"),
        )

    def test_related_but_different_filename_is_not_exact(self):
        score, exact = filename_match_score(
            "test six docks",
            "test6 notes.docx",
        )
        self.assertGreaterEqual(score, 0.80)
        self.assertFalse(exact)

    def test_one_character_candidate_is_not_a_match_for_long_query(self):
        score, exact = filename_match_score("system", "m")
        self.assertFalse(exact)
        self.assertLess(score, 0.58)


if __name__ == "__main__":
    unittest.main()
