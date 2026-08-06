from fastapi import FastAPI, HTTPException
from playwright.sync_api import sync_playwright
import logging

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

        current_page = 1
        stagnant_steps = 0
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

            if max_pages is not None and current_page >= max_pages:
                break

            first_row_before = rows[0].inner_text().strip()

            next_page = page.evaluate(
                """(currentPage) => {
                    const nav = document.querySelector("nav[aria-label='Page navigation example']");
                    if (!nav) return null;

                    const links = Array.from(nav.querySelectorAll("a[href*='__doPostBack']"));
                    let best = null;
                    let bestLink = null;

                    for (const link of links) {
                        const href = link.getAttribute("href") || "";
                        const m = href.match(/__doPostBack\('([^']+)'\s*,\s*'(\d+)'\)/);
                        if (!m) continue;

                        const pageNum = parseInt(m[2], 10);
                        if (Number.isNaN(pageNum) || pageNum <= currentPage) continue;

                        if (!best || pageNum < best.pageNum) {
                            best = { pageNum: pageNum };
                            bestLink = link;
                        }
                    }

                    if (best && bestLink) {
                        bestLink.click();
                    }

                    return best;
                }""",
                current_page,
            )

            if not next_page:
                break

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

            first_row_after = ""
            first_row_after_el = page.query_selector("table tbody tr")
            if first_row_after_el:
                first_row_after = first_row_after_el.inner_text().strip()

            if first_row_after == first_row_before:
                stagnant_steps += 1
            else:
                stagnant_steps = 0

            # Allow one slow/non-changing step, then stop to avoid infinite loops.
            if stagnant_steps >= 2:
                break

            current_page = int(next_page["pageNum"])

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
        return scrape_mcmc(max_pages=10)
    except Exception as exc:
        logging.exception("MCMC scrape failed")
        raise HTTPException(status_code=500, detail=f"Scrape failed: {exc}") from exc
