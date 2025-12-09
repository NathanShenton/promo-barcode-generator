import io
import zipfile
from typing import Optional

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from barcode import Code128
from barcode.writer import ImageWriter


# ------------- Helpers ------------- #

def parse_pasted_data(text: str) -> pd.DataFrame:
    """
    Parse pasted text into a DataFrame.
    Assumes tab- or comma-separated with a header row.
    """
    from io import StringIO

    if not text.strip():
        return pd.DataFrame()

    # Try tab-separated first, then comma-separated as fallback
    try:
        df = pd.read_csv(StringIO(text), sep="\t")
    except Exception:
        df = pd.read_csv(StringIO(text))

    return df


def validate_dataframe(df: pd.DataFrame):
    """
    Ensure required columns exist.
    Returns (is_valid: bool, message: str).
    """
    required_cols = {"Barcode", "JPEG Name"}
    if df.empty:
        return False, "No data found. Please upload a CSV or paste data."

    if not required_cols.issubset(df.columns):
        return False, f"Data must contain columns: {', '.join(required_cols)}"

    return True, ""


def generate_barcode_image(
    barcode_value: str,
    dpi: int,
    width_px: Optional[int],
    height_px: Optional[int],
) -> Image.Image:
    """
    Generate a PIL Image for a given barcode value.

    - Bars and human-readable text are drawn separately.
    - Text is always fully visible below the bars.
    - Output can be scaled into a target box while keeping aspect ratio
      (with white padding if needed).
    """

    # 1️⃣ Create barcode bars only (no text)
    buffer = io.BytesIO()
    code = Code128(barcode_value, writer=ImageWriter())
    code.write(
        buffer,
        {
            "format": "JPEG",
            "dpi": dpi,
            "module_width": 0.2,     # width of narrow bar
            "module_height": 12.0,   # bar height (not insanely tall)
            "quiet_zone": 10.0,      # margin left/right so nothing is cut off
            "write_text": False,     # IMPORTANT: we draw text ourselves
        },
    )
    buffer.seek(0)
    barcode_img = Image.open(buffer).convert("RGB")

    # 2️⃣ Create a text strip underneath
    # Use default font (no external files needed)
    try:
        font = ImageFont.truetype("arial.ttf", 24)   # if available
    except:
        # Fallback: scale default bitmap font manually
        font = ImageFont.load_default()

    # Measure text size
    dummy_img = Image.new("RGB", (1, 1))
    draw_dummy = ImageDraw.Draw(dummy_img)
    bbox = draw_dummy.textbbox((0, 0), barcode_value, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Add some horizontal padding so digits don't touch edge
    text_padding_x = 10
    text_padding_y = 5

    # Text strip width should match at least the barcode width
    bar_w, bar_h = barcode_img.size
    text_strip_w = max(bar_w, text_w + 2 * text_padding_x)
    text_strip_h = text_h + 2 * text_padding_y

    text_img = Image.new("RGB", (text_strip_w, text_strip_h), "white")
    draw_text = ImageDraw.Draw(text_img)

    # Center text horizontally
    text_x = (text_strip_w - text_w) // 2
    text_y = text_padding_y
    draw_text.text((text_x, text_y), barcode_value, fill="black", font=font)

    # 3️⃣ Combine barcode + text vertically
    combined_w = max(bar_w, text_strip_w)
    combined_h = bar_h + text_strip_h
    combined = Image.new("RGB", (combined_w, combined_h), "white")

    # Center barcode and text horizontally
    bar_x = (combined_w - bar_w) // 2
    text_x_offset = (combined_w - text_strip_w) // 2

    combined.paste(barcode_img, (bar_x, 0))
    combined.paste(text_img, (text_x_offset, bar_h))

    # 4️⃣ If no target size -> return combined as-is
    if not width_px and not height_px:
        return combined

    orig_w, orig_h = combined.size

    # 5️⃣ Scale while keeping aspect ratio
    if width_px and height_px:
        scale = min(width_px / orig_w, height_px / orig_h)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
    elif width_px and not height_px:
        scale = width_px / orig_w
        new_w = width_px
        new_h = max(1, int(orig_h * scale))
    elif height_px and not width_px:
        scale = height_px / orig_h
        new_h = height_px
        new_w = max(1, int(orig_w * scale))
    else:
        # Shouldn't hit this, but just in case
        return combined

    resized = combined.resize((new_w, new_h), Image.LANCZOS)

    # 6️⃣ Paste onto exact-size white canvas (no cropping)
    canvas_w = width_px if width_px else new_w
    canvas_h = height_px if height_px else new_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

    offset_x = (canvas_w - new_w) // 2
    offset_y = (canvas_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    return canvas


def create_zip_of_barcodes(
    df: pd.DataFrame,
    dpi: int,
    width_px: Optional[int],
    height_px: Optional[int],
) -> bytes:
    """
    Generate a ZIP file (as bytes) containing one JPEG per row in df.
    JPEG file names are taken from 'JPEG Name' column.
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for _, row in df.iterrows():
            barcode_value = str(row["Barcode"]).strip()
            jpeg_name = str(row["JPEG Name"]).strip()

            if not barcode_value or not jpeg_name:
                continue

            img = generate_barcode_image(
                barcode_value=barcode_value,
                dpi=dpi,
                width_px=width_px,
                height_px=height_px,
            )

            img_bytes = io.BytesIO()
            img.save(img_bytes, format="JPEG")
            img_bytes.seek(0)

            filename = (
                f"{jpeg_name}.jpg"
                if not jpeg_name.lower().endswith(".jpg")
                else jpeg_name
            )

            zipf.writestr(filename, img_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# ------------- Streamlit UI ------------- #

st.set_page_config(
    page_title="Bulk Barcode JPEG Generator",
    page_icon="🏷️",
    layout="centered",
)

st.title("🏷️ Bulk Barcode JPEG Generator")

st.markdown(
    """
Upload a **CSV** or **paste data** with columns:

- `Barcode` – the full barcode string (e.g. `T0125123126021725551630`)
- `JPEG Name` – the desired file name (without extension)

Example (tab-separated):

Barcode\tJPEG Name  
T0125123126021725551630\t25_off_55_uk  
T0125123126021724351635\t24_off_35_uk  
T0525123126021710154362\t10_off_15_roi  
T0525123126021710204367\t10_off_20_roi
"""
)

st.header("1. Provide your data")

tab_csv, tab_paste = st.tabs(["📂 Upload CSV", "📝 Paste data"])

df = pd.DataFrame()
uploaded_file = None
pasted_text = ""

# --- CSV upload tab ---
with tab_csv:
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV file: {e}")

# --- Paste data tab ---
with tab_paste:
    pasted_text = st.text_area(
        "Paste your table here (tab- or comma-separated, include header row)",
        height=200,
        placeholder=(
            "Barcode\tJPEG Name\n"
            "T0125123126021725551630\t25_off_55_uk\n"
            "T0125123126021724351635\t24_off_35_uk\n"
            "T0525123126021710154362\t10_off_15_roi\n"
            "T0525123126021710204367\t10_off_20_roi"
        ),
    )
    if pasted_text.strip():
        try:
            pasted_df = parse_pasted_data(pasted_text)
            if df.empty:
                df = pasted_df
        except Exception as e:
            st.error(f"Error parsing pasted data: {e}")

valid, msg = validate_dataframe(df)

if not valid and (uploaded_file is not None or pasted_text.strip()):
    st.error(msg)

if valid:
    st.subheader("Preview of input data")
    st.dataframe(df.head())

st.header("2. Configure barcode output")

col1, col2 = st.columns(2)

with col1:
    dpi = st.number_input(
        "DPI (resolution)",
        min_value=72,
        max_value=1200,
        value=300,
        step=10,
        help="Higher DPI = sharper image",
    )

with col2:
    resize_option = st.selectbox(
        "Image size",
        ["Auto", "Custom (pixels)"],
    )

width_px: Optional[int] = None
height_px: Optional[int] = None

if resize_option == "Custom (pixels)":
    c1, c2 = st.columns(2)
    with c1:
        width_px = st.number_input(
            "Width (pixels)",
            min_value=100,
            max_value=5000,
            value=600,
            step=10,
        )
    with c2:
        height_px = st.number_input(
            "Height (pixels)",
            min_value=50,
            max_value=5000,
            value=300,
            step=10,
        )

st.header("3. Generate barcodes")

if valid:
    if st.button("🚀 Generate JPEGs & create ZIP"):
        with st.spinner("Generating barcodes..."):
            try:
                zip_bytes = create_zip_of_barcodes(
                    df=df,
                    dpi=dpi,
                    width_px=width_px,
                    height_px=height_px,
                )

                st.success("Barcodes generated successfully!")

                st.download_button(
                    label="⬇️ Download ZIP of JPEGs",
                    data=zip_bytes,
                    file_name="barcodes_jpegs.zip",
                    mime="application/zip",
                )

                st.subheader("Preview (first few barcodes)")
                for _, row in df.head(3).iterrows():
                    barcode_value = str(row["Barcode"]).strip()
                    jpeg_name = str(row["JPEG Name"]).strip()
                    if not barcode_value or not jpeg_name:
                        continue
                    img = generate_barcode_image(
                        barcode_value=barcode_value,
                        dpi=dpi,
                        width_px=width_px,
                        height_px=height_px,
                    )
                    st.caption(f"`{jpeg_name}.jpg` — {barcode_value}")
                    st.image(img)

            except Exception as e:
                st.error(f"Error generating barcodes: {e}")
else:
    st.info("Upload a CSV or paste data to begin.")
