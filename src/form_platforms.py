"""
Tier 1 contact-form platform detection and scoped selectors.

Platforms:
  - contact_form_7  (.wpcf7)
  - wpforms         (.wpforms-form)
  - gravity_forms   (.gform_wrapper / .gform_body)
  - hubspot         (.hs-form / hs-form iframe)
  - elementor       (.elementor-form)
  - generic         plain HTML / unknown
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Frame, Page


@dataclass
class PlatformInfo:
    name: str
    container_selector: str
    submit_selectors: list[str]
    notes: str = ""


PLATFORM_SPECS: list[tuple[str, list[str], list[str]]] = [
    (
        "contact_form_7",
        [".wpcf7", ".wpcf7-form", "div.wpcf7 form", "form.wpcf7-form"],
        [
            ".wpcf7-submit",
            "input.wpcf7-submit",
            ".wpcf7 input[type='submit']",
            ".wpcf7 button[type='submit']",
            "input[type='submit']",
            "button[type='submit']",
        ],
    ),
    (
        "wpforms",
        [".wpforms-form", "form.wpforms-form", ".wpforms-container form"],
        [
            ".wpforms-submit",
            "button.wpforms-submit",
            ".wpforms-submit-container button",
            "button[type='submit']",
            "input[type='submit']",
        ],
    ),
    (
        "gravity_forms",
        [".gform_wrapper", "form.gform_wrapper", ".gform_body", "form[id^='gform_']"],
        [
            ".gform_button",
            "input.gform_button",
            "#gform_submit_button_1",
            "input[type='submit'].gform_button",
            "input[type='submit']",
            "button[type='submit']",
        ],
    ),
    (
        "hubspot",
        [
            ".hs-form",
            "form.hs-form",
            ".hbspt-form form",
            ".hs-form-field",
            "form[data-form-id]",
        ],
        [
            ".hs-button",
            "input.hs-button",
            ".hs-submit input[type='submit']",
            ".hs-button.primary",
            "input[type='submit']",
            "button[type='submit']",
        ],
    ),
    (
        "elementor",
        [
            ".elementor-form",
            "form.elementor-form",
            ".elementor-widget-form form",
        ],
        [
            ".elementor-button[type='submit']",
            "button.elementor-button",
            ".elementor-form button[type='submit']",
            "button[type='submit']",
            "input[type='submit']",
        ],
    ),
]

GENERIC = PlatformInfo(
    name="generic",
    container_selector="form, body",
    submit_selectors=[
        "form button[type='submit']",
        "form input[type='submit']",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Send')",
        "button:has-text('Send message')",
        "button:has-text('Send Message')",
        "button:has-text('Contact us')",
        "button:has-text('Get in touch')",
        "button:has-text('Enquire')",
        "button:has-text('Inquire')",
        "[type='submit']",
    ],
)


async def detect_platform(page: Page | Frame) -> PlatformInfo:
    """Return the first matching Tier-1 platform, else generic."""
    for name, containers, submits in PLATFORM_SPECS:
        for sel in containers:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return PlatformInfo(
                        name=name,
                        container_selector=sel,
                        submit_selectors=submits,
                        notes=f"detected:{sel}",
                    )
            except Exception:
                continue

    if isinstance(page, Page):
        try:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                url = (frame.url or "").lower()
                if "hubspot" in url or "hsforms" in url or "hs-scripts" in url:
                    return PlatformInfo(
                        name="hubspot",
                        container_selector="form.hs-form, form, body",
                        submit_selectors=PLATFORM_SPECS[3][2],
                        notes="detected:hubspot_iframe",
                    )
                for sel in (".hs-form", "form.hs-form", ".hs-form-field"):
                    try:
                        if await frame.locator(sel).count() > 0:
                            return PlatformInfo(
                                name="hubspot",
                                container_selector=sel,
                                submit_selectors=PLATFORM_SPECS[3][2],
                                notes="detected:hubspot_frame_dom",
                            )
                    except Exception:
                        continue
        except Exception:
            pass

    return GENERIC


def field_scope_selector(platform: PlatformInfo) -> str:
    if platform.name == "generic":
        return "form input, form textarea, form select, input, textarea, select"
    base = platform.container_selector
    return (
        f"{base} input, {base} textarea, {base} select, "
        f"form input, form textarea, form select, input, textarea, select"
    )


PLATFORM_FIELD_HINTS: dict[str, dict[str, list[str]]] = {
    "contact_form_7": {
        "email": ["your-email", "wpcf7-email"],
        "full_name": ["your-name", "wpcf7-text"],
        "first_name": ["your-name", "first-name"],
        "last_name": ["last-name"],
        "phone": ["your-phone", "tel", "phone"],
        "subject": ["your-subject"],
        "message": ["your-message", "wpcf7-textarea"],
        "company": ["your-company", "company"],
    },
    "wpforms": {
        "email": ["wpforms-field-email", "email"],
        "full_name": ["wpforms-field-name", "name"],
        "first_name": ["first-name", "wpforms-field-name-first"],
        "last_name": ["last-name", "wpforms-field-name-last"],
        "phone": ["wpforms-field-phone", "phone"],
        "message": ["wpforms-field-textarea", "message", "comment"],
        "subject": ["subject"],
        "company": ["company"],
    },
    "gravity_forms": {
        "email": ["input_email", "ginput_email", "email"],
        "full_name": ["ginput_full", "input_1"],
        "first_name": ["ginput_left", "first"],
        "last_name": ["ginput_right", "last"],
        "phone": ["phone", "ginput_container_phone"],
        "message": ["textarea", "message"],
        "company": ["company"],
        "subject": ["subject"],
    },
    "hubspot": {
        "email": ["email", "hs-input"],
        "full_name": ["firstname", "lastname", "name"],
        "first_name": ["firstname"],
        "last_name": ["lastname"],
        "phone": ["phone", "mobilephone"],
        "company": ["company"],
        "message": ["message", "TICKET.hs_content"],
        "job_title": ["jobtitle"],
        "website": ["website"],
    },
    "elementor": {
        "email": ["form-field-email", "email"],
        "full_name": ["form-field-name", "name"],
        "first_name": ["first-name", "name"],
        "last_name": ["last-name"],
        "phone": ["form-field-phone", "phone", "tel"],
        "message": ["form-field-message", "message"],
        "subject": ["subject"],
    },
}


def boost_signals(platform_name: str, signals: str, field_type: str) -> float:
    hints = PLATFORM_FIELD_HINTS.get(platform_name, {}).get(field_type, [])
    s = (signals or "").lower()
    for h in hints:
        if h.lower() in s:
            return 1.5
    return 0.0
