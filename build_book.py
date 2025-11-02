"""Build a book that displays numbers 1 to 50,000 using collected number images."""
from pathlib import Path
import argparse
import pypdf


def get_image_for_number(number: int, numbers_dir: Path) -> Path:
    """Get the first available PNG for a number."""
    number_dir = numbers_dir / str(number)
    png_files = list(number_dir.glob('*.png'))
    if not png_files:
        raise FileNotFoundError(f"No PNG files found for number {number} in {number_dir}")
    return png_files[0]


GRID_COLUMNS = 5
GRID_ROWS = 10


def get_html_style() -> list[str]:
    """Get the HTML style section used for all pages."""
    return [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '    <title>The Numbers</title>',
        '    <style>',
        '        @page {',
        '            margin: 2in;',
        '        }',
        '        body {',
        '            font-family: Georgia, serif;',
        '            margin: 0;',
        '            padding: 0;',
        '        }',
        '        .container {',
        '            display: grid;',
        f'            grid-template-columns: repeat({GRID_COLUMNS}, 1fr);',
        f'            grid-template-rows: repeat({GRID_ROWS}, 1fr);',
        '            grid-auto-flow: column;',
        '            gap: 10px;',
        '            box-sizing: border-box;',
        '            min-height: 100vh;',
        '        }',
        '        .number-item {',
        '            display: flex;',
        '            align-items: center;',
        '            justify-content: center;',
        '        }',
        '        .number-image {',
        '            max-width: 100%;',
        '            max-height: 100%;',
        '            object-fit: contain;',
        '        }',
        '    </style>',
        '</head>',
        '<body>',
    ]


def build_page_html(numbers_dir: Path, start_number: int, count: int = 250) -> str:
    """Build HTML for a single page with specified numbers."""
    html_parts = get_html_style()
    html_parts.append('    <div class="container">')

    for number in range(start_number, start_number + count):
        image_path = get_image_for_number(number, numbers_dir)
        # Use absolute path to avoid relative path issues
        html_parts.append('        <div class="number-item">')
        html_parts.append(f'            <img src="file://{image_path.absolute()}" alt="{number}" class="number-image">')
        html_parts.append('        </div>')

    html_parts.extend([
        '    </div>',
        '</body>',
        '</html>'
    ])

    return '\n'.join(html_parts)


def html_to_pdf(html_path: Path, pdf_path: Path):
    """Convert HTML to PDF using playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(
            f"file://{html_path.absolute()}",
            wait_until="load",
            timeout=120_000
        )

        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        browser.close()


def merge_pdfs(pdf_paths: list[Path], output_path: Path):
    """Merge multiple PDFs into a single PDF."""
    merger = pypdf.PdfWriter()

    for pdf_path in pdf_paths:
        merger.append(str(pdf_path))

    merger.write(str(output_path))
    merger.close()


def main():
    """Generate PDF book with numbers 1 to max_number."""
    parser = argparse.ArgumentParser(description='Build a book of numbers 1 to 50,000')
    parser.add_argument('--max-number', type=int, default=50_000, help='Maximum number to include (default: 50,000)')
    args = parser.parse_args()

    numbers_dir = Path('data/numbers')
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)
    temp_dir = output_dir / 'temp_pages'
    temp_dir.mkdir(exist_ok=True)

    numbers_per_page = GRID_COLUMNS * GRID_ROWS
    total_pages = (args.max_number + numbers_per_page - 1) // numbers_per_page

    print(f"Generating {total_pages} pages...")

    page_pdfs = []

    for page_num in range(total_pages):
        start_number = page_num * numbers_per_page + 1
        remaining = args.max_number - start_number + 1
        count = min(numbers_per_page, remaining)

        if count <= 0:
            break

        print(f"Page {page_num + 1}/{total_pages} (numbers {start_number}-{start_number + count - 1})...")

        # Generate HTML for this page
        html_content = build_page_html(numbers_dir, start_number, count)
        html_path = temp_dir / f'page_{page_num:04d}.html'
        html_path.write_text(html_content, encoding='utf-8')

        # Convert to PDF
        pdf_path = temp_dir / f'page_{page_num:04d}.pdf'
        html_to_pdf(html_path, pdf_path)
        page_pdfs.append(pdf_path)

    print(f"\nMerging {len(page_pdfs)} pages...")
    final_pdf = output_dir / 'the_numbers.pdf'
    merge_pdfs(page_pdfs, final_pdf)

    print("\nCleaning up temporary PDFs...")
    for pdf_file in temp_dir.glob('*.pdf'):
        pdf_file.unlink()

    print(f"\nPDF created: {final_pdf}")
    print(f"HTML pages kept in: {temp_dir}")


if __name__ == '__main__':
    main()
