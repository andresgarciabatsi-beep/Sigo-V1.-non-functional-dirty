from pathlib import Path
import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig
import asyncio


def get_html_httpx(url: str) -> tuple[str, int, str]:
    """Descarga una página web y devuelve su HTML empleando httpx"""

    #Encabezados que iran en el paquete para evitar bloqueos
    headers = {
        "User-Agent": "Mozilla/5.0",        #Se simula una consulta desde Mozilla
        "Accept-Language": "es-EC,es;q=0.9" #Para forzar que se devuelva la versión en español
    }

    #Abrir una conexion HTTP con la página web
    with httpx.Client(
        headers=headers,
        timeout=20,
        follow_redirects=True
    ) as client:

        #Realizar peticion web
        response = client.get(url)

        #Obtener el código de estado HTTP de la respuesta
        response_http_status_code = response.status_code

        #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))
        print("fetch: get_html_httpx in get_html.py: accessing URL:", response.url)
        print("fetch: get_html_httpx in get_html.py: HTTP code received:", response_http_status_code)
        #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))

        #Detener el programa si la petición no fue exitosa.
        #response.raise_for_status()


        #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))
        #Avisar si la respuesta recibida no contiene html
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("fetch: get_html_httpx in get_html.py: HTTP response does not contain HTML.")
        else:
            print("fetch: get_html_httpx in get_html.py: HTTP response contains HTML.")
        #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))

        return response.text, response_http_status_code, str(response.url)


def get_html_crawling(url: str) -> tuple[str, int, str]:

    #Corutina para ejecutar el crawler
    async def get_html_crawling_async():
        #Configurar el buscador Chromium en modo headless --> no GUI)
        async with AsyncWebCrawler(config=BrowserConfig(browser_type="chromium", 
                                                                     headless=True, 
                                                                     verbose=False)) as crawler:
            #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))
            print("fetch: get_html_crawling in get_html.py: accessing URL:", {url})
            #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))                    
            result = await crawler.arun(url=url)

            html = result.html or ""

            #(((((((((((((((((((((((((((((((((((((((((((LOGS))))))))))))))))))))))))))))))))))))))))))
            if not html:
                print("fetch: get_html_crawling in get_html.py: No HTML content received from the crawler.")
            #(((((((((((((((((((((((((((((((((((((((((((LOGS))))))))))))))))))))))))))))))))))))))))
            
            #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))
            response_http_status_code = result.status_code
            print("fetch: get_html_crawling in get_html.py: HTTP code received:", response_http_status_code)
            #(((((((((((((((((((((((((((((((((((((((((((LOGS)))))))))))))))))))))))))))))))))))))))))))
                                
        return html, response_http_status_code, result.url or url
    
    return asyncio.run(get_html_crawling_async())

# if __name__ == "__main__":
#     url = str("https://www.kubii.com/fr/cartes-nano-ordinateurs/5051-arduino-ventuno-q-7630049205949.html").strip()

#     try:
#         html, http_status_code = get_html_httpx(url)
#         SRC_PATH = Path(__file__).resolve().parent
        
#         #Guardando html
#         html_saved = SRC_PATH.parent/"results"/"pagina_producto.html"
#         html_saved.write_text(html, encoding="utf-8")

#         print("+"*100)
#         print("DEBUGGING")
#         print("+"*100)
#         print("Código HTTP:", http_status_code)
#         print("HTML guardado en:", html_saved)

#     except (httpx.HTTPError, ValueError, OSError) as error:
#         print("Error:", error)