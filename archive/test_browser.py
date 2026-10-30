
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            locale="uk-UA",
            timezone_id="Europe/Kyiv"
        )

        try:
            print("Відкриваємо ДТЕК...")

            def log_request(request):
                if request.method == "POST":
                    print(f"\nЗАПИТ: {request.method} {request.url}")
                    print("ДАНІ:", (request.post_data or "")[:500])

            def log_response(response):
                if "/ua/ajax" in response.url:
                    async def show_response():
                        try:
                            print(f"\nВІДПОВІДЬ HTTP: {response.status}")
                            print("URL:", response.url)
                            print("ТЕКСТ:", (await response.text())[:1000])
                        except Exception as error:
                            print("Помилка відповіді:", error)

                    asyncio.create_task(show_response())

            page.on("request", log_request)
            page.on("response", log_response)

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000
            )
            await page.wait_for_timeout(2000)

            modal = page.locator("#modal-attention")
            if await modal.count():
                if await modal.get_attribute("aria-hidden") == "false":
                    close_button = modal.locator(
                        "button.m-attention__close"
                    )
                    if await close_button.count():
                        await close_button.evaluate("(el) => el.click()")
                        await page.wait_for_timeout(1000)

            street = page.locator("#street").first

            print("\nВводимо назву вулиці...")
            await street.fill("Іленка")
            await page.wait_for_timeout(5000)

            print("\nЗначення поля:", await street.input_value())

            results = await page.locator("body").evaluate("""
                body => [...body.querySelectorAll('*')]
                    .filter(el =>
                        el.children.length === 0 &&
                        /Іленка/i.test(el.textContent || '') &&
                        el.getClientRects().length > 0
                    )
                    .slice(0, 15)
                    .map(el => ({
                        tag: el.tagName,
                        className: String(el.className),
                        text: el.textContent.trim()
                    }))
            """)

            print("\nЗнайдені підказки:")
            if results:
                for item in results:
                    print(
                        item["tag"],
                        item["className"],
                        item["text"][:150]
                    )
            else:
                print("Підказок не знайдено.")

            await page.screenshot(path="street_debug.png")
            print("\nСкриншот збережено: street_debug.png")

            await page.wait_for_timeout(1000)

        except Exception as error:
            print("Помилка:", error)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
