"""Evaluation protocol constants."""

# A review team works a fixed number of alerts a day, which is what makes
# precision at that depth the metric and accuracy meaningless at 0.8% positives.
DAILY_BUDGET = 100

# Reported alongside the budget to show how the curve falls off.
BUDGET_SWEEP = (20, 50, 100, 200)
