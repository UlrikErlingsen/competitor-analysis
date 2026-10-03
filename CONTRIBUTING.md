# Contributing

Contributions should preserve Rival Signal’s central boundaries: unknowns stay visible and never become "no", nothing counts on the map until a person has reviewed it, the app makes no AI or network calls, named methods come with their limits, no threat scores or forecasts, and fictional demo data only.

Before submitting a change:

```bash
python -m pytest
python -m ruff check .
python -m build
```

Use fictional or openly licensed test data. Do not contribute proprietary course material, customer or respondent data, or third-party content without clear redistribution rights.

