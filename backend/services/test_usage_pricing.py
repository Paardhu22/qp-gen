"""Pricing tokens in rupees. See services/usage_pricing.py."""

from django.test import TestCase, override_settings

from services.usage_pricing import (
    format_inr,
    inr_cost,
    inr_cost_of_rows,
    rate_for,
    usd_cost,
    usd_to_inr_rate,
)


class RateLookupTests(TestCase):
    def test_a_known_model_gets_its_own_rate(self):
        self.assertEqual(rate_for("gpt-4.1-mini"), (0.40, 1.60))

    def test_a_dated_snapshot_bills_at_its_base_rate(self):
        self.assertEqual(rate_for("gpt-4.1-mini-2025-04-14"), (0.40, 1.60))

    def test_the_longest_prefix_wins(self):
        # Otherwise "gpt-4.1-mini-..." would bill at the (much dearer) gpt-4.1 rate.
        self.assertEqual(rate_for("gpt-4.1-mini-2025-04-14"), rate_for("gpt-4.1-mini"))
        self.assertNotEqual(rate_for("gpt-4.1-mini"), rate_for("gpt-4.1"))

    def test_an_unknown_model_is_never_free(self):
        # A zero would read as "this stage costs nothing", which is worse than
        # a plausible estimate.
        prompt, completion = rate_for("some-model-we-have-never-heard-of")
        self.assertGreater(prompt, 0)
        self.assertGreater(completion, 0)

    @override_settings(MODEL_PRICING_USD_JSON='{"gpt-4.1-mini": [1.0, 2.0]}')
    def test_a_deployment_can_correct_a_stale_price(self):
        self.assertEqual(rate_for("gpt-4.1-mini"), (1.0, 2.0))

    @override_settings(MODEL_PRICING_USD_JSON='{"text-embedding-3-small": 0.05}')
    def test_a_single_number_means_the_same_rate_both_ways(self):
        self.assertEqual(rate_for("text-embedding-3-small"), (0.05, 0.05))

    @override_settings(MODEL_PRICING_USD_JSON="{not json at all")
    def test_a_malformed_override_is_ignored_rather_than_raised(self):
        # A typo in an env var must not take the analytics dashboard down.
        self.assertEqual(rate_for("gpt-4.1-mini"), (0.40, 1.60))


class ConversionTests(TestCase):
    def test_cost_is_per_million_tokens(self):
        self.assertAlmostEqual(usd_cost("gpt-4.1-mini", 1_000_000, 0), 0.40, places=6)
        self.assertAlmostEqual(usd_cost("gpt-4.1-mini", 0, 1_000_000), 1.60, places=6)

    @override_settings(USD_TO_INR=90.0)
    def test_rupees_are_dollars_times_the_rate(self):
        self.assertAlmostEqual(inr_cost("gpt-4.1-mini", 1_000_000, 0), 36.0, places=2)

    @override_settings(USD_TO_INR=0)
    def test_a_nonsense_rate_falls_back_rather_than_zeroing_every_figure(self):
        self.assertGreater(usd_to_inr_rate(), 0)

    def test_rows_are_priced_per_model_not_on_their_combined_total(self):
        # Pricing a combined total would bill image generation at the chat rate.
        rows = [
            {"model": "gpt-4.1-mini", "prompt": 1_000_000, "completion": 0},
            {"model": "gpt-image-1", "prompt": 0, "completion": 1_000_000},
        ]
        expected = (0.40 + 40.00) * usd_to_inr_rate()
        self.assertAlmostEqual(inr_cost_of_rows(rows), round(expected, 2), places=2)

    def test_formatting_is_for_humans(self):
        self.assertEqual(format_inr(1840.5), "₹1,840.50")
