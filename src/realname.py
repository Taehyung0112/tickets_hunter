#!/usr/bin/env python3
#encoding=utf-8
"""Real-name (實名制) attendee auto-fill for TicketPlus checkout.

Ours, not upstream's: platforms/ticketplus.py fills no identity field, and a fix
there would be reverted by the next platform sync. nodriver_tixcraft.py calls
fill_realname_fields() before handing the tab to upstream, because upstream's
confirm handler submits the form on the same tick it first sees the page.

Fields are matched by visible label text, never by position, so a Vuetify
re-render does not silently write an id number into the wrong box.
"""

import asyncio
import json

import util

CONST_SEPARATORS = [",", "，", "\t", ";", "；"]

# Ordered: an id label is tested first because "證件姓名" and "證件號碼" share a prefix.
CONST_ID_LABEL_KEYWORDS = [
    "證件號碼", "證件字號", "身分證", "身份證", "統一證號", "居留證", "護照號碼",
    "護照", "證號", "id number", "identity", "passport",
]

CONST_NAME_LABEL_KEYWORDS = [
    "證件姓名", "持票人", "觀眾姓名", "取票人", "真實姓名", "姓名", "full name", "real name",
]

CONST_CONFIRM_WAIT_SEC = 6.0


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


def should_fill_for_url(url):
    url = (url or "").lower()
    return any(path in url for path in ["/confirm/", "/confirmseat/", "/order/"])


def wait_budget_for_url(url):
    """Seconds to wait for the fields to render.

    Zero on the order page: it is re-polled every tick, and blocking there
    costs grab latency for a form that may not exist on it at all.
    """
    url = (url or "").lower()
    if "/confirm/" in url or "/confirmseat/" in url:
        return CONST_CONFIRM_WAIT_SEC
    return 0


CONST_FILL_SCRIPT = r"""
(function() {
    const attendees = __ATTENDEES__;
    const nameKeywords = __NAME_KEYWORDS__;
    const idKeywords = __ID_KEYWORDS__;

    function labelTextOf(input) {
        const parts = [];
        const wrapper = input.closest('.v-input') || input.closest('.v-text-field') || input.parentElement;
        if (wrapper) {
            wrapper.querySelectorAll('label, .label, .v-label').forEach(function(el) {
                parts.push(el.textContent || '');
            });
        }
        if (input.id) {
            const explicit = document.querySelector('label[for="' + input.id + '"]');
            if (explicit) parts.push(explicit.textContent || '');
        }
        parts.push(input.placeholder || '');
        parts.push(input.getAttribute('aria-label') || '');
        parts.push(input.name || '');
        parts.push(input.id || '');
        return parts.join(' ').toLowerCase();
    }

    function classify(label) {
        for (const keyword of idKeywords) {
            if (label.indexOf(keyword) >= 0) return 'id';
        }
        for (const keyword of nameKeywords) {
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

    const nameInputs = [];
    const idInputs = [];
    const labels = [];

    document.querySelectorAll('input').forEach(function(input) {
        const type = (input.type || 'text').toLowerCase();
        if (['hidden', 'checkbox', 'radio', 'submit', 'button', 'file'].indexOf(type) >= 0) return;
        if (input.offsetParent === null) return;
        if (input.disabled || input.readOnly) return;

        const label = labelTextOf(input);
        const kind = classify(label);
        if (!kind) return;

        labels.push(kind + ':' + label.trim().slice(0, 40));
        (kind === 'id' ? idInputs : nameInputs).push(input);
    });

    // No id box means this is an ordinary contact form, not the real-name block.
    if (idInputs.length === 0) {
        return {name_fields: nameInputs.length, id_fields: 0, filled: 0, labels: labels};
    }

    let filled = 0;
    const rows = Math.min(attendees.length, Math.max(nameInputs.length, idInputs.length));
    for (let i = 0; i < rows; i++) {
        const attendee = attendees[i];
        const nameInput = nameInputs[i];
        const idInput = idInputs[i];
        if (nameInput && !nameInput.value) {
            setValue(nameInput, attendee.name);
            filled++;
        }
        if (idInput && !idInput.value) {
            setValue(idInput, attendee.id_number);
            filled++;
        }
    }

    return {
        name_fields: nameInputs.length,
        id_fields: idInputs.length,
        filled: filled,
        labels: labels
    };
})()
"""


def _build_fill_script(attendees):
    payload = json.dumps(attendees, ensure_ascii=False)
    return (CONST_FILL_SCRIPT
            .replace("__ATTENDEES__", payload)
            .replace("__NAME_KEYWORDS__", json.dumps(CONST_NAME_LABEL_KEYWORDS))
            .replace("__ID_KEYWORDS__", json.dumps(CONST_ID_LABEL_KEYWORDS)))


async def fill_realname_fields(tab, config_dict, url):
    """Fill 證件姓名 / 證件號碼 on a TicketPlus checkout page.

    Returns a summary dict, or None when the feature is off or out of scope.
    Never raises: a failure here must not abort the purchase attempt.
    """
    if not should_fill_for_url(url):
        return None

    attendees = attendees_from_config(config_dict)
    if not attendees:
        return None

    debug = util.create_debug_logger(config_dict)
    script = _build_fill_script(attendees)
    deadline_sec = wait_budget_for_url(url)

    attempt = 0
    result = None
    while True:
        attempt += 1
        try:
            result = await tab.evaluate(script)
        except Exception as exc:
            debug.log(f"[REALNAME] evaluate failed: {exc}")
            result = None

        if isinstance(result, dict) and result.get("id_fields", 0) > 0:
            break
        if deadline_sec <= 0:
            break

        deadline_sec -= 0.3
        await asyncio.sleep(0.3)

    if not isinstance(result, dict):
        return None

    if result.get("id_fields", 0) == 0:
        debug.log(f"[REALNAME] no identity field on this page (attempt {attempt})")
        return result

    print("[REALNAME] filled %d field(s) for %d attendee(s), page has %d name / %d id box(es)" %
          (result.get("filled", 0), len(attendees),
           result.get("name_fields", 0), result.get("id_fields", 0)))

    if result.get("filled", 0) == 0:
        print("[REALNAME][WARN] identity fields found but none were written — "
              "already filled, or the labels did not match; fill them by hand now")

    debug.log(f"[REALNAME] matched labels: {result.get('labels', [])}")

    return result
