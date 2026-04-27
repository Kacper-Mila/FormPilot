"""Google Form parsing for FormPilot.

The parser uses Playwright against the visible Google Forms page so it can
extract the question text, answer options, supported widget type, and basic
section/page structure from the live form DOM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _default_options() -> list[str]:
    return []


def _default_question_ids() -> list[str]:
    return []


def _default_sections() -> list["FormSection"]:
    return []


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_heading_text(value: str) -> str:
    text = _normalize_whitespace(value)
    text = text.replace(" *", "")
    text = text.replace("Wymagane", "")
    return _normalize_whitespace(text)


def _is_truthy_flag(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"true", "1", "yes", "tak"}


def _deduplicate_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(value)
    return unique_values


def _looks_like_scale(options: list[str]) -> bool:
    if len(options) < 3 or len(options) > 11:
        return False

    normalized = [_normalize_whitespace(option) for option in options]
    if all(re.fullmatch(r"\d+", value) for value in normalized):
        return True

    likert_labels = {
        "zdecydowanie nie",
        "raczej nie",
        "ani tak, ani nie",
        "ani tak ani nie",
        "trudno powiedziec",
        "neutral",
        "raczej tak",
        "zdecydowanie tak",
        "very unlikely",
        "unlikely",
        "likely",
        "very likely",
    }
    return all(value.casefold() in likert_labels for value in normalized)


def _normalize_form_url(form_url: str) -> str:
    parsed = urlparse(form_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid Google Form URL: {form_url}")
    return form_url


def _extract_locator_text(locator: Any) -> str:
    try:
        text = locator.inner_text(timeout=1000)
    except Exception:
        try:
            text = locator.text_content(timeout=1000) or ""
        except Exception:
            text = ""
    return _normalize_whitespace(text)


def _collect_option_labels(option_locator: Any) -> list[str]:
    labels: list[str] = []
    count = option_locator.count()

    for index in range(count):
        option = option_locator.nth(index)
        label = option.get_attribute("aria-label")
        if not label:
            label = _extract_locator_text(option)
        label = _normalize_whitespace(label or "")
        if label:
            labels.append(label)

    return _deduplicate_preserving_order(labels)


def _collect_dropdown_option_labels(page: Any, listbox_locator: Any) -> list[str]:
    if listbox_locator.count() == 0:
        return []

    trigger = listbox_locator.first
    try:
        trigger.click(force=True)
        try:
            page.wait_for_timeout(200)
        except Exception:
            pass

        option_labels = _collect_option_labels(page.locator("[role='option']"))
        return option_labels
    except Exception:
        return []
    finally:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass


def _build_question_text(heading_locator: Any) -> str:
    heading_text = _extract_locator_text(heading_locator)
    if not heading_text:
        return ""

    parts = [part for part in heading_text.split(" ") if part]
    cleaned_parts = [part for part in parts if part != "*" and part != "Wymagane"]
    return _clean_heading_text(" ".join(cleaned_parts))


def _detect_field_type(
    *,
    radio_options: list[str],
    checkbox_options: list[str],
    listbox_options: list[str],
    text_input_count: int,
    textarea_count: int,
) -> str:
    if radio_options:
        return "scale" if _looks_like_scale(radio_options) else "radio"
    if checkbox_options:
        return "checkbox"
    if listbox_options:
        return "dropdown"
    if textarea_count > 0:
        return "paragraph"
    if text_input_count > 0:
        return "short_text"
    return "unknown"


@dataclass(slots=True)
class FormQuestion:
    """Representation of one visible Google Form question."""

    form_question_id: str
    visible_text: str
    field_type: str
    options: list[str] = field(default_factory=_default_options)
    page_index: int = 0
    required: bool = False


@dataclass(slots=True)
class FormSection:
    """Representation of one visible Google Forms section/page."""

    page_index: int
    title: str
    description: str = ""
    question_ids: list[str] = field(default_factory=_default_question_ids)


@dataclass(slots=True)
class ParsedFormSchema:
    """Normalized view of a Google Form."""

    form_title: str
    form_url: str
    sections: list[FormSection] = field(default_factory=_default_sections)
    questions: list[FormQuestion] = field(default_factory=_default_options)

    def to_dict(self) -> dict[str, Any]:
        return {
            "form_title": self.form_title,
            "form_url": self.form_url,
            "sections": [
                {
                    "page_index": section.page_index,
                    "title": section.title,
                    "description": section.description,
                    "question_ids": list(section.question_ids),
                }
                for section in self.sections
            ],
            "questions": [
                {
                    "form_question_id": question.form_question_id,
                    "visible_text": question.visible_text,
                    "field_type": question.field_type,
                    "options": list(question.options),
                    "page_index": question.page_index,
                    "required": question.required,
                }
                for question in self.questions
            ],
        }


class GoogleFormParser:
    """Parse a Google Form into a normalized, inspectable schema."""

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30_000,
        logger: logging.Logger | None = None,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.logger = logger or logging.getLogger(__name__)

    def parse(self, form_url: str) -> list[FormQuestion]:
        """Return just the visible questions for backward compatibility."""

        return self.parse_form(form_url).questions

    def parse_form(self, form_url: str) -> ParsedFormSchema:
        """Open a Google Form and extract the visible schema."""

        normalized_url = _normalize_form_url(form_url)
        self.logger.info("Parsing Google Form: %s", normalized_url)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            try:
                page.goto(
                    normalized_url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
                except PlaywrightTimeoutError:
                    self.logger.debug(
                        "Timed out waiting for network idle while parsing %s",
                        normalized_url,
                    )

                form_title = _normalize_whitespace(page.title() or "") or normalized_url
                questions, sections = self._extract_schema_from_page(page, form_title)
                return ParsedFormSchema(
                    form_title=form_title,
                    form_url=page.url,
                    sections=sections,
                    questions=questions,
                )
            finally:
                browser.close()

    def _extract_schema_from_page(
        self, page: Any, form_title: str
    ) -> tuple[list[FormQuestion], list[FormSection]]:
        list_items = page.locator("div[role='listitem']")
        questions: list[FormQuestion] = []
        sections_by_page: dict[int, FormSection] = {}
        current_page_index = 0
        question_counter = 0
        section_counter = 0

        def ensure_section(page_index: int, title: str) -> FormSection:
            section = sections_by_page.get(page_index)
            if section is None:
                section = FormSection(page_index=page_index, title=title)
                sections_by_page[page_index] = section
            elif section.title == form_title and title != form_title:
                section.title = title
            return section

        ensure_section(0, form_title)

        for index in range(list_items.count()):
            item = list_items.nth(index)
            heading_locator = item.locator("[role='heading'][aria-level='3']").first
            heading_text = ""
            if heading_locator.count() > 0:
                heading_text = _build_question_text(heading_locator)

            radio_locator = item.locator("[role='radio']")
            checkbox_locator = item.locator("[role='checkbox']")
            listbox_locator = item.locator("[role='listbox']")
            text_input_locator = item.locator("input[type='text']")
            textarea_locator = item.locator("textarea")

            radio_options = _collect_option_labels(radio_locator)
            checkbox_options = _collect_option_labels(checkbox_locator)
            listbox_options = _collect_dropdown_option_labels(page, listbox_locator)
            text_input_count = text_input_locator.count()
            textarea_count = textarea_locator.count()

            item_text = _extract_locator_text(item)
            required = _is_truthy_flag(item.get_attribute("aria-required"))
            required = required or "Wymagane" in item_text

            field_type = _detect_field_type(
                radio_options=radio_options,
                checkbox_options=checkbox_options,
                listbox_options=listbox_options,
                text_input_count=text_input_count,
                textarea_count=textarea_count,
            )

            is_section = bool(heading_text) and field_type == "unknown"

            if is_section:
                section_counter += 1
                current_page_index = section_counter
                ensure_section(current_page_index, heading_text)
                continue

            if not heading_text or field_type == "unknown":
                continue

            question_counter += 1
            question_id = f"form_q_{question_counter}"
            options = radio_options or checkbox_options or listbox_options
            questions.append(
                FormQuestion(
                    form_question_id=question_id,
                    visible_text=heading_text,
                    field_type=field_type,
                    options=options,
                    page_index=current_page_index,
                    required=required,
                )
            )
            ensure_section(current_page_index, form_title)
            sections_by_page[current_page_index].question_ids.append(question_id)

        sections = [sections_by_page[index] for index in sorted(sections_by_page)]
        return questions, sections
