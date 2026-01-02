from PIL import Image, ImageDraw, ImageFont
import os
import json
import io
import urllib.request


DEFAULT_INVITATION_TEXT = (
    "✨ You are cordially invited ✨\n\n"
    "Please join us for this special occasion.\n"
    "Your presence and blessings are cherished."
)


def ensure_gujarati_font(dest_filename='NotoSerifGujarati-Regular.ttf'):
    """Ensure a Gujarati-capable TTF exists in the project root.

    Prefer the Noto Serif Gujarati family. If missing, try to download it from
    the Google Fonts GitHub repository. Returns the absolute path to the font
    file if available, otherwise returns None.
    """
    possible_names = [
        dest_filename,
        'NotoSerifGujarati-Regular.ttf',
        'NotoSerifGujarati.ttf',
        'NotoSansGujarati-Regular.ttf',
        'NotoSansGujarati.ttf',
        'Lohit-Gujarati.ttf',
        'gujarati.ttf',
        'FreeSerif.ttf',
    ]
    for name in possible_names:
        if os.path.exists(name):
            return os.path.abspath(name)

    # Try to download Noto Serif Gujarati
    url = 'https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerifGujarati/NotoSerifGujarati-Regular.ttf'
    try:
        print(f"Downloading Gujarati serif font to {dest_filename}...")
        urllib.request.urlretrieve(url, dest_filename)
        if os.path.exists(dest_filename):
            return os.path.abspath(dest_filename)
    except Exception as e:
        print(f"Could not download Gujarati font automatically: {e}")

    return None

# No need for template creation since we use invitation2.jpeg as template

if __name__ == "__main__":
    print("Template creation not needed - using existing Wedding_invitation.jpeg")


def create_personalized_invitation(name: str, out_path: str, invitation_text: str | None = None):
    """
    Create a personalized invitation by adding name to the existing template.
    Uses template type and position from name_position.json
    """
    # Load name position and template info
    name_pos_file = os.path.join(os.path.dirname(__file__), "name_position.json")
    if not os.path.exists(name_pos_file):
        raise FileNotFoundError("Run select_name_position1.py first to set name position")
        
    with open(name_pos_file, 'r', encoding='utf-8') as f:
        pos = json.load(f)
        
    template_type = pos.get('template_type', 'image')  # Default to image for backward compatibility
    template_path = pos.get('template_path')
    
    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    if template_type == 'pdf':
        # Create PDF with name at specified position
        return create_personalized_pdf(
            template_path, name, out_path,
            x=pos['pdf_x'], y=pos['pdf_y'],
            page=pos.get('page', 0)
        )
    
    # Image template handling
    try:
        img = Image.open(template_path)
        draw = ImageDraw.Draw(img)
        name_font = None
        if font_path:
            try:
                name_font = ImageFont.truetype(font_path, 22)
            except Exception:
                name_font = None
        if name_font is None:
            try:
                name_font = ImageFont.truetype("arial.ttf", 22)
            except Exception:
                name_font = ImageFont.load_default()
                
        # Draw name (orange)
        draw.text((x, y), f"{name}", font=name_font, fill=(220, 14, 14), anchor="mm")
        
        # Save
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
            
        img.save(out_path, quality=95)
        print(f"Created invitation for {name} -> {out_path}")
        
    except Exception as e:
        raise Exception(f"Failed to create invitation for {name}: {e}")


