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
        
        max_pages = 5  # Check the top 5 recent pages daily
        
        for current_page in range(max_pages):
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
            
            # Click 'Next' button if present
            next_button = page.query_selector("a:has-text('Next'), a:has-text('>')")
            if next_button and current_page < max_pages - 1:
                next_button.click()
                page.wait_for_timeout(3000) # Pause for ASP.NET postback to complete
            else:
                break
                
        browser.close()

    return func.HttpResponse(
        json.dumps(results),
        mimetype="application/json",
        status_code=200
    )
