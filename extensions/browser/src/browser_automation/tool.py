"""Browser automation tool using Playwright — navigate, click, type, screenshot, extract."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BrowserTool:
    """Headless browser automation via Playwright.

    Provides tools for web navigation, interaction, screenshot capture,
    and text extraction — all usable by the agent at runtime.
    """

    def __init__(self, headless: bool = True, screenshot_dir: Path | None = None) -> None:
        self._headless = headless
        self._screenshot_dir = screenshot_dir or Path.home() / ".jalaagent" / "screenshots"
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def _ensure_browser(self) -> None:
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()

    async def navigate(self, url: str) -> str:
        """Navigate to a URL and return the page title."""
        await self._ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded")
        title = await self._page.title()
        return f"Navigated to: {title} ({url})"

    async def click(self, selector: str) -> str:
        """Click an element by CSS selector."""
        await self._ensure_browser()
        await self._page.click(selector)
        return f"Clicked: {selector}"

    async def type_text(self, selector: str, text: str) -> str:
        """Type text into an input element."""
        await self._ensure_browser()
        await self._page.fill(selector, text)
        return f"Typed into {selector}"

    async def screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot and save to disk."""
        await self._ensure_browser()
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._screenshot_dir / f"{name}.png"
        await self._page.screenshot(path=str(path), full_page=True)
        return f"Screenshot saved: {path}"

    async def extract_text(self, selector: str = "body") -> str:
        """Extract visible text from the page or a specific element."""
        await self._ensure_browser()
        text = await self._page.inner_text(selector)
        preview = text[:5000] if len(text) > 5000 else text
        if len(text) > 5000:
            preview += f"\n... (truncated, {len(text)} chars total)"
        return preview

    async def get_html(self) -> str:
        """Return the full page HTML."""
        await self._ensure_browser()
        html = await self._page.content()
        return html[:10000]

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None

    # ------------------------------------------------------------------
    # Tool descriptors for registry
    # ------------------------------------------------------------------

    @staticmethod
    def tools() -> list[dict[str, Any]]:
        return [
            {"name": "browser_navigate", "description": "Navigate to a URL", "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
            {"name": "browser_click", "description": "Click an element by CSS selector", "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
            {"name": "browser_type", "description": "Type text into an input element", "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}},
            {"name": "browser_screenshot", "description": "Take a screenshot", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}}},
            {"name": "browser_extract_text", "description": "Extract text from page", "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}}}},
        ]
