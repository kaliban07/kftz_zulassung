"""KFZ-Zulassung Köln – Terminprüfer (Playwright).

Jeder Lauf startet frisch auf der Startseite, dadurch spielt die alle 30 Min.
wechselnde uid keine Rolle. Jeder Schritt wird geloggt und als Screenshot/HTML
in debug/ gespeichert (in GitHub unter "Artifacts" des Laufs abrufbar).
"""
import os, re, sys, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

START_URL = "https://termine.stadt-koeln.de/m/kfz-zulassung/"
SERVICE_TEXT = os.environ.get("SERVICE_TEXT", "Anmeldung eines Gebrauchtfahrzeug")
LIMIT = datetime.strptime(os.environ.get("DATE_LIMIT", "2026-10-23"), "%Y-%m-%d")
NO_SLOTS_PATTERNS = [r"keine\s+(freien\s+)?termine", r"keine\s+termine\s+verf", r"ausgebucht"]

SMTP_SERVER = os.environ.get("SMTP_SERVER") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 465)
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")

os.makedirs("debug", exist_ok=True)
step_no = 0


def snap(page, name):
    global step_no
    step_no += 1
    base = f"debug/{step_no:02d}_{name}"
    try:
        page.screenshot(path=base + ".png", full_page=True)
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print(f"  (Snapshot fehlgeschlagen: {e})")
    print(f"[{step_no:02d}] {name}  ->  {page.url}")


def click_first(page, selectors, label):
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            page.wait_for_load_state("networkidle")
            print(f"  geklickt: {label} ({sel})")
            return True
    print(f"  nicht gefunden: {label}")
    return False


def send_email(subject, body):
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_RECIPIENT]):
        print("E-Mail-Secrets unvollständig – keine Mail.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"], msg["To"], msg["Subject"] = EMAIL_USER, EMAIL_RECIPIENT, subject
    if SMTP_PORT == 465:
        s = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
    else:
        s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30); s.starttls()
    s.login(EMAIL_USER, EMAIL_PASS)
    s.sendmail(EMAIL_USER, [EMAIL_RECIPIENT], msg.as_string())
    s.quit()
    print("E-Mail versendet.")


def dates_in_text(text):
    """Findet Datumsangaben 'dd.mm.yyyy' bzw. 'yyyy-mm-dd' im Seitentext."""
    found = set()
    for d, m, y in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(20\d\d)\b", text):
        try: found.add(datetime(int(y), int(m), int(d)))
        except ValueError: pass
    for y, m, d in re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text):
        try: found.add(datetime(int(y), int(m), int(d)))
        except ValueError: pass
    return sorted(found)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="de-DE", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"))
        page.set_default_timeout(20000)

        page.goto(START_URL, wait_until="networkidle")
        snap(page, "start")

        # Cookie-/Hinweisbanner wegklicken (falls vorhanden)
        click_first(page, ["button:has-text('Akzeptieren')", "button:has-text('Alle akzeptieren')",
                           "button:has-text('OK')"], "Cookie-Banner")

        click_first(page, ["text=Neuen Termin buchen", "text=Termin buchen",
                           "a:has-text('Termin vereinbaren')"], "Termin buchen")
        snap(page, "nach_termin_buchen")

        # Dienstleistung: Anzahl auf 1 – sowohl <select>, Zahlenfeld als auch "+"-Button probieren
        row = page.locator(f"text={SERVICE_TEXT}").first
        if not row.count():
            snap(page, "FEHLER_dienstleistung_fehlt")
            print(f"Dienstleistung '{SERVICE_TEXT}' nicht gefunden – siehe Screenshot.")
            sys.exit(1)
        container = row.locator("xpath=ancestor::*[.//select or .//input or .//button][1]")
        if container.locator("select").count():
            container.locator("select").first.select_option("1")
        elif container.locator("input[type=number], input[type=text]").count():
            container.locator("input[type=number], input[type=text]").first.fill("1")
        elif container.locator("button:has-text('+')").count():
            container.locator("button:has-text('+')").first.click()
        else:
            row.click()
        snap(page, "dienstleistung_gewaehlt")

        # Bis zu 3 "Weiter"-Schritte (Hinweise, Standortwahl …) durchklicken
        for i in range(3):
            if not click_first(page, ["button:has-text('Weiter')", "input[value='Weiter']",
                                      "a:has-text('Weiter')"], f"Weiter #{i+1}"):
                break
            page.wait_for_timeout(1500)
            snap(page, f"nach_weiter_{i+1}")

        text = page.inner_text("body")
        low = text.lower()
        if any(re.search(p, low) for p in NO_SLOTS_PATTERNS):
            print("Ergebnis: keine freien Termine.")
            browser.close()
            return

        # Freie Tage: klickbare Kalendertage (nicht disabled) + Datumsangaben im Text
        candidates = set(d for d in dates_in_text(text) if datetime.now() <= d <= LIMIT)
        for el in page.locator("[data-date]:not([disabled]):not(.disabled)").all():
            ds = el.get_attribute("data-date") or ""
            try:
                d = datetime.strptime(ds[:10], "%Y-%m-%d")
                if d <= LIMIT: candidates.add(d)
            except ValueError:
                pass

        snap(page, "kalender")
        if candidates:
            days = ", ".join(d.strftime("%d.%m.%Y") for d in sorted(candidates))
            print(f"Ergebnis: mögliche Termine bis {LIMIT:%d.%m.%Y}: {days}")
            send_email("Freier KFZ-Termin in Köln?",
                       f"Möglicherweise freie Tage bis {LIMIT:%d.%m.%Y}: {days}\n\n"
                       f"Jetzt buchen: {START_URL}\n")
        else:
            print("Ergebnis: Kalender erreicht, aber keine passenden Tage erkannt "
                  "(Screenshot 'kalender' prüfen).")
        browser.close()


if __name__ == "__main__":
    try:
        run()
    except PWTimeout as e:
        print(f"Timeout: {e}"); sys.exit(1)
