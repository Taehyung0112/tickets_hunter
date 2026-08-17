"""Behaviour snapshot of the keyword matching layer.

These pin current behaviour so the planned SelectionPolicy extraction can prove
it changed nothing. They are not a specification.
"""

import pytest

import util


class TestIsTextMatchKeyword:
    @pytest.mark.parametrize(
        "keyword, text",
        [
            ('"11/16"', "2026/11/16 (六) 19:30"),  # already quoted
            ("11/16", "2026/11/16 (六) 19:30"),  # bare
            ("11/16;11/17", "2026/11/17 (日) 14:00"),  # second alternative
            ("三壘;一壘", "內野一壘 3,280"),
        ],
    )
    def test_semicolon_is_or(self, keyword, text):
        assert util.is_text_match_keyword(keyword, text) is True

    def test_space_is_and(self):
        assert util.is_text_match_keyword("週六 19:30", "11/16 (週六) 19:30") is True
        # "週六" missing -> the AND fails even though "19:30" is present
        assert util.is_text_match_keyword("週六 19:30", "11/17 (週日) 19:30") is False

    @pytest.mark.parametrize("keyword", ['"3,280"', "3,280;2,680"])
    def test_comma_is_a_thousands_separator_not_a_delimiter(self, keyword):
        assert util.is_text_match_keyword(keyword, "票價 3,280 元") is True

    def test_no_match_returns_false(self):
        assert util.is_text_match_keyword("找不到", "完全不相干") is False

    def test_empty_means_match_everything(self):
        """Load-bearing: an empty filter must not select nothing.

        Both guards return True. If a refactor flips either to False the bot
        silently stops picking anything when the user leaves a keyword blank.
        """
        assert util.is_text_match_keyword("", "任何文字") is True
        assert util.is_text_match_keyword("關鍵字", "") is True


class TestKeywordFormatRoundTrip:
    @pytest.mark.parametrize(
        "stored, displayed",
        [
            ('"AA BB","CC","DD"', "AA BB;CC;DD"),
            ('"3,280","2,680"', "3,280;2,680"),
            ('"單一"', "單一"),
            ("", ""),
        ],
    )
    def test_json_to_display(self, stored, displayed):
        assert util.format_keyword_for_display(stored) == displayed

    @pytest.mark.parametrize(
        "stored", ['"AA BB","CC","DD"', '"3,280","2,680"', '"單一"', ""]
    )
    def test_round_trip_is_stable(self, stored):
        displayed = util.format_keyword_for_display(stored)
        assert util.format_config_keyword_for_json(displayed) == stored

    def test_blank_items_are_dropped(self):
        assert util.format_config_keyword_for_json("A;;B") == '"A","B"'

    def test_json_conversion_is_not_idempotent(self):
        """Known defect, pinned so a refactor cannot change it unnoticed.

        format_config_keyword_for_json() carries a "for idempotency" comment,
        but applying it twice strips the quotes and leaves commas with no
        semicolon left to split on - so N keywords silently collapse into one.

        Safe today only because the UI always round-trips through
        format_keyword_for_display() first. Feeding stored JSON straight back
        in would turn two areas into one unmatchable literal.
        """
        once = util.format_config_keyword_for_json("內野一壘;內野三壘")
        assert once == '"內野一壘","內野三壘"'

        twice = util.format_config_keyword_for_json(once)
        assert twice == '"內野一壘,內野三壘"'
        assert twice != once
