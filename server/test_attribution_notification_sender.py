from pathlib import Path
import pytest

from attribution_notification import (
    NotificationLedger,
    attribution_content_selector,
    content_crop_box,
    attribution_ready_selector,
    attribution_trend_selector,
    trend_ready_expression,
    flatten_scroll_container,
    fund_content_selector,
    fund_ready_selector,
    save_fund_report_png,
    theme_init_script,
    browser_launch_options,
    login_submit_selector,
    login_password_selector,
    login_username_selector,
    _ensure_logged_in,
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


class _StubLocator:
    def __init__(self, log: list, name: str, count: int = 1):
        self.log = log
        self.name = name
        self._count = count
        self.first = self

    def count(self) -> int:
        return self._count

    def wait_for(self, state: str, timeout: int = 0) -> None:
        self.log.append(("wait_for", self.name, state))
        if self._count == 0:  # 和真实 playwright 一致：元素不在就等不到
            raise TimeoutError(f"{self.name} not attached")

    def fill(self, value: str) -> None:
        self.log.append(("fill", self.name, value))

    def click(self) -> None:
        self.log.append(("click", self.name))


class _StubPage:
    """Replays a login form that ignores early submits / mounts late, like a real SPA."""

    def __init__(
        self,
        *,
        login_present: int = 1,
        accepted_attempts: int = 2,
        content_present: int = 0,
        form_mounts_after_reload: int | None = None,
    ):
        self.log: list = []
        self._login_present = login_present
        self._accepted = accepted_attempts
        self._attempts = 0
        self._content_present = content_present
        self._form_mounts_after_reload = form_mounts_after_reload
        self._reloads = 0

    def locator(self, selector: str) -> _StubLocator:
        if "username" in selector or "请输入用户名" in selector:
            return _StubLocator(self.log, "username", self._login_present)
        if "password" in selector or "请输入密码" in selector:
            return _StubLocator(self.log, "password")
        if "content" in selector:
            return _StubLocator(self.log, "content", self._content_present)
        return _StubLocator(self.log, "submit")

    def goto(self, url: str, wait_until: str = "load", timeout: int = 0) -> None:
        self.log.append(("goto", url, wait_until))
        self._reloads += 1
        if (
            self._form_mounts_after_reload is not None
            and self._reloads >= self._form_mounts_after_reload
        ):
            self._login_present = 1  # 重新加载后表单才挂上(SPA 首屏渲染慢的真实情况)

    def wait_for_selector(self, selector: str, state: str = "attached", timeout: int = 0) -> None:
        self.log.append(("wait_content", selector))
        self._attempts += 1
        if self._attempts < self._accepted:
            raise TimeoutError("content not attached yet")


def test_login_is_retried_and_reloaded_when_the_first_submit_is_ignored():
    page = _StubPage(login_present=1, accepted_attempts=2)

    logged_in = _ensure_logged_in(
        page,
        "admin",
        "admin123",
        web_url="http://host/?tab=credit",
        content_selector="[data-testid='credit-attribution-content']",
        timeout_ms=1000,
    )

    assert logged_in is True
    assert [entry[0] for entry in page.log].count("click") == 2
    # 第一次提交无效后必须带会话重新导航，否则会带着旧 token 请求而拿到 401
    assert ("goto", "http://host/?tab=credit", "domcontentloaded") in page.log
    assert page.log[-1][0] == "wait_content"


def test_login_returns_ok_when_content_is_already_rendered():
    """不需要登录(内容区已经在)时直接成功，不去点表单。"""
    page = _StubPage(login_present=0, content_present=1)

    assert (
        _ensure_logged_in(
            page,
            "",
            "",
            web_url="http://host/",
            content_selector="[data-testid='credit-attribution-content']",
            timeout_ms=1000,
        )
        is True
    )
    assert [entry[0] for entry in page.log].count("click") == 0


def test_login_waits_for_a_login_form_that_mounts_late():
    """回归：表单晚挂载时不能当成"已登录"直接返回，否则截图会卡到超时
    (10/10 资金归结日报截图失败回退文字就是这么来的)。"""
    page = _StubPage(login_present=0, content_present=0, form_mounts_after_reload=1, accepted_attempts=1)

    assert (
        _ensure_logged_in(
            page,
            "admin",
            "admin123",
            web_url="http://host/?tab=fund",
            content_selector="[data-testid='fund-attribution-content']",
            timeout_ms=1000,
        )
        is True
    )
    assert [entry[0] for entry in page.log].count("goto") == 1
    assert [entry[0] for entry in page.log].count("click") == 1


def test_login_gives_up_with_a_clear_error_instead_of_hanging():
    page = _StubPage(login_present=1, accepted_attempts=99)

    with pytest.raises(RuntimeError, match="登录提交后未进入监控页面"):
        _ensure_logged_in(
            page,
            "admin",
            "admin123",
            web_url="http://host/?tab=fund",
            content_selector="[data-testid='fund-attribution-content']",
            timeout_ms=1000,
        )
    assert [entry[0] for entry in page.log].count("click") == 3
    assert [entry[0] for entry in page.log].count("goto") == 2


def test_login_without_credentials_raises_before_clicking():
    page = _StubPage(login_present=1)

    with pytest.raises(ValueError, match="ATTRIBUTION_NOTIFY_USERNAME"):
        _ensure_logged_in(
            page,
            "",
            "",
            web_url="http://host/",
            content_selector="[data-testid='credit-attribution-content']",
            timeout_ms=1000,
        )
    assert [entry[0] for entry in page.log].count("click") == 0


def test_login_fails_fast_when_neither_form_nor_content_appears():
    page = _StubPage(login_present=0, content_present=0)

    with pytest.raises(RuntimeError, match="登录提交后未进入监控页面"):
        _ensure_logged_in(
            page,
            "admin",
            "admin123",
            web_url="http://host/",
            content_selector="[data-testid='credit-attribution-content']",
            timeout_ms=1000,
        )
    assert [entry[0] for entry in page.log].count("click") == 0


def test_fund_screenshot_targets_the_fund_content_column():
    assert fund_content_selector() == "[data-testid='fund-attribution-content']"
    assert fund_ready_selector() == fund_content_selector()


def test_fund_report_png_is_named_for_the_fund_prefix(tmp_path: Path):
    from datetime import datetime, timezone

    path = save_fund_report_png(
        tmp_path, "20260928", b"png", datetime(2026, 9, 29, 6, 1, 34, tzinfo=timezone.utc)
    )

    assert path.parent == tmp_path
    assert path.name == "fund_attribution_20260928_20260929_060134.png"
    assert path.read_bytes() == b"png"
