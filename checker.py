"""KFZ-Zulassung Köln – Terminprüfer (Playwright).

Ablauf (wie von Hand):
 1. stadt-koeln.de/artikel/06415 öffnen, Link "Terminbuchung Kfz-Zulassungsstelle" holen
 2. Dienstleistung "Anmeldung eines Gebrauchtfahrzeuges (Umschreibung ...)" auf 1 setzen
 3. "Weiter" klicken -> Terminkalender
Jeder Schritt wird geloggt und als Screenshot/HTML in debug/ gespeichert.
"""
import os, re, sys, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INFO_URL = "https://www.stadt-koeln.de/artikel/06415/index.html"
FALLBACK_URL = ("https://termine.stadt-koeln.de/m/kfz-zulassung/extern/calendar/"
                "?uid=67523a04-37af-4131-9495-0a3566e0eb8b")
SERVICE_TEXT = os.environ.get("SERVICE_TEXT", "Anmeldung eines Gebrauchtfahrzeuges (Umschreibung")
LIMIT = datetime.strptime(os.environ.get("DATE_LIMIT", "2026-10-30"), "%Y-%m-%d")
NO_SLOTS_PATTERNS = [r"keine\s+(freien\s+)?termine", r"keine\s+termine\s+verf",
                     r"ausgebucht", r"keine\s+verf.gbaren\s+termine"]

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
    print(f"[{step_no:02d}] {name}  ->  {page.url}  | Titel: {page.title()!r}")


def settle(page, ms=1500):
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    page.wait_for_timeout(ms)


def click_first(page, selectors, label):
    for sel in selectors:
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            if el.is_visible() and el.is_enabled():
                el.click()
                settle(page)
                print(f"  geklickt: {label} ({sel})")
                return True
    print(f"  nicht gefunden: {label}")
    return False


def dismiss_popups(page):
    # Cookie-Banner / Hinweis-Dialoge (falls vorhanden)
    click_first(page, ["button:has-text('Alle akzeptieren')", "button:has-text('Akzeptieren')",
                       "button:has-text('Einverstanden')", "[role=dialog] button:has-text('OK')",
                       ".modal button:has-text('OK')", ".modal button:has-text('Schließen')"],
                "Banner/Dialog")


