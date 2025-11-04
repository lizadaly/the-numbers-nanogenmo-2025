"""Build a book displaying all instances of a specific word using collected images."""

from pathlib import Path
import argparse
from jinja2 import Environment, FileSystemLoader
from utils import extract_scaled_height_from_image, distribute_items_to_columns, html_to_pdf, compress_pdf, merge_pdfs

GRID_COLUMNS = 5

# Letter page: 8.5in × 11in, margins: top 0.88in, bottom 1in, sides 2in
# Content area height: 11 - 0.88 - 1 = 9.12in, minus 0.75in running head space = 8.37in
# At 96 DPI:
#   - Width: 4.5 * 96 = 432px total, minus 4 gaps of 10px = 392px
#   - Column width: 392 / 5 = 78px per column (reduced for safety margin)
#   - Height: 8.37 * 96 = 804px height available (reduced for safety margin)
COLUMN_WIDTH_PX = 75
COLUMN_TARGET_HEIGHT_PX = 790

OUTPUT_DIR = Path("output")


def get_all_word_images(word_dir: Path) -> list[Path]:
    """Get all PNG images for a word, sorted by name.

    Args:
        word_dir: Directory containing word images (data/word/{word})

    Returns:
        List of image paths sorted by filename
    """
    png_files = sorted(word_dir.glob("*.png"))
    if not png_files:
        raise FileNotFoundError(f"No PNG files found in {word_dir}")
    return png_files


def build_page_html(
    word: str, images: list[Path], start_idx: int, max_count: int, page_num: int, bw: bool = False
) -> tuple[str, int]:
    """Build HTML for a single page with word images starting from start_idx.

    Images are distributed across columns to fill each column to approximately
    the target height based on actual image heights encoded in filenames.

    Args:
        word: The word being displayed
        images: List of all image paths for the word
        start_idx: Index of first image to include on this page
        max_count: Maximum number of images to try to fit
        page_num: Page number for running head (1-indexed)
        bw: Whether to render in black and white

    Returns:
        Tuple of (html_content, images_used)
    """
    # Collect images with their scaled heights (up to max_count available)
    # Normalize all widths to column width for consistent appearance
    items_with_heights = []
    for idx in range(start_idx, min(start_idx + max_count, len(images))):
        image_path = images[idx]
        scaled_height = extract_scaled_height_from_image(image_path, COLUMN_WIDTH_PX, normalize_width=True)
        items_with_heights.append((idx, scaled_height, image_path))

    # Distribute images across columns based on heights
    columns, images_used = distribute_items_to_columns(items_with_heights, GRID_COLUMNS, COLUMN_TARGET_HEIGHT_PX)

    # Calculate page type
    is_recto = page_num % 2 == 1

    # Prepare columns with absolute paths for template
    # Use image index as the "number" for display
    template_columns = [[(idx + 1, str(image_path.absolute())) for idx, image_path in column] for column in columns]

    # Render template
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("page.html")
    html_content = template.render(
        fonts_dir=Path("fonts").absolute(),
        page_num=page_num,
        start_number=start_idx + 1,
        end_number=start_idx + images_used,
        is_recto=is_recto,
        columns=template_columns,
        bw=bw,
        normalize_width=True,
    )

    return html_content, images_used


def main(word: str, images_per_page: int, bw: bool, pdf_quality: int):
    """Generate PDF book with all instances of a word."""
    word_dir = Path("data/word") / word
    if not word_dir.exists():
        raise FileNotFoundError(f"Word directory not found: {word_dir}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    temp_dir = OUTPUT_DIR / f"temp_pages_{word}"
    temp_dir.mkdir(exist_ok=True)

    # Get all images for this word
    images = get_all_word_images(word_dir)
    total_images = len(images)
    print(f"Found {total_images} images for word '{word}'")

    print("Generating pages (filling available space, actual count varies by image height)...")

    page_pdfs = []
    current_idx = 0
    page_num = 0

    while current_idx < total_images:
        # Calculate how many images we could try to fit on this page
        remaining = total_images - current_idx
        max_count = min(images_per_page, remaining)

        # Generate HTML for this page and see how many images actually fit
        html_content, images_used = build_page_html(word, images, current_idx, max_count, page_num + 1, bw)

        print(f"Page {page_num + 1} (images {current_idx + 1}-{current_idx + images_used})...")

        html_path = temp_dir / f"page_{page_num:04d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        # Convert to PDF and compress
        pdf_path = temp_dir / f"page_{page_num:04d}.pdf"
        html_to_pdf(html_path, pdf_path)
        compress_pdf(pdf_path, pdf_quality)
        page_pdfs.append(pdf_path)

        # Move to next page
        current_idx += images_used
        page_num += 1

    print(f"\nMerging {len(page_pdfs)} pages...")
    output_file = f"{word}_book.pdf"
    final_pdf = OUTPUT_DIR / output_file
    merge_pdfs(page_pdfs, final_pdf)

    print("\nCleaning up temporary PDFs...")
    for pdf_file in temp_dir.glob("*.pdf"):
        pdf_file.unlink()

    print(f"\nPDF created: {final_pdf}")
    print(f"HTML pages kept in: {temp_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a book of word occurrences")
    parser.add_argument("word", type=str, help="Word to create a book for")
    parser.add_argument(
        "--images-per-page",
        type=int,
        default=1000,
        help="Maximum number of images to try per page (default: 1000, fills available space)",
    )
    parser.add_argument("--bw", action="store_true", help="Render in black and white (default: False)")
    parser.add_argument(
        "--pdf-quality",
        type=int,
        default=70,
        help="JPEG quality for PDF images (0-100, lower = smaller file, default: 70)",
    )
    args = parser.parse_args()

    main(args.word, args.images_per_page, args.bw, args.pdf_quality)
