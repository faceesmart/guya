"""The scorer behind every accuracy number in the report must itself be right."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval"))

from wer import cer_counts, normalize_en, normalize_fa, wer, wer_counts  # noqa: E402


class NormalizeEnglishTests(unittest.TestCase):
    def test_identical_text_scores_zero(self):
        self.assertEqual(wer_counts("hello world", "hello world", "en"), (0, 2))

    def test_case_and_punctuation_are_ignored(self):
        self.assertEqual(wer("Hello, World!", "hello world", "en"), 0.0)

    def test_spelled_numbers_match_digits(self):
        # Whisper writes digits; a correct transcription must not be an error.
        self.assertEqual(wer("he bought twelve apples", "he bought 12 apples", "en"), 0.0)
        self.assertEqual(normalize_en("twenty-one dogs"), "21 dogs")
        self.assertEqual(normalize_en("three o'clock"), "3 o clock")

    def test_bare_tens_and_and_are_left_alone(self):
        self.assertEqual(normalize_en("twenty and thirty"), "20 and 30")

    def test_substitution_counts_one_edit(self):
        self.assertEqual(wer_counts("send the report", "send a report", "en"), (1, 3))

    def test_empty_hypothesis_is_all_deletions(self):
        self.assertEqual(wer_counts("one two three", "", "en"), (3, 3))


class NormalizePersianTests(unittest.TestCase):
    def test_arabic_letter_forms_are_unified(self):
        self.assertEqual(normalize_fa("كتاب علي"), normalize_fa("کتاب علی"))

    def test_diacritics_and_zwnj_are_removed(self):
        self.assertEqual(normalize_fa("می‌خواهم"), normalize_fa("میخواهم"))
        self.assertEqual(normalize_fa("مَدرَسه"), "مدرسه")

    def test_latin_words_are_lowercased_inside_persian(self):
        self.assertEqual(wer("گزارش GitHub", "گزارش github", "fa"), 0.0)

    def test_persian_digits_and_number_words(self):
        self.assertEqual(normalize_fa("۴۰ زندانی"), "40 زندانی")
        self.assertEqual(normalize_fa("بیست و یک نفر"), "21 نفر")
        self.assertEqual(normalize_fa("دوازده کتاب"), "12 کتاب")

    def test_standalone_conjunction_is_preserved(self):
        self.assertEqual(normalize_fa("کتاب و دفتر"), "کتاب و دفتر")

    def test_punctuation_is_ignored(self):
        self.assertEqual(wer("سلام، این یک آزمایش است.", "سلام این یک آزمایش است", "fa"), 0.0)

    def test_cer_ignores_spaces(self):
        # Word-boundary disagreement costs one word but zero characters.
        self.assertEqual(wer_counts("کتاب ها", "کتابها", "fa")[0], 2)
        self.assertEqual(cer_counts("کتاب ها", "کتابها", "fa")[0], 0)


if __name__ == "__main__":
    unittest.main()
