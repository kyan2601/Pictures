import os
import shutil
from typing import Any

import cv2
import numpy as np
from enum import Enum
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from pillow_heif import register_heif_opener

from src import helper, constants
from src.classes import media_class_factory
from src.classes.entities.PictureEntry import PictureEntry

register_heif_opener()


class DuplicateImageCheck:
    """
    A class to find and handle duplicate images in a directory using a 3-tier classification system.
    Tiers:
    1. pHash: Groups visually similar images.
    2. Pixel Hash: Identifies byte-for-byte identical images within a pHash group.
    3. SSIM: Identifies visually identical (but not byte-for-byte identical) images.
    """

    PHASH_DISTANCE_THRESHOLD = 8
    SSIM_IDENTICAL_THRESHOLD = 0.99

    # Scoring weights
    WEIGHT_MEGAPIXELS = 1.0
    WEIGHT_SHARPNESS = 0.002
    WEIGHT_FILESIZE_DEFAULT = 0.2
    WEIGHT_FILESIZE_HEIC = 0.1

    class SimilarityTiers(Enum):
        SIMILAR = 1
        IDENTICAL = 2
        EXACT = 3

    def __init__(self, directory_path: str):
        if not os.path.isdir(directory_path):
            raise ValueError(f"Directory not found: {directory_path}")
        self.directory_path = directory_path
        self.picture_entries = {}

    def _get_media_entry(self, filepath: str) -> PictureEntry:
        """Gets or creates a MediaEntry for a given filepath."""
        if filepath not in self.picture_entries:
            self.picture_entries[filepath] = media_class_factory.create_media_entry(filepath)
        return self.picture_entries[filepath]

    def _get_phash(self, filepath: str) -> str:
        """Gets pHash from metadata."""
        entry = self._get_media_entry(filepath)
        if entry.phash and isinstance(entry.phash, str):
            return entry.phash
        else:
            raise RuntimeError(f"phash could not be found for: {filepath}. All images are expected to have phashes.")

    @staticmethod
    def _phash_distance(h1: str, h2: str) -> int:
        """Calculates the bit difference between two pHash hex strings."""
        return (int(h1, 16) ^ int(h2, 16)).bit_count()

    def _get_norm_pixel_hash(self, filepath: str) -> str:
        """Gets normalized pixel hash from metadata."""
        entry = self._get_media_entry(filepath)
        if entry.norm_pixel_hash and isinstance(entry.norm_pixel_hash, str):
            return entry.norm_pixel_hash
        else:
            raise RuntimeError(f"Normalized pixel hash could not be found for: {filepath}. All images are expected to have pixel hashes.")

    @staticmethod
    def _compute_sharpness(filepath: str) -> float:
        """Computes the sharpness of an image using the Laplacian variance."""
        with Image.open(filepath) as img:
            img = img.convert("RGB")
            arr = np.array(img)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            return cv2.Laplacian(gray, cv2.CV_64F).var()

    def _compute_quality_score(self, filepath: str) -> float:
        """Calculates a quality score for an image to find the 'best' duplicate."""
        entry = self._get_media_entry(filepath)
        width, height = entry.width, entry.height
        if not width or not height:
            with Image.open(filepath) as img:
                width, height = img.size
        
        megapixels = (width * height) / 1_000_000
        filesize = os.path.getsize(filepath)
        sharpness = self._compute_sharpness(filepath)
        bpp = filesize / max(1, width * height)

        ext = helper.decompose_filepath(filepath)['ext'].lower()
        filesize_weight = self.WEIGHT_FILESIZE_HEIC if ext in ('.heic', '.heif') else self.WEIGHT_FILESIZE_DEFAULT

        return (
            self.WEIGHT_MEGAPIXELS * megapixels +
            self.WEIGHT_SHARPNESS * sharpness +
            filesize_weight * bpp
        )

    @staticmethod
    def _ssim_score(path1: str, path2: str) -> float:
        """Computes the Structural Similarity Index (SSIM) between two images."""
        with Image.open(path1) as img1, Image.open(path2) as img2:
            img1 = img1.convert("L")
            img2 = img2.convert("L")
            
            if img1.size != img2.size:
                img2 = img2.resize(img1.size, Image.Resampling.BICUBIC)

            a1 = np.array(img1)
            a2 = np.array(img2)

            score, _ = ssim(a1, a2, full=True)
            return score

    def _find_image_files(self) -> list[str]:
        """Finds all image files in the directory."""
        image_files = []
        for root, _, files in os.walk(self.directory_path):
            for f in files:
                if os.path.splitext(f.lower())[1].replace('.', '') in constants.PICTURE_EXTENSIONS:
                    image_files.append(os.path.join(root, f))
        return image_files

    def _group_by_phash(self, images: list[str]) -> list[list[str]]:
        """Groups images based on pHash similarity."""
        hashes = {}
        for p in images:
            try:
                hashes[p] = self._get_phash(p)
            except Exception as e:
                print(f"Warning: Could not process {p}: {e}")
                continue

        groups = []
        used = set()
        items = list(hashes.items())

        for i, (p1, h1) in enumerate(items):
            if p1 in used:
                continue

            group = [p1]
            used.add(p1)

            for p2, h2 in items[i + 1:]:
                if p2 in used:
                    continue
                if self._phash_distance(h1, h2) <= self.PHASH_DISTANCE_THRESHOLD:
                    group.append(p2)
                    used.add(p2)

            if len(group) > 1:
                groups.append(group)

        return groups

    def _process_group(self, group: list[str]) -> list[tuple[SimilarityTiers, Any]]:
        """Processes a pHash group to find EXACT, IDENTICAL, and SIMILAR matches."""
        # Tier 2: Pixel Hash for exact matches
        pixel_map = {}
        for p in group:
            try:
                h = self._get_norm_pixel_hash(p)
                pixel_map.setdefault(h, []).append(p)
            except Exception as e:
                print(f"Warning: Could not compute pixel hash for {p}: {e}")

        exact_matches = [paths for paths in pixel_map.values() if len(paths) > 1]
        remaining_for_ssim = [paths[0] for paths in pixel_map.values() if len(paths) == 1]
        
        categorized = [(self.SimilarityTiers.EXACT, paths) for paths in exact_matches]

        # Tier 3: SSIM for visually identical matches
        used = set()
        for i, p1 in enumerate(remaining_for_ssim):
            if p1 in used:
                continue
            
            identical_cluster = [p1]
            used.add(p1)

            for j in range(i + 1, len(remaining_for_ssim)):
                p2 = remaining_for_ssim[j]
                if p2 in used:
                    continue
                
                try:
                    if self._ssim_score(p1, p2) >= self.SSIM_IDENTICAL_THRESHOLD:
                        identical_cluster.append(p2)
                        used.add(p2)
                except Exception as e:
                    print(f"Warning: Could not compute SSIM between {p1} and {p2}: {e}")

            if len(identical_cluster) > 1:
                categorized.append((self.SimilarityTiers.IDENTICAL, identical_cluster))
            else:
                # The leftover single images from the original pHash group are just 'similar'
                pass
        
        # Consolidate all "similar" images that were not exact or identical
        all_categorized_files = {p for _, paths in categorized for p in paths}
        similar_images = [p for p in group if p not in all_categorized_files]
        if similar_images:
            categorized.append((self.SimilarityTiers.SIMILAR, similar_images))
             
        return categorized

    def _handle_groups(self, groups: list[list[str]], dry_run: bool):
        """Processes categorized groups to select the best image and optionally remove others."""
        all_categorized_subgroups = []
        for group in groups:
            categorized_subgroups = self._process_group(group)
            all_categorized_subgroups.extend(categorized_subgroups)

        # Sort by similarity tier, highest value first
        all_categorized_subgroups.sort(key=lambda item: item[0].value, reverse=True)

        total_groups = len(all_categorized_subgroups)
        for i, (tag, imgs) in enumerate(all_categorized_subgroups):
            if len(imgs) <= 1:
                continue

            if tag in [self.SimilarityTiers.EXACT, self.SimilarityTiers.IDENTICAL]:
                scores = {p: self._compute_quality_score(p) for p in imgs}
                best_image = max(scores, key=scores.get)

                print(f"\nGROUP {i+1}: [Tier {tag.value} - {tag.name} DUPLICATES]")
                for p, s in sorted(scores.items(), key=lambda item: item[1], reverse=True):
                    action = "KEEP" if p == best_image else "REMOVE"
                    print(f"  [{action}] {p} (Score: {s:.2f})")

                if not dry_run:
                    backup_dir = helper.create_backup_directory("remove_duplicate_images")
                    for p in imgs:
                        if p != best_image:
                            try:
                                print(f"Moving {p} to {backup_dir}")
                                shutil.move(p, backup_dir)
                            except (OSError, shutil.Error) as e:
                                print(f"Error moving file {p}: {e}")

            elif tag in [self.SimilarityTiers.SIMILAR]:
                print(f"\nGROUP {i+1}: [Tier {tag.value} - {tag.name} IMAGES] - should manually review")
                for img in imgs:
                    print(f"  - {img}")

            else:
                raise ValueError(f"Unrecognized tag: {tag}")

    def run(self, dry_run: bool = True):
        """
        Executes the duplicate image checking process.
        :param dry_run: If True, no files will be deleted. Defaults to True.
        """
        print("Finding image files...")
        image_files = self._find_image_files()
        print(f"Found {len(image_files)} image files.")

        if not image_files:
            print("No image files to process.")
            return

        print("Grouping images by perceptual hash (pHash)...")
        phash_groups = self._group_by_phash(image_files)
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


if __name__ == '__main__':
    image_dir = helper.get_directory_for_year_month(2025, 10)
    checker = DuplicateImageCheck(image_dir)
    checker.run(dry_run=True)
