"""Extract word images from hOCR files and JP2 images."""

import sys
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from selectolax.parser import HTMLParser
from PIL import Image

from utils import parse_bbox, parse_confidence, parse_image_path

type WordWithBbox = tuple[int, int, int, int]

# Directory paths
RAW_DIR = Path("data/raw")


def extract_word_from_hocr(hocr_path: Path, target_word: str) -> dict[str, list[WordWithBbox]]:
    """
    Parse hOCR file and extract all occurrences of the target word with their bounding boxes.

    Returns:
        Dict mapping image filename to list of (x0, y0, x1, y1) tuples
    """
    html = HTMLParser(hocr_path.read_text())
    words_by_image: dict[str, list[WordWithBbox]] = defaultdict(list)
    target_word_lower = target_word.lower()

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
            if text.strip().lower() != target_word_lower:
                continue
            if not (word_title := word.attributes.get("title")):
                continue
            if (confidence := parse_confidence(word_title)) is None or confidence <= 90:
                continue
            if (bbox := parse_bbox(word_title)) is None:
                continue

            words_by_image[image_name].append(bbox)

    return words_by_image


def extract_and_save_word(hocr_path: Path, jp2_dir: Path, output_dir: Path, book_name: str, target_word: str):
    """
    Extract all occurrences of target word from hOCR file and save corresponding image regions.
    """
    print(f"Processing {book_name}...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse hOCR to get word instances and bounding boxes
    words_by_image = extract_word_from_hocr(hocr_path, target_word)

    count = 0
    skipped = 0
    # Extract each word instance from corresponding JP2
    for image_name, bboxes in words_by_image.items():
        jp2_path = jp2_dir / image_name
        if not jp2_path.exists():
            print(f"Warning: JP2 not found: {jp2_path}")
            continue

        png_name = Path(image_name).with_suffix(".png").name

        # Open JP2 image once for this page
        with Image.open(jp2_path) as img:
            # Process all word instances on this page
            for idx, (x0, y0, x1, y1) in enumerate(bboxes):
                # Crop first to get actual dimensions
                cropped = img.crop((x0, y0, x1, y1))
                width, height = cropped.size

                # Include width and height in filename
                base_name = Path(png_name).stem
                output_path = output_dir / f"{target_word}_{book_name}_{base_name}_{idx}_w{width}_h{height}.png"

                if output_path.exists():
                    cropped.close()
                    skipped += 1
                    continue

                cropped.save(output_path, "PNG")
                cropped.close()
                count += 1

    print(f"Completed {book_name}: extracted {count} instances of '{target_word}', skipped {skipped} existing")
    return count


def process_book(book_dir: Path, output_dir: Path, target_word: str) -> int:
    """Process a single book directory."""
    # Find hOCR file
    hocr_files = list(book_dir.glob("*_hocr.html"))
    if not hocr_files:
        print(f"No hOCR file found in {book_dir}, skipping")
        return 0

    hocr_path = hocr_files[0]

    # Find JP2 directory
    jp2_dirs = list(book_dir.glob("*_jp2"))
    if not jp2_dirs:
        print(f"No JP2 files found in {book_dir}, skipping")
        return 0

    jp2_dir = jp2_dirs[0]

    return extract_and_save_word(hocr_path, jp2_dir, output_dir, book_dir.name, target_word)


def main():
    """Process all downloaded books in parallel to extract a specific word."""
    if len(sys.argv) != 2:
        print("Usage: python extract_word.py <word>")
        sys.exit(1)

    target_word = sys.argv[1]
    output_dir = Path("data/word") / target_word

    # Collect all book directories
    book_dirs = [d for d in RAW_DIR.iterdir() if d.is_dir()]

    print(f"Found {len(book_dirs)} books to process")
    print(f"Extracting word: '{target_word}'")
    print(f"Output directory: {output_dir}")

    # Process books in parallel
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_book, book_dir, output_dir, target_word): book_dir for book_dir in book_dirs}
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error processing {futures[future]}: {e}")
                results.append(0)

    total = sum(results)
    print(f"Total instances of '{target_word}' extracted: {total}")


if __name__ == "__main__":
    main()
