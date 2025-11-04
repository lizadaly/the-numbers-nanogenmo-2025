"""Build a book that displays numbers 1 to 50,000 using collected number images."""

from pathlib import Path
import argparse
import re
from num2words import num2words
from jinja2 import Environment, FileSystemLoader
from utils import get_image_with_dimensions, distribute_items_to_columns, html_to_pdf, compress_pdf, merge_pdfs

GRID_COLUMNS = 5

# Letter page: 8.5in × 11in, margins: top 0.88in, bottom 1in, sides 2in
# Content area height: 11 - 0.88 - 1 = 9.12in, minus 0.75in running head space = 8.37in
# At 96 DPI:
#   - Width: 4.5 * 96 = 432px total, minus 4 gaps of 10px = 392px
#   - Column width: 392 / 5 = 78px per column (reduced for safety margin)
#   - Height: 8.37 * 96 = 804px height available (reduced for safety margin)
COLUMN_WIDTH_PX = 75
COLUMN_TARGET_HEIGHT_PX = 790

NUMBERS_DIR = Path("data/numbers")
OUTPUT_DIR = Path("output")


def get_image_for_number(number: int, numbers_dir: Path, column_width_px: int) -> tuple[Path, int]:
    """Get the first available PNG for a number and compute its scaled height.

    Args:
        number: The number to get an image for
        numbers_dir: Directory containing number subdirectories
        column_width_px: Maximum width available in each column

    Returns:
        Tuple of (image_path, scaled_height_in_pixels)
    """
    number_dir = numbers_dir / str(number)
    try:
        return get_image_with_dimensions(number_dir, column_width_px)
    except FileNotFoundError:
        raise FileNotFoundError(f"No PNG files found for number {number} in {number_dir}; do you need to run compose?")


def distribute_numbers_to_columns(
    numbers_with_heights: list[tuple[int, int, Path]], num_columns: int, target_height: int
) -> tuple[list[list[tuple[int, Path]]], int]:
    """Distribute numbers across columns sequentially, filling each column to target height.

    Args:
        numbers_with_heights: List of (number, height, image_path) tuples in sequential order
        num_columns: Number of columns to distribute across
        target_height: Target height in pixels for each column

    Returns:
        Tuple of (columns, numbers_used) where columns is a list of columns and
        numbers_used is the count of numbers actually placed
    """
    return distribute_items_to_columns(numbers_with_heights, num_columns, target_height)


def build_page_html(
    numbers_dir: Path, start_number: int, max_count: int, page_num: int, bw: bool = False
) -> tuple[str, int, int]:
    """Build HTML for a single page with numbers starting from start_number.

    Numbers are distributed across columns to fill each column to approximately
    the target height based on actual image heights encoded in filenames.

    Args:
        numbers_dir: Directory containing number subdirectories
        start_number: First number to include on this page
        max_count: Maximum number of numbers to try to fit
        page_num: Page number for running head (1-indexed)
        bw: Whether to render in black and white

    Returns:
        Tuple of (html_content, numbers_used, end_number)
    """
    # Collect numbers with their scaled heights (up to max_count available)
    numbers_with_heights = []
    for number in range(start_number, start_number + max_count):
        image_path, scaled_height = get_image_for_number(number, numbers_dir, COLUMN_WIDTH_PX)
        numbers_with_heights.append((number, scaled_height, image_path))

    # Distribute numbers across columns based on heights
    columns, numbers_used = distribute_numbers_to_columns(numbers_with_heights, GRID_COLUMNS, COLUMN_TARGET_HEIGHT_PX)

    # Calculate end number and page type
    end_number = start_number + numbers_used - 1
    is_recto = page_num % 2 == 1

    # Prepare columns with absolute paths for template
    template_columns = [[(number, str(image_path.absolute())) for number, image_path in column] for column in columns]

    # Render template
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("page.html")
    html_content = template.render(
        fonts_dir=Path("fonts").absolute(),
        page_num=page_num,
        start_number=start_number,
        end_number=end_number,
        is_recto=is_recto,
        columns=template_columns,
        bw=bw,
    )

    return html_content, numbers_used, end_number


def build_toc_html(toc_entries: list[tuple[int, int, int]]) -> str:
    # Prepare entries with chapter words
    template_entries = []
    for chapter_num, (start, end, page) in enumerate(toc_entries, start=1):
        chapter_word = num2words(chapter_num)
        template_entries.append((start, end, page, chapter_word))

    # Render template
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("toc.html")
    return template.render(fonts_dir=Path("fonts").absolute(), toc_entries=template_entries)


