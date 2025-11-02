# Fetch book images from IA on request
import argparse
import asyncio
from pathlib import Path
import aiohttp
import requests


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    output_path: Path,
    identifier: str,
    filename: str,
    semaphore: asyncio.Semaphore,
    md5: str,
):
    async with semaphore:
        md5_path = output_path.with_suffix(output_path.suffix + ".md5")
        if output_path.exists() and md5_path.exists() and md5_path.read_text().strip() == md5:
            print(f"Skipping {identifier}/{filename}")
            return

        print(f"Downloading {identifier}/{filename}")
        async with session.get(url) as response:
            response.raise_for_status()
            output_path.write_bytes(await response.read())
        md5_path.write_text(md5)
        print(f"✅ Wrote {output_path}")
        await asyncio.sleep(1)


async def download_item(
    session: aiohttp.ClientSession, identifier: str, output_base: str, semaphore: asyncio.Semaphore
):
    item_dir = Path(output_base) / identifier
    item_dir.mkdir(exist_ok=True)

    # Get metadata to find files
    metadata_url = f"https://archive.org/metadata/{identifier}"
    async with session.get(metadata_url) as response:
        response.raise_for_status()
        metadata = await response.json()

    # Download only page images and hOCR files
    tasks = []
    for file in metadata.get("files", []):
        filename = file["name"]
        # Filter for the ZIP containing page images and hOCR files
        if not (filename.endswith("_hocr.html") or filename.endswith("jp2.zip")):
            continue

        download_url = f"https://archive.org/download/{identifier}/{filename}"
        output_path = item_dir / filename
        tasks.append(download_file(session, download_url, output_path, identifier, filename, semaphore, file["md5"]))

    await asyncio.gather(*tasks)


async def main(email: str, collection: str):
    headers = {"User-Agent": f"fetch-from-ia/0.1 (mailto:{email})"}
    search_query = f"mediatype:texts AND format:hocr AND date:[* TO 1924-12-31] AND NOT access-restricted-item:true AND NOT identifier:*mpeg21* AND language:eng AND collection:{collection}"
    output_base = "data/raw"

    Path(output_base).mkdir(parents=True, exist_ok=True)
    search_url = "https://archive.org/advancedsearch.php"
    search_params = {
        "q": search_query,
        "fl[]": "identifier",
        "output": "json",
        "start": "1",
    }

    # Send the search request to IA and return the json blob
    response = requests.get(search_url, params=search_params, headers=headers)
    response.raise_for_status()
    results = response.json()

    print(f"Found {results['response']['numFound']} items in collection '{collection}'")

    # Download all items concurrently with rate limiting
    # Limit concurrent downloads to avoid overwhelming IA
    semaphore = asyncio.Semaphore(5)
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = []
        for result in results["response"]["docs"]:
            identifier = result["identifier"]
            tasks.append(download_item(session, identifier, output_base, semaphore))

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch book images with hOCR from Internet Archive")
    parser.add_argument("email", help="Email address for User-Agent header")
    parser.add_argument("collection", help="Internet Archive collection name")

    args = parser.parse_args()
    asyncio.run(main(args.email, args.collection))
