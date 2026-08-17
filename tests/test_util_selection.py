"""Behaviour snapshot of the selection-policy layer.

get_target_index_by_mode() and get_matched_blocks_by_keyword_item_set() are the
shared policy that all 10 platform modules re-glue by hand. Extracting that
duplication later needs these pinned first.
"""

import pytest

import util


class FakeRow:
    """Stands in for the DOM element the real callers pass in."""

    def __init__(self, html):
        self._html = html

    def get_attribute(self, name):
        assert name == "innerHTML"
        return self._html


class TestGetTargetIndexByMode:
    @pytest.mark.parametrize("mode", ["from top to bottom", "from_top_to_bottom"])
    def test_top_is_first_in_both_spellings(self, mode):
        assert util.get_target_index_by_mode(5, mode) == 0

    @pytest.mark.parametrize(
        "length, expected", [(1, 0), (2, 1), (5, 4), (10, 9)]
    )
    def test_bottom_is_last(self, length, expected):
        assert util.get_target_index_by_mode(length, "from bottom to top") == expected

    @pytest.mark.parametrize("length, expected", [(1, 0), (2, 1), (5, 2), (10, 5)])
    def test_center_is_floor_division(self, length, expected):
        assert util.get_target_index_by_mode(length, "center") == expected

    @pytest.mark.parametrize(
        "mode", ["from top to bottom", "from bottom to top", "center", "random"]
    )
    def test_empty_list_yields_none(self, mode):
        assert util.get_target_index_by_mode(0, mode) is None

    def test_random_stays_in_range_and_can_reach_both_ends(self):
        drawn = {util.get_target_index_by_mode(10, "random") for _ in range(300)}
        assert drawn <= set(range(10))
        assert {0, 9} <= drawn, "random should be able to reach both ends"


class TestGetMatchedBlocksByKeywordItemSet:
    ROWS = [
        FakeRow("<div>內野一壘 3,280</div>"),
        FakeRow("<div>內野三壘 3,280</div>"),
        FakeRow("<div>外野 1,280</div>"),
        FakeRow("<div>內野一壘 2,280</div>"),
    ]
    # keyword_exclude is read with bare indexing, not .get() - see
    # test_config_without_keyword_exclude_raises below.
    CONFIG = {"keyword_exclude": '"輪椅","身障"'}

    def test_single_keyword_matches_every_row(self):
        matched = util.get_matched_blocks_by_keyword_item_set(
            self.CONFIG, "random", "內野一壘", self.ROWS
        )
        assert len(matched) == 2

    def test_top_to_bottom_short_circuits_after_first_hit(self):
        matched = util.get_matched_blocks_by_keyword_item_set(
            self.CONFIG, "from top to bottom", "內野一壘", self.ROWS
        )
        assert len(matched) == 1
        assert matched[0] is self.ROWS[0]

    def test_space_is_and_across_the_row_text(self):
        matched = util.get_matched_blocks_by_keyword_item_set(
            self.CONFIG, "random", "內野一壘 2,280", self.ROWS
        )
        assert matched == [self.ROWS[3]]

    def test_no_match_returns_empty(self):
        matched = util.get_matched_blocks_by_keyword_item_set(
            self.CONFIG, "random", "貴賓包廂", self.ROWS
        )
        assert matched == []

    def test_excluded_rows_are_dropped_before_matching(self):
        rows = [FakeRow("<div>內野一壘 輪椅席</div>"), FakeRow("<div>內野一壘 3,280</div>")]
        matched = util.get_matched_blocks_by_keyword_item_set(
            self.CONFIG, "random", "內野一壘", rows
        )
        assert matched == [rows[1]]

    def test_html_is_stripped_before_matching(self):
        rows = [FakeRow("<span class='內野三壘'>內野一壘</span>")]
        # the class attribute must not be matchable - only the visible text is
        assert (
            util.get_matched_blocks_by_keyword_item_set(self.CONFIG, "random", "內野三壘", rows)
            == []
        )
        assert (
            len(util.get_matched_blocks_by_keyword_item_set(self.CONFIG, "random", "內野一壘", rows))
            == 1
        )

    def test_config_without_keyword_exclude_raises(self):
        """Pins the brittleness: the config contract is mandatory, not optional.

        reset_row_text_if_match_keyword_exclude() indexes config_dict directly.
        Real callers always pass the full config so this never fires in
        production, but any new caller passing a partial dict gets a KeyError
        rather than a sane default.
        """
        with pytest.raises(KeyError):
            util.get_matched_blocks_by_keyword_item_set({}, "random", "內野一壘", self.ROWS)
