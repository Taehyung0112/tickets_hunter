"""Attendee list parsing for real-name (實名制) auto-fill.

Only the pure parsing layer is covered here; the DOM filler needs a live tab.
"""

import pytest

import realname


class TestParseAttendees:
    def test_one_line_is_one_attendee(self):
        assert realname.parse_attendees("王小明,A123456789") == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_order_is_preserved(self):
        raw = "王小明,A123456789\n李小美,B234567890"
        assert [a["name"] for a in realname.parse_attendees(raw)] == ["王小明", "李小美"]

    @pytest.mark.parametrize("raw", [
        "王小明，A123456789",     # full-width comma
        "王小明 , A123456789 ",   # padded
        "王小明\tA123456789",     # tab
    ])
    def test_accepts_common_separators(self, raw):
        assert realname.parse_attendees(raw) == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_id_number_is_upper_cased(self):
        """Taiwan ID letters are upper-case on the document; the gate matches exactly."""
        parsed = realname.parse_attendees("王小明,a123456789")
        assert parsed[0]["id_number"] == "A123456789"

    @pytest.mark.parametrize("raw", [
        "",
        "   \n  \n",
        "# 註解不算一列",
        "只有名字沒有證號",
        ",A123456789",
    ])
    def test_unusable_lines_are_dropped(self, raw):
        assert realname.parse_attendees(raw) == []

    def test_blank_and_comment_lines_do_not_shift_the_pairing(self):
        raw = "# 第一場\n王小明,A123456789\n\n李小美,B234567890\n"
        assert len(realname.parse_attendees(raw)) == 2

    def test_extra_commas_stay_with_the_id(self):
        """Split on the first separator only — a name may legitimately contain one."""
        parsed = realname.parse_attendees("王小明,A123456789,備註")
        assert parsed == [{"name": "王小明", "id_number": "A123456789,備註"}]


class TestParseAttendeesFallback:
    def test_falls_back_to_the_single_buyer_when_no_list(self):
        assert realname.parse_attendees("", "王小明", "A123456789") == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_list_wins_over_the_fallback(self):
        parsed = realname.parse_attendees("李小美,B234567890", "王小明", "A123456789")
        assert parsed == [{"name": "李小美", "id_number": "B234567890"}]

    def test_half_a_fallback_is_no_fallback(self):
        assert realname.parse_attendees("", "王小明", "") == []
        assert realname.parse_attendees("", "", "A123456789") == []


class TestAttendeesFromConfig:
    def test_disabled_yields_nothing_even_with_data(self):
        config = {"contact": {
            "realname_enable": False,
            "realname_attendees": "王小明,A123456789",
        }}
        assert realname.attendees_from_config(config) == []

    def test_enabled_reads_the_list(self):
        config = {"contact": {
            "realname_enable": True,
            "realname_attendees": "王小明,A123456789",
        }}
        assert len(realname.attendees_from_config(config)) == 1

    def test_enabled_falls_back_to_real_name_and_id(self):
        config = {"contact": {
            "realname_enable": True,
            "realname_attendees": "",
            "real_name": "王小明",
            "ID": "A123456789",
        }}
        assert realname.attendees_from_config(config) == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    @pytest.mark.parametrize("config", [{}, {"contact": {}}, {"contact": None}])
    def test_a_config_without_the_section_is_off_not_a_crash(self, config):
        assert realname.attendees_from_config(config) == []


class TestShouldFillForUrl:
    @pytest.mark.parametrize("url", [
        "https://ticketplus.com.tw/confirm/abc/def",
        "https://ticketplus.com.tw/confirmseat/abc/def",
        "https://ticketplus.com.tw/order/abc/def",
    ])
    def test_checkout_pages_are_in_scope(self, url):
        assert realname.should_fill_for_url(url) is True

    @pytest.mark.parametrize("url", [
        "https://ticketplus.com.tw/",
        "https://ticketplus.com.tw/activity/21d3c3504ff522a6732789a46f5796d7",
        "",
        None,
    ])
    def test_everything_else_is_out_of_scope(self, url):
        assert realname.should_fill_for_url(url) is False

    def test_only_the_confirmation_page_is_worth_waiting_for(self):
        """The order page is polled every tick; blocking there costs grab latency."""
        assert realname.wait_budget_for_url("https://ticketplus.com.tw/confirm/a/b") > 0
        assert realname.wait_budget_for_url("https://ticketplus.com.tw/order/a/b") == 0
