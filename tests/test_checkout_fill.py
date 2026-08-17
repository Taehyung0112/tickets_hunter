"""Pure layers of the checkout autofill: attendee parsing, card prefix, scope.

The injected observer itself needs a live tab and is exercised by hand.
"""

import pytest

import checkout_fill


class TestParseAttendees:
    def test_one_line_is_one_attendee(self):
        assert checkout_fill.parse_attendees("王小明,A123456789") == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_order_is_preserved(self):
        raw = "王小明,A123456789\n李小美,B234567890"
        assert [a["name"] for a in checkout_fill.parse_attendees(raw)] == ["王小明", "李小美"]

    @pytest.mark.parametrize("raw", [
        "王小明，A123456789",     # full-width comma
        "王小明 , A123456789 ",   # padded
        "王小明\tA123456789",     # tab
    ])
    def test_accepts_common_separators(self, raw):
        assert checkout_fill.parse_attendees(raw) == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_id_number_is_upper_cased(self):
        """Taiwan ID letters are upper-case on the document; the gate matches exactly."""
        parsed = checkout_fill.parse_attendees("王小明,a123456789")
        assert parsed[0]["id_number"] == "A123456789"

    @pytest.mark.parametrize("raw", [
        "",
        "   \n  \n",
        "# 註解不算一列",
        "只有名字沒有證號",
        ",A123456789",
    ])
    def test_unusable_lines_are_dropped(self, raw):
        assert checkout_fill.parse_attendees(raw) == []

    def test_blank_and_comment_lines_do_not_shift_the_pairing(self):
        raw = "# 第一場\n王小明,A123456789\n\n李小美,B234567890\n"
        assert len(checkout_fill.parse_attendees(raw)) == 2

    def test_extra_commas_stay_with_the_id(self):
        """Split on the first separator only — a name may legitimately contain one."""
        parsed = checkout_fill.parse_attendees("王小明,A123456789,備註")
        assert parsed == [{"name": "王小明", "id_number": "A123456789,備註"}]


class TestParseAttendeesFallback:
    def test_falls_back_to_the_single_buyer_when_no_list(self):
        assert checkout_fill.parse_attendees("", "王小明", "A123456789") == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    def test_list_wins_over_the_fallback(self):
        parsed = checkout_fill.parse_attendees("李小美,B234567890", "王小明", "A123456789")
        assert parsed == [{"name": "李小美", "id_number": "B234567890"}]

    def test_half_a_fallback_is_no_fallback(self):
        assert checkout_fill.parse_attendees("", "王小明", "") == []
        assert checkout_fill.parse_attendees("", "", "A123456789") == []


class TestAttendeesFromConfig:
    def test_disabled_yields_nothing_even_with_data(self):
        config = {"contact": {
            "realname_enable": False,
            "realname_attendees": "王小明,A123456789",
        }}
        assert checkout_fill.attendees_from_config(config) == []

    def test_enabled_reads_the_list(self):
        config = {"contact": {
            "realname_enable": True,
            "realname_attendees": "王小明,A123456789",
        }}
        assert len(checkout_fill.attendees_from_config(config)) == 1

    def test_enabled_falls_back_to_real_name_and_id(self):
        config = {"contact": {
            "realname_enable": True,
            "realname_attendees": "",
            "real_name": "王小明",
            "ID": "A123456789",
        }}
        assert checkout_fill.attendees_from_config(config) == [
            {"name": "王小明", "id_number": "A123456789"}
        ]

    @pytest.mark.parametrize("config", [{}, {"contact": {}}, {"contact": None}])
    def test_a_config_without_the_section_is_off_not_a_crash(self, config):
        assert checkout_fill.attendees_from_config(config) == []


class TestShouldFillForUrl:
    @pytest.mark.parametrize("url", [
        "https://ticketplus.com.tw/confirm/abc/def",
        "https://ticketplus.com.tw/confirmseat/abc/def",
        "https://ticketplus.com.tw/order/abc/def",
    ])
    def test_checkout_pages_are_in_scope(self, url):
        assert checkout_fill.should_fill_for_url(url) is True

    @pytest.mark.parametrize("url", [
        "https://ticketplus.com.tw/",
        "https://ticketplus.com.tw/activity/21d3c3504ff522a6732789a46f5796d7",
        "",
        None,
    ])
    def test_everything_else_is_out_of_scope(self, url):
        assert checkout_fill.should_fill_for_url(url) is False


class TestCardPrefix:
    @pytest.mark.parametrize("raw, expected", [
        ("412345", "412345"),
        ("4123 4567", "41234567"),
        ("4123-4567", "41234567"),
        ("41234567890123", "41234567"),   # capped at 8
        ("", ""),
        ("abc", ""),
    ])
    def test_digits_only_capped_at_eight(self, raw, expected):
        config = {"contact": {"credit_card_prefix": raw}}
        assert checkout_fill.card_prefix_from_config(config) == expected

    def test_card_prefix_is_independent_of_the_realname_switch(self):
        """A card-issuer presale needs the prefix whether or not it is real-name."""
        config = {"contact": {"credit_card_prefix": "412345", "realname_enable": False}}
        assert checkout_fill.card_prefix_from_config(config) == "412345"

    @pytest.mark.parametrize("config", [{}, {"contact": {}}, {"contact": None}])
    def test_a_config_without_the_section_is_empty_not_a_crash(self, config):
        assert checkout_fill.card_prefix_from_config(config) == ""


class TestAllowsCardPrefix:
    def test_order_page_only(self):
        assert checkout_fill.allows_card_prefix("https://ticketplus.com.tw/order/a/b") is True

    @pytest.mark.parametrize("url", [
        "https://ticketplus.com.tw/confirm/a/b",
        "https://ticketplus.com.tw/confirmseat/a/b",
        "https://ticketplus.com.tw/activity/abc",
        "",
        None,
    ])
    def test_never_on_a_payment_or_browse_page(self, url):
        """The confirmation page takes the real card number, not a prefix."""
        assert checkout_fill.allows_card_prefix(url) is False


class TestInstallScript:
    def _script(self, **kwargs):
        kwargs.setdefault("attendees", [{"name": "王小明", "id_number": "A123456789"}])
        kwargs.setdefault("card_prefix", "412345")
        kwargs.setdefault("allow_card", True)
        return checkout_fill._build_install_script(**kwargs)

    def test_config_is_embedded_as_json(self):
        assert '"card_prefix": "412345"' in self._script()
        assert '"王小明"' in self._script()

    def test_no_placeholder_survives(self):
        assert "__CONFIG__" not in self._script()

    def test_card_keywords_cannot_match_a_full_card_number_label(self):
        """信用卡號 on the payment page must never classify as a prefix box."""
        label = "信用卡號"
        assert not any(kw in label for kw in checkout_fill.CONST_CARD_LABEL_KEYWORDS)
