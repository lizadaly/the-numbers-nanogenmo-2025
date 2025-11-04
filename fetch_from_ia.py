# Fetch book images from IA on request
import argparse
from pathlib import Path
import requests
import zipfile


def download_file(
    session: requests.Session,
    url: str,
    output_path: Path,
    identifier: str,
    filename: str,
    md5: str,
):
    md5_path = output_path.with_suffix(output_path.suffix + ".md5")
    if output_path.exists() and md5_path.exists() and md5_path.read_text().strip() == md5:
        print(f"Skipping {identifier}/{filename}")
        return

    print(f"Downloading {identifier}/{filename}")
    response = session.get(url)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    md5_path.write_text(md5)
    print(f"✅ Wrote {output_path}")


def download_item(session: requests.Session, identifier: str, output_base: str):
    item_dir = Path(output_base) / identifier
    item_dir.mkdir(exist_ok=True)

    # Get metadata to find files
    metadata_url = f"https://archive.org/metadata/{identifier}"
    response = session.get(metadata_url)
    response.raise_for_status()
    metadata = response.json()

    # Download only page images and hOCR files
    for file in metadata.get("files", []):
        filename = file["name"]
        # Filter for the ZIP containing page images and hOCR files
        if not (filename.endswith("_hocr.html") or filename.endswith("jp2.zip")):
            continue

        download_url = f"https://archive.org/download/{identifier}/{filename}"
        output_path = item_dir / filename
        download_file(session, download_url, output_path, identifier, filename, file["md5"])


def main(email: str, collection: str, limit: int):
    headers = {"User-Agent": f"fetch-from-ia/0.1 (mailto:{email})"}
    search_query = f"mediatype:texts AND format:hocr AND date:[* TO 1924-12-31] AND NOT access-restricted-item:true AND NOT identifier:*mpeg21* AND language:eng AND collection:{collection}"
    output_base = "data/raw"

    Path(output_base).mkdir(parents=True, exist_ok=True)
    search_url = "https://archive.org/advancedsearch.php"
    search_params = {
        "q": search_query,
        "fl[]": "identifier",
        "output": "json",
        "rows": str(limit),
        "start": "1",
    }

    # Send the search request to IA and return the json blob
    with requests.Session() as session:
        session.headers.update(headers)

        response = session.get(search_url, params=search_params)
        response.raise_for_status()
        results = response.json()

        print(f"Found {results['response']['numFound']} items in collection '{collection}'")

        for result in results["response"]["docs"]:
            identifier = result["identifier"]
            download_item(session, identifier, output_base)

    # unpack zip files
    for item_dir in Path(output_base).iterdir():
        for zip_path in item_dir.glob("*.zip"):
            # Check if already extracted
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                all_extracted = all((item_dir / name).exists() for name in zip_ref.namelist())

            if all_extracted:
                continue

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(item_dir)
            print(f"✅ Extracted {zip_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch book images with hOCR from Internet Archive")
    parser.add_argument("email", help="Email address for User-Agent header")
    parser.add_argument("collection", help="Internet Archive collection name")
    parser.add_argument("--limit", type=int, default=200, help="Number of books to fetch (default: 200)")

    args = parser.parse_args()
    main(args.email, args.collection, args.limit)
