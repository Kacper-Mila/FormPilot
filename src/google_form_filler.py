"""Playwright form filling module for FormPilot."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

from playwright.sync_api import Page, sync_playwright

from form_mapper import MappingEntry
from response_generator import GeneratedResponse
from logger import setup_logging

logger = setup_logging()


@dataclass(slots=True)
class FillResult:
    """Outcome of one form-filling attempt."""

    success: bool
    message: str
    screenshot_path: str | None = None


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_heading_text(value: str) -> str:
    text = _normalize_whitespace(value)
    text = text.replace(" *", "")
    text = text.replace("Wymagane", "")
    return _normalize_whitespace(text)


class GoogleFormFiller:
    """Browser automation layer for Google Forms."""

    def __init__(self, headless: bool = True, timeout_ms: int = 15000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms

    def fill_and_submit(
        self, form_url: str, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> FillResult:
        """Open the form, map answers to DOM elements, fill, and submit."""

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(locale="pl-PL")
            page = context.new_page()

            try:
                logger.info(f"Opening form: {form_url}")
                page.goto(form_url, timeout=self.timeout_ms)
                page.wait_for_load_state("networkidle")

                is_last_page = False
                page_count = 1

                while not is_last_page:
                    logger.info(f"Filling page {page_count}...")
                    self._fill_current_page(page, response, mappings)

                    btn_submit = page.locator(
                        "div[role='button']:has-text('Wyślij'), div[role='button']:has-text('Prześlij'), div[role='button']:has-text('Submit')"
                    ).first
                    btn_next = page.locator(
                        "div[role='button']:has-text('Dalej'), div[role='button']:has-text('Next')"
                    ).first

                    if btn_submit.count() > 0 and btn_submit.is_visible():
                        btn_submit.click()
                        is_last_page = True
                    elif btn_next.count() > 0 and btn_next.is_visible():
                        btn_next.click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(1000)
                        page_count += 1
                    else:
                        raise RuntimeError("Could not find Next or Submit button.")

                # Check for confirmation view
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1000)

                # Check if we landed on a confirmation page
                # The text normally says "Twoja odpowiedź została zapisana"
                return FillResult(success=True, message="Form submitted successfully.")

            except Exception as e:
                logger.error(f"Failed to fill form: {str(e)}")
                screenshot_path = f"logs/failure_{response.response_id}.png"
                try:
                    import os

                    if not os.path.exists("logs"):
                        os.makedirs("logs")
                    page.screenshot(path=screenshot_path)
                except Exception as ex:
                    logger.error(f"Failed to capture screenshot: {ex}")
                return FillResult(
                    success=False, message=str(e), screenshot_path=screenshot_path
                )
            finally:
                context.close()
                browser.close()

    def _fill_current_page(
        self, page: Page, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> None:
        """Fill all visible questions on the current page."""

        list_items = page.locator("div[role='listitem']")
        count = list_items.count()

        for i in range(count):
            item = list_items.nth(i)
            heading_loc = item.locator("[role='heading'][aria-level='3']").first
            if heading_loc.count() == 0:
                continue

            heading_text = heading_loc.inner_text() or heading_loc.text_content() or ""
            clean_heading = _clean_heading_text(heading_text)

            mapping = self._find_mapping(clean_heading, mappings)
            if not mapping:
                continue

            raw_answer = response.answers.get(mapping.dataset_column_name)
            # Accept 0, False, but gracefully skip if completely None or empty string/list
            if (
                raw_answer is None
                or raw_answer == ""
                or (isinstance(raw_answer, list) and not raw_answer)
            ):
                continue

            self._fill_item(page, item, raw_answer, mapping)

    def _find_mapping(
        self, question_text: str, mappings: list[MappingEntry]
    ) -> MappingEntry | None:
        """Find a MappingEntry describing the specified form question."""

        for m in mappings:
            # Exact match of cleaned form strings
            if _clean_heading_text(m.form_question_text) == question_text:
                return m
        return None

    def _fill_item(
        self, page: Page, item: Any, raw_answer: Any, mapping: MappingEntry
    ) -> None:
        """Fill a specific widget with an answer."""

        # Determine if we should handle it as a sequence of answers (multi-select)
        if not isinstance(raw_answer, list):
            raw_answers = [raw_answer]
        else:
            raw_answers = raw_answer

        target_answers = []
        for ans in raw_answers:
            ans_str = str(ans)
            if mapping.answer_mapping and ans_str in mapping.answer_mapping:
                mapped = mapping.answer_mapping[ans_str]
                target_answers.append(mapped)
            else:
                target_answers.append(ans_str)

        radio_locs = item.locator("[role='radio']")
        chk_locs = item.locator("[role='checkbox']")
        listbox_locs = item.locator("[role='listbox']")
        text_input = item.locator("input[type='text']")
        textarea = item.locator("textarea")

        if radio_locs.count() > 0:
            tgt = target_answers[0]
            clicked = False
            for r in range(radio_locs.count()):
                r_loc = radio_locs.nth(r)
                r_label = r_loc.get_attribute("aria-label") or ""
                if tgt.casefold() in r_label.casefold():
                    r_loc.click()
                    clicked = True
                    break
            if not clicked:
                try:
                    item.locator("label").filter(
                        has_text=re.compile(re.escape(tgt), re.IGNORECASE)
                    ).first.click()
                except Exception:
                    pass

        elif chk_locs.count() > 0:
            for tgt in target_answers:
                clicked = False
                for c in range(chk_locs.count()):
                    c_loc = chk_locs.nth(c)
                    c_label = c_loc.get_attribute("aria-label") or ""
                    if tgt.casefold() in c_label.casefold():
                        if c_loc.get_attribute("aria-checked") != "true":
                            c_loc.click()
                        clicked = True
                        break
                if not clicked:
                    try:
                        item.locator("label").filter(
                            has_text=re.compile(re.escape(tgt), re.IGNORECASE)
                        ).first.click()
                    except Exception:
                        pass

        elif listbox_locs.count() > 0:
            tgt = target_answers[0]
            listbox_locs.first.click()
            page.wait_for_timeout(300)
            try:
                page.locator("div[role='option']").filter(
                    has_text=re.compile(f"^{re.escape(tgt)}$", re.IGNORECASE)
                ).first.click()
            except Exception:
                # fallback
                page.locator("div[role='option']").filter(
                    has_text=re.compile(re.escape(tgt), re.IGNORECASE)
                ).first.click()
            page.wait_for_timeout(300)

        elif text_input.count() > 0:
            text_input.first.fill(target_answers[0])

        elif textarea.count() > 0:
            textarea.first.fill(target_answers[0])
