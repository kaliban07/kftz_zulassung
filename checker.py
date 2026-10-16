import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from playwright.sync_api import sync_playwright

# Konfiguration
TARGET_DATE_LIMIT = datetime.strptime("2026-10-23", "%Y-%m-%d")
START_URL = "https://termine.stadt-koeln.de/m/kfz-zulassung/"

# E-Mail Zugangsdaten aus Umgebungsvariablen lesen
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")

def send_email_notification(available_dates, booking_url):
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_RECIPIENT]):
        print("E-Mail Zugangsdaten sind nicht vollständig konfiguriert.")
        return

    subject = "🎉 Freier KFZ-Termin in Köln gefunden!"
    dates_formatted = ", ".join(available_dates)
    
    body = f"""Hallo!

Es wurde ein freier KFZ-Zulassungstermin in Köln gefunden.

Verfügbare Tage bis 23.10.2026: {dates_formatted}

Hier geht es direkt zur Buchung:
{booking_url}

Beste Grüße
Dein autonomer Termin-Checker
"""

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        # Verbindung über SSL (Port 465) oder STARTTLS (Port 587)
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("E-Mail erfolgreich versendet.")
    except Exception as e:
        print(f"Fehler beim E-Mail-Versand: {e}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. Startseite aufrufen
        page.goto(START_URL)
        page.wait_for_timeout(2000)

        # 2. "Neuen Termin buchen" klicken (falls Button vorhanden)
        new_booking_btn = page.query_selector("text=Neuen Termin buchen")
        if new_booking_btn:
            new_booking_btn.click()
            page.wait_for_timeout(2000)

        # 3. Dienstleistung auswählen (Anmeldung Gebrauchtfahrzeug)
        service_label = page.locator("text=Anmeldung eines Gebrauchtfahrzeuges")
        if service_label.count() > 0:
            # Setze die Anzahl auf 1
            select_box = service_label.locator("xpath=..").locator("select")
            select_box.select_option("1")
            
            # Weiter-Button klicken
            page.click("button:has-text('Weiter')")
            page.wait_for_timeout(3000)

            # 4. Freie Termine im Kalender prüfen
            available_dates = page.query_selector_all(".calendar-day.available, [data-date]")
            
            found_dates = []
            for date_elem in available_dates:
                date_str = date_elem.get_attribute("data-date")
                if date_str:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    if date_obj <= TARGET_DATE_LIMIT:
                        found_dates.append(date_str)

            # 5. E-Mail senden, wenn passende Termine frei sind
            if found_dates:
                send_email_notification(found_dates, page.url)

        browser.close()

if __name__ == "__main__":
    run()
