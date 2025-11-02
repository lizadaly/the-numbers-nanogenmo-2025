# Fetch book images from IA on request
import argparse
from pathlib import Path
import requests

def main(email: str, collection: str):


    headers = {"User-Agent": f"fetch-from-ia/0.1 (mailto:{email})"}
    search_query = f'mediatype:texts AND format:hocr AND date:[* TO 1924-12-31] AND NOT access-restricted-item:true AND NOT identifier:*mpeg21* AND language:eng AND collection:{collection}'
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
    for result in results['response']['docs']:
        # download the item
        identifier = result['identifier']
        item_dir = Path(output_base) / identifier
        item_dir.mkdir(exist_ok=True)

        # Get metadata to find files
        metadata_url = f"https://archive.org/metadata/{identifier}"
        metadata_response = requests.get(metadata_url, headers=headers)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()

        # Download only page images and hOCR files
        for file in metadata.get('files', []):
            filename = file['name']
            file_format = file.get('format', '')
            # Filter for the ZIP containing page images and hOCR files
            if not (filename.endswith('_hocr.html') or filename.endswith('jp2.zip')):
                continue

            download_url = f"https://archive.org/download/{identifier}/{filename}"
            output_path = item_dir / filename

            print(f"Downloading {identifier}/{filename}")
            file_response = requests.get(download_url, headers=headers, stream=True)
            file_response.raise_for_status()

            output_path.write_bytes(file_response.content) 
        break 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch book images with hOCR from Internet Archive")
    parser.add_argument("email", help="Email address for User-Agent header")
    parser.add_argument("collection", help="Internet Archive collection name")

    args = parser.parse_args()    
    main(args.email, args.collection)
