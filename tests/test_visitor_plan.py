import random

import pandas as pd

from src.simulate.visitor import plan_visits


def _plan(visits, cart, form):
    return pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "visits": visits,
                "add_to_cart": cart,
                "form_submit": form,
                "utm_source": "ssp_a",
                "utm_medium": "cpc",
                "utm_campaign": "autumn_sale",
                "utm_content": "news_portal",
            }
        ]
    )


def test_profiles_follow_plan():
    visits = plan_visits(_plan(100, 8, 2), scale=1.0, rng=random.Random(1))
    profiles = pd.Series([v.profile for v in visits]).value_counts()
    assert len(visits) == 100
    assert profiles["cart"] == 8
    assert profiles["lead"] == 2
    assert all(v.utm["utm_source"] == "ssp_a" for v in visits)


def test_goals_over_visits_become_repeat_submits():
    visits = plan_visits(_plan(10, 0, 25), scale=1.0, rng=random.Random(1))
    leads = [v for v in visits if v.profile == "lead"]
    assert len(leads) == 10
    assert sum(1 + v.extra_forms for v in leads) == 25


def test_scale():
    assert len(plan_visits(_plan(200, 10, 4), scale=0.05, rng=random.Random(1))) == 10
