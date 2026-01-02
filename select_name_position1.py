from PIL import Image, ImageTk, ImageDraw, ImageFont
import tkinter as tk
import os
import json
import fitz  # PyMuPDF for PDF handling

# Support both image and PDF templates
TEMPLATE_IMAGE = 'invitation2.jpeg'  # JPEG template
TEMPLATE_PDF = 'Invitation From Kambaliya Family2.pdf'  # PDF template
OUTPUT_JSON = 'name_position.json'

def load_template():
    """Load either PDF or image template, converting PDF page to image if needed."""
    if os.path.exists(TEMPLATE_PDF):
        # Load PDF and convert first page to image
        try:
            doc = fitz.open(TEMPLATE_PDF)
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for better quality
            img_data = pix.tobytes("png")
            
            # Convert to PIL Image
            from io import BytesIO
            pil_img = Image.open(BytesIO(img_data))
            return pil_img, "pdf", TEMPLATE_PDF
        except Exception as e:
            print(f"Failed to load PDF template: {e}")
    
    if os.path.exists(TEMPLATE_IMAGE):
        return Image.open(TEMPLATE_IMAGE), "image", TEMPLATE_IMAGE
        
    print(f"No template found. Put either {TEMPLATE_PDF} or {TEMPLATE_IMAGE} in project root.")
    raise SystemExit(1)

# Load the template (either PDF or image)
pil_img, template_type, template_path = load_template()
width, height = pil_img.size

# PDF support state
doc = None
current_page = 0
render_scale = 1.0
num_pages = 1
if template_type == 'pdf':
    try:
        doc = fitz.open(template_path)
        num_pages = len(doc)
        current_page = 0
        render_scale = 2.0  # must match rendering used in load_template()
    except Exception:
        doc = None

# Set initial position to center of image
init_x = width / 2
init_y = height / 3  # Place name about 1/3 down from top

print(f"Initial position set to x={init_x:.2f}, y={init_y:.2f}")

# Tkinter UI for preview and adjustment
root = tk.Tk()
root.title('Adjust name position if needed')

canvas = tk.Canvas(root, width=width, height=height)
canvas.pack()

# Keep a copy of the original PIL image for redraws
orig_pil_img = pil_img.copy()
tk_img = ImageTk.PhotoImage(pil_img)
image_on_canvas = canvas.create_image(0, 0, anchor='nw', image=tk_img)

coords_text = tk.StringVar()
coords_text.set(f'Initial position at x={init_x:.2f}, y={init_y:.2f}\nUse arrow keys for adjustments or click to reposition. Press Enter to save')
label = tk.Label(root, textvariable=coords_text)
label.pack()

# If using a PDF template, provide page navigation controls
if template_type == 'pdf' and doc is not None:
    page_frame = tk.Frame(root)
    page_frame.pack(pady=4)

    page_label_var = tk.StringVar()
    def _update_page_label():
        page_label_var.set(f"Page: {current_page+1}/{num_pages}")

    def show_page(page_index: int):
        global pil_img, orig_pil_img, tk_img, image_on_canvas, width, height, current_page
        if page_index < 0 or page_index >= num_pages:
            return
        try:
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale))
            img_data = pix.tobytes("png")
            from io import BytesIO
            pil_img = Image.open(BytesIO(img_data))
            width, height = pil_img.size
            orig_pil_img = pil_img.copy()
            tk_img = ImageTk.PhotoImage(pil_img)
            canvas.config(width=width, height=height)
            canvas.itemconfig(image_on_canvas, image=tk_img)
            current_page = page_index
            # reset selection to center of new page to help user
            selected['x'] = width / 2
            selected['y'] = height / 3
            coords_text.set(f'Position: x={selected["x"]:.2f}, y={selected["y"]:.2f}')
            _update_page_label()
        except Exception as e:
            print(f"Failed to render page {page_index}: {e}")

    def on_prev():
        if current_page > 0:
            show_page(current_page - 1)

    def on_next():
        if current_page < num_pages - 1:
            show_page(current_page + 1)

    prev_btn = tk.Button(page_frame, text='<< Prev', command=on_prev)
    prev_btn.pack(side='left')
    tk.Label(page_frame, textvariable=page_label_var).pack(side='left', padx=6)
    next_btn = tk.Button(page_frame, text='Next >>', command=on_next)
    next_btn.pack(side='left')
    _update_page_label()

# Entry for preview name
preview_frame = tk.Frame(root)
preview_frame.pack(pady=6)
tk.Label(preview_frame, text='Preview name:').pack(side='left')
preview_name_var = tk.StringVar(value='કાંબલીયા')  # Default Gujarati name
preview_entry = tk.Entry(preview_frame, textvariable=preview_name_var)
preview_entry.pack(side='left')

# Initialize with center position
selected = {'x': init_x, 'y': init_y}

