"""Playwright form filling module for FormPilot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, cast

from playwright.sync_api import Browser, BrowserContext, Locator, Page, sync_playwright

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
    final_url: str | None = None


@dataclass(slots=True)
class FieldFillResult:
    """Outcome of filling one form field."""

    success: bool
    answers: list[str]
    message: str = ""


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_heading_text(value: str) -> str:
    text = _normalize_whitespace(value)
    text = text.replace(" *", "")
    text = text.replace("Wymagane", "")
    return _normalize_whitespace(text)


def _has_answer(value: object) -> bool:
    return not (
        value is None or value == "" or (isinstance(value, list) and not value)
    )


def _answer_values(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return [value]


def _normalize_option(value: str) -> str:
    return _normalize_whitespace(value).casefold()


def _short_log_value(value: object, max_length: int = 120) -> str:
    text = _normalize_whitespace(str(value))
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _format_answers_for_log(values: list[str]) -> str:
    if not values:
        return "<empty>"
    return ", ".join(_short_log_value(value, 80) for value in values)


def _option_matches(target: str, label: str) -> bool:
    target_norm = _normalize_option(target)
    label_norm = _normalize_option(label)
    return bool(
        target_norm
        and label_norm
        and (
            target_norm == label_norm
            or target_norm in label_norm
            or label_norm in target_norm
        )
    )


def _mapped_answer_values(
    raw_answer: object, mapping: MappingEntry, *, split_composites: bool
) -> list[str]:
    answer_mapping = mapping.answer_mapping or {}
    raw_values = [str(value).strip() for value in _answer_values(raw_answer)]
    raw_values = [value for value in raw_values if value]

    targets: list[str] = []
    for raw_value in raw_values:
        if raw_value in answer_mapping:
            targets.append(answer_mapping[raw_value])
            continue

        if split_composites and answer_mapping:
            raw_norm = _normalize_option(raw_value)
            matched_keys = [
                key
                for key in answer_mapping
                if _normalize_option(key) and _normalize_option(key) in raw_norm
            ]
            matched_keys.sort(key=lambda key: raw_norm.find(_normalize_option(key)))
            if matched_keys:
                targets.extend(answer_mapping[key] for key in matched_keys)
                continue

            pieces = [
                piece.strip()
                for piece in re.split(r"\s*[,;]\s*", raw_value)
                if piece.strip()
            ]
            mapped_pieces = [answer_mapping.get(piece, piece) for piece in pieces]
            targets.extend(mapped_pieces)
            continue

        targets.append(raw_value)

    unique_targets: list[str] = []
    seen: set[str] = set()
    for target in targets:
        normalized = _normalize_option(target)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_targets.append(target)
    return unique_targets


class GoogleFormFiller:
    """Browser automation layer for Google Forms."""

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 15000,
        action_delay_ms: int = 50,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.action_delay_ms = action_delay_ms
        self._playwright_manager: Any | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "GoogleFormFiller":
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        """Start a reusable Playwright browser session."""

        if self._browser is not None:
            return

        self._playwright_manager = sync_playwright().start()
        try:
            self._browser = self._playwright_manager.chromium.launch(
                headless=self.headless
            )
            self._context = self._browser.new_context(locale="pl-PL")
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the reusable Playwright browser session if one is open."""

        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright_manager is not None:
            self._playwright_manager.stop()
            self._playwright_manager = None

    def fill_and_submit(
        self, form_url: str, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> FillResult:
        """Open the form, map answers to DOM elements, fill, and submit."""

        started_here = self._browser is None
        if started_here:
            self.start()
        if self._context is None:
            raise RuntimeError("Playwright browser context was not initialized.")

        page = self._context.new_page()

        try:
            logger.info("Opening form: %s", form_url)
            page.goto(form_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._wait_for_form_ready(page)

            page_count = 1
            while True:
                logger.info("Filling page %d...", page_count)
                self._fill_current_page(page, response, mappings)

                submit_button = page.locator(
                    "div[role='button']:has-text('Wyślij'), "
                    "div[role='button']:has-text('Prześlij'), "
                    "div[role='button']:has-text('Submit')"
                ).first
                next_button = page.locator(
                    "div[role='button']:has-text('Dalej'), "
                    "div[role='button']:has-text('Next')"
                ).first

                last_click_error: Exception | None = None
                try:
                    if submit_button.count() > 0 and submit_button.is_visible():
                        logger.info("Submitting page %d", page_count)
                        submit_button.click()
                        self._wait_after_action(page)
                        self._assert_submission_complete(page)
                        return FillResult(
                            success=True,
                            message="Form submitted successfully.",
                            final_url=page.url,
                        )
                except Exception as e:
                    last_click_error = e
                    logger.warning("Submit click failed: %s", e)

                try:
                    if next_button.count() > 0 and next_button.is_visible():
                        logger.info("Going to next page from page %d", page_count)
                        before_heading = self._first_question_heading(page)
                        next_button.click()
                        self._wait_after_action(page)
                        after_heading = self._first_question_heading(page)

                        if (
                            before_heading
                            and after_heading
                            and before_heading == after_heading
                        ):
                            logger.warning(
                                "Next click did not advance the page. Looking for "
                                "required unanswered questions..."
                            )
                            self._fill_required_questions(page, response, mappings)
                            logger.info("Retrying Next click after required fields")
                            next_button.click()
                            self._wait_after_action(page)
                            retry_heading = self._first_question_heading(page)
                            if before_heading and retry_heading == before_heading:
                                raise RuntimeError(
                                    "Next did not advance after retry; required "
                                    "questions remain unanswered."
                                )

                        page_count += 1
                        continue
                except Exception as e:
                    last_click_error = e
                    logger.warning("Next click failed: %s", e)

                html = page.content()
                failure_detail = f": {last_click_error}" if last_click_error else ""
                logger.error(
                    "Could not find or click Next/Submit on page %d. "
                    "Page snapshot length=%d%s",
                    page_count,
                    len(html),
                    failure_detail,
                )
                raise RuntimeError(
                    "Could not find or complete Next/Submit button action"
                    f"{failure_detail}."
                ) from last_click_error

        except Exception as e:
            logger.error("Failed to fill form: %s", e)
            screenshot_path = f"logs/failure_{response.response_id}.png"
            try:
                Path("logs").mkdir(exist_ok=True)
                page.screenshot(path=screenshot_path)
            except Exception as ex:
                logger.error("Failed to capture screenshot: %s", ex)
            return FillResult(
                success=False,
                message=str(e),
                screenshot_path=screenshot_path,
                final_url=page.url,
            )
        finally:
            try:
                page.close()
            finally:
                if started_here:
                    self.close()

    def _wait_for_form_ready(self, page: Page) -> None:
        try:
            page.locator("div[role='listitem'], div[role='button']").first.wait_for(
                state="visible",
                timeout=self.timeout_ms,
            )
        except Exception:
            logger.debug("Form controls were not visible yet; waiting for network idle")
            try:
                page.wait_for_load_state(
                    "networkidle", timeout=min(self.timeout_ms, 3000)
                )
            except Exception:
                if self.action_delay_ms > 0:
                    page.wait_for_timeout(self.action_delay_ms)

    def _first_question_heading(self, page: Page) -> str:
        try:
            heading = page.locator("div[role='listitem'] [role='heading']").first
            if heading.count() == 0:
                return ""
            try:
                text = heading.inner_text(timeout=1000)
            except Exception:
                text = heading.text_content(timeout=1000) or ""
            return _clean_heading_text(text)
        except Exception:
            return ""

    def _fill_required_questions(
        self, page: Page, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> None:
        required_markers = page.locator("text=Wymagane")
        required_count = required_markers.count()
        summaries = self._required_error_summaries(page)
        if summaries:
            logger.error("Required unanswered blocks (sample): %s", summaries[:10])

        for index in range(required_count):
            try:
                parent = required_markers.nth(index).locator(
                    "xpath=ancestor::div[@role='listitem']"
                )
                heading_loc = parent.locator("[role='heading']").first
                heading_text = (
                    heading_loc.inner_text() or heading_loc.text_content() or ""
                )
                clean_heading = _clean_heading_text(heading_text)
                mapping = self._find_mapping(clean_heading, mappings)
                if mapping is None:
                    logger.debug("No mapping for required question: %s", clean_heading)
                    continue

                raw_answer = response.answers.get(mapping.dataset_column_name)
                if _has_answer(raw_answer):
                    self._fill_item(page, parent, raw_answer, mapping)
                else:
                    logger.debug(
                        "No available answer for required mapping %s",
                        mapping.dataset_column_name,
                    )
            except Exception as e:
                logger.debug(
                    "Failed to attempt auto-fill for required block %d: %s",
                    index,
                    e,
                )

    def _fill_current_page(
        self, page: Page, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> None:
        """Fill all visible questions on the current page."""

        list_items = page.locator("div[role='listitem']")
        total = list_items.count()
        logger.debug("Found %d candidate list items on page", total)

        for i in range(total):
            item = list_items.nth(i)
            heading_loc = item.locator("[role='heading'][aria-level='3']").first
            if heading_loc.count() == 0:
                # Not a question block we care about
                continue

            try:
                heading_text = (
                    heading_loc.inner_text() or heading_loc.text_content() or ""
                )
            except Exception:
                heading_text = heading_loc.text_content() or ""

            clean_heading = _clean_heading_text(heading_text)
            logger.debug(
                "Processing question heading: '%s' -> normalized '%s'",
                heading_text,
                clean_heading,
            )

            mapping = self._find_mapping(clean_heading, mappings)
            if not mapping:
                logger.debug("No mapping found for question: %s", clean_heading)
                continue

            raw_answer = response.answers.get(mapping.dataset_column_name)
            # Accept 0 and False, but skip fully empty values.
            if not _has_answer(raw_answer):
                logger.debug(
                    "Skipping question '%s' due to empty answer for column '%s'",
                    clean_heading,
                    mapping.dataset_column_name,
                )
                continue

            fill_result = self._fill_item(page, item, raw_answer, mapping)
            status = "success" if fill_result.success else "failed"
            log_method = logger.info if fill_result.success else logger.warning
            log_method(
                'Question filled | status=%s | question="%s" | answer="%s"',
                status,
                _short_log_value(clean_heading),
                _format_answers_for_log(fill_result.answers),
            )
            if fill_result.message:
                logger.debug(
                    "Question fill detail for '%s': %s",
                    clean_heading,
                    fill_result.message,
                )

    def _find_mapping(
        self, question_text: str, mappings: list[MappingEntry]
    ) -> MappingEntry | None:
        """Find a MappingEntry describing the specified form question."""

        for m in mappings:
            # Exact match of cleaned form strings
            if _clean_heading_text(m.form_question_text) == question_text:
                return m
        return None

    def _wait_after_action(self, page: Page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=1500)
        except Exception:
            if self.action_delay_ms > 0:
                page.wait_for_timeout(self.action_delay_ms)

    def _pause_after_field_action(self, page: Page) -> None:
        if self.action_delay_ms > 0:
            page.wait_for_timeout(self.action_delay_ms)

    def _is_submission_confirmation(self, page: Page) -> bool:
        if "/formResponse" in page.url:
            return True

        confirmation_texts = [
            "Twoja odpowiedź została zapisana",
            "Your response has been recorded",
            "Odpowiedź została zapisana",
        ]
        for text in confirmation_texts:
            try:
                if page.get_by_text(text, exact=False).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    def _required_error_summaries(self, page: Page) -> list[str]:
        required_markers = page.locator("text=Wymagane")
        summaries: list[str] = []
        for index in range(required_markers.count()):
            try:
                parent = required_markers.nth(index).locator(
                    "xpath=ancestor::div[@role='listitem']"
                )
                heading = parent.locator("[role='heading']").first.text_content() or ""
            except Exception:
                heading = required_markers.nth(index).text_content() or ""
            summary = _normalize_whitespace(heading)
            if summary:
                summaries.append(summary[:200])
        return summaries

    def _assert_submission_complete(self, page: Page) -> None:
        if not self._is_submission_confirmation(page):
            try:
                page.wait_for_url(re.compile(r"/formResponse(?:$|[?#])"), timeout=5000)
            except Exception:
                pass

        if self._is_submission_confirmation(page):
            logger.info("Submission confirmed via /formResponse")
            logger.debug("Submission confirmation URL: %s", page.url)
            return

        required_errors = self._required_error_summaries(page)
        if required_errors:
            logger.error(
                "Submit stayed on the form with required errors: %s",
                required_errors[:10],
            )
            raise RuntimeError(
                "Submit did not complete; required questions remain unanswered: "
                + "; ".join(required_errors[:5])
            )

        logger.error(
            "Submit did not reach confirmation screen. Current URL: %s", page.url
        )
        raise RuntimeError(
            "Submit did not reach the confirmation screen or /formResponse path."
        )

    def _fill_item(
        self, page: Page, item: Locator, raw_answer: object, mapping: MappingEntry
    ) -> FieldFillResult:
        """Fill a specific widget with an answer."""

        radio_locs = item.locator("[role='radio']")
        chk_locs = item.locator("[role='checkbox']")
        listbox_locs = item.locator("[role='listbox']")
        text_input = item.locator("input[type='text']")
        textarea = item.locator("textarea")

        try:
            if radio_locs.count() > 0:
                target_answers = _mapped_answer_values(
                    raw_answer, mapping, split_composites=True
                )
                if len(target_answers) > 1:
                    logger.info(
                        "Multiple answers produced for a radio question; "
                        "selecting the first one: %s",
                        _format_answers_for_log(target_answers),
                    )
                tgt = target_answers[0]
                logger.debug(
                    "Question has %d radio options; raw=%r targets=%s",
                    radio_locs.count(),
                    raw_answer,
                    target_answers,
                )
                clicked = self._click_choice(
                    page,
                    radio_locs,
                    item,
                    tgt,
                    role_name="radio",
                    expected_checked="true",
                )
                if not clicked:
                    return FieldFillResult(
                        success=False,
                        answers=target_answers,
                        message=(
                            f"Could not select radio target '{tgt}'. "
                            f"Available options: {self._option_labels(radio_locs)}"
                        ),
                    )
                return FieldFillResult(success=True, answers=[tgt])

            elif chk_locs.count() > 0:
                target_answers = _mapped_answer_values(
                    raw_answer, mapping, split_composites=True
                )
                logger.debug(
                    "Question has %d checkboxes; raw=%r targets=%s",
                    chk_locs.count(),
                    raw_answer,
                    target_answers,
                )
                failed_targets: list[str] = []
                for tgt in target_answers:
                    clicked = self._click_choice(
                        page,
                        chk_locs,
                        item,
                        tgt,
                        role_name="checkbox",
                        expected_checked="true",
                    )
                    if not clicked:
                        failed_targets.append(tgt)
                if failed_targets:
                    return FieldFillResult(
                        success=False,
                        answers=target_answers,
                        message=(
                            f"Could not select checkbox target(s): {failed_targets}. "
                            f"Available options: {self._option_labels(chk_locs)}"
                        ),
                    )
                return FieldFillResult(success=True, answers=target_answers)

            elif listbox_locs.count() > 0:
                target_answers = _mapped_answer_values(
                    raw_answer, mapping, split_composites=True
                )
                if len(target_answers) > 1:
                    logger.info(
                        "Multiple answers produced for a listbox question; "
                        "selecting the first one: %s",
                        _format_answers_for_log(target_answers),
                    )
                tgt = target_answers[0]
                logger.debug(
                    "Question has listbox; raw=%r targets=%s",
                    raw_answer,
                    target_answers,
                )
                try:
                    listbox_locs.first.click(timeout=2000)
                    options = page.locator("div[role='option']")
                    try:
                        options.filter(
                            has_text=re.compile(
                                f"^{re.escape(tgt)}$", re.IGNORECASE
                            )
                        ).first.click(timeout=1500)
                    except Exception:
                        options.filter(
                            has_text=re.compile(re.escape(tgt), re.IGNORECASE)
                        ).first.click(timeout=1500)
                    self._pause_after_field_action(page)
                    return FieldFillResult(success=True, answers=[tgt])
                except Exception as e:
                    return FieldFillResult(
                        success=False,
                        answers=target_answers,
                        message=f"Failed to select listbox option '{tgt}': {e}",
                    )

            elif text_input.count() > 0:
                target_answers = _mapped_answer_values(
                    raw_answer, mapping, split_composites=False
                )
                logger.debug("Filling text input with '%s'", target_answers[0])
                try:
                    text_input.first.fill(target_answers[0], timeout=2000)
                    return FieldFillResult(success=True, answers=target_answers)
                except Exception as e:
                    return FieldFillResult(
                        success=False,
                        answers=target_answers,
                        message=f"Failed to fill text input: {e}",
                    )

            elif textarea.count() > 0:
                target_answers = _mapped_answer_values(
                    raw_answer, mapping, split_composites=False
                )
                logger.debug("Filling textarea with '%s'", target_answers[0])
                try:
                    textarea.first.fill(target_answers[0], timeout=2000)
                    return FieldFillResult(success=True, answers=target_answers)
                except Exception as e:
                    return FieldFillResult(
                        success=False,
                        answers=target_answers,
                        message=f"Failed to fill textarea: {e}",
                    )
            else:
                logger.debug(
                    "No known widget type found for mapping '%s'",
                    mapping.dataset_column_name,
                )
                return FieldFillResult(
                    success=False,
                    answers=[],
                    message="No supported form widget found.",
                )
        except Exception as e:
            logger.exception(
                "Unexpected error while filling item for '%s': %s",
                mapping.dataset_column_name,
                e,
            )
            return FieldFillResult(
                success=False,
                answers=[],
                message=f"Unexpected error while filling field: {e}",
            )

    def _option_labels(self, options: Locator) -> list[str]:
        labels: list[str] = []
        for index in range(options.count()):
            option = options.nth(index)
            label = option.get_attribute("aria-label") or ""
            if not label:
                try:
                    label = option.inner_text(timeout=500)
                except Exception:
                    label = option.text_content(timeout=500) or ""
            labels.append(_normalize_whitespace(label))
        return labels

    def _click_choice(
        self,
        page: Page,
        options: Locator,
        item: Locator,
        target: str,
        *,
        role_name: str,
        expected_checked: str,
    ) -> bool:
        option_count = options.count()
        for index in range(option_count):
            option = options.nth(index)
            label = _normalize_whitespace(option.get_attribute("aria-label") or "")
            if not _option_matches(target, label):
                continue

            logger.debug(
                "Clicking %s option '%s' for target '%s'", role_name, label, target
            )
            if option.get_attribute("aria-checked") == expected_checked:
                logger.debug("%s option already selected: '%s'", role_name, label)
                return True

            try:
                option.scroll_into_view_if_needed(timeout=1000)
                option.click(timeout=2000, force=True)
                self._pause_after_field_action(page)
                if option.get_attribute("aria-checked") == expected_checked:
                    logger.debug("%s option selected: '%s'", role_name, label)
                    return True

                box = option.bounding_box(timeout=1000)
                if box:
                    page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    self._pause_after_field_action(page)
                    if option.get_attribute("aria-checked") == expected_checked:
                        logger.debug(
                            "%s option selected by mouse fallback: '%s'",
                            role_name,
                            label,
                        )
                        return True

                logger.debug(
                    "%s option '%s' clicked but aria-checked=%r",
                    role_name,
                    label,
                    option.get_attribute("aria-checked"),
                )
            except Exception as e:
                logger.debug(
                    "%s click failed for label '%s': %s", role_name, label, e
                )

        try:
            label_locator = (
                item.locator("label")
                .filter(has_text=re.compile(re.escape(target), re.IGNORECASE))
                .first
            )
            label_locator.click(timeout=1000, force=True)
            self._pause_after_field_action(page)
        except Exception as e:
            logger.debug(
                "No %s label fallback matched for '%s': %s", role_name, target, e
            )
            return False

        for index in range(option_count):
            option = options.nth(index)
            label = _normalize_whitespace(option.get_attribute("aria-label") or "")
            if _option_matches(target, label):
                checked = option.get_attribute("aria-checked")
                if checked == expected_checked:
                    logger.debug(
                        "%s fallback label selected option '%s'", role_name, label
                    )
                    return True
                logger.debug(
                    "%s fallback label clicked but option '%s' aria-checked=%r",
                    role_name,
                    label,
                    checked,
                )
        return False
