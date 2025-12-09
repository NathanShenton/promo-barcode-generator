import io
import zipfile

import pandas as pd
import streamlit as st
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image


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


def validate_dataframe(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Ensure required columns exist.
    """
    required_cols = {"Barcode", "JPEG Name"}
    if df.empty:
        return False, "No data found. Please upload a CSV or paste data."

    if not required_cols.issubset(df.columns):
        return False, f"Data must contain columns: {', '.join(required_cols)}"

    # Optionally, you could also drop rows where Barcode/JPEG Name is missing
    return True, ""


def generate_barcode_image(
    barcode_value: str,
    dpi: int,
    width_px: int | None,
    height_px: int | None,
) -> Image.Image:
    """
    Generate a PIL Image for a given barcode value.
    Uses Code128 and resizes to requested dimensions if provided.
    """
    # Generate barcode into an in-memory buffer as JPEG
    buffer = io.BytesIO()
    code = Code128(barcode_value, writer=ImageWriter())
    code.write(
        buffer,
        {
            "format": "JPEG",
            "dpi": dpi,
            # You can tweak these for "density" of bars vs size
            "module_width": 0.2,
            "module_height": 15,
            "font_size": 12,
            "text_distance": 1,
        },
    )

    buffer.seek(0)
    img = Image.open(buffer)

    # If user specified dimensions, resize
    if width_px and height_px:
        img = img.resize((width_px, height_px), Image.LANCZOS)

    return img


def create_zip_of_barcodes(
    df: pd.DataFrame,
    dpi: int,
    width_px: int | None,
    height_px: int | None,
) -> bytes:
    """
    Generate a ZIP file (as bytes) containing one JPEG per row in df.
    JPEG file names are taken from 'JPEG Name' column.
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for idx, row in df.iterrows():
            barcode_value = str(row["Barcode"]).strip()
            jpeg_name = str(row["JPEG Name"]).strip()

            if not barcode_value or not jpeg_name:
                # Skip rows that don't have both values
                continue

            # Generate barcode image
            img = generate_barcode_image(
                barcode_value=barcode_value,
                dpi=dpi,
                width_px=width_px,
                height_px=height_px,
            )

            # Save image to in-memory buffer
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="JPEG")
            img_bytes.seek(0)

            # Ensure file name ends with .jpg
            filename = f"{jpeg_name}.jpg" if not jpeg_name.lower().endswith(".jpg") else jpeg_name

            # Add to ZIP
            zipf.writestr(filename, img_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# ------------- Streamlit UI ------------- #

st.set_page_config(page_title="Bulk Barcode JPEG Generator", page_icon="🏷️", layout="centered")

st.title("🏷️ Bulk Barcode JPEG Generator")

st.markdown(
    """
Upload a **CSV** or **paste data** with columns:

- `Barcode` – the full barcode string (e.g. `T0125123126021725551630`)
- `JPEG Name` – the desired **file name** for the JPEG (without extension)

Example:

```text
Barcode\tJPEG Name
T0125123126021725551630\t25_off_55_uk
T0125123126021724351635\t24_off_35_uk
T0525123126021710154362\t10_off_15_roi
T0525123126021710204367\t10_off_20_roi
