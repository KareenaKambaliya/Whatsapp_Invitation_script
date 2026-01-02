import logging
import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException, 
                                     StaleElementReferenceException,
                                     TimeoutException)
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import datetime

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('whatsapp_sender.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class WhatsAppSender:
    def __init__(self, chrome_profile_path: str = "chrome_profile", headless: bool = False):
        """Initialize WhatsApp sender with Chrome profile path."""
        self.chrome_profile_path = chrome_profile_path
        self.headless = headless
        self.driver = None
        self._initialize_driver()

    def _update_excel_status(self, excel_file: str, contact_number: str, status: str, 
                           message: Optional[str] = None, error_msg: Optional[str] = None) -> None:
        """Update contact status in Excel file with timestamp and details."""
        try:
            df = pd.read_excel(excel_file)
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Find the row with matching contact number
            mask = df['Number'].astype(str).str.replace(r'[^0-9]', '', regex=True) == str(contact_number).replace(r'[^0-9]', '')
            if not mask.any():
                logger.error(f"Contact number {contact_number} not found in Excel file")
                return
                
            # Update status columns
            df.loc[mask, 'Status'] = status
            df.loc[mask, 'Last Updated'] = timestamp
            df.loc[mask, 'Message'] = message if message else df.loc[mask, 'Message']
            df.loc[mask, 'Error'] = error_msg if error_msg else ''
            
            # Try to save to original file
            try:
                df.to_excel(excel_file, index=False)
                logger.info(f"Updated status for {contact_number} in {excel_file}")
            except PermissionError:
                # If original file is locked, save to timestamped copy
                backup_file = f"{os.path.splitext(excel_file)[0]}_{int(time.time())}_status.xlsx"
                df.to_excel(backup_file, index=False)
                logger.warning(f"Original file locked, saved status to {backup_file}")
            
        except Exception as e:
            logger.error(f"Failed to update Excel status: {e}")

    def send_file_with_message(self, excel_file: str, contact_number: str, 
                             message: str, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Send a file with a message to a WhatsApp contact and track status in Excel.
        
        Args:
            excel_file: Path to Excel file containing contacts and status
            contact_number: Contact number to send to
            message: Message text to send
            file_path: Path to file to attach
            
        Returns:
            Tuple of (success boolean, error message if any)
        """
        if not os.path.exists(file_path):
            error = f"File not found: {file_path}"
            self._update_excel_status(excel_file, contact_number, "FAILED", 
                                    message=message, error_msg=error)
            return False, error

        try:
            # Update status to sending
            self._update_excel_status(excel_file, contact_number, "SENDING", message=message)
            
            # Clean and format phone number
            contact_number = str(contact_number).strip().replace("+", "").replace(" ", "")
            url = f"https://web.whatsapp.com/send?phone=+91{contact_number}"
            self.driver.get(url)
            
            if not self._check_whatsapp_ready():
                error = "WhatsApp Web not ready"
                self._update_excel_status(excel_file, contact_number, "FAILED", 
                                        message=message, error_msg=error)
                return False, error

            # Check for invalid number
            try:
                invalid_number = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="popup-contents"]'))
                )
                if "Phone number shared via url is invalid" in invalid_number.text:
                    error = f"Invalid WhatsApp number: +91{contact_number}"
                    self._update_excel_status(excel_file, contact_number, "FAILED", 
                                            message=message, error_msg=error)
                    return False, error
            except TimeoutException:
                pass

            # Wait for chat to load
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tab="11"]'))
                )
            except TimeoutException:
                error = "Chat failed to load"
                self._update_excel_status(excel_file, contact_number, "FAILED", 
                                        message=message, error_msg=error)
                return False, error

            # Attach file
            try:
                attach_button = None
                attach_selectors = [
                    '[data-testid="attach-menu-plus"]',
                    '[data-testid="menu-bar-menu"]',
                    '[data-testid="attach"]',
                    '[data-testid="clip"]',
                    '[data-icon="attach"]',
                    '[data-icon="clip"]',
                    '[data-icon="attach-menu-plus"]',
                    '[aria-label*="attach"]',
                    '[aria-label*="Attach"]',
                    'span[data-icon="clip"]',
                    'span[data-testid="clip"]',
                    'button.input-button[aria-label*="attach"]'
                ]
                
                for selector in attach_selectors:
                    try:
                        elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        if elem.is_displayed():
                            attach_button = elem
                            break
                    except Exception:
                        continue

                if not attach_button:
                    error = "Could not find attach button"
                    self._update_excel_status(excel_file, contact_number, "FAILED", 
                                            message=message, error_msg=error)
                    return False, error

                try:
                    attach_button.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", attach_button)

                time.sleep(2)

                file_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
                )

                abs_path = os.path.abspath(file_path)
                file_input.send_keys(abs_path)
                logger.info(f"Attached file: {abs_path}")

                # Wait for upload
                time.sleep(3)

            except Exception as e:
                error = f"Failed to attach file: {str(e)}"
                self._update_excel_status(excel_file, contact_number, "FAILED", 
                                        message=message, error_msg=error)
                return False, error

            # Send message
            try:
                message_box = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"]'))
                )
                
                try:
                    message_box.click()
                    time.sleep(1)
                    
                    script = """
                        var element = arguments[0];
                        element.focus();
                        var temp = document.createElement('div');
                        temp.textContent = arguments[1];
                        element.innerHTML = temp.innerHTML;
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                        element.dispatchEvent(new Event('change', { bubbles: true }));
                    """
                    self.driver.execute_script(script, message_box, message)
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"Failed to input message: {e}")
                    # Fallback to clipboard
                    try:
                        import pyperclip
                        pyperclip.copy(message)
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        time.sleep(1)
                    except:
                        # Last resort: character by character
                        for char in message:
                            try:
                                message_box.send_keys(char)
                                time.sleep(0.05)
                            except:
                                continue

                # Click send
                send_button = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="Send"]'))
                )
                send_button.click()

                # Wait for message to appear in chat
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '//div[contains(@class,"message-out")]'))
                )

                # Check delivery status
                end_time = time.time() + 90
                status = None
                while time.time() < end_time:
                    try:
                        outs = self.driver.find_elements(By.XPATH, '//div[contains(@class,"message-out")]')
                        if not outs:
                            time.sleep(0.5)
                            continue
                        last = outs[-1]

                        if last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-dblcheck"], svg[data-icon="msg-dblcheck"]'):
                            status = 'DELIVERED'
                            break
                        elif last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-check"], svg[data-icon="msg-check"]'):
                            status = 'SENT'
                            break

                    except Exception:
                        time.sleep(0.5)
                        continue

                if status in ('DELIVERED', 'SENT'):
                    self._update_excel_status(excel_file, contact_number, status, message=message)
                    return True, None
                else:
                    error = "Message sent but delivery not confirmed"
                    self._update_excel_status(excel_file, contact_number, "UNCONFIRMED", 
                                            message=message, error_msg=error)
                    return False, error

            except Exception as e:
                error = f"Failed to send message: {str(e)}"
                self._update_excel_status(excel_file, contact_number, "FAILED", 
                                        message=message, error_msg=error)
                return False, error

        except Exception as e:
            error = f"Error sending message: {str(e)}"
            self._update_excel_status(excel_file, contact_number, "FAILED", 
                                    message=message, error_msg=error)
            return False, error

    def _initialize_driver(self):
        """Initialize Chrome WebDriver with appropriate options."""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument(f"user-data-dir={os.path.abspath(self.chrome_profile_path)}")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--silent")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--start-maximized")
            
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            if self.driver:
                self.driver.quit()
            raise

    def _check_whatsapp_ready(self, wait_time: int = 10) -> bool:
        """Check if WhatsApp Web interface is ready."""
        try:
            # Wait for key UI elements
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tab="11"]'))
            )
            return True
        except Exception:
            return False

    def close(self):
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()