import os
import cv2
import numpy as np
import hashlib
from PIL import Image
import imagehash
from skimage.metrics import structural_similarity as ssim

# ----------------------------
# NOT TESTED
# based on convo with chatgpt: https://chatgpt.com/share/69632252-0598-8009-988b-bcda58fbffb8
# 3 tier classification:
# EXACT - pixel-identical
# IDENTICAL - visually identical (SSIM)
# SIMILAR - perceptual duplicate (pHash only)
# Steps:
# 1. pHash grouping
# 2. pixel hash for identical pixels
# 3. SSIM for new-identical images
# ----------------------------


# ----------------------------
# HEIC SUPPORT
# ----------------------------
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    print("WARNING: pillow-heif not installed; HEIC files may fail")

# ----------------------------
# CONFIG
# ----------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

PHASH_DISTANCE_THRESHOLD = 8
SSIM_IDENTICAL_THRESHOLD = 0.99

DRY_RUN = True

WEIGHT_MEGAPIXELS = 1.0
WEIGHT_SHARPNESS = 0.002
WEIGHT_FILESIZE = 0.2  # down-weighted for HEIC

# ----------------------------
# BASIC UTILITIES
# ----------------------------
def is_image(path):
    return os.path.splitext(path.lower())[1] in IMAGE_EXTS


def phash_hex(path):
    with Image.open(path) as img:
        img = img.convert("RGB")
        return str(imagehash.phash(img))


def phash_distance(h1, h2):
    return (int(h1, 16) ^ int(h2, 16)).bit_count()


def pixel_hash(path):
    with Image.open(path) as img:
        img = img.convert("RGB")
        return hashlib.sha256(img.tobytes()).hexdigest(), img.size


def compute_sharpness(path):
    with Image.open(path) as img:
        img = img.convert("RGB")
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()


def compute_quality_score(path):
    with Image.open(path) as img:
        width, height = img.size
        megapixels = (width * height) / 1_000_000

    filesize = os.path.getsize(path)
    sharpness = compute_sharpness(path)
    bpp = filesize / max(1, width * height)

    ext = os.path.splitext(path)[1].lower()
    filesize_weight = 0.1 if ext in (".heic", ".heif") else WEIGHT_FILESIZE

    return (
        WEIGHT_MEGAPIXELS * megapixels
        + WEIGHT_SHARPNESS * sharpness
        + filesize_weight * bpp
    )


# ----------------------------
# SSIM (STRUCTURAL IDENTITY)
# ----------------------------
def ssim_score(path1, path2):
    with Image.open(path1) as img1, Image.open(path2) as img2:
        img1 = img1.convert("L")
        img2 = img2.convert("L")
        img2 = img2.resize(img1.size, Image.BICUBIC)

        a1 = np.array(img1)
        a2 = np.array(img2)

        score, _ = ssim(a1, a2, full=True)
        return score


# ----------------------------
# PIPELINE
# ----------------------------
def find_images(root):
    out = []
    for dp, _, files in os.walk(root):
        for f in files:
            p = os.path.join(dp, f)
            if is_image(p):
                out.append(p)
    return out


def group_by_phash(images):
    hashes = {}
    for p in images:
        try:
            hashes[p] = phash_hex(p)
        except Exception:
            continue

    groups = []
    used = set()
    items = list(hashes.items())

    for i, (p1, h1) in enumerate(items):
        if p1 in used:
            continue

        group = [p1]
        used.add(p1)

        for p2, h2 in items[i + 1 :]:
            if p2 in used:
                continue
            if phash_distance(h1, h2) <= PHASH_DISTANCE_THRESHOLD:
                group.append(p2)
                used.add(p2)

        if len(group) > 1:
            groups.append(group)

    return groups


def process_group(group):
    # Step 1: pixel identity
    pixel_map = {}
    for p in group:
        h, size = pixel_hash(p)
        pixel_map.setdefault((h, size), []).append(p)

    results = []

    for identical in pixel_map.values():
        if len(identical) == 1:
            results.append(("UNIQUE", identical))
            continue

        results.append(("EXACT", identical))

    # Step 2: SSIM on non-exact
    remaining = [p for tag, lst in results if tag == "UNIQUE" for p in lst]
    final_groups = []

    while remaining:
        base = remaining.pop(0)
        cluster = [base]

        for other in remaining[:]:
            if ssim_score(base, other) >= SSIM_IDENTICAL_THRESHOLD:
                cluster.append(other)
                remaining.remove(other)

        if len(cluster) > 1:
            final_groups.append(("IDENTICAL", cluster))
        else:
            final_groups.append(("SIMILAR", cluster))

    return results + final_groups


def handle_groups(groups):
    for group in groups:
        categorized = process_group(group)

        for tag, imgs in categorized:
            if len(imgs) == 1:
                continue

            scores = {p: compute_quality_score(p) for p in imgs}
            best = max(scores, key=scores.get)

            print(f"\n[{tag}]")
            for p, s in scores.items():
                action = "KEEP" if p == best else "REMOVE"
                print(f"  [{action}] {p}  score={s:.2f}")

            if not DRY_RUN:
                for p in imgs:
                    if p != best:
                        os.remove(p)


# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python dedupe_images.py <directory>")
        sys.exit(1)

    root = sys.argv[1]
    images = find_images(root)

    print(f"Found {len(images)} images")

    phash_groups = group_by_phash(images)
    print(f"Found {len(phash_groups)} pHash groups")

    handle_groups(phash_groups)

    if DRY_RUN:
        print("\nDRY RUN — no files deleted")
