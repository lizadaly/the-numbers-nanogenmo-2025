"""Extract number images from hOCR files and JP2 images."""
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from selectolax.parser import HTMLParser
from PIL import Image
from word2number import w2n


def extract_number_from_text(text: str) -> int | None:
    """Extract a number from text if it's between 1-50,000."""
    text = text.strip()

    # Try direct numeric parsing first
    if text.isdigit():
        num = int(text)
        if 1 <= num <= 50_000:
            return num

    # Try word to number conversion (e.g., "twenty-three" -> 23)
    try:
        num = w2n.word_to_num(text)
        if isinstance(num, int) and 1 <= num <= 50_000:
            return num
    except ValueError:
        pass

    return None


def parse_bbox(title: str) -> tuple[int, int, int, int] | None:
    """Extract bounding box coordinates from hOCR title attribute."""
    if match := re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', title):
        x0, y0, x1, y1 = map(int, match.groups())
        return (x0, y0, x1, y1)
    return None


def parse_ppageno(title: str) -> int | None:
    """Extract physical page number from hOCR title attribute."""
    if match := re.search(r'ppageno (\d+)', title):
        return int(match.group(1))
    return None


def extract_numbers_from_hocr(hocr_path: Path) -> dict[int, list[tuple[int, int, int, int, int]]]:
    """
    Parse hOCR file and extract all numbers with their bounding boxes.
    Only capture the first occurrence of each number per book.

    Returns:
        Dict mapping page number to list of (number, x0, y0, x1, y1) tuples
    """
    html = HTMLParser(hocr_path.read_text())
    numbers_by_page = {}
    seen_numbers = set()

    # Find all pages
    for page in html.css('div.ocr_page'):
        if not (page_title := page.attributes.get('title')):
            continue
        if (page_num := parse_ppageno(page_title)) is None:
            continue

        # Find all words on this page
        for word in page.css('span.ocrx_word'):
            if not (text := word.text()):
                continue

            if (number := extract_number_from_text(text)) is None:
                continue

            # Skip if we've already captured this number in this book
            if number in seen_numbers:
                continue

            if not (word_title := word.attributes.get('title')):
                continue
            if (bbox := parse_bbox(word_title)) is None:
                continue

            if page_num not in numbers_by_page:
                numbers_by_page[page_num] = []

            numbers_by_page[page_num].append((number, *bbox))
            seen_numbers.add(number)

    return numbers_by_page


def extract_and_save_numbers(hocr_path: Path, jp2_dir: Path, output_dir: Path, book_name: str):
    """
    Extract all numbers from hOCR file and save corresponding image regions.

    Args:
        hocr_path: Path to hOCR HTML file
        jp2_dir: Directory containing JP2 page images
        output_dir: Directory to save extracted number PNGs
        book_name: Name of the book being processed
    """
    print(f"Processing {book_name}...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse hOCR to get numbers and bounding boxes
    numbers_by_page = extract_numbers_from_hocr(hocr_path)

    count = 0
    skipped = 0
    # Extract each number from corresponding JP2
    for page_num, numbers in numbers_by_page.items():
        # Find JP2 file for this page
        # Pattern: identifier_0001.jp2, identifier_0002.jp2, etc.
        jp2_pattern = f"*_{page_num:04d}.jp2"
        jp2_files = list(jp2_dir.glob(jp2_pattern))

        if not jp2_files:
            print(f"Warning: No JP2 found for page {page_num} (pattern: {jp2_pattern})")
            continue

        jp2_path = jp2_files[0]

        # Open JP2 image once for this page
        with Image.open(jp2_path) as img:
            # Process all numbers on this page
            for number, x0, y0, x1, y1 in numbers:
                # Check if output already exists
                number_dir = output_dir / str(number)
                output_path = number_dir / f"{number}_{book_name}_p{page_num}.png"

                if output_path.exists():
                    skipped += 1
                    continue

                # Crop region
                region = img.crop((x0, y0, x1, y1))

                # Save as PNG - create numbered subdirectories for organization
                number_dir.mkdir(exist_ok=True)
                region.save(output_path, 'PNG')
                count += 1

    print(f"Completed {book_name}: extracted {count} numbers, skipped {skipped} existing")
    return count


def process_book(book_dir: Path, output_dir: Path) -> int:
    """Process a single book directory."""
    # Find hOCR file
    hocr_files = list(book_dir.glob('*_hocr.html'))
    if not hocr_files:
        print(f"No hOCR file found in {book_dir}")
        return 0

    hocr_path = hocr_files[0]

    # Find JP2 directory
    jp2_dirs = list(book_dir.glob('*_jp2'))
    if not jp2_dirs:
        print(f"No JP2 directory found in {book_dir}")
        return 0

    jp2_dir = jp2_dirs[0]

    return extract_and_save_numbers(hocr_path, jp2_dir, output_dir, book_dir.name)


def main():
    """Process all downloaded books in parallel."""
    raw_dir = Path('data/raw')
    output_dir = Path('data/numbers')

    # Collect all book directories
    book_dirs = [d for d in raw_dir.iterdir() if d.is_dir()]

    print(f"Found {len(book_dirs)} books to process")

    # Process books in parallel
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_book, book_dir, output_dir) for book_dir in book_dirs]
        results = [f.result() for f in futures]

    total = sum(results)
    print(f"Total numbers extracted: {total}")


if __name__ == '__main__':
    main()
