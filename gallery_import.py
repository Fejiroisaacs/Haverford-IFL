"""
IFL Gallery Image Import Module

Automates the process of adding images to the gallery system:
- Converts images to WebP format
- Resizes to thumbnail (300x200) and full (1200x800) sizes
- Auto-numbers images sequentially per season
- Updates gallery.json metadata

Usage:
    python gallery_import.py --season 6 --input "New Photos"
    python gallery_import.py -s 6 -i "New Photos" --caption "Championship Game"
"""

import os
import json
import argparse
from pathlib import Path
from PIL import Image
from typing import Dict, List, Optional
import sys


class GalleryImporter:
    """Handles importing and processing images for the IFL gallery."""

    # Configuration
    GALLERY_BASE = Path("templates/static/Images/Gallery")
    GALLERY_JSON = Path("templates/static/data/gallery.json")

    THUMBNAIL_SIZE = (300, 200)
    FULL_SIZE = (1200, 800)

    WEBP_QUALITY_THUMBNAIL = 85
    WEBP_QUALITY_FULL = 82

    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

    def __init__(self, season: int):
        """
        Initialize the importer for a specific season.

        Args:
            season: Season number (e.g., 6 for Season 6)
        """
        self.season = season
        self.season_folder = self.GALLERY_BASE / f"Season{season}"
        self.thumbnails_folder = self.season_folder / "thumbnails"
        self.full_folder = self.season_folder / "full"

        # Ensure folders exist
        self._create_folders()

        # Load existing gallery data
        self.gallery_data = self._load_gallery_json()

    def _create_folders(self):
        """Create necessary folder structure if it doesn't exist."""
        self.thumbnails_folder.mkdir(parents=True, exist_ok=True)
        self.full_folder.mkdir(parents=True, exist_ok=True)
        print(f"✓ Folders ready: {self.season_folder}")

    def _load_gallery_json(self) -> Dict:
        """Load the gallery.json metadata file."""
        if not self.GALLERY_JSON.exists():
            raise FileNotFoundError(
                f"Gallery JSON not found at {self.GALLERY_JSON}. "
                "Please ensure the file exists."
            )

        with open(self.GALLERY_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_gallery_json(self):
        """Save updated gallery data back to JSON file."""
        with open(self.GALLERY_JSON, 'w', encoding='utf-8') as f:
            json.dump(self.gallery_data, f, indent=2, ensure_ascii=False)
        print(f"✓ Updated {self.GALLERY_JSON}")

    def _get_next_image_number(self) -> int:
        """
        Find the next sequential image number for this season.

        Returns:
            Next available image number
        """
        season_key = str(self.season)
        if season_key not in self.gallery_data['seasons']:
            return 1

        existing_images = self.gallery_data['seasons'][season_key].get('images', [])

        if not existing_images:
            return 1

        # Extract numbers from image IDs (e.g., "s6_image_5" -> 5)
        numbers = []
        for img in existing_images:
            img_id = img.get('id', '')
            if '_image_' in img_id:
                try:
                    num = int(img_id.split('_image_')[1])
                    numbers.append(num)
                except (ValueError, IndexError):
                    continue

        return max(numbers) + 1 if numbers else 1

    def _resize_image(self, image: Image.Image, size: tuple, maintain_aspect: bool = True) -> Image.Image:
        """
        Resize image to specified dimensions.

        Args:
            image: PIL Image object
            size: Target size (width, height)
            maintain_aspect: If True, maintain aspect ratio and fit within size

        Returns:
            Resized PIL Image
        """
        if maintain_aspect:
            # Calculate aspect ratio
            image.thumbnail(size, Image.Resampling.LANCZOS)

            # Create new image with exact dimensions (center the thumbnail)
            new_image = Image.new('RGB', size, (255, 255, 255))
            paste_x = (size[0] - image.width) // 2
            paste_y = (size[1] - image.height) // 2
            new_image.paste(image, (paste_x, paste_y))
            return new_image
        else:
            return image.resize(size, Image.Resampling.LANCZOS)

    def _process_image(self, input_path: Path, image_number: int,
                      alt: str = "", caption: str = "", match: str = "",
                      date: str = "", tags: List[str] = None,
                      players: List[str] = None) -> Dict:
        """
        Process a single image: resize, convert to WebP, save, and create metadata.

        Args:
            input_path: Path to input image
            image_number: Sequential number for this image
            alt: Alt text for accessibility
            caption: Image caption
            match: Match/game description
            date: Date of the photo
            tags: List of tags
            players: List of player names

        Returns:
            Metadata dictionary for this image
        """
        try:
            # Open and convert to RGB
            with Image.open(input_path) as img:
                # Convert to RGB if needed (handles RGBA, grayscale, etc.)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Generate filenames
                image_id = f"s{self.season}_image_{image_number}"
                filename = f"{image_id}.webp"

                # Process thumbnail
                thumbnail_img = self._resize_image(img.copy(), self.THUMBNAIL_SIZE)
                thumbnail_path = self.thumbnails_folder / filename
                thumbnail_img.save(
                    thumbnail_path,
                    'WEBP',
                    quality=self.WEBP_QUALITY_THUMBNAIL,
                    method=6  # Maximum compression effort
                )

                # Process full size
                full_img = self._resize_image(img.copy(), self.FULL_SIZE)
                full_path = self.full_folder / filename
                full_img.save(
                    full_path,
                    'WEBP',
                    quality=self.WEBP_QUALITY_FULL,
                    method=6
                )

                # Get file sizes for reporting
                thumb_size_kb = thumbnail_path.stat().st_size / 1024
                full_size_kb = full_path.stat().st_size / 1024

                print(f"  ✓ {input_path.name} -> {filename}")
                print(f"    Thumbnail: {thumb_size_kb:.1f}KB | Full: {full_size_kb:.1f}KB")

                # Create metadata entry
                return {
                    "id": image_id,
                    "thumbnail": f"/static/Images/Gallery/Season{self.season}/thumbnails/{filename}",
                    "full": f"/static/Images/Gallery/Season{self.season}/original/{filename}",
                    "alt": alt or f"Season {self.season} image {image_number}",
                    "caption": caption,
                    "match": match,
                    "date": date,
                    "tags": tags or [],
                    "players": players or []
                }

        except Exception as e:
            print(f"  ✗ Error processing {input_path.name}: {e}")
            return None

    def import_images(self, input_folder: str,
                     alt: str = "", caption: str = "", match: str = "",
                     date: str = "", tags: List[str] = None,
                     players: List[str] = None) -> int:
        """
        Import all images from the specified folder.

        Args:
            input_folder: Path to folder containing images to import
            alt: Default alt text for all images
            caption: Default caption for all images
            match: Match/game description
            date: Date of photos
            tags: List of tags to apply to all images
            players: List of players in all images

        Returns:
            Number of images successfully imported
        """
        input_path = Path(input_folder)

        if not input_path.exists():
            print(f"✗ Error: Input folder not found: {input_folder}")
            return 0

        # Find all image files
        image_files = [
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS
        ]

        if not image_files:
            print(f"✗ No supported image files found in {input_folder}")
            print(f"  Supported formats: {', '.join(self.SUPPORTED_FORMATS)}")
            return 0

        print(f"\nFound {len(image_files)} image(s) to process")
        print(f"Season: {self.season}")
        print(f"Output: {self.season_folder}")
        print()

        # Get starting number
        next_number = self._get_next_image_number()

        # Process each image
        imported_count = 0
        new_metadata = []

        for idx, image_file in enumerate(sorted(image_files)):
            image_number = next_number + idx
            metadata = self._process_image(
                image_file,
                image_number,
                alt=alt,
                caption=caption,
                match=match,
                date=date,
                tags=tags,
                players=players
            )

            if metadata:
                new_metadata.append(metadata)
                imported_count += 1

        # Update gallery.json
        if new_metadata:
            season_key = str(self.season)
            if season_key not in self.gallery_data['seasons']:
                print(f"✗ Error: Season {self.season} not found in gallery.json")
                return 0

            if 'images' not in self.gallery_data['seasons'][season_key]:
                self.gallery_data['seasons'][season_key]['images'] = []

            self.gallery_data['seasons'][season_key]['images'].extend(new_metadata)
            self._save_gallery_json()

        print(f"\n✓ Successfully imported {imported_count} image(s)")
        return imported_count


def main():
    """Command-line interface for the gallery importer."""
    parser = argparse.ArgumentParser(
        description='Import images to IFL gallery system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import images from "New Photos" folder for Season 6
  python gallery_import.py -s 6 -i "New Photos"

  # Import with metadata
  python gallery_import.py -s 6 -i "New Photos" \\
      --caption "Championship Game" \\
      --match "Finals: BingChillin vs Team Munch" \\
      --date "2024-12-15" \\
      --tags "championship,finals,season6"
        """
    )

    parser.add_argument(
        '-s', '--season',
        type=int,
        required=True,
        help='Season number (e.g., 6 for Season 6)'
    )

    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input folder containing images to import'
    )

    parser.add_argument(
        '--alt',
        type=str,
        default='',
        help='Alt text for accessibility (optional)'
    )

    parser.add_argument(
        '--caption',
        type=str,
        default='',
        help='Caption for images (optional)'
    )

    parser.add_argument(
        '--match',
        type=str,
        default='',
        help='Match/game description (optional)'
    )

    parser.add_argument(
        '--date',
        type=str,
        default='',
        help='Date of photos in YYYY-MM-DD format (optional)'
    )

    parser.add_argument(
        '--tags',
        type=str,
        default='',
        help='Comma-separated list of tags (optional)'
    )

    parser.add_argument(
        '--players',
        type=str,
        default='',
        help='Comma-separated list of player names (optional)'
    )

    args = parser.parse_args()

    # Parse tags and players
    tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else []
    players = [p.strip() for p in args.players.split(',') if p.strip()] if args.players else []

    try:
        # Create importer and process images
        importer = GalleryImporter(args.season)
        importer.import_images(
            args.input,
            alt=args.alt,
            caption=args.caption,
            match=args.match,
            date=args.date,
            tags=tags,
            players=players
        )

    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