def select_service(page):
    """Setzt die Anzahl der gewünschten Dienstleistung auf 1.
    Sucht vom Text aus nach oben den kleinsten Block, der genau EIN Eingabeelement hat."""
    result = page.evaluate(
        """(needle) => {
          const all = [...document.querySelectorAll('body *')];
          const hit = all.find(e => e.children.length === 0 && e.textContent.includes(needle))
                   || all.reverse().find(e => e.textContent.includes(needle));
          if (!hit) return 'TEXT_NICHT_GEFUNDEN';
          let n = hit;
          for (let up = 0; up < 8 && n; up++, n = n.parentElement) {
            const sels = n.querySelectorAll('select');
            const nums = n.querySelectorAll('input[type=number], input[type=text]');
            const plus = [...n.querySelectorAll('button, a, input[type=button]')]
                         .filter(b => /^\\s*\\+\\s*$/.test(b.textContent || b.value || '')
                                   || /plus|erh(ö|oe)hen|increase|add/i.test(
                                        (b.getAttribute('aria-label')||'') + ' ' + (b.title||'') + ' ' + b.className + ' ' + b.id));
            if (sels.length === 1) {
              const s = sels[0];
              const opt = [...s.options].find(o => o.value === '1' || o.text.trim() === '1');
              if (!opt) return 'SELECT_OHNE_1';
              s.value = opt.value;
              s.dispatchEvent(new Event('input', {bubbles: true}));
              s.dispatchEvent(new Event('change', {bubbles: true}));
              return 'select';
            }
            if (nums.length === 1) {
              nums[0].value = '1';
              nums[0].dispatchEvent(new Event('input', {bubbles: true}));
              nums[0].dispatchEvent(new Event('change', {bubbles: true}));
              return 'input';
            }
            if (plus.length === 1) { plus[0].click(); return 'plus-button'; }
            if (sels.length + nums.length + plus.length > 1) return 'MEHRDEUTIG';
          }
          return 'KEIN_EINGABEFELD';
        }""",
        SERVICE_TEXT,
    )
    print(f"  Dienstleistung setzen: {result}")
    return result in ("select", "input", "plus-button")


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
    found = set()
    for d, m, y in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(20\d\d)\b", text):
        try: found.add(datetime(int(y), int(m), int(d)))
        except ValueError: pass
    return sorted(found)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="de-DE", viewport={"width": 1280, "height": 900}, user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"))
        page.set_default_timeout(20000)

        # 1. Link zur Kfz-Terminbuchung frisch von stadt-koeln.de holen
        booking_url = FALLBACK_URL
        try:
            page.goto(INFO_URL, wait_until="domcontentloaded")
            link = page.locator("a:has-text('Terminbuchung Kfz-Zulassungsstelle')").first
            if link.count():
                booking_url = link.get_attribute("href") or FALLBACK_URL
        except Exception as e:
            print(f"  Info-Seite nicht lesbar ({e}) – nutze Fallback-URL")
        print(f"  Buchungs-URL: {booking_url}")

        page.goto(booking_url, wait_until="domcontentloaded")
        settle(page)
        snap(page, "terminseite")
        if "nicht zugelassen" in page.inner_text("body").lower():
            print("GESPERRT: Die Stadt Köln lehnt den Zugriff ab (Sperrseite).")
            sys.exit(1)

        dismiss_popups(page)

        # 2. Dienstleistung auf 1
        if not select_service(page):
            snap(page, "FEHLER_dienstleistung")
            print("Seitentext (Auszug):\n" + page.inner_text("body")[:2500])
            sys.exit(1)
        settle(page, 800)
        snap(page, "dienstleistung_gewaehlt")

        # 3. Weiter (ggf. mehrere Schritte: Hinweise, Standort ...)
        for i in range(4):
            dismiss_popups(page)
            text = page.inner_text("body").lower()
            if any(re.search(p, text) for p in NO_SLOTS_PATTERNS) or re.search(r"\d{1,2}\.\d{1,2}\.20\d\d", text) and i > 0:
                break
            if not click_first(page, ["button:has-text('Weiter')", "input[value='Weiter']",
                                      "a:has-text('Weiter')", "button:has-text('OK')"], f"Weiter #{i+1}"):
                break
            snap(page, f"nach_weiter_{i+1}")

        snap(page, "kalender")
        text = page.inner_text("body")
        print("---- Seitentext Kalender (Auszug) ----\n" + text[:3000] + "\n---------------------------")

        low = text.lower()
        if any(re.search(p, low) for p in NO_SLOTS_PATTERNS):
            print("Ergebnis: keine freien Termine.")
            browser.close()
            return

        # Nur den Abschnitt "Tage mit verfügbaren Terminen" auswerten
        m = re.search(r"Tage mit verf.gbaren Terminen(.*?)(Ihre bisherigen Angaben|$)", text, re.S)
        section = m.group(1) if m else text
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        free = [d for d in dates_in_text(section) if d >= today]
        print("Freie Tage laut Kalender: " + (", ".join(d.strftime("%d.%m.%Y") for d in free) or "keine"))
        hits = [d for d in free if d <= LIMIT]
        if hits:
            days = ", ".join(d.strftime("%d.%m.%Y") for d in hits)
            print(f"Ergebnis: mögliche Termine bis {LIMIT:%d.%m.%Y}: {days}")
            send_email("Freier KFZ-Termin in Köln?",
                       f"Möglicherweise freie Tage bis {LIMIT:%d.%m.%Y}: {days}\n\n"
                       f"Jetzt buchen: {booking_url}\n")
        else:
            print(f"Ergebnis: kein freier Tag bis {LIMIT:%d.%m.%Y}.")
        browser.close()


if __name__ == "__main__":
    try:
        run()
    except PWTimeout as e:
        print(f"Timeout: {e}"); sys.exit(1)
