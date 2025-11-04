"""Compose missing numbers from existing digit primitives.

For numbers 1 to 50,000, compose missing digits out of multiple existing digit
primitives from the data/numbers directory. Use the largest possible value.
"""

import random
from pathlib import Path
from PIL import Image


def get_available_numbers(numbers_dir: Path) -> set[int]:
    """Get all numbers that have existing image files."""
    available = set()
    for d in numbers_dir.iterdir():
        if d.is_dir() and d.name.isdigit():
            # Only count as available if there are actual PNG files
            if list(d.glob("*.png")):
                available.add(int(d.name))
    return available


def get_image_for_number(number: int, numbers_dir: Path) -> Path | None:
    """Get a random available PNG for a number, or None if not found."""
    number_dir = numbers_dir / str(number)
    if not number_dir.exists():
        return None

    png_files = list(number_dir.glob("*.png"))
    return random.choice(png_files) if png_files else None


def find_largest_string_decomposition(target: str, available: set[int]) -> list[int] | None:
    """
    Decompose target number string into available numbers by matching prefixes.

    Uses greedy approach: repeatedly select the longest available number that matches
    the current prefix. For example, "12345" with available {1,2,3,123,45} becomes [123, 45].
    Returns list of numbers that compose the target string, or None if impossible.
    """
    # Convert available numbers to strings for prefix matching
    available_strs = {str(n): n for n in available}

    components = []
    pos = 0

    while pos < len(target):
        # Try from longest to shortest prefix; exit loop early on match
        for end in range(len(target), pos, -1):
            chunk = target[pos:end]
            if chunk in available_strs:
                components.append(available_strs[chunk])
                pos = end
                break
        else:
            # Can't compose this number
            return None

    return components


def concatenate_images_horizontally(image_paths: list[Path]) -> Image.Image:
    """Concatenate multiple images horizontally with consistent height."""
    images: list[Image.Image] = [Image.open(p) for p in image_paths]

    # Use max height to avoid cutting off any digits
    max_height = max(img.height for img in images)

    # Resize images to same height, maintaining aspect ratio
    resized: list[Image.Image] = []
    for img in images:
        if img.height != max_height:
            aspect_ratio = img.width / img.height
            new_width = int(max_height * aspect_ratio)
            resized.append(img.resize((new_width, max_height), Image.Resampling.LANCZOS))
        else:
            resized.append(img)

    # Calculate total width
    total_width = sum(img.width for img in resized)

    # Create composite image
    composite = Image.new("RGB", (total_width, max_height), color="white")

    # Paste images
    x_offset = 0
    for img in resized:
        composite.paste(img, (x_offset, 0))
        x_offset += img.width

    # Clean up
    for img in images:
        img.close()

    return composite


def compose_missing_numbers(numbers_dir: Path, max_number: int = 50_000):
    """
    Compose all missing numbers from 1 to max_number using existing primitives.

    Args:
        numbers_dir: Directory containing existing number images (also used for output)
        max_number: Maximum number to compose (default 50,000)
    """

    # Remove all existing composed images first (both old and new format)
    composed_files = list(numbers_dir.glob("*/*_composed*.png"))
    if composed_files:
        print(f"Removing {len(composed_files)} existing composed images...")
        for f in composed_files:
            f.unlink()

    available = get_available_numbers(numbers_dir)
    print(f"Found {len(available)} numbers with source images")

    missing_count = 0
    composed_count = 0
    impossible_count = 0

    for target in range(1, max_number + 1):
        if target in available:
            continue

        missing_count += 1

        # Find decomposition
        components = find_largest_string_decomposition(str(target), available)

        if components is None:
            impossible_count += 1
            if impossible_count <= 10:  # Only print first 10
                print(f"Cannot compose {target} from available numbers")
            continue

        # Get image paths for components
        image_paths = []
        for num in components:
            img_path = get_image_for_number(num, numbers_dir)
            if img_path is None:
                print(f"Warning: Expected image for {num} but not found")
                break
            image_paths.append(img_path)
        else:
            # All component images found - compose them
            composite = concatenate_images_horizontally(image_paths)

            # Save to number-specific subdirectory in numbers_dir with width and height in filename
            target_dir = numbers_dir / str(target)
            target_dir.mkdir(exist_ok=True)
            width, height = composite.size
            output_path = target_dir / f"{target}_composed_w{width}_h{height}.png"
            composite.save(output_path, "PNG")
            composite.close()

            composed_count += 1
            if composed_count % 1000 == 0:
                print(f"Composed {composed_count} numbers...")

    print("\nSummary:")
    print(f"  Missing numbers: {missing_count}")
    print(f"  Successfully composed: {composed_count}")
    print(f"  Impossible to compose: {impossible_count}")


def main():
    """Compose all missing numbers from existing primitives."""
    numbers_dir = Path("data/numbers")

    compose_missing_numbers(numbers_dir)


if __name__ == "__main__":
    main()
