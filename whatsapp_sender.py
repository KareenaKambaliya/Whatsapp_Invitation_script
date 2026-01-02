import logging
import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict

import pandas as pd
from PIL import Image
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

from create_invitation import create_personalized_invitation, create_personalized_pdf
from message_queue import MessageQueue

# Optional clipboard helper (pyperclip preferred)
try:
    import pyperclip  # type: ignore
except Exception:
    pyperclip = None

# Configure logging with UTF-8 support
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File handler with UTF-8 encoding
file_handler = logging.FileHandler('whatsapp_sender.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler with proper encoding - use UTF-8
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
logger.addHandler(console_handler)

# Prevent propagation to root logger
logger.propagate = False

# Constants
EXCEL_FILE = "contacts.xlsx"                                                                
TEMPLATE_PDF = "D:\\WorkflowAuto\\Invitation\\Invitation From Kambaliya Family.pdf"
INVITATION_IMAGE = "D:\\WorkflowAuto\\Invitation\\Wedding_invitation.jpeg"
NAME_POS_JSON = "name_position.json"
OUTPUT_FOLDER = "invitations"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def convert_image_to_pdf(image_path: str, output_pdf_path: str) -> bool:
    """
    Convert an image file to PDF format.
    
    Args:
        image_path: Path to the source image file
        output_pdf_path: Path where the PDF should be saved
        
    Returns:
        True if conversion succeeded, False otherwise
    """
    try:
        # Open the image
        img = Image.open(image_path)
        
        # Convert to RGB if necessary (PDF doesn't support RGBA)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as PDF
        img.save(output_pdf_path, 'PDF', resolution=100.0, quality=95)
        logger.info(f"Successfully converted image to PDF: {output_pdf_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to convert image to PDF: {e}")
        return False

class WhatsAppSender:
    def send_text_message(self, contact_number: str, message: str) -> bool:
        """Send only a WhatsApp text message (no attachment)."""
        try:
            contact_number = contact_number.strip().replace("+", "").replace(" ", "")
            url = f"https://web.whatsapp.com/send?phone=+91{contact_number}"
            self.driver.get(url)
            if not self._check_whatsapp_ready():
                logger.error("WhatsApp Web not ready")
                return False
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tab="11"]'))
                )
            except TimeoutException:
                logger.error("Chat failed to load")
                return False
            # Try multiple selectors for message box
            message_box = None
            try:
                message_box = self.driver.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"]')
            except Exception:
                try:
                    message_box = self.driver.find_element(By.XPATH, '//*[@id="main"]/footer/div[1]/div/span/div/div[2]/div/div[3]/div[1]')
                except Exception:
                    logger.error("Message box not found with any selector")
                    return False
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
                    var range = document.createRange();
                    range.selectNodeContents(element);
                    range.collapse(false);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                """
                self.driver.execute_script(script, message_box, message)
                time.sleep(2)
            except Exception as e:
                logger.error(f"Failed to input message: {e}")
                return False
            # Try multiple selectors for send button
            send_button = None
            send_selectors = [
                (By.XPATH, '//div[@aria-label="Send"]'),
                (By.CSS_SELECTOR, 'span[data-icon="send"]'),
                (By.XPATH, '//*[@id="main"]/footer/div[1]/div/span/div/div[2]/div/div[3]/div[2]'),
            ]
            for by, selector in send_selectors:
                try:
                    send_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((by, selector)))
                    if send_button:
                        break
                except Exception:
                    continue
            if not send_button:
                logger.error("Send button not found with any selector")
                return False
            try:
                send_button.click()
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '//div[contains(@class,"message-out")]'))
                )
                logger.info("Outgoing message appeared in chat")
                return True
            except Exception as e:
                logger.error(f"Failed to click send: {e}")
                return False
        except Exception as e:
            logger.error(f"Error sending text message: {e}")
            return False
    """Enhanced WhatsApp automation with robust error handling and message queue support."""
    
    def __init__(self, chrome_profile_path: str = "chrome_profile", headless: bool = False):
        self.chrome_profile_path = chrome_profile_path
        self.headless = headless
        self.driver = None
        self.queue = MessageQueue()
        self.wait_time = 60
        
    @staticmethod
    def _check_chrome_running() -> bool:
        """Check if Chrome is running with our profile directory."""
        import psutil
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] == 'chrome.exe':
                    cmdline = proc.info.get('cmdline', [])
                    if any('--user-data-dir=' in arg for arg in cmdline):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False
        
    def setup_driver(self) -> None:
        """Initialize Chrome WebDriver with profile."""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument(f"user-data-dir={os.path.abspath(self.chrome_profile_path)}")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--start-maximized")
            
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # Set connection timeout and service port options
            chrome_options.add_argument("--remote-debugging-port=0")
            
            if self._check_chrome_running():
                logger.info("Attempting to close existing Chrome processes...")
                if sys.platform == 'win32':
                    os.system('taskkill /f /im chrome.exe')
                    time.sleep(2)
            
            logger.info("Starting WebDriver initialization...")
            
            # Try to get ChromeDriver with retry logic
            chromedriver_path = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting to get ChromeDriver (attempt {attempt + 1}/{max_retries})...")
                    chromedriver_path = ChromeDriverManager().install()
                    logger.info(f"ChromeDriver obtained: {chromedriver_path}")
                    
                    # Verify the file exists and is executable
                    if not os.path.exists(chromedriver_path):
                        raise FileNotFoundError(f"ChromeDriver not found at {chromedriver_path}")
                    
                    logger.info(f"ChromeDriver file size: {os.path.getsize(chromedriver_path)} bytes")
                    break
                except Exception as get_driver_e:
                    logger.warning(f"Failed to get ChromeDriver on attempt {attempt + 1}: {get_driver_e}")
                    if attempt == max_retries - 1:
                        raise Exception(f"Could not obtain ChromeDriver after {max_retries} attempts: {get_driver_e}")
                    time.sleep(2)
            
            try:
                from selenium.webdriver.chrome.service import Service as ChromeService
                
                logger.info("Creating ChromeDriver service...")
                service = ChromeService(chromedriver_path)
                
                logger.info("Initializing WebDriver...")
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Chrome browser launched successfully")
            except Exception as chrome_e:
                logger.error(f"Failed with Service: {chrome_e}")
                logger.info("Attempting direct WebDriver initialization...")
                try:
                    self.driver = webdriver.Chrome(chromedriver_path, options=chrome_options)
                    logger.info("Chrome launched (direct method)")
                except Exception as alt_e:
                    logger.error(f"Direct method failed: {alt_e}")
                    logger.info("Final attempt: default discovery...")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    logger.info("Chrome launched (default discovery)")

            time.sleep(5)  # Give Chrome time to fully initialize
            self.driver.maximize_window()
            logger.info("Browser window maximized")

            logger.info("Loading WhatsApp Web...")
            self.driver.get("https://web.whatsapp.com/send?phone=9662043954")
            
            if not self._wait_for_whatsapp():
                raise Exception("WhatsApp Web failed to initialize")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            raise

    def _check_whatsapp_ready(self, wait_time: int = 10) -> bool:
        """Check if WhatsApp Web UI elements are present and visible."""
        selectors = {
            'menu': ['[data-testid="menu"]', '[data-testid="menu-bar"]', '[data-icon="menu"]', 'div[aria-label="Menu"]'],
            'chat_list': ['[data-testid="chat-list"]', '#pane-side', 'div[role="navigation"]'],
            'message_input': ['div[contenteditable="true"]', 'footer div[contenteditable="true"]', 'div[role="textbox"]'],
            'main_area': ['[role="application"]', '#main', 'div[data-testid="conversation-panel-wrapper"]']
        }

        error_selectors = ['[data-testid="alert-phone"]', '[data-testid="alert-network"]', 
                          '[data-testid="qr-code"]', 'div[role="alert"]']
        for sel in error_selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    logger.error(f"Found blocking/error state selector: {sel}")
                    return False
            except Exception:
                pass

        found = {k: False for k in selectors}
        found_any = []

        for group, group_selectors in selectors.items():
            for sel in group_selectors:
                try:
                    el = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    if el and el.is_displayed():
                        found[group] = True
                        found_any.append((group, sel))
                        logger.info(f"Found {group} using selector: {sel}")
                        break
                except Exception:
                    continue

        if found_any:
            logger.info(f"WhatsApp readiness probe found selectors: {found_any}")
        else:
            logger.warning("WhatsApp readiness probe did not find expected selectors")

        is_ready = found.get('message_input', False) and (found.get('chat_list', False) or found.get('main_area', False))
        if is_ready:
            logger.info("WhatsApp Web interface appears ready")
        else:
            logger.warning(f"Readiness check failed; detected flags: {found}")

        return is_ready

    def _wait_for_whatsapp(self, timeout: int = 30) -> bool:
        """Wait for WhatsApp Web to load and become ready."""
        debug_dir = os.path.abspath("debug_whatsapp")
        os.makedirs(debug_dir, exist_ok=True)
        start_time = time.time()
        attempts = 0
        max_attempts = 3

        while attempts < max_attempts:
            attempts += 1
            logger.info(f"Checking WhatsApp Web status (attempt {attempts}/{max_attempts})...")
            
            try:
                time.sleep(2)  # Give page time to load between attempts
                
                # Check for QR code
                try:
                    qr_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-icon="qr-code"]')
                    if qr_elements:
                        logger.info("Please scan the QR code in the browser window...")
                        try:
                            self.driver.save_screenshot(os.path.join(debug_dir, f"qr_code_{attempts}.png"))
                            logger.info(f"QR code screenshot saved")
                        except Exception as e:
                            logger.warning(f"Could not save QR code screenshot: {e}")
                            
                        try:
                            WebDriverWait(self.driver, 60).until_not(
                                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-icon="qr-code"]'))
                            )
                            logger.info("QR code scanned successfully")
                        except TimeoutException:
                            if attempts < max_attempts:
                                logger.warning("QR code not scanned, will retry...")
                                continue
                            else:
                                logger.error("QR code was not scanned within timeout")
                                return False
                except Exception as qr_e:
                    logger.debug(f"Error checking for QR code: {qr_e}")

                # Check if WhatsApp is ready
                try:
                    if self._check_whatsapp_ready(wait_time=5):
                        elapsed = int(time.time() - start_time)
                        logger.info(f"WhatsApp Web loaded successfully after {elapsed}s")
                        return True
                except Exception as ready_e:
                    logger.debug(f"Error during ready check: {ready_e}")
                    
                logger.warning("WhatsApp Web not fully loaded yet, retrying...")
                try:
                    self.driver.save_screenshot(os.path.join(debug_dir, f"loading_{attempts}.png"))
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Error checking WhatsApp status: {e}")
                try:
                    self.driver.save_screenshot(os.path.join(debug_dir, f"error_{attempts}.png"))
                except Exception:
                    pass

            if attempts < max_attempts:
                logger.info("Refreshing page...")
                try:
                    self.driver.refresh()
                    time.sleep(5)
                except Exception as e:
                    logger.warning(f"Failed to refresh: {e}")

        logger.error(f"WhatsApp Web not ready. Debug screenshots saved in {debug_dir}/")
        return False

    def _prepare_message(self, name: str) -> str:
        """Create personalized message using contact's name."""
        return f"""🌸 હાર્દિક આમંત્રણ 🌸

માનનીય *{name}*,

શ્રી *મુકેશભાઈ કાંબલિયા* તરફથી
તેમની લાડકી પુત્રી કરીનાના લગ્ન પ્રસંગે,
આપને હાર્દિક આમંત્રણ પાઠવવામાં આવે છે.

આ શુભ અવસર પર આપની ઉપસ્થિતિ,
આશીર્વાદ અને સ્નેહની ઉપસ્થિતિ અમૂલ્ય રહેશે. 💐

સાદર આમંત્રણ,
*શ્રી મુકેશભાઈ ડોસાભાઈ કાંબલિયા તથા પરિવાર,*

*સુખપુર,જૂનાગઢ.*"""

    def _preview_file(self, file_path: str) -> tuple[bool, bool]:
        """Preview file and get user confirmation."""
        try:
            if sys.platform == 'win32':
                os.startfile(file_path)
            else:
                import subprocess
                if sys.platform == 'darwin':
                    subprocess.run(['open', file_path])
                else:
                    subprocess.run(['xdg-open', file_path])
            
            while True:
                choice = input(f"\nPreview opened for {os.path.basename(file_path)}. "
                             "Send? [Y]es/[N]o/[S]kip/[Q]uit: ").lower()
                if choice in ['y', 'yes']:
                    return True, False
                elif choice in ['n', 'no']:
                    return False, False
                elif choice in ['s', 'skip']:
                    return False, True
                elif choice in ['q', 'quit']:
                    logger.info("User requested to quit")
                    sys.exit(0)
                else:
                    print("Invalid choice. Please enter Y, N, S, or Q.")
        except Exception as e:
            logger.error(f"Failed to preview {file_path}: {e}")
            return False, False

    def _read_contacts(self, excel_file: str) -> Optional[pd.DataFrame]:
        """Read contacts from Excel file."""
        try:
            df = pd.read_excel(excel_file)
            
            required_cols = {'Name', 'Number'}
            if not all(col in df.columns for col in required_cols):
                logger.error(f"Excel file must contain columns: {required_cols}")
                return None
                
            df['Number'] = df['Number'].astype(str)
            df['Number'] = df['Number'].str.replace(r'[^0-9+]', '', regex=True)
            
            invalid_numbers = df[~df['Number'].str.match(r'^\+?\d{10,15}$')]
            if not invalid_numbers.empty:
                logger.warning("Invalid phone numbers found:")
                for _, row in invalid_numbers.iterrows():
                    logger.warning(f"{row['Name']}: {row['Number']}")
                    
            return df
            
        except Exception as e:
            logger.error(f"Failed to read contacts from {excel_file}: {e}")
            return None

    def send_invitation(self, contact: Dict[str, str], preview_files: bool = True) -> bool:
        """Create (optional) invitation, convert to PDF, and send via WhatsApp.

        Args:
            contact: contact dict with 'Name' and 'Number'
            preview_files: whether to preview the generated file before sending
            create_if_missing: if False, skip creating the c and expect an
                existing PDF at the expected path.
        """
        def _make_paths(name: str):
            safe_name = str(name).strip().replace(' ', '_')
            image_path = os.path.join(OUTPUT_FOLDER, f"Wedding_Invitation_{safe_name}.jpg")
            pdf_path = os.path.join(OUTPUT_FOLDER, f"invitation_{safe_name}.pdf")
            return image_path, pdf_path

        try:
            name = contact.get('Name')
            number = contact.get('Number')
            if not name or not number:
                logger.error(f"Invalid contact data: {contact}")
                return False

            message = self._prepare_message(name)
            image_path, pdf_path = _make_paths(name)

            # By default, create the invitation if missing. Callers can pass
            # create_if_missing=False to only send existing files.
            create_if_missing = True
            # If caller passed a kwarg, pick it up (backwards compatible)
            # (This keeps older calls working.)
            if isinstance(contact, dict) and 'create_if_missing' in contact:
                create_if_missing = bool(contact.get('create_if_missing'))

            # If file isn't present and creation is allowed, create it
            if not os.path.exists(pdf_path):
                if not create_if_missing:
                    logger.error(f"PDF not found and creation disabled: {pdf_path}")
                    return False

                # Decide creation path based on configured template type
                try:
                    template_type = 'image'
                    pos = None
                    if os.path.exists(NAME_POS_JSON):
                        try:
                            with open(NAME_POS_JSON, 'r', encoding='utf-8') as nf:
                                pos = json.load(nf)
                                template_type = pos.get('template_type', 'image')
                        except Exception:
                            pos = None

                    if template_type == 'pdf' and pos:
                        # Create personalized PDF directly using saved coordinates
                        try:
                            tpl_path = pos.get('template_path')
                            x = float(pos.get('pdf_x', 72))
                            y = float(pos.get('pdf_y', 72))
                            page = int(pos.get('page', 0))
                            create_personalized_pdf(tpl_path, name, pdf_path, x, y, page=page, fontsize=12)
                            logger.info(f"Created personalized PDF invitation for {name} from PDF template")
                        except Exception as pex:
                            logger.error(f"Failed to create personalized PDF from template: {pex}")
                            raise
                    else:
                        # Image template flow: create image then convert
                        create_personalized_invitation(name, image_path, message)
                        logger.info(f"Created personalized image invitation for {name}")
                        if not convert_image_to_pdf(image_path, pdf_path):
                            logger.error(f"Failed to convert image to PDF for {name}")
                            return False
                        logger.info(f"Converted image to PDF for {name}")

                except Exception as img_e:
                    logger.error(f"Failed to create invitation for {name}: {img_e}")
                    # Fallback: try copying configured template
                    try:
                        if os.path.exists(NAME_POS_JSON):
                            try:
                                with open(NAME_POS_JSON, 'r', encoding='utf-8') as nf:
                                    pos = json.load(nf)
                            except Exception:
                                pos = None
                        # If PDF template available, copy it
                        if pos and pos.get('template_type') == 'pdf' and os.path.exists(pos.get('template_path','')):
                            import shutil
                            shutil.copy2(pos.get('template_path'), pdf_path)
                            logger.info(f"Copied template PDF as fallback for {name}")
                        elif os.path.exists(INVITATION_IMAGE):
                            import shutil
                            shutil.copy2(os.path.abspath(INVITATION_IMAGE), image_path)
                            if not convert_image_to_pdf(image_path, pdf_path):
                                logger.error("Failed to convert template image to PDF")
                                return False
                            logger.info(f"Used template image and converted to PDF for {name}")
                        else:
                            logger.error("No template available for fallback")
                            return False
                    except Exception as copy_e:
                        logger.error(f"Failed to use template fallback: {copy_e}")
                        return False

            # Verify PDF exists and is non-empty
            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
                logger.error(f"Generated PDF is invalid: {pdf_path}")
                return False

            # Preview if requested
            if preview_files:
                proceed, skip = self._preview_file(pdf_path)
                if skip:
                    logger.info(f"User chose to skip {name}")
                    return True
                if not proceed:
                    logger.info(f"User chose not to send for {name}")
                    return False

            # Send the PDF
            return self.send_message(number, message, pdf_path)

        except Exception as e:
            logger.error(f"send_invitation error for {contact}: {e}")
            return False

    def process_contacts(self, excel_file: str, preview_files: bool = True) -> None:
        """Read contacts and send invitations."""
        contacts_df = self._read_contacts(excel_file)
        if contacts_df is None:
            logger.error("No contacts to process")
            return

        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        total = len(contacts_df)
        success = 0

        logger.info(f"Starting to send invitations to {total} contacts...")
        for idx, row in contacts_df.iterrows():
            contact = {'Name': row['Name'], 'Number': row['Number']}
            logger.info(f"Processing {idx+1}/{total}: {contact['Name']}")
            try:
                ok = self.send_invitation(contact, preview_files=preview_files)
                if ok:
                    success += 1
                    logger.info(f"✓ Sent to {contact['Name']}")
                else:
                    logger.warning(f"X Not sent to {contact['Name']}")
            except Exception as e:
                logger.error(f"Error processing {contact['Name']}: {e}")
            time.sleep(2)

        logger.info(f"Completed: {success}/{total} sent")

    def create_invitations(self, excel_file: str) -> None:
        """Create personalized invitation images and PDFs for all contacts (no sending)."""
        contacts_df = self._read_contacts(excel_file)
        if contacts_df is None:
            logger.error("No contacts to process for creation")
            return

        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        total = len(contacts_df)
        logger.info(f"Starting creation of invitations for {total} contacts...")
        for idx, row in contacts_df.iterrows():
            name = row['Name']
            try:
                safe_name = str(name).strip().replace(' ', '_')
                image_path = os.path.join(OUTPUT_FOLDER, f"invitation_{safe_name}.jpg")
                pdf_path = os.path.join(OUTPUT_FOLDER, f"invitation_{safe_name}.pdf")

                # Respect template type saved in name_position.json
                try:
                    template_type = 'image'
                    pos = None
                    if os.path.exists(NAME_POS_JSON):
                        with open(NAME_POS_JSON, 'r', encoding='utf-8') as nf:
                            pos = json.load(nf)
                            template_type = pos.get('template_type', 'image')
                except Exception:
                    template_type = 'image'

                if template_type == 'pdf' and pos:
                    try:
                        tpl = pos.get('template_path')
                        x = float(pos.get('pdf_x', 72))
                        y = float(pos.get('pdf_y', 72))
                        page = int(pos.get('page', 0))
                        create_personalized_pdf(tpl, name, pdf_path, x, y, page=page, fontsize=12)
                        logger.info(f"Created PDF for {name}")
                        
                    except Exception as e:
                        logger.error(f"Failed to create PDF for {name} from template: {e}")
                else:
                    create_personalized_invitation(name, image_path, self._prepare_message(name))
                    logger.info(f"Created image for {name}")
                    if not convert_image_to_pdf(image_path, pdf_path):
                        logger.error(f"Failed to convert image to PDF for {name}")
                    else:
                        logger.info(f"Created PDF for {name}")
            except Exception as e:
                logger.error(f"Error creating invitation for {name}: {e}")
            time.sleep(0.5)

    def send_invitations(self, excel_file: str, preview_files: bool = True) -> None:
        """Send invitations using existing PDFs; do not create images/PDFs if missing."""
        contacts_df = self._read_contacts(excel_file)
        if contacts_df is None:
            logger.error("No contacts to process for sending")
            return

        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        total = len(contacts_df)
        success = 0

        # Ensure there are columns for status and error details
        if contacts_df.shape[1] >= 3:
            status_col = contacts_df.columns[2]
        else:
            status_col = 'Status'
            contacts_df.insert(2, status_col, '')
            
        # Add error details column if not present
        if contacts_df.shape[1] >= 4:
            error_col = contacts_df.columns[3]
        else:
            error_col = 'Error Details'
            contacts_df.insert(3, error_col, '')

        logger.info(f"Starting to send existing invitations to {total} contacts...")
        # We'll attempt to save to the original file; if locked, fall back to a single fallback file
        fallback_path = None

        for idx, row in contacts_df.iterrows():
            contact = {'Name': row['Name'], 'Number': row['Number'], 'create_if_missing': False}
            logger.info(f"Sending {idx+1}/{total}: {contact['Name']}")
            error_msg = ''
            try:
                ok = self.send_invitation(contact, preview_files=preview_files)
            except Exception as e:
                ok = False
                error_msg = str(e)
                logger.error(f"Error sending to {contact['Name']}: {error_msg}")

            # If send_invitation returned False but no explicit error captured, try to infer from log
            if not ok and not error_msg:
                try:
                    with open('whatsapp_sender.log', 'r', encoding='utf-8') as logf:
                        lines = logf.readlines()[-200:]
                        joined = "\n".join(lines)
                        if 'Phone number shared via url is invalid' in joined or 'Invalid WhatsApp number' in joined:
                            error_msg = 'Invalid WhatsApp number'
                        elif 'Number not found on WhatsApp' in joined or 'not on WhatsApp' in joined:
                            error_msg = 'Not on WhatsApp'
                        else:
                            # pick the last non-empty log line as a hint
                            for l in reversed(lines):
                                l = l.strip()
                                if l:
                                    error_msg = l
                                    break
                except Exception:
                    error_msg = ''

            # Write status and error into dataframe
            try:
                contacts_df.at[idx, status_col] = 'Sent' if ok else 'Failed'
                contacts_df.at[idx, error_col] = error_msg
            except Exception as write_e:
                logger.warning(f"Could not write status for {contact['Name']}: {write_e}")

            if ok:
                success += 1
                logger.info(f"✓ Sent to {contact['Name']}")
            else:
                if error_msg:
                    logger.warning(f"X Not sent to {contact['Name']} - {error_msg}")
                else:
                    logger.warning(f"X Not sent to {contact['Name']}")

            # Try to persist statuses after each contact to avoid losing progress
            try:
                target_path = excel_file if fallback_path is None else fallback_path
                contacts_df.to_excel(target_path, index=False)
            except PermissionError:
                # First time we detect locked file, choose a fallback filename and continue writing there
                if fallback_path is None:
                    timestamp = int(time.time())
                    fallback_path = os.path.splitext(excel_file)[0] + f"_with_status_{timestamp}.xlsx"
                    try:
                        contacts_df.to_excel(fallback_path, index=False)
                        logger.warning(f"Permission denied saving {excel_file}; saving statuses to {fallback_path} instead")
                    except Exception as fe:
                        logger.error(f"Failed to save statuses to fallback file: {fe}")
                else:
                    try:
                        contacts_df.to_excel(fallback_path, index=False)
                    except Exception as fe:
                        logger.error(f"Failed to save statuses to fallback file: {fe}")
            except Exception as save_e:
                logger.error(f"Failed to persist statuses after contact {contact['Name']}: {save_e}")

            # Small delay between sends
            time.sleep(2)

        logger.info(f"Completed sending: {success}/{total} sent")

    def send_message(self, contact_number: str, message: str, attachment_path: Optional[str] = None) -> bool:
        """Send WhatsApp message with optional attachment."""
        try:
            contact_number = contact_number.strip().replace("+", "").replace(" ", "")
            url = f"https://web.whatsapp.com/send?phone=+91{contact_number}"
            self.driver.get(url)
            
            if not self._check_whatsapp_ready():
                logger.error("WhatsApp Web not ready")
                return False

            # First check for invalid number message
            try:
                invalid_number = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="popup-contents"]'))
                )
                if "Phone number shared via url is invalid" in invalid_number.text:
                    logger.error(f"Invalid WhatsApp number: +91{contact_number}")
                    return False
            except TimeoutException:
                pass  # No invalid number message, continue normally
            
            # Wait for chat to load
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tab="11"]'))
                )
            except TimeoutException:
                # Check for phone number not on WhatsApp message
                try:
                    phone_error = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="alert-phone"]')
                    if phone_error and phone_error.is_displayed():
                        logger.error(f"Number not found on WhatsApp: +91{contact_number}")
                        return False
                except Exception:
                    pass
                logger.error("Chat failed to load")
                return False

            # Send attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                try:
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="textbox"]'))
                    )
                    
                    attach_selectors = [
                        '[data-testid="attach-menu-plus"]',
                        '[data-testid="menu-bar-menu"]', # Menu button as fallback
                        '[data-testid="attach"]',
                        '[data-testid="clip"]',
                        '[data-icon="attach"]',
                        '[data-icon="clip"]',
                        '[data-icon="attach-menu-plus"]',
                        '[aria-label*="attach"]', # Accessibility attributes as fallback
                        '[aria-label*="Attach"]',
                        'span[data-icon="clip"]', # Additional specific selectors
                        'span[data-testid="clip"]',
                        'button.input-button[aria-label*="attach"]'
                       
                    ]
                    
                    attach_button = None
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
                        raise Exception("Could not find attach button")
                        
                    try:
                        attach_button.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", attach_button)
                    
                    time.sleep(2)
                    
                    file_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
                    )
                    
                    abs_path = os.path.abspath(attachment_path)
                    file_input.send_keys(abs_path)
                    logger.info(f"Attached file: {abs_path}")
                    
                    # Wait for upload
                    time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"Failed to attach file: {e}")
                    return False

            # Send message
            try:
                # Try multiple selectors for the message box: CSS first, then XPath as fallback
                try:
                    message_box = self.driver.find_element(By.CSS_SELECTOR, 'div[aria-label="Type a message"] p[class="selectable-text copyable-text x15bjb6t x1n2onr6"]')
                except Exception:
                    message_box = self.driver.find_element(By.XPATH, '//div[@aria-label="Type a message"]//p[@class="selectable-text copyable-text x15bjb6t x1n2onr6"]')
            except Exception:
                logger.error("Message box not found")
                return False

            try:
                message_box.click()
                time.sleep(1)
                
                # Enhanced JavaScript injection with proper Unicode handling
                script = """
                    var element = arguments[0];
                    element.focus();
                    
                    // Create a temporary div to properly handle HTML entities
                    var temp = document.createElement('div');
                    temp.textContent = arguments[1];
                    
                    element.innerHTML = temp.innerHTML;
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    
                    // Force cursor to end
                    var range = document.createRange();
                    range.selectNodeContents(element);
                    range.collapse(false);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                """
                self.driver.execute_script(script, message_box, message)
                time.sleep(2)  # Give WhatsApp more time to process the input
                
                # Verify the message was actually set
                actual_text = self.driver.execute_script("return arguments[0].textContent", message_box)
                if not actual_text:
                    # If empty, try alternative method
                    if pyperclip:
                        pyperclip.copy(message)
                        message_box.clear()
                        time.sleep(0.5)
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to input message: {e}")
                logger.debug("Attempting fallback input method...")
                try:
                    # Fallback: try clipboard if available
                    if pyperclip:
                        pyperclip.copy(message)
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        time.sleep(1)
                    else:
                        # Last resort: character by character
                        for char in message:
                            try:
                                message_box.send_keys(char)
                                time.sleep(0.05)
                            except:
                                continue
                except Exception as fallback_e:
                    logger.error(f"All input methods failed: {fallback_e}")
                    return False

            # Click send
            try:
                #send_button = WebDriverWait(self.driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'span[data-icon="send"], span[data-icon="wds-ic-send-filled"]'))
                send_button = WebDriverWait(self.driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="Send"]')))

            
                send_button.click()
                # Wait for the outgoing message bubble and verify delivery
                try:
                    # First, wait for an outgoing message to appear in the chat
                    WebDriverWait(self.driver, 30).until(
                        EC.presence_of_element_located((By.XPATH, '//div[contains(@class,"message-out")]'))
                    )
                    logger.info("Outgoing message appeared in chat")

                    # Poll the last outgoing message for double-tick status
                    def _check_delivered(driver):
                        try:
                            outs = driver.find_elements(By.XPATH, '//div[contains(@class,"message-out")]')
                            if not outs:
                                return False
                            last = outs[-1]
                            
                            # Look for double-tick specifically (indicates message reached server)
                            double_check = last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-dblcheck"], svg[data-icon="msg-dblcheck"]')
                            if double_check:
                                logger.info("Double-tick detected - message delivered to server")
                                return True
                                
                            # Also check for single tick (sent but not delivered)
                            single_check = last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-check"], svg[data-icon="msg-check"]')
                            if single_check:
                                logger.info("Single-tick detected - message sent but not yet delivered")
                                return False
                                
                            # If neither found, message might still be sending
                            logger.debug("No delivery indicators found yet")
                            return False
                        except Exception as e:
                            logger.debug(f"Error checking delivery status: {e}")
                            return False

                    # Wait up to 90 seconds for delivery confirmation (polling)
                    status = None
                    end_time = time.time() + 120  # Wait up to 2 minutes for verification
                    status = None
                    message_appeared = False
                    verification_start = time.time()
                    
                    try:
                        while time.time() < end_time:
                            try:
                                # First verify message appears in chat
                                outs = self.driver.find_elements(By.XPATH, '//div[contains(@class,"message-out")]')
                                if not outs:
                                    time.sleep(0.5)
                                    if not message_appeared:
                                        logger.debug("Waiting for message to appear in chat...")
                                    continue
                                
                                if not message_appeared:
                                    message_appeared = True
                                    logger.info(f"Message appeared in chat after {time.time() - verification_start:.1f}s")
                                
                                last = outs[-1]
                                
                                # Check for delivery indicators
                                double_check = last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-dblcheck"], svg[data-icon="msg-dblcheck"]')
                                if double_check:
                                    status = 'double'
                                    logger.debug("Double tick detected")
                                    break

                                single_check = last.find_elements(By.CSS_SELECTOR, 'span[data-icon="msg-check"], svg[data-icon="msg-check"]')
                                if single_check:
                                    status = 'single'
                                    logger.debug("Single tick detected")
                                    # Don't break on single tick, give it a chance to get to double tick
                                    time.sleep(0.5)

                            except Exception as verify_e:
                                logger.debug(f"Transient error during verification: {verify_e}")
                                time.sleep(0.5)
                                continue

                        verification_time = time.time() - verification_start
                        
                        if status == 'double':
                            logger.info(f"✓ Message delivery confirmed (double-tick) after {verification_time:.1f}s")
                            time.sleep(1)
                            return True
                        elif status == 'single':
                            logger.info(f"✓ Single-tick verified (message sent) after {verification_time:.1f}s")
                            time.sleep(1)
                            return True
                        else:
                            error_msg = "Message verification failed: "
                            if not message_appeared:
                                error_msg += "Message never appeared in chat"
                            else:
                                error_msg += "No delivery indicators (ticks) detected"
                            error_msg += f" after {verification_time:.1f}s"
                            logger.warning(error_msg)
                            try:
                                debug_file = os.path.join("debug_whatsapp", f"send_verification_failed_{int(time.time())}.html")
                                os.makedirs("debug_whatsapp", exist_ok=True)
                                with open(debug_file, 'w', encoding='utf-8') as f:
                                    f.write(self.driver.page_source)
                                    # Always create a fallback status file for error/status tracking
                                    fallback_path = os.path.splitext(excel_file)[0] + f"_with_status_{int(time.time())}.xlsx"
                                    # Ensure status and error columns exist
                                    if 'Status' not in contacts_df.columns:
                                        contacts_df['Status'] = ''
                                    if 'Error' not in contacts_df.columns:
                                        contacts_df['Error'] = ''
                                    if 'Last Updated' not in contacts_df.columns:
                                        contacts_df['Last Updated'] = ''
                                    if 'Message' not in contacts_df.columns:
                                        contacts_df['Message'] = ''
                                self.driver.save_screenshot(debug_file.replace('.html', '.png'))
                                logger.info(f"Saved debug info to {debug_file}")
                            except Exception as e:
                                logger.error(f"Could not save debug info: {e}")
                            return False
                    except Exception as e:
                        logger.error(f"Error while polling delivery status: {e}")
                        return False
                except TimeoutException:
                    logger.warning("Could not verify message delivery within timeout; saving screenshot")
                    try:
                        os.makedirs("debug_whatsapp", exist_ok=True)
                        self.driver.save_screenshot(os.path.join("debug_whatsapp", f"send_unverified_{contact_number}.png"))
                    except Exception:
                        pass
                    return False
            except Exception as e:
                logger.error(f"Failed to click send: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Send WhatsApp invitations from Excel')
    parser.add_argument('--no-preview', dest='no_preview', action='store_true',
                      help='Skip preview and send automatically')
    parser.add_argument('--excel', dest='excel', default=EXCEL_FILE,
                        help='Path to contacts Excel file')
    parser.add_argument('--create-only', dest='create_only', action='store_true',
                        help='Only create invitation files (images+PDF), do not send')
    parser.add_argument('--send-only', dest='send_only', action='store_true',
                        help='Only send existing invitation PDFs, do not create')
    parser.add_argument('--send-message-only', dest='send_message_only', action='store_true',
                        help='Send only personalized WhatsApp message (no attachment)')
    args = parser.parse_args()

    preview_files = not args.no_preview
    sender = WhatsAppSender()

    # Validate exclusive flags
    if args.create_only and args.send_only:
        logger.error("--create-only and --send-only are mutually exclusive")
        return
    if args.send_message_only and (args.create_only or args.send_only):
        logger.error("--send-message-only cannot be combined with --create-only or --send-only")
        return

    try:
        if args.create_only:
            sender.create_invitations(args.excel)
            return

        if args.send_only:
            sender.setup_driver()
            sender.send_invitations(args.excel, preview_files=preview_files)
            return

        if args.send_message_only:
            sender.setup_driver()
            contacts_df = sender._read_contacts(args.excel)
            if contacts_df is None:
                logger.error("No contacts to process for message-only mode")
                return
            total = len(contacts_df)
            logger.info(f"Starting to send personalized messages to {total} contacts...")
            for idx, row in contacts_df.iterrows():
                name = row['Name']
                number = row['Number']
                message = sender._prepare_message(name)
                logger.info(f"Sending message to {name} ({number})")
                ok = sender.send_text_message(number, message)
                if ok:
                    logger.info(f"✓ Message sent to {name}")
                else:
                    logger.warning(f"X Message not sent to {name}")
                time.sleep(2)
            logger.info(f"Completed sending messages: {total} attempted")
            return

        # Default: create then send
        sender.setup_driver()
        sender.create_invitations(args.excel)
        sender.send_invitations(args.excel, preview_files=preview_files)
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")

if __name__ == "__main__":
    main()