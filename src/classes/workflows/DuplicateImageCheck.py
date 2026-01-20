import math
import os
import shutil
from typing import Any

from enum import Enum
from PIL import Image
from pillow_heif import register_heif_opener

from src import helper, constants
from src.classes import media_class_factory
from src.classes.entities.PictureEntry import PictureEntry

register_heif_opener()


class DuplicateImageCheck:
    """
    A class to find and handle duplicate images in a directory using a 2-tier classification system.
    Tiers:
    1. pHash: Groups visually similar images.
    2. dHash: Identifies duplicate images within a pHash group.
    """

    PHASH_DISTANCE_THRESHOLD = 8
    DHASH_DISTANCE_THRESHOLD = 5

    # Scoring weights
    WEIGHT_MEGAPIXELS = 1.0
    WEIGHT_SHARPNESS = 0.002
    WEIGHT_FILESIZE_DEFAULT = 0.2
    WEIGHT_FILESIZE_HEIC = 0.1

    class SimilarityTiers(Enum):
        SIMILAR = 1
        DUPLICATE = 2

    def __init__(self, directory_path: str):
        if not os.path.isdir(directory_path):
            raise ValueError(f"Directory not found: {directory_path}")
        self.directory_path = directory_path
        self.picture_entries: dict[str, PictureEntry] = {}

    @staticmethod
    def _hash_distance(h1: str, h2: str) -> int:
        """Calculates the bit difference between two hash hex strings."""
        return (int(h1, 16) ^ int(h2, 16)).bit_count()

    def _compute_quality_score(self, filepath: str) -> float:
        """Calculates a quality score for an image to find the 'best' duplicate."""
        entry = self.picture_entries[filepath]
        width, height = entry.width, entry.height
        if not width or not height:
            with Image.open(filepath) as img:
                width, height = img.size
        
        megapixels = (width * height) / 1_000_000
        filesize = os.path.getsize(filepath)
        bpp = filesize / max(1, width * height)

        ext = helper.decompose_filepath(filepath)['ext'].lower()
        filesize_weight = self.WEIGHT_FILESIZE_HEIC if ext in ('.heic', '.heif') else self.WEIGHT_FILESIZE_DEFAULT

        return round(self.WEIGHT_MEGAPIXELS * megapixels + filesize_weight * bpp, 2)

    def _load_picture_entries(self):
        """
        Finds all image files in the directory, creates PictureEntry objects,
        and validates that they have phash and dhash values.
        """
        print("Loading picture entries...")
        filepaths = helper.get_filepaths_by_directory(self.directory_path)

        for filepath in filepaths:
            ext = helper.decompose_filepath(filepath)['ext']
            if ext in constants.PICTURE_EXTENSIONS:
                entry = media_class_factory.create_media_entry(filepath)
                if not isinstance(entry, PictureEntry):
                    continue

                if not entry.phash or not isinstance(entry.phash, str):
                    raise RuntimeError(
                        f"phash could not be found for: {filepath}. All images are expected to have phashes.")
                if not entry.dhash or not isinstance(entry.dhash, str):
                    raise RuntimeError(
                        f"dhash could not be found for: {filepath}. All images are expected to have dhashes.")

                self.picture_entries[filepath] = entry
        print(f"Loaded {len(self.picture_entries)} picture entries.")

    def _group_by_phash(self) -> list[list[str]]:
        """Groups images based on pHash similarity."""
        phashes = {filepath: entry.phash for filepath, entry in self.picture_entries.items()}

        groups = []
        used = set()
        items = list(phashes.items())

        for i, (p1, h1) in enumerate(items):
            if p1 in used:
                continue

            group = [p1]
            used.add(p1)

            for p2, h2 in items[i + 1:]:
                if p2 in used:
                    continue
                if self._hash_distance(h1, h2) <= self.PHASH_DISTANCE_THRESHOLD:
                    group.append(p2)
                    used.add(p2)

            if len(group) > 1:
                groups.append(group)

        return groups

    def _process_group(self, group: list[str]) -> list[tuple[SimilarityTiers, Any]]:
        """Processes a pHash group to find DUPLICATE and SIMILAR matches."""
        # Tier 2: dHash for duplicate matches using a distance threshold
        dhashes = {p: self.picture_entries[p].dhash for p in group}

        sub_groups = []
        used = set()
        items = list(dhashes.items())

        for i, (p1, h1) in enumerate(items):
            if p1 in used:
                continue

            sub_group = [p1]
            used.add(p1)

            for p2, h2 in items[i + 1:]:
                if p2 in used:
                    continue
                if self._hash_distance(h1, h2) <= self.DHASH_DISTANCE_THRESHOLD:
                    sub_group.append(p2)
                    used.add(p2)
            
            if len(sub_group) > 1:
                sub_groups.append(sub_group)
        
        categorized = [(self.SimilarityTiers.DUPLICATE, paths) for paths in sub_groups]
        
        # Consolidate all "similar" images that were not duplicates
        all_categorized_files = {p for _, paths in categorized for p in paths}
        similar_images = [p for p in group if p not in all_categorized_files]
        if len(similar_images) > 1:
            categorized.append((self.SimilarityTiers.SIMILAR, similar_images))
             
        return categorized
    
    def _handle_groups(self, groups: list[list[str]], dry_run: bool):
        """Processes categorized groups to select the best image and optionally remove others."""
        all_categorized_subgroups = []
        for group in groups:
            categorized_subgroups = self._process_group(group)
            all_categorized_subgroups.extend(categorized_subgroups)

        if len(all_categorized_subgroups) > 0:
            print(f"Found {len(all_categorized_subgroups)} groups based on dHash.")
        else:
            print("No groups found based on dHash.")
            return

        backup_dir = ""
        if not dry_run:
            backup_dir = helper.create_backup_directory("remove_duplicate_images")

        # Sort by similarity tier, highest value first
        all_categorized_subgroups.sort(key=lambda item: item[0].value, reverse=True)

        for i, (tag, imgs) in enumerate(all_categorized_subgroups):
            if tag in [self.SimilarityTiers.DUPLICATE]:
                scores = {p: self._compute_quality_score(p) for p in imgs}
                max_score = max(scores.values())
                best_images = [p for p, s in scores.items() if math.isclose(s, max_score)]
                actions = {}

                print(f"\nGROUP {i + 1}: [Tier {tag.value} - {tag.name} IMAGES]")
                for p, s in sorted(scores.items(), key=lambda item: item[1], reverse=True):
                    action = ""
                    if len(best_images) > 1:
                        action = "UNSURE"
                    elif len(best_images) == 1 and p == best_images[0]:
                        action = "KEEP"
                    elif len(best_images) == 1 and p != best_images[0]:
                        action = "REMOVE"
                    elif len(best_images) == 0:
                        raise RuntimeError(f"Could not identify best image for group {scores}")
                    else:
                        raise RuntimeError(f"Not possible, shouldn't logically be able to get here")
                    actions[p] = action
                    print(f"  [{action}] {p} (Score: {s:.2f})")

                if not dry_run and "REMOVE" in actions.values():
                    for p, action in actions.items():
                        if action == "REMOVE":
                            try:
                                print(f"Moving {p} to {backup_dir}")
                                shutil.move(p, backup_dir)
                            except (OSError, shutil.Error) as e:
                                print(f"Error moving file {p}: {e}")

            elif tag in [self.SimilarityTiers.SIMILAR]:
                print(f"\nGROUP {i + 1}: [Tier {tag.value} - {tag.name} IMAGES] - should manually review")
                for img in imgs:
                    print(f"  - {img}")

            else:
                raise ValueError(f"Unrecognized tag: {tag}")

    def run(self, dry_run: bool = True):
        """
        Executes the duplicate image checking process.
        :param dry_run: If True, no files will be deleted. Defaults to True.
        """
        self._load_picture_entries()

        if not self.picture_entries:
            print("No image files to process.")
            return

        print("Grouping images by perceptual hash (pHash)...")
        phash_groups = self._group_by_phash()
        print(f"Found {len(phash_groups)} potential duplicate groups based on pHash.")

        if not phash_groups:
            print("No potential duplicates found.")
            return
            
        print("Processing groups to find exact and identical matches...")
        self._handle_groups(phash_groups, dry_run=dry_run)

        if dry_run:
            print("\nDRY RUN COMPLETE. No files were deleted.")
        else:
            print("\nDuplicate removal complete.")
            print("\nIMPORTANT: Please double check and run MetadataCleanupChecks to update metadata!")


if __name__ == '__main__':
    image_dir = helper.get_directory_for_year_month(2025, 10)
    DuplicateImageCheck(image_dir).run(dry_run=True)
