from fastapi import FastAPI, HTTPException
from playwright.sync_api import sync_playwright
import logging
import re

TARGET_URL = (
    "https://www.mcmc.gov.my/en/legal/registers/cma-registers/"
    "register-of-directions-section-54-1/list-of-register-of-directions-section-54"
)

app = FastAPI(title="MCMC Scraper API")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "mcmc-scraper-api",
        "health": "/health",
        "scrape": "/scrape",
    }


def scrape_mcmc(max_pages: int | None = None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)

        pager_target = None
        detected_last_page = 1
        pager_links = page.query_selector_all(
            "nav[aria-label='Page navigation example'] a[href*='__doPostBack']"
        )
        for link in pager_links:
            href = link.get_attribute("href") or ""
            match = re.search(r"__doPostBack\('([^']+)'\s*,\s*'([^']+)'\)", href)
            if not match:
                continue

            pager_target = pager_target or match.group(1)
            page_token = match.group(2)
            if page_token.isdigit():
                detected_last_page = max(detected_last_page, int(page_token))

        max_page_to_scrape = detected_last_page
        if max_pages is not None:
            max_page_to_scrape = min(max_page_to_scrape, max_pages)

        current_page = 1
        while True:
            try:
                # In containerized headless runs, table can be attached before visible.
                page.wait_for_selector("table tbody tr", state="attached", timeout=45000)
            except Exception:
                page.wait_for_load_state("networkidle", timeout=20000)

            rows = page.query_selector_all("table tbody tr")
            if not rows:
                break

            for row in rows:
                cols = row.query_selector_all("td")
                if len(cols) >= 4:
                    no_val = cols[0].inner_text().strip()

                    link_elem = cols[1].query_selector("a")
                    dir_no_text = (
                        link_elem.inner_text().strip()
                        if link_elem
                        else cols[1].inner_text().strip()
                    )
                    dir_no_url = link_elem.get_attribute("href") if link_elem else ""

                    if dir_no_url and not dir_no_url.startswith("http"):
                        dir_no_url = "https://www.mcmc.gov.my" + dir_no_url

                    date_reg = cols[2].inner_text().strip()
                    details_text = cols[3].inner_text().strip()

                    results.append(
                        {
                            "No": no_val,
                            "DirectionNoText": dir_no_text,
                            "DirectionNoUrl": dir_no_url,
                            "DateOfRegistration": date_reg,
                            "Details": details_text,
                        }
                    )

            if current_page >= max_page_to_scrape:
                break

            if not pager_target:
                break

            first_row_before = rows[0].inner_text().strip()
            next_page_number = current_page + 1

            page.evaluate(
                """(args) => {
                    if (typeof __doPostBack === 'function') {
                        __doPostBack(args.target, String(args.nextPage));
                    }
                }""",
                {"target": pager_target, "nextPage": next_page_number},
            )

            try:
                page.wait_for_function(
                    """prev => {
                        const row = document.querySelector('table tbody tr');
                        return row && row.innerText.trim() !== prev;
                    }""",
                    first_row_before,
                    timeout=30000,
                )
            except Exception:
                page.wait_for_timeout(5000)

            current_page = next_page_number

        context.close()
        browser.close()

    return results


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/scrape")
def scrape() -> list[dict[str, str]]:
    try:
        logging.info("MCMC scrape started")
        return scrape_mcmc(max_pages=5)
    except Exception as exc:
        logging.exception("MCMC scrape failed")
        raise HTTPException(status_code=500, detail=f"Scrape failed: {exc}") from exc
