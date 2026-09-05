"""The model recommendation must be calibrated and monotonic: on the reference
machine it reproduces the measured table, and a slower machine is never told
to run a bigger model than a faster one."""

import unittest

from guya import benchmark, profiler

CPU_PROFILE = {"ram_gb": 16, "has_cuda": False, "vram_gb": 0, "apple_silicon": True}


def recommended(rtf_base, language):
    options = profiler.recommend_models(dict(CPU_PROFILE))
    benchmark.annotate_and_recommend(options, rtf_base, language=language)
    chosen = [o for o in options if o["recommended"]]
    return chosen[0]["model_size"] if chosen[0]["backend"] != "cloud" else "cloud"


class CalibrationTests(unittest.TestCase):
    def test_reference_machine_reproduces_measured_table(self):
        for model, measured in benchmark.MEASURED_RTF.items():
            self.assertAlmostEqual(measured, benchmark.predict_rtf(benchmark.REFERENCE_PROXY_RTF, model), places=2)

    def test_turbo_is_recommended_on_the_reference_machine_for_every_language(self):
        for language in ("fa", "en", "dual"):
            self.assertEqual("large-v3-turbo", recommended(benchmark.REFERENCE_PROXY_RTF, language))

    def test_a_very_slow_machine_is_sent_online(self):
        self.assertEqual("cloud", recommended(1.0, "fa"))
        self.assertEqual("cloud", recommended(1.0, "en"))

    def test_persian_never_gets_a_model_below_turbo(self):
        for rtf in (0.02, 0.05, 0.1, 0.2, 0.5):
            self.assertIn(recommended(rtf, "fa"), ("large-v3-turbo", "large-v3", "cloud"))


class MonotonicityTests(unittest.TestCase):
    def test_accuracy_rank_never_rises_as_the_machine_gets_slower(self):
        rank = dict(benchmark.ACCURACY_RANK, cloud=0)
        for language in ("fa", "en", "dual"):
            last = None
            for i in range(1, 60):
                current = rank[recommended(i / 100.0, language)]
                if last is not None:
                    self.assertLessEqual(current, last, f"{language} at rtf_base={i/100}")
                last = current

    def test_exactly_one_option_is_recommended(self):
        for rtf in (0.03, 0.1, 0.3):
            options = profiler.recommend_models(dict(CPU_PROFILE))
            benchmark.annotate_and_recommend(options, rtf, language="en")
            self.assertEqual(1, sum(1 for o in options if o["recommended"]))


if __name__ == "__main__":
    unittest.main()
