from fastapi import FastAPI, HTTPException
from playwright.sync_api import sync_playwright
import logging

app = FastAPI(title="MCMC Scraper API")


def scrape_mcmc(max_pages: int = 5) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()
        page.goto(
            "https://www.mcmc.gov.my/en/legal/registers/cma-registers/register-of-directions-section-54-1/list-of-register-of-directions-section-54"
        )

        for current_page in range(max_pages):
            page.wait_for_selector("table")

            rows = page.query_selector_all("table tbody tr")
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

            next_button = page.query_selector("a:has-text('Next'), a:has-text('>')")
            if next_button and current_page < max_pages - 1:
                next_button.click()
                page.wait_for_timeout(3000)
            else:
                break

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