# If using a PDF template with at least 3 pages, open page 3 by default
if template_type == 'pdf' and doc is not None and num_pages >= 3:
    try:
        show_page(2)
    except NameError:
        # show_page may not be defined if PDF controls failed to initialize
        pass

def update_preview():
    """Redraw the canvas image with the sample name at the selected point."""
    name = preview_name_var.get().strip()
    pil_copy = orig_pil_img.copy()
    draw = ImageDraw.Draw(pil_copy)
    
    # Try to use Gujarati font if available
    font = None
    font_size = 22  # Larger font size for image
    gujarati_fonts = [
        'NotoSerifGujarati-Regular.ttf',
        'NotoSansGujarati-Regular.ttf',
        'Lohit-Gujarati.ttf',
        'gujarati.ttf'
    ]
    
    for font_name in gujarati_fonts:
        if os.path.exists(font_name):
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except Exception:
                pass
    
    if font is None:
        try:
            font = ImageFont.truetype('arial.ttf', font_size)
        except Exception:
            font = ImageFont.load_default()

    if selected['x'] is not None and selected['y'] is not None and name:
        x = selected['x']
        y = selected['y']
        text = f"{name},"
        
        # Draw a semi-transparent white box behind text for readability
        try:
            bbox = draw.textbbox((x, y), text, font=font, anchor='mm')
            box_margin = 12
            box_coords = [bbox[0] - box_margin, bbox[1] - box_margin,
                         bbox[2] + box_margin, bbox[3] + box_margin]
            # Draw white background with some transparency
            draw.rectangle(box_coords, fill=(255, 255, 255, 180))
        except Exception:
            pass  # Skip background if bbox calculation fails
        
        # Draw the text centered at selected point
        draw.text((x, y), text, font=font, fill='black', anchor='mm')
        
        # Draw crosshair
        line_length = 20
        draw.line([(x - line_length, y), (x + line_length, y)], fill='red', width=2)
        draw.line([(x, y - line_length), (x, y + line_length)], fill='red', width=2)

    global tk_img
    tk_img = ImageTk.PhotoImage(pil_copy)
    canvas.itemconfig(image_on_canvas, image=tk_img)

def save_position():
    """Save the selected position and template info to the output JSON file."""
    # For PDF templates we rendered the page with a scale factor; convert
    # pixel coordinates back to PDF points by dividing by the render_scale.
    pdf_x = None
    pdf_y = None
    page_to_save = 0
    try:
        if template_type == "pdf":
            pdf_x = selected['x'] / render_scale
            pdf_y = selected['y'] / render_scale
            page_to_save = int(current_page)
    except Exception:
        pdf_x = None
        pdf_y = None
        page_to_save = 0

    data = {
        'x': selected['x'],
        'y': selected['y'],
        'template_type': template_type,
        'template_path': template_path,
        'pdf_x': pdf_x,
        'pdf_y': pdf_y,
        'page': page_to_save
    }
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Saved position to {OUTPUT_JSON}")
    root.destroy()

def move(dx=0, dy=0):
    """Move the selected position by dx, dy pixels."""
    selected['x'] += dx
    selected['y'] += dy
    coords_text.set(f"Position: x={selected['x']:.2f}, y={selected['y']:.2f}")
    update_preview()

def click(event):
    """Handle canvas click by moving selection to clicked point."""
    selected['x'] = event.x
    selected['y'] = event.y
    coords_text.set(f"Position: x={selected['x']:.2f}, y={selected['y']:.2f}")
    update_preview()

# Key bindings for fine adjustments
root.bind('<Left>', lambda e: move(dx=-1))
root.bind('<Right>', lambda e: move(dx=1))
root.bind('<Up>', lambda e: move(dy=-1))
root.bind('<Down>', lambda e: move(dy=1))
root.bind('<Shift-Left>', lambda e: move(dx=-10))
root.bind('<Shift-Right>', lambda e: move(dx=10))
root.bind('<Shift-Up>', lambda e: move(dy=-10))
root.bind('<Shift-Down>', lambda e: move(dy=10))
root.bind('<Return>', lambda e: save_position())

# Mouse click for repositioning
canvas.bind('<Button-1>', click)

# Update preview when name changes
preview_name_var.trace_add('write', lambda *args: update_preview())

# Show initial preview
update_preview()

print("Use arrow keys to fine-tune position (hold Shift for larger steps)")
print("Click anywhere to move position to that point")
print("Press Enter to save position when satisfied")
print("Close window to quit without saving")

root.mainloop()

try:
    os.remove('tmp_invitation_page.png')
except:
    pass

def outer():
    pil_img = None
    orig_pil_img = None
    tk_img = None
    image_on_canvas = None
    width = 0
    height = 0
    current_page = 0

    def inner():
        global pil_img
        pil_img = load_image()  # modify outer scope variables
    return inner