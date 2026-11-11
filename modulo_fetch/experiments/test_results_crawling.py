
#Configurar el buscador Chromium en modo headless --> no GUI)
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig

url = "https://www.amazon.com/login"

async def main():
    async with AsyncWebCrawler(config=BrowserConfig(browser_type="chromium", 
                                                                     headless=True, 
                                                                     verbose=False)) as crawler:
    
        result = await crawler.arun(url=url)

        response_http_status_code = result.status_code
        response_http_success = result.success
        response_http_error_message = result.error_message
        
        print(response_http_status_code, "\n")
        print(response_http_success,"\n")
        print(response_http_error_message)
        

        
asyncio.run(main())
                                