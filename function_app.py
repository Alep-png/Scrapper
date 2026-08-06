import azure.functions as func
from playwright.sync_api import sync_playwright
import json
import logging

app = func.FunctionApp()

@app.function_name(name="MCMCScraper")
@app.route(route="scrape", auth_level=func.AuthLevel.FUNCTION)
def MCMCScraper(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('MCMC Scraper HTTP trigger function started.')
    results = []
    
    with sync_playwright() as p:
        # Linux consumption plans often require no-sandbox Chromium flags.
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()
        
        # Navigate to MCMC Register page
        page.goto("https://www.mcmc.gov.my/en/legal/registers/cma-registers/register-of-directions-section-54-1/list-of-register-of-directions-section-54")
        
        # Set to an int (for example, 5) to cap pages for automation later.
        max_pages = None
        current_page = 1

        while True:
            page.wait_for_selector("table")
            
            rows = page.query_selector_all("table tbody tr")
            for row in rows:
                cols = row.query_selector_all("td")
                if len(cols) >= 4:
                    no_val = cols[0].inner_text().strip()
                    
                    # Extract document URL and text
                    link_elem = cols[1].query_selector("a")
                    dir_no_text = link_elem.inner_text().strip() if link_elem else cols[1].inner_text().strip()
                    dir_no_url = link_elem.get_attribute("href") if link_elem else ""
                    
                    # Form absolute URL if relative
                    if dir_no_url and not dir_no_url.startswith("http"):
                        dir_no_url = "https://www.mcmc.gov.my" + dir_no_url
                    
                    date_reg = cols[2].inner_text().strip()
                    details_text = cols[3].inner_text().strip()
                    
                    results.append({
                        "No": no_val,
                        "DirectionNoText": dir_no_text,
                        "DirectionNoUrl": dir_no_url,
                        "DateOfRegistration": date_reg,
                        "Details": details_text
                    })
            
            if max_pages is not None and current_page >= max_pages:
                break

            first_row_before = rows[0].inner_text().strip() if rows else ""

            # Numbered links can roll in groups (for example 1-10), so use Next.
            next_button = page.query_selector(
                "nav[aria-label='Page navigation example'] li.page-item:not(.disabled) a[aria-label='Next'], "
                "nav[aria-label='Page navigation example'] a[rel='next'], "
                "nav[aria-label='Page navigation example'] a:has-text('Next'), "
                "nav[aria-label='Page navigation example'] a:has-text('>')"
            )
            if next_button:
                next_button.scroll_into_view_if_needed()
                next_button.click(force=True)
                page.wait_for_timeout(3000) # Pause for ASP.NET postback to complete

                first_row_after = ""
                first_row_after_el = page.query_selector("table tbody tr")
                if first_row_after_el:
                    first_row_after = first_row_after_el.inner_text().strip()

                if first_row_after == first_row_before:
                    break

                current_page += 1
            else:
                break
                
        browser.close()

    return func.HttpResponse(
        json.dumps(results),
        mimetype="application/json",
        status_code=200
    )
