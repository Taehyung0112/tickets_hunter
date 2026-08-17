#!/usr/bin/env python3
#encoding=utf-8
"""Checkout fields upstream leaves blank, filled by an injected observer.

TicketPlus real-name events ask for 證件姓名 / 證件號碼 per ticket, and a
card-issuer presale adds a "信用卡前 6/8 碼" qualification box. Upstream's
platforms/ticketplus.py fills neither, and a fix there is reverted by the next
sync, so the filler lives here.

Both boxes render only after the ticket quantity is chosen, part-way through
upstream's select -> code -> agree -> submit chain, which we cannot hook into.
So we inject a MutationObserver instead: it fills each box the moment it
appears. Upstream's steps are await-separated, so the browser event loop — and
therefore the observer — runs before it clicks submit.

Matching is on visible label text, never position.
"""

import json

import util

CONST_SEPARATORS = [",", "，", "\t", ";", "；"]

# Ordered: an id label is tested first because 證件姓名 and 證件號碼 share a prefix.
CONST_ID_LABEL_KEYWORDS = [
    "證件號碼", "證件字號", "身分證", "身份證", "統一證號", "居留證", "護照號碼",
    "護照", "證號", "id number", "identity", "passport",
]

CONST_NAME_LABEL_KEYWORDS = [
    "證件姓名", "持票人", "觀眾姓名", "取票人", "真實姓名", "姓名", "full name", "real name",
]

# "信用卡號" must not match: that is the real card number on the payment page.
CONST_CARD_LABEL_KEYWORDS = [
    "信用卡前", "卡號前", "前六碼", "前6碼", "前八碼", "前8碼", "卡片前", "card prefix", "bin",
]

# Checked before any classification. Without it "持票人手機" matches 持票人 and a
# name lands in a phone box, which also desyncs the name/id pairing.
CONST_LABEL_EXCLUDE_KEYWORDS = [
    "手機", "電話", "phone", "mobile", "email", "e-mail", "信箱", "郵件",
    "生日", "出生", "地址", "驗證碼", "數量", "張數", "備註",
    # The buyer block, not a ticket holder: its 姓名 must not join the pairing.
    "訂購人", "購票人", "購買人", "聯絡人", "收件人",
]

CONST_MAX_CARD_PREFIX_LEN = 8

# Written totals only grow within a page, so this suppresses a per-tick log line
# while still reporting every new field filled. Keyed by tab, reset on install.
_last_written = {}


def parse_attendees(raw, fallback_name="", fallback_id=""):
    """One attendee per line, ``name<sep>id_number``, in ticket order.

    Returns [] when nothing usable is configured; the caller reads that as
    "feature off", not as an error.
    """
    attendees = []

    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        cut = min((line.find(sep) for sep in CONST_SEPARATORS if sep in line), default=-1)
        if cut <= 0:
            continue

        name = line[:cut].strip()
        id_number = line[cut + 1:].strip().upper()
        if name and id_number:
            attendees.append({"name": name, "id_number": id_number})

    if not attendees:
        fallback_name = (fallback_name or "").strip()
        fallback_id = (fallback_id or "").strip().upper()
        if fallback_name and fallback_id:
            attendees.append({"name": fallback_name, "id_number": fallback_id})

    return attendees


def attendees_from_config(config_dict):
    contact = (config_dict or {}).get("contact") or {}
    if not contact.get("realname_enable", False):
        return []

    return parse_attendees(
        contact.get("realname_attendees", ""),
        contact.get("real_name", ""),
        contact.get("ID", ""),
    )


def card_prefix_from_config(config_dict):
    """Digits only, capped at 8.

    A presale box asks for the first 6 or 8 digits depending on the event, so
    the stored value is the longer one and each box is trimmed to its own
    maxlength at fill time.
    """
    contact = (config_dict or {}).get("contact") or {}
    digits = "".join(ch for ch in str(contact.get("credit_card_prefix", "") or "") if ch.isdigit())
    return digits[:CONST_MAX_CARD_PREFIX_LEN]


