"""Extract number images from hOCR files and JP2 images."""

import shutil
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from selectolax.parser import HTMLParser
from PIL import Image
from word2number import w2n

from utils import parse_bbox, parse_confidence, parse_image_path

type NumberWithBbox = tuple[int, int, int, int, int]

# Directory paths
RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/numbers")


def extract_number_from_text(text: str) -> int | None:
    """Extract a number from text if it's between 0-50,000."""
    text = text.strip().lower()

    # Handle "zero" explicitly
    if text == "zero":
        return 0

    # Try direct numeric parsing - but only accept properly formatted numbers
    # (no leading zeros except for "0" itself)
    if text.isdigit():
        # Reject strings like "00" or "000" - only accept "0"
        if text.startswith("0") and len(text) > 1:
            return None
        num = int(text)
        if 0 <= num <= 50_000:
            return num

    # Try word to number conversion (e.g., "twenty-three" -> 23)
    # Skip if result would be 0 (word2number incorrectly converts "point" and other words to 0)
    try:
        result = w2n.word_to_num(text)
        if isinstance(result, int) and 1 <= result <= 50_000:
            return result
    except (ValueError, IndexError):
        pass

    return None


def extract_numbers_from_hocr(hocr_path: Path) -> dict[str, list[NumberWithBbox]]:
    """
    Parse hOCR file and extract all numbers with their bounding boxes.
    Only capture the first occurrence of each number per book.

    Returns:
        Dict mapping image filename to list of (number, x0, y0, x1, y1) tuples
    """
    html = HTMLParser(hocr_path.read_text())
    numbers_by_image: dict[str, list[NumberWithBbox]] = defaultdict(list)
    seen_numbers: set[int] = set()

    # Find all pages
    for page in html.css("div.ocr_page"):
        if not (page_title := page.attributes.get("title")):
            continue
        if (image_name := parse_image_path(page_title)) is None:
            continue

        # Find all words on this page
        for word in page.css("span.ocrx_word"):
            if not (text := word.text()):
                continue
            if (number := extract_number_from_text(text)) is None or number in seen_numbers:
                continue
            if not (word_title := word.attributes.get("title")):
                continue
            if (confidence := parse_confidence(word_title)) is None or confidence <= 90:
                continue
            if (bbox := parse_bbox(word_title)) is None:
                continue

            numbers_by_image[image_name].append((number, *bbox))
            seen_numbers.add(number)

    return numbers_by_image


def extract_and_save_numbers(hocr_path: Path, jp2_dir: Path, output_dir: Path, book_name: str):
    """
    Extract all numbers from hOCR file and save corresponding image regions.
    """
    print(f"Processing {book_name}...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse hOCR to get numbers and bounding boxes
    numbers_by_image = extract_numbers_from_hocr(hocr_path)

    count = 0
    skipped = 0
    # Extract each number from corresponding JP2
    for image_name, numbers in numbers_by_image.items():
        jp2_path = jp2_dir / image_name
        if not jp2_path.exists():
            print(f"Warning: JP2 not found: {jp2_path}")
            continue

        png_name = Path(image_name).with_suffix(".png").name

        # Open JP2 image once for this page
        with Image.open(jp2_path) as img:
            # Process all numbers on this page
            for number, x0, y0, x1, y1 in numbers:
                number_dir = output_dir / str(number)

                # Crop first to get actual dimensions
                cropped = img.crop((x0, y0, x1, y1))
                width, height = cropped.size

                # Include width and height in filename
                base_name = Path(png_name).stem
                output_path = number_dir / f"{number}_{book_name}_{base_name}_w{width}_h{height}.png"

                if output_path.exists():
                    cropped.close()
                    skipped += 1
                    continue

                number_dir.mkdir(exist_ok=True)
                cropped.save(output_path, "PNG")
                cropped.close()
                count += 1

    print(f"Completed {book_name}: extracted {count} numbers, skipped {skipped} existing")
    return count


def process_book(book_dir: Path, output_dir: Path) -> int:
    """Process a single book directory."""
    # Find hOCR file
    hocr_files = list(book_dir.glob("*_hocr.html"))
    if not hocr_files:
        print(f"No hOCR file found in {book_dir}, deleting archive")
        shutil.rmtree(book_dir)
        return 0

    hocr_path = hocr_files[0]

    # Find JP2 directory
    jp2_dirs = list(book_dir.glob("*_jp2"))
    if not jp2_dirs:
        print(f"No JP2 files found in {book_dir}, deleting archive")
        shutil.rmtree(book_dir)
        return 0

    jp2_dir = jp2_dirs[0]

    return extract_and_save_numbers(hocr_path, jp2_dir, output_dir, book_dir.name)


def main():
    """Process all downloaded books in parallel."""
    # Collect all book directories
    book_dirs = [d for d in RAW_DIR.iterdir() if d.is_dir()]

    print(f"Found {len(book_dirs)} books to process")

    # Process books in parallel
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_book, book_dir, OUTPUT_DIR): book_dir for book_dir in book_dirs}
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error processing {futures[future]}: {e}")
                results.append(0)

    total = sum(results)
    print(f"Total numbers extracted: {total}")


if __name__ == "__main__":
    main()
