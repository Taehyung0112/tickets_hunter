"""Behaviour snapshot of the text-normalisation helpers.

full2half() is deliberately absent: it has no callers anywhere in the tree and
is scheduled for removal.
"""

import pytest

import util


class TestChineseNumeric:
    @pytest.mark.parametrize(
        "char, expected",
        [
            ("3", 3),
            ("３", 3),  # full-width
            ("三", 3),
            ("叁", 3),  # formal
            ("③", 3),
            ("❸", 3),
            ("⑶", 3),
            ("three", 3),
            ("零", 0),
            ("九", 9),
        ],
    )
    def test_all_notations_map_to_the_same_int(self, char, expected):
        assert util.chinese_numeric_to_int(char) == expected

    def test_case_is_ignored_for_english(self):
        assert util.chinese_numeric_to_int("THREE") == 3

    def test_unmapped_char_returns_none(self):
        assert util.chinese_numeric_to_int("x") is None

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("第三區", "3"),
            ("VIP1", "1"),
            ("一壘", "1"),
            ("沒有數字", ""),
            ("", ""),
        ],
    )
    def test_normalize_keeps_only_digits(self, text, expected):
        assert util.normalize_chinese_numeric(text) == expected


class TestContinuousPattern:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("票價3280元", "3280"),
            ("3280", "3280"),
            ("無數字", ""),
            ("", ""),
        ],
    )
    def test_find_continuous_number(self, text, expected):
        assert util.find_continuous_number(text) == expected

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("12a34", "12"),  # first run wins, the rest is unreachable
            ("a12", "12"),  # leading noise is skipped
            ("票價3280元x99", "3280"),
        ],
    )
    def test_only_the_first_run_is_returned(self, text, expected):
        """Once a run has started and ended, later runs cannot be collected.

        find_continuous_pattern() only opens a run while `len(ret) == 0`, so
        after the first digits are captured every later group is dropped.
        """
        assert util.find_continuous_number(text) == expected


class TestRemoveHtmlTags:
    @pytest.mark.parametrize(
        "html, expected",
        [
            ("<b>VIP</b> 區", "VIP 區"),
            ("<div class='x'>內野</div>", "內野"),
            ("純文字", "純文字"),
            ("", ""),
        ],
    )
    def test_tags_are_stripped(self, html, expected):
        assert util.remove_html_tags(html) == expected
