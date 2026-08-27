from abhayleads.models import LeadCandidate
from abhayleads.scoring import is_excluded, score_candidate

BASE_CONFIG = {
    "product": {
        "keywords": ["looking for a crm", "alternative to salesforce"],
        "exclude_keywords": ["hiring"],
    },
    "scoring": {
        "points_per_keyword": 20,
        "title_match_bonus": 15,
        "source_weights": {"hackernews": 1.0, "reddit": 0.5},
    },
}


def make_candidate(**overrides):
    defaults = dict(
        source="hackernews",
        source_detail="1",
        title="",
        raw_text="",
    )
    defaults.update(overrides)
    return LeadCandidate(**defaults)


def test_no_keywords_configured_scores_zero():
    config = {"product": {"keywords": []}, "scoring": {}}
    candidate = make_candidate(raw_text="looking for a crm")
    score, matched = score_candidate(candidate, config)
    assert score == 0
    assert matched == ""


def test_no_match_scores_zero():
    candidate = make_candidate(raw_text="completely unrelated text")
    score, matched = score_candidate(candidate, BASE_CONFIG)
    assert score == 0
    assert matched == ""


def test_body_match_scores_points_per_keyword():
    candidate = make_candidate(raw_text="we are looking for a crm right now")
    score, matched = score_candidate(candidate, BASE_CONFIG)
    assert score == 20
    assert matched == "looking for a crm"


def test_title_match_gets_bonus_on_top_of_body_points():
    candidate = make_candidate(title="looking for a crm", raw_text="looking for a crm")
    score, _ = score_candidate(candidate, BASE_CONFIG)
    assert score == 20 + 15


def test_multiple_keyword_matches_stack():
    candidate = make_candidate(
        raw_text="looking for a crm, ideally an alternative to salesforce"
    )
    score, matched = score_candidate(candidate, BASE_CONFIG)
    assert score == 40
    assert "looking for a crm" in matched
    assert "alternative to salesforce" in matched


def test_source_weight_applied():
    candidate = make_candidate(source="reddit", raw_text="looking for a crm")
    score, _ = score_candidate(candidate, BASE_CONFIG)
    assert score == 10  # 20 * 0.5


def test_score_clamped_to_100():
    config = {
        "product": {"keywords": ["a", "b", "c", "d", "e", "f"]},
        "scoring": {"points_per_keyword": 50, "title_match_bonus": 0, "source_weights": {}},
    }
    candidate = make_candidate(raw_text="a b c d e f")
    score, _ = score_candidate(candidate, config)
    assert score == 100


def test_is_excluded_true_when_exclude_keyword_present():
    candidate = make_candidate(raw_text="we are hiring a sales rep")
    assert is_excluded(candidate, BASE_CONFIG) is True


def test_is_excluded_false_otherwise():
    candidate = make_candidate(raw_text="looking for a crm")
    assert is_excluded(candidate, BASE_CONFIG) is False


def test_source_base_score_used_when_no_keyword_match():
    config = {
        "product": {"keywords": ["looking for a crm"]},
        "scoring": {"points_per_keyword": 20, "source_base_score": {"osm_places": 30}},
    }
    candidate = make_candidate(source="osm_places", raw_text="Hospital near Baner")
    score, matched = score_candidate(candidate, config)
    assert score == 30
    assert matched == ""


def test_source_base_score_does_not_reduce_a_real_keyword_match():
    config = {
        "product": {"keywords": ["looking for a crm"]},
        "scoring": {"points_per_keyword": 20, "source_base_score": {"osm_places": 30}},
    }
    candidate = make_candidate(source="osm_places", raw_text="we are looking for a crm")
    score, matched = score_candidate(candidate, config)
    assert score == 30  # 20 from the keyword match is lower than the 30 floor
    assert matched == "looking for a crm"


def test_source_base_score_defaults_to_zero_for_unlisted_source():
    config = {"product": {"keywords": []}, "scoring": {}}
    candidate = make_candidate(source="osm_places", raw_text="Hospital near Baner")
    score, _ = score_candidate(candidate, config)
    assert score == 0
