import pytest


@pytest.fixture()
def pattern(page, static_server):
    page.goto(f"{static_server}/frontend/testpattern.html")
    page.wait_for_selector(".wedge")
    return page


def test_the_greyscale_wedge_has_eleven_steps_from_black_to_white(pattern):
    steps = pattern.eval_on_selector_all(".wedge .step", "els => els.map(e => e.dataset.value)")
    assert steps == [str(v) for v in range(0, 101, 10)]


def test_the_font_ladder_covers_the_expected_sizes(pattern):
    sizes = pattern.eval_on_selector_all(".ladder .rung", "els => els.map(e => e.dataset.size)")
    assert sizes == ["14", "18", "22", "26", "30", "36", "44"]


def test_each_rung_shows_a_real_term_label_not_lorem_ipsum(pattern):
    texts = pattern.eval_on_selector_all(".ladder .rung", "els => els.map(e => e.textContent)")
    assert all("Betonspritzen mit Drohnen" in text for text in texts)


def test_the_page_fills_exactly_1920x1080(pattern):
    size = pattern.evaluate("({w: document.body.scrollWidth, h: document.body.scrollHeight})")
    assert size == {"w": 1920, "h": 1080}