def should_fill_for_url(url):
    url = (url or "").lower()
    return any(path in url for path in ["/confirm/", "/confirmseat/", "/order/"])


def allows_card_prefix(url):
    """Only the order page.

    The confirmation page is where the real card number is entered; a prefix
    written into a payment field would be a wrong card, not a qualification.
    """
    return "/order/" in (url or "").lower()


CONST_INSTALL_SCRIPT = r"""
(function() {
    const config = __CONFIG__;

    window.__thFillConfig = config;

    if (window.__thFillInstalled) {
        window.__thFillPass();
        return Object.assign({installed: false}, window.__thFillStats);
    }

    const stats = {name_filled: 0, id_filled: 0, card_filled: 0, unpaired_ids: 0, passes: 0, labels: []};
    window.__thFillStats = stats;

    // Our own writes mutate the DOM and re-trigger the observer; the pass is a
    // no-op by then because filled boxes are skipped. The cap is a backstop.
    const MAX_PASSES = 400;

    function labelTextOf(input) {
        const parts = [];
        const wrapper = input.closest('.v-input') || input.closest('.v-text-field') || input.parentElement;
        if (wrapper) {
            wrapper.querySelectorAll('label, .label, .v-label').forEach(function(el) {
                parts.push(el.textContent || '');
            });
        }
        if (input.id) {
            const explicit = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
            if (explicit) parts.push(explicit.textContent || '');
        }
        parts.push(input.placeholder || '');
        parts.push(input.getAttribute('aria-label') || '');
        parts.push(input.name || '');
        parts.push(input.id || '');
        return parts.join(' ').toLowerCase();
    }

    function classify(label) {
        const cfg = window.__thFillConfig;
        for (const keyword of cfg.exclude_keywords) {
            if (label.indexOf(keyword) >= 0) return '';
        }
        for (const keyword of cfg.card_keywords) {
            if (label.indexOf(keyword) >= 0) return 'card';
        }
        for (const keyword of cfg.id_keywords) {
            if (label.indexOf(keyword) >= 0) return 'id';
        }
        for (const keyword of cfg.name_keywords) {
            if (label.indexOf(keyword) >= 0) return 'name';
        }
        return '';
    }

    function setValue(input, value) {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        input.dispatchEvent(new Event('blur', {bubbles: true}));
    }

    function recordLabel(entry) {
        if (stats.labels.indexOf(entry) < 0 && stats.labels.length < 20) {
            stats.labels.push(entry);
        }
    }

    window.__thFillPass = function() {
        const cfg = window.__thFillConfig;
        if (stats.passes >= MAX_PASSES) return;
        stats.passes++;
        stats.unpaired_ids = 0;

        const idInputs = [];
        const cardInputs = [];
        const ordered = [];   // name and id boxes in document order, for pairing

        document.querySelectorAll('input').forEach(function(input) {
            const type = (input.type || 'text').toLowerCase();
            if (['hidden', 'checkbox', 'radio', 'submit', 'button', 'file'].indexOf(type) >= 0) return;
            if (input.offsetParent === null) return;
            if (input.disabled || input.readOnly) return;

            const label = labelTextOf(input);
            const kind = classify(label);
            if (!kind) return;

            recordLabel(kind + ':' + label.trim().slice(0, 40));
            if (kind === 'card') {
                cardInputs.push(input);
                return;
            }
            if (kind === 'id') idInputs.push(input);
            ordered.push({el: input, kind: kind});
        });

        if (cfg.card_prefix && cfg.allow_card) {
            cardInputs.forEach(function(input) {
                if (input.value) return;
                const limit = input.maxLength > 0 ? input.maxLength : cfg.card_prefix.length;
                setValue(input, cfg.card_prefix.slice(0, limit));
                stats.card_filled++;
            });
        }

        // No id box means this is an ordinary contact form, not the real-name block.
        if (idInputs.length === 0) return;

        // The id box is the anchor: 證件號碼 is unambiguous, whereas a stray 姓名
        // elsewhere on the page would shift every attendee by one if the two
        // lists were paired on their global index.
        const usedNames = new Set();
        idInputs.forEach(function(idInput, index) {
            const attendee = cfg.attendees[index];
            if (!attendee) return;

            if (!idInput.value) {
                setValue(idInput, attendee.id_number);
                stats.id_filled++;
            }

            const nameInput = pairedNameInput(idInput, ordered, usedNames);
            if (!nameInput) {
                stats.unpaired_ids++;
                return;
            }
            usedNames.add(nameInput);
            if (!nameInput.value) {
                setValue(nameInput, attendee.name);
                stats.name_filled++;
            }
        });
    };

    // The name box belonging to this ticket: the nearest one in document order
    // with no other id box in between. Walks backwards first because these forms
    // put 證件姓名 above 證件號碼. A 姓名 belonging to another ticket therefore
    // cannot be claimed, and a stray one outside the block is never reached.
    function pairedNameInput(idInput, ordered, usedNames) {
        const start = ordered.findIndex(function(entry) { return entry.el === idInput; });
        if (start < 0) return null;

        for (const step of [-1, 1]) {
            for (let i = start + step; i >= 0 && i < ordered.length; i += step) {
                const entry = ordered[i];
                if (entry.kind === 'id') break;
                if (!usedNames.has(entry.el)) return entry.el;
            }
        }
        return null;
    }

    let scheduled = false;
    const observer = new MutationObserver(function() {
        if (scheduled) return;
        scheduled = true;
        setTimeout(function() {
            scheduled = false;
            try { window.__thFillPass(); } catch (exc) {}
        }, 0);
    });
    observer.observe(document.body || document.documentElement, {childList: true, subtree: true});

    window.__thFillInstalled = true;
    window.__thFillPass();

    return Object.assign({installed: true}, stats);
})()
"""


