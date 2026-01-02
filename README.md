# WhatsApp Invitation Automation

This Python script automates sending personalized WhatsApp invitations to contacts listed in an Excel file.

## Features

- Reads contact information from Excel file
- Sends personalized messages with invitation images
- Handles multiple contacts automatically
- Includes error handling and progress tracking

## Requirements

- Python 3.7+
- WhatsApp Web access
- Excel file with contacts
- Invitation image

## Installation

1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

2. Prepare your files:
   - Create `contacts.xlsx` with columns: 'Name' and 'Number'
   - Save your invitation image as `invitation.jpg`

## Usage

1. Ensure your WhatsApp Web is ready:
   - Open WhatsApp on your phone
   - Go to WhatsApp Web (https://web.whatsapp.com)
   - Scan the QR code

2. Run the script:
```bash
python whatsapp_sender.py
```

## Important Notes

- Numbers in Excel should be in international format (e.g., "911234567890")
- Keep WhatsApp Web open during execution
- The script includes delays to prevent blocking
- Make sure your internet connection is stable

## File Structure

```
├── whatsapp_sender.py    # Main script
├── requirements.txt      # Python dependencies
├── contacts.xlsx         # Your contact list (you need to create this)
└── invitation.jpg        # Your invitation image (you need to add this)
```

## Customization

You can modify the message template in the `prepare_message()` function within `whatsapp_sender.py`.