def create_personalized_pdf(template_pdf: str, name: str, out_path: str, x: float, y: float, page: int = 0, fontsize: int = 36, fontname: str = "helv", color=(255, 140, 0)):
    """
    Create a personalized PDF by placing `name` at coordinates (x, y) on `page`
    of `template_pdf` and saving it to `out_path`.

    - `page` is 0-based (page 0 = first page). The `select_name_position.py` tool
      saves coordinates in PDF points and also records the page index; pass that
      page value here so the name is drawn on the correct page.
    - Coordinates are in PDF points (1/72 inch).
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF (fitz) is required to create personalized PDFs. Install pymupdf.")

    if not os.path.exists(template_pdf):
        raise FileNotFoundError(f"Template PDF not found: {template_pdf}")

    doc = fitz.open(template_pdf)
    if page < 0 or page >= len(doc):
        raise ValueError(f"Requested page {page} is out of range for {template_pdf} (has {len(doc)} pages)")
    page = doc.load_page(page)

    # Prepare text
    text = f"{name}"

    # Insert text at the given position
    # fitz expects color as floats 0..1, convert if given as 0..255
    r, g, b = color
    if max(r, g, b) > 1:
        color = (r/255.0, g/255.0, b/255.0)

    # Many fonts used by PyMuPDF do not support Gujarati. To reliably render
    # Gujarati names we render the target PDF page to an image, draw the text
    # with PIL using a TTF that supports Gujarati (if present), and rebuild the
    # PDF with the modified page rasterized. This preserves visual alignment
    # and supports complex scripts.
    try:
        import fitz  # PyMuPDF

        # Render the target page to an image at a higher resolution
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes('png')

        pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
        draw = ImageDraw.Draw(pil_img)

        # Ensure Gujarati font is available (downloads Noto Sans Gujarati if needed)
        font_path = ensure_gujarati_font()

        scale = 2  # because we rendered at 2x
        pixel_fontsize = max(8, int(fontsize * scale))
        stroke_w = max(1, int(2 * scale))
        pil_font = None
        if font_path:
            try:
                pil_font = ImageFont.truetype(font_path, pixel_fontsize)
            except Exception:
                pil_font = None
        if pil_font is None:
            try:
                pil_font = ImageFont.truetype("arial.ttf", pixel_fontsize)
            except Exception:
                pil_font = ImageFont.load_default()

        # Compute position in pixel coordinates (scale PDF points by render scale)
        px = x * scale
        py = y * scale
        text_str = f"{name}"

        # Measure text and draw background box for readability
        try:
            bbox = draw.textbbox((0, 0), text_str, font=pil_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w, text_h = draw.textsize(text_str, font=pil_font)

        box_margin = int(8 * scale)
        box_coords = [px - text_w/2 - box_margin, py - text_h/2 - box_margin,
                      px + text_w/2 + box_margin, py + text_h/2 + box_margin]
        # NOTE: removed the semi-opaque white rectangle behind the text to avoid
        # drawing a white background. This keeps the template's original look.
        # If readability is still an issue on some templates, we can replace
        # this with a dark semi-opaque box or increase stroke/font size.

        # Draw text centered with a subtle stroke for contrast (orange fill)
        try:
            draw.text((px - text_w/2, py - text_h/2), text_str, font=pil_font, fill=(220, 14, 14), stroke_width=stroke_w, stroke_fill=(255,255,255))
        except TypeError:
            # Older Pillow may not support stroke parameters; fall back
            draw.text((px - text_w/2, py - text_h/2), text_str, font=pil_font, fill=(0, 0, 0))

        # Convert back to PNG bytes
        out_buf = io.BytesIO()
        pil_img.save(out_buf, format='PNG')
        out_bytes = out_buf.getvalue()

        # Build a new PDF copying all pages but replacing the target page with the image
        new_doc = fitz.open()
        for i in range(len(doc)):
            if i == page.number:
                # create a new page with original size in points
                r = doc[i].rect
                new_page = new_doc.new_page(width=r.width, height=r.height)
                new_page.insert_image(new_page.rect, stream=out_bytes)
            else:
                new_doc.insert_pdf(doc, from_page=i, to_page=i)

        new_doc.save(out_path)
        new_doc.close()
        doc.close()
        print(f"Created personalized PDF for {name} -> {out_path}")
        return
    except Exception as e_img:
        # Fall back to simple vector text insertion if anything fails
        try:
            page.insert_text((x, y), text, fontsize=fontsize, fontname=fontname, fill=color)
        except Exception:
            raise RuntimeError(f"Failed to create personalized PDF: {e_img}")

    # Save to output (preserve other pages)
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    doc.save(out_path)
    doc.close()
    print(f"Created personalized PDF for {name} -> {out_path}")