def _build_install_script(attendees, card_prefix, allow_card):
    config = {
        "attendees": attendees,
        "card_prefix": card_prefix,
        "allow_card": allow_card,
        "name_keywords": CONST_NAME_LABEL_KEYWORDS,
        "id_keywords": CONST_ID_LABEL_KEYWORDS,
        "card_keywords": CONST_CARD_LABEL_KEYWORDS,
        "exclude_keywords": CONST_LABEL_EXCLUDE_KEYWORDS,
    }
    return CONST_INSTALL_SCRIPT.replace("__CONFIG__", json.dumps(config, ensure_ascii=False))


async def install_autofill(tab, config_dict, url):
    """Install (or refresh) the checkout autofill observer on the current page.

    Cheap to call every tick: an already-installed page just runs one more fill
    pass. A reload drops the observer with the old document, and the next call
    re-installs it. Returns a summary dict, or None when out of scope.
    Never raises: a failure here must not abort the purchase attempt.
    """
    if not should_fill_for_url(url):
        return None

    attendees = attendees_from_config(config_dict)
    card_prefix = card_prefix_from_config(config_dict)
    allow_card = allows_card_prefix(url)

    if not attendees and not (card_prefix and allow_card):
        return None

    debug = util.create_debug_logger(config_dict)
    script = _build_install_script(attendees, card_prefix, allow_card)

    try:
        result = await tab.evaluate(script)
    except Exception as exc:
        debug.log(f"[CHECKOUT FILL] evaluate failed: {exc}")
        return None

    if not isinstance(result, dict):
        return None

    tab_key = id(tab)
    if result.get("installed", False):
        print("[CHECKOUT FILL] observer installed (%d attendee(s), card prefix %s)" %
              (len(attendees), "on" if (card_prefix and allow_card) else "off"))
        _last_written[tab_key] = -1

    written = result.get("name_filled", 0) + result.get("id_filled", 0) + result.get("card_filled", 0)
    if written > _last_written.get(tab_key, -1):
        print("[CHECKOUT FILL] name=%d id=%d card=%d (pass %d)" %
              (result.get("name_filled", 0), result.get("id_filled", 0),
               result.get("card_filled", 0), result.get("passes", 0)))
        debug.log(f"[CHECKOUT FILL] matched labels: {result.get('labels', [])}")
    _last_written[tab_key] = written

    return result