def main(start: int, max_number: int, numbers_per_page: int, bw: bool, output_file: str, pdf_quality: int):
    """Generate PDF book with numbers 1 to max_number."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    temp_dir = OUTPUT_DIR / "temp_pages"
    temp_dir.mkdir(exist_ok=True)

    print("Generating pages (filling available space, actual count varies by image height)...")

    page_pdfs = []
    current_number = start
    page_num = 0

    # Track which 1000-number ranges we've seen: maps range_num -> first page where it appeared
    range_to_page = {}

    while current_number <= max_number:
        # Calculate how many numbers we could try to fit on this page
        remaining = max_number - current_number + 1
        max_count = min(numbers_per_page, remaining)

        # Generate HTML for this page and see how many numbers actually fit
        html_content, numbers_used, end_number = build_page_html(
            NUMBERS_DIR, current_number, max_count, page_num + 1, bw
        )

        print(f"Page {page_num + 1} (numbers {current_number}-{end_number})...")

        # Track TOC entry for each 1000-number range that appears on this page
        page_start_range = (current_number - 1) // 1000
        page_end_range = (end_number - 1) // 1000

        # Record the first page for any new ranges on this page
        for range_idx in range(page_start_range, page_end_range + 1):
            if range_idx not in range_to_page:
                range_to_page[range_idx] = page_num + 1

        html_path = temp_dir / f"page_{page_num:04d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        # Convert to PDF and compress
        pdf_path = temp_dir / f"page_{page_num:04d}.pdf"
        html_to_pdf(html_path, pdf_path)
        compress_pdf(pdf_path, pdf_quality)
        page_pdfs.append(pdf_path)

        # Move to next page
        current_number += numbers_used
        page_num += 1

    # Build TOC entries from range tracking
    toc_entries = []
    for range_idx in sorted(range_to_page.keys()):
        range_start = range_idx * 1000 + 1
        range_end = min(range_start + 999, max_number)
        page_num = range_to_page[range_idx]
        toc_entries.append((range_start, range_end, page_num))

    # Generate title page
    print("\nGenerating title page...")

    # Format max_number for display
    if max_number >= 1000 and max_number % 1000 == 0:
        max_number_text = f"{max_number // 1000} thousand"
    else:
        max_number_text = f"{max_number:,}"

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("title_page.html")
    title_page_html = template.render(
        fonts_dir=Path("fonts").absolute(), bw=bw, start_word=num2words(start), max_number_text=max_number_text
    )

    title_page_temp = temp_dir / "title_page.html"
    title_page_temp.write_text(title_page_html, encoding="utf-8")

    title_pdf_path = temp_dir / "title_page.pdf"
    html_to_pdf(title_page_temp, title_pdf_path)
    compress_pdf(title_pdf_path, pdf_quality)

    # Generate TOC
    print("Generating table of contents...")
    toc_html = build_toc_html(toc_entries)
    toc_html_path = temp_dir / "toc.html"
    toc_html_path.write_text(toc_html, encoding="utf-8")

    toc_pdf_path = temp_dir / "toc.pdf"
    html_to_pdf(toc_html_path, toc_pdf_path)
    compress_pdf(toc_pdf_path, pdf_quality)

    print(f"\nMerging title page + TOC + {len(page_pdfs)} pages...")
    final_pdf = OUTPUT_DIR / output_file
    merge_pdfs([title_pdf_path, toc_pdf_path] + page_pdfs, final_pdf)

    print("\nCleaning up temporary PDFs...")
    for pdf_file in temp_dir.glob("*.pdf"):
        pdf_file.unlink()

    print(f"\nPDF created: {final_pdf}")
    print(f"HTML pages kept in: {temp_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a book of numbers")
    parser.add_argument("--start", type=int, default=1, help="Starting number (default: 1)")
    parser.add_argument("--max-number", type=int, default=50_000, help="Maximum number to include (default: 50,000)")
    parser.add_argument(
        "--numbers-per-page",
        type=int,
        default=1000,
        help="Maximum number of images to try per page (default: 1000, fills available space)",
    )
    parser.add_argument("--bw", action="store_true", help="Render in black and white (default: False)")
    parser.add_argument(
        "--output-file", type=str, default="the_numbers.pdf", help="Output PDF filename (default: the_numbers.pdf)"
    )
    parser.add_argument(
        "--pdf-quality",
        type=int,
        default=70,
        help="JPEG quality for PDF images (0-100, lower = smaller file, default: 70)",
    )
    args = parser.parse_args()

    main(args.start, args.max_number, args.numbers_per_page, args.bw, args.output_file, args.pdf_quality)
