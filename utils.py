"""Common utilities for extracting data from hOCR files and building books."""

import re
from pathlib import Path
from typing import TypeVar, Callable
import pypdf

T = TypeVar("T")

# Precompiled regex patterns for hOCR metadata
_BBOX_RE = re.compile(r"bbox (\d+) (\d+) (\d+) (\d+)")
_CONFIDENCE_RE = re.compile(r"x_wconf (\d+(?:\.\d+)?)")
_IMAGE_PATH_RE = re.compile(r'image "([^"]+)"')


def _match_group(title: str, pattern: re.Pattern, *, cast: Callable[[str], T]) -> T | None:
    """Extract and convert a regex match from hOCR title attribute."""
    if match := pattern.search(title):
        return cast(match.group(1))
    return None


def parse_bbox(title: str) -> tuple[int, int, int, int] | None:
    """Extract bounding box coordinates from hOCR title attribute."""
    if match := _BBOX_RE.search(title):
        x0, y0, x1, y1 = map(int, match.groups())
        return (x0, y0, x1, y1)
    return None


def parse_confidence(title: str) -> float | None:
    """Extract OCR confidence from hOCR title attribute (x_wconf)."""
    return _match_group(title, _CONFIDENCE_RE, cast=float)


def parse_image_path(title: str) -> str | None:
    """Extract image path from hOCR title attribute."""
    return _match_group(title, _IMAGE_PATH_RE, cast=lambda p: Path(p).name)


def extract_scaled_height_from_image(image_path: Path, column_width_px: int, normalize_width: bool = False) -> int:
    """Extract dimensions from image filename and compute scaled height.

    Args:
        image_path: Path to image file with format *_w{width}_h{height}.png
        column_width_px: Maximum width available in each column
        normalize_width: If True, scale all images to exactly column_width_px.
                        If False, only scale down images that are too wide.

    Returns:
        Scaled height in pixels
    """
    # Extract width and height from filename pattern: *_w{width}_h{height}.png
    match = re.search(r"_w(\d+)_h(\d+)\.png$", image_path.name)
    if not match:
        raise ValueError(f"Image filename does not contain width and height: {image_path}")

    width = int(match.group(1))
    height = int(match.group(2))

    # Calculate scaling factor based on column width
    if normalize_width:
        # Always scale to exactly the column width
        scale_factor = column_width_px / width
    else:
        # Only scale down if wider than column
        scale_factor = min(1.0, column_width_px / width)

    scaled_height = int(height * scale_factor)

    return scaled_height


def get_image_with_dimensions(image_dir: Path, column_width_px: int) -> tuple[Path, int]:
    """Get the first available PNG in a directory and compute its scaled height.

    The height is scaled based on the column width, since images wider than
    the column will be scaled down proportionally by the CSS max-width: 100%.

    Args:
        image_dir: Directory containing PNG files
        column_width_px: Maximum width available in each column

    Returns:
        Tuple of (image_path, scaled_height_in_pixels)
    """
    png_files = list(image_dir.glob("*.png"))
    if not png_files:
        raise FileNotFoundError(f"No PNG files found in {image_dir}")

    image_path = png_files[0]
    scaled_height = extract_scaled_height_from_image(image_path, column_width_px)

    return image_path, scaled_height


def distribute_items_to_columns(
    items_with_heights: list[tuple[T, int, Path]], num_columns: int, target_height: int
) -> tuple[list[list[tuple[T, Path]]], int]:
    """Distribute items across columns sequentially, filling each column to target height.

    Items are added in order down the first column until target height is reached,
    then down the second column, etc. Stops when all columns are filled.

    Args:
        items_with_heights: List of (item, height, image_path) tuples in sequential order
        num_columns: Number of columns to distribute across
        target_height: Target height in pixels for each column

    Returns:
        Tuple of (columns, items_used) where columns is a list of columns and
        items_used is the count of items actually placed
    """
    columns: list[list[tuple[T, Path]]] = [[] for _ in range(num_columns)]
    current_column_idx = 0
    current_height = 0
    items_used = 0

    for item, height, image_path in items_with_heights:
        # If adding this item would exceed target, try to move to next column
        if current_height + height > target_height:
            # Stop if we're already on the last column and it would exceed target
            if current_column_idx >= num_columns - 1:
                break
            # Otherwise move to next column
            current_column_idx += 1
            current_height = 0

        # Add to current column
        columns[current_column_idx].append((item, image_path))
        current_height += height
        items_used += 1

    return columns, items_used


def html_to_pdf(html_path: Path, pdf_path: Path):
    """Convert HTML to PDF using playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(f"file://{html_path.absolute()}", wait_until="load", timeout=120_000)

        page.pdf(path=str(pdf_path), format="Letter", print_background=True)
        browser.close()


def compress_pdf(pdf_path: Path, quality: int = 70):
    """Compress images in PDF to reduce file size.

    Args:
        pdf_path: Path to PDF file to compress (will be overwritten)
        quality: JPEG quality for images (0-100, default 70)
    """
    writer = pypdf.PdfWriter(clone_from=str(pdf_path))
    for page in writer.pages:
        for img in page.images:
            img.replace(img.image, quality=quality)  # type: ignore[arg-type]
    with open(pdf_path, "wb") as f:
        writer.write(f)
    writer.close()


def merge_pdfs(pdf_paths: list[Path], output_path: Path):
    """Merge multiple PDFs into a single PDF."""
    merger = pypdf.PdfWriter()

    for pdf_path in pdf_paths:
        merger.append(str(pdf_path))

    merger.write(str(output_path))
    merger.close()
