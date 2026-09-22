from pathlib import Path

from attribution_notification import (
    NotificationLedger,
    attribution_content_selector,
    content_crop_box,
    attribution_ready_selector,
    attribution_trend_selector,
    trend_ready_expression,
    flatten_scroll_container,
    theme_init_script,
    browser_launch_options,
    login_submit_selector,
    login_password_selector,
    login_username_selector,
)


def test_notification_ledger_claims_a_pt_once(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    assert ledger.claim("20260901") is False


def test_notification_ledger_releases_failed_claim(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    ledger.release("20260901")
    assert ledger.claim("20260901") is True


def test_browser_launch_options_uses_configured_executable(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_BROWSER_EXECUTABLE_PATH", r"C:\Browser\edge.exe")

    assert browser_launch_options() == {
        "headless": True,
        "executable_path": r"C:\Browser\edge.exe",
    }


def test_login_uses_explicit_submit_button():
    assert login_submit_selector() == "button[type='submit']"


def test_login_selectors_support_the_dashboard_placeholders():
    assert "请输入用户名" in login_username_selector()
    assert "请输入密码" in login_password_selector()


def test_screenshot_waits_for_loaded_attribution_content():
    assert attribution_ready_selector() == "[data-testid='credit-attribution-content']"


def test_screenshot_targets_content_without_sidebar():
    assert attribution_content_selector() == "[data-testid='credit-attribution-content']"


def test_content_crop_box_uses_content_bounds():
    assert content_crop_box({"x": 244.4, "y": 84.2, "width": 1176.1, "height": 1715.8}) == (244, 84, 1421, 1800)


def test_screenshot_waits_for_trend_chart():
    assert attribution_trend_selector() == "[data-testid='credit-attribution-trend-chart']"


def test_trend_ready_expression_requires_a_rendered_canvas():
    assert "Boolean" in trend_ready_expression()
    assert "canvas" in trend_ready_expression()


def test_screenshot_flattens_internal_main_scroll_container():
    script = flatten_scroll_container()
    assert "document.querySelector('main')" in script
    assert "overflow = 'visible'" in script


def test_screenshot_can_force_teal_theme():
    script = theme_init_script("teal")
    assert "rc-bi-theme" in script
    assert "teal" in script
