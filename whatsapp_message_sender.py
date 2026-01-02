import os
import sys
import time
import argparse
import logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# pyperclip is optional — if it's not installed we'll fall back to typing the message
try:
    import pyperclip
except Exception:
    pyperclip = None


def prepare_message(name: str) -> str:
    return f"""🌸 હાર્દિક આમંત્રણ 🌸
માનનીય *{name}*,

શ્રી *મુકેશભાઈ કાંબલિયા* તરફથી
તેમની લાડકી પુત્રી કરીનાના લગ્ન પ્રસંગે,
આપને હાર્દિક આમંત્રણ પાઠવવામાં આવે છે.

આ શુભ અવસર પર આપની ઉપસ્થિતિ,
આશીર્વાદ અને સ્નેહની ઉપસ્થિતિ અમૂલ્ય રહેશે. 💐

સાદર આમંત્રણ,
*શ્રી મુકેશભાઈ ડોસાભાઈ કાંબલિયા તથા પરિવાર,સુખપુર,જૂનાગઢ.*"""


class WhatsAppMessageSender:
    def __init__(self, chrome_profile_path: str = "chrome_profile", headless: bool = False):
        self.chrome_profile_path = chrome_profile_path
        self.headless = headless
        self.driver = None
        self.wait_time = 60

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument(f"user-data-dir={os.path.abspath(self.chrome_profile_path)}")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option('prefs', {
            'profile.default_content_setting_values.notifications': 2,
            'profile.default_content_settings.popups': 0,
        })
        service = Service(ChromeDriverManager().install())
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.maximize_window()
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(30)
        except Exception as e:
            print(f"Failed to start Chrome: {e}")
            raise

    def _check_whatsapp_ready(self, wait_time: int = 30) -> bool:
        try:
            print("Waiting for WhatsApp Web to load...")
            WebDriverWait(self.driver, wait_time).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#pane-side')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#main')),
                    EC.presence_of_element_located((By.XPATH, '//*[contains(text(), "Phone number shared via url is invalid.")]'))
                )
            )
            try:
                invalid_num = self.driver.find_element(By.XPATH, '//*[contains(text(), "Phone number shared via url is invalid.")]')
                if invalid_num.is_displayed():
                    print("Invalid phone number detected")
                    return False
            except Exception:
                pass
            message_input = WebDriverWait(self.driver, wait_time).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#main > footer > div.x1n2onr6.xhtitgo.x9f619.x78zum5.x1q0g3np.xuk3077.xjbqb8w.x1wiwyrm.xquzyny.xvc5jky.x11t971q.xnpuxes.copyable-area > div > span > div > div._ak1r > div > div.x1n2onr6.xh8yej3.xjdcl3y.lexical-rich-text-input')),
                    EC.presence_of_element_located((By.XPATH, '//*[@id="main"]/footer/div[1]/div/span/div/div[2]/div/div[3]/div[1]'))
                )
            )
            time.sleep(2)
            return True
        except Exception as e:
            print(f"WhatsApp Web loading error: {e}")
            return False

    def send_text_message(self, contact_number: str, message: str) -> tuple:
        try:
            contact_number = str(contact_number).strip().replace("+", "").replace(" ", "")
            url = f"https://web.whatsapp.com/send?phone=+91{contact_number}"
            print(f"Opening chat for +91{contact_number}")
            self.driver.get(url)
            if not self._check_whatsapp_ready():
                print("WhatsApp Web not ready")
                return False, "WhatsApp Web not ready"
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tab="11"]'))
                )
            except Exception:
                print("Chat failed to load")
                return False, "Chat failed to load"

            message_box = None
            try:
                message_box = self.driver.find_element(By.CSS_SELECTOR, '#main > footer > div.x1n2onr6.xhtitgo.x9f619.x78zum5.x1q0g3np.xuk3077.xjbqb8w.x1wiwyrm.xquzyny.xvc5jky.x11t971q.xnpuxes.copyable-area > div > span > div > div._ak1r > div > div.x1n2onr6.xh8yej3.xjdcl3y.lexical-rich-text-input')
            except Exception:
                try:
                    message_box = self.driver.find_element(By.XPATH, '/html[1]/body[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[1]/div[5]/div[1]/footer[1]/div[1]/div[1]/span[1]/div[1]/div[2]/div[1]/div[3]/div[1]/p[1]')
                except Exception:
                    print("Message box not found with any selector")
                    return False, "Message box not found"

            try:
                # 1) Type 'test' using keyboard events to reveal send button
                print("Typing dummy text 'test' to reveal send button...")
                actions = ActionChains(self.driver)
                actions.click(message_box)
                actions.pause(0.3)
                actions.send_keys('test')
                actions.pause(0.8)
                actions.perform()

                # 2) Wait for send button to appear
                print("Waiting for send button to appear...")
                try:
                    send_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'span[data-icon="wds-ic-send-filled"]'))
                    ).find_element(By.XPATH, '//span[@data-icon="wds-ic-send-filled"]')
                    print("Send button appeared.")
                except Exception as e:
                    print(f"Send button did not appear: {e}")
                    return False, f"Send button did not appear: {e}"

                # 3) Clear the 'test' text
                print("Clearing dummy text...")
                actions = ActionChains(self.driver)
                actions.click(message_box)
                actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL)
                actions.send_keys(Keys.DELETE)
                actions.pause(0.4)
                actions.perform()
                time.sleep(0.4)

                # 4) Paste the personalized message at once using clipboard (faster than typing)
                print("Pasting personalized message from clipboard...")
                try:
                    pyperclip.copy(message)
                    actions = ActionChains(self.driver)
                    actions.click(message_box)
                    actions.pause(0.2)
                    # Ctrl+V to paste on Windows; use COMMAND on Mac if needed
                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL)
                    actions.pause(0.5)
                    actions.perform()
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Clipboard paste failed ({e}); falling back to typing...")
                    actions = ActionChains(self.driver)
                    actions.click(message_box)
                    actions.pause(0.2)
                    actions.send_keys(message)
                    actions.pause(0.6)
                    actions.perform()
                    time.sleep(0.5)

                # Ensure input event dispatched so WhatsApp registers pasted content
                try:
                    self.driver.execute_script('arguments[0].dispatchEvent(new Event("input", {bubbles:true}));', message_box)
                except Exception:
                    pass

                # 5) Re-locate the send button (after paste) with multiple fallbacks and click it
                print("Locating send button after paste...")
                send_button = None
                # Candidate locators: prefer the button element; fall back to span then get parent
                candidate_locators = [
                    # explicit long CSS selector provided by user
                    (By.CSS_SELECTOR, ".html-div.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.xyri2b.x18d9i69.x1c1uobl.x78zum5.xl56j7k.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x1so62im.x1syfmzz.x1ja2u2z.x1s928wv.x1j6awrg.x4eaejv.x1wsn0xg.x1r0yslu.x2q1x1w.xapdjt.xr6f91l.x5rv0tg.x1akc3lz.xikp0eg.x1xl5mkn.x1mfml39.x1l5mzlr.xgmdoj8.x1f1wgk5.x1x3ic1u.xfn3atn.x1pse0pq.x1yxkqql.xk8lq53.x9f619.xt8t1vi.x1xc408v.x129tdwq.x15urzxu.x1vqgdyp.x100vrsf"),
                    (By.XPATH, "//button[.//span[@data-icon='send'] ]"),
                    (By.XPATH, "//button[.//span[@data-icon='wds-ic-send-filled'] ]"),
                    (By.XPATH, "//button[.//span[contains(@data-icon,'send')]]"),
                    (By.CSS_SELECTOR, "button span[data-icon='send']"),
                    (By.CSS_SELECTOR, "button span[data-icon='wds-ic-send-filled']"),
                    (By.XPATH, "//div[@role='button' and .//span[@data-icon='send']]")
                ]

                for locator in candidate_locators:
                    try:
                        el = WebDriverWait(self.driver, 3).until(EC.presence_of_element_located(locator))
                        # If locator matched a span inside button, find ancestor button
                        tag = el.tag_name.lower()
                        if tag == 'button':
                            send_button = el
                        else:
                            try:
                                send_button = el.find_element(By.XPATH, "ancestor::button[1]")
                            except Exception:
                                # try parent
                                try:
                                    send_button = el.find_element(By.XPATH, '..')
                                except Exception:
                                    send_button = None

                        if send_button:
                            # ensure it's visible and enabled (simple polling)
                            found_ready = False
                            for _ in range(6):
                                try:
                                    if send_button.is_displayed() and send_button.is_enabled():
                                        found_ready = True
                                        break
                                except Exception:
                                    pass
                                time.sleep(0.25)

                            if found_ready:
                                # scroll into view for safety
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", send_button)
                                except Exception:
                                    pass
                                print(f"Found send button using locator: {locator}")
                                break
                            else:
                                # not ready, continue to next locator
                                send_button = None
                    except Exception:
                        continue

                if not send_button:
                    # Last resort: try original span locator then navigate to parent
                    try:
                        span = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "span[data-icon='send']"))
                        )
                        send_button = span.find_element(By.XPATH, "ancestor::button[1]")
                    except Exception:
                        send_button = None

                if not send_button:
                    print("Could not locate send button after paste.")
                    # proceed to verification but report send-button-missing if verification fails
                else:
                    try:
                        print("Clicking send button (JS click)...")
                        self.driver.execute_script("arguments[0].click();", send_button)
                        time.sleep(1.5)
                    except Exception as e:
                        print(f"JS click failed: {e}; attempting Selenium click...")
                        try:
                            send_button.click()
                            time.sleep(1.5)
                        except Exception as e2:
                            print(f"Failed to click send button: {e2}")

                # Verification: check for message content and/or status icon
                print("Verifying message status...")
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, f"//div[contains(@class,'message-out')]//span[contains(text(), '{message.replace('"', '\"')}')]"))
                    )
                    print("Message appears in chat (outgoing).")
                except Exception:
                    print("Could not find exact message text in chat; will try status icon check.")

                try:
                    status_element = WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'message-out')]//span[@data-icon='msg-check' or @data-icon='msg-time']"))
                    )
                    status_type = status_element.get_attribute('data-icon')
                    print(f"Found message status: {status_type}")
                    return True, ""
                except Exception as e:
                    print(f"Could not verify message status: {e}")
                    return False, f"Could not verify message status: {e}"

            except Exception as e:
                print(f"Failed to send message: {e}")
                return False, str(e)

        except Exception as e:
            print(f"Error sending text message: {e}")
            return False, str(e)


def main():
    parser = argparse.ArgumentParser(description='Send WhatsApp messages from Excel')
    parser.add_argument('--excel', dest='excel', default='contacts.xlsx', help='Path to contacts Excel file')
    args = parser.parse_args()

    sender = WhatsAppMessageSender(chrome_profile_path="chrome_profile")

    try:
        sender.setup_driver()
        contacts_df = pd.read_excel(args.excel)
        total = len(contacts_df)
        print(f"Starting to send personalized messages to {total} contacts...")

        # Ensure a 'Status' column exists to record results
        if 'Status' not in contacts_df.columns:
            contacts_df['Status'] = ''

        for idx, row in contacts_df.iterrows():
            name = row['Name']
            number = str(row['Number'])
            message = prepare_message(name)
            print(f"Sending message to {name} ({number})")
            ok = sender.send_text_message(number, message)
            # send_text_message now returns (success: bool, error_msg: str)
            success = False
            error_msg = ''
            try:
                success, error_msg = ok
            except Exception:
                # backward compatibility if function returned bool
                success = bool(ok)
                error_msg = '' if success else 'Unknown error'

            if success:
                print(f"✓ Message sent to {name}")
                contacts_df.at[idx, 'Status'] = 'Sent'
            else:
                print(f"X Message not sent to {name}: {error_msg}")
                contacts_df.at[idx, 'Status'] = f"Failed: {error_msg}"
            time.sleep(2)

        print(f"Completed sending messages: {total} attempted")

        # Attempt to save results back to the Excel file. If permission denied,
        # save to a new file with a timestamp suffix.
        try:
            contacts_df.to_excel(args.excel, index=False)
            print(f"Saved statuses to {args.excel}")
        except PermissionError:
            fallback = f"{os.path.splitext(args.excel)[0]}_status_{int(time.time())}.xlsx"
            contacts_df.to_excel(fallback, index=False)
            print(f"Could not write to {args.excel} (permission denied). Saved statuses to {fallback}")
        except Exception as e:
            fallback = f"{os.path.splitext(args.excel)[0]}_status_{int(time.time())}.xlsx"
            try:
                contacts_df.to_excel(fallback, index=False)
                print(f"Saved statuses to fallback file {fallback} after error: {e}")
            except Exception as e2:
                print(f"Failed to save statuses to both original and fallback files: {e2}")

    except Exception as e:
        print(f"Error during execution: {str(e)}")
    finally:
        if sender.driver:
            sender.driver.quit()


if __name__ == "__main__":
    main()
