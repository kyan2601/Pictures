"""Face detection, clustering and naming for the photo library.

Pipeline: InsightFace (face detection + ArcFace embeddings) -> greedy
centroid clustering on cosine distance -> cluster review page -> the user
names clusters -> names are applied to the `people` metadata column.

Derived data lives under <ROOT_DIR>/.faces and never touches the library:
  {year}.npz     per-face embeddings plus the set of already-scanned files
                (face keys look like "<filepath>\\x00<face_idx>")
  clusters.json {face_key: cluster_id}  (-1 means unassigned/noise)
  names.json    {cluster_id: person name}

Detection is incremental (only unscanned files are processed). Clustering
re-runs over the full face universe on every scan and carries names forward
by member overlap, so clusters stay meaningful as the library grows.
"""

import json
import os

import numpy as np
import pandas as pd

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite


FACE_DIRNAME = '.faces'
UNASSIGNED = -1
_KEY_SEP = '\x00'  # NUL cannot appear in a real filepath
_MAX_DIM = 1600  # downscale larger images before detection; bboxes are mapped back

_PICTURE_EXTENSIONS = {e.value for e in constants.PictureExtension}


def _is_picture(filepath):
    ext = str(filepath).rsplit('.', 1)[-1].lower() if '.' in str(filepath) else ''
    return ext in _PICTURE_EXTENSIONS


_app = None


def _get_app():
    """Lazily builds the InsightFace analysis app.

    Models (~300MB) download once to ~/.insightface on first use.
    """
    global _app
    if _app is None:
        try:
            from insightface.app import FaceAnalysis
        except ImportError:
            raise RuntimeError(
                'Face clustering needs the insightface package: '
                'pip install insightface onnxruntime')
        _app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _read_image_bgr(filepath):
    """Reads any picture (JPEG/PNG/HEIC) as a BGR numpy array for InsightFace.

    Returns (image, scale) where scale maps detection coordinates back to the
    original image size.
    """
    from PIL import Image
    from pillow_heif import register_heif_opener
    register_heif_opener()
    with Image.open(filepath) as img:
        img = img.convert('RGB')
        scale = min(1.0, _MAX_DIM / max(img.width, img.height))
        if scale < 1.0:
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        arr = np.asarray(img)
    import cv2
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), scale


def _faces_for_file(filepath, app):
    """Returns [(bbox, embedding, det_score)] for one file.

    bbox is in original-image coordinates.
    """
    img, scale = _read_image_bgr(filepath)
    faces = app.get(img) or []
    return [((np.asarray(f.bbox, dtype=float) / scale).tolist(),
             np.asarray(f.normed_embedding, dtype=np.float32),
             float(f.det_score))
            for f in faces]


def _face_dir():
    d = os.path.join(constants.ROOT_DIR, FACE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def _index_path(year):
    return os.path.join(_face_dir(), f'{year}.npz')


def _load_index(year):
    """Returns ({face_key: {'embedding', 'bbox', 'score'}}, {scanned filepaths})."""
    path = _index_path(year)
    if not os.path.exists(path):
        return {}, set()
    data = np.load(path, allow_pickle=True)
    keys = [str(k) for k in data['keys']]
    index = {}
    for i, key in enumerate(keys):
        index[key] = {'embedding': data['embeddings'][i],
                      'bbox': data['bboxes'][i],
                      'score': float(data['scores'][i])}
    return index, {str(fp) for fp in data['scanned']}


def _save_index(year, index, scanned):
    keys = sorted(index)
    n = len(keys)
    np.savez(_index_path(year),
             keys=np.array(keys),
             embeddings=(np.stack([np.asarray(index[k]['embedding'], dtype=np.float32)
                                   for k in keys]).astype(np.float32)
                         if n else np.zeros((0, 512), dtype=np.float32)),
             bboxes=(np.array([index[k]['bbox'] for k in keys], dtype=np.float32)
                     if n else np.zeros((0, 4), dtype=np.float32)),
             scores=(np.array([index[k]['score'] for k in keys], dtype=np.float32)
                     if n else np.zeros((0,), dtype=np.float32)),
             scanned=np.array(sorted(scanned)))


def _clusters_path():
    return os.path.join(_face_dir(), 'clusters.json')


def _names_path():
    return os.path.join(_face_dir(), 'names.json')


def _load_clusters():
    path = _clusters_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return {k: int(v) for k, v in json.load(f).items()}


def _save_clusters(assignments):
    with open(_clusters_path(), 'w', encoding='utf-8') as f:
        json.dump({k: int(v) for k, v in assignments.items()}, f)


def _load_names():
    path = _names_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return {str(k): v for k, v in json.load(f).items()}


def _save_names(names):
    with open(_names_path(), 'w', encoding='utf-8') as f:
        json.dump({str(k): v for k, v in names.items()}, f, ensure_ascii=False, indent=2)


def _greedy_cluster(embeddings, eps, min_samples):
    """Greedy centroid clustering on cosine distance.

    Single pass over the (L2-normalized) embeddings in the given order: each
    embedding joins the nearest cluster whose centroid is within `eps`,
    otherwise it starts a new cluster. Linear time and memory, at the cost of
    some order dependence (callers pass sorted keys for determinism).
    Clusters smaller than `min_samples` are labeled UNASSIGNED (-1).
    """
    n = len(embeddings)
    labels = np.full(n, -1)
    centroids = []  # [(sum_vector, count)]
    for i, emb in enumerate(embeddings):
        assigned = False
        if centroids:
            sums = np.stack([s for s, _ in centroids])
            sums = sums / np.linalg.norm(sums, axis=1, keepdims=True).clip(min=1e-9)
            dists = 1.0 - sums @ emb
            best = int(np.argmin(dists))
            if dists[best] <= eps:
                s, cnt = centroids[best]
                centroids[best] = (s + emb, cnt + 1)
                labels[i] = best
                assigned = True
        if not assigned:
            centroids.append((emb.copy(), 1))
            labels[i] = len(centroids) - 1

    counts = np.bincount(labels[labels >= 0].astype(int), minlength=len(centroids))
    keep = sorted(c for c in range(len(centroids)) if counts[c] >= min_samples)
    remap = {old: new for new, old in enumerate(keep)}
    out = np.full(n, UNASSIGNED)
    for i in range(n):
        if labels[i] >= 0 and int(labels[i]) in remap:
            out[i] = remap[int(labels[i])]
    return out


def _carry_names(old_assignments, old_names, new_assignments):
    """Carries person names to new cluster ids by member overlap.

    A new cluster inherits the name of the old cluster contributing the
    largest share of its members, provided that share exceeds 50%.
    """
    old_members = {}
    for key, cid in old_assignments.items():
        if cid != UNASSIGNED:
            old_members.setdefault(cid, set()).add(key)
    new_members = {}
    for key, cid in new_assignments.items():
        if cid != UNASSIGNED:
            new_members.setdefault(cid, set()).add(key)

    carried = {}
    for new_cid, nmembers in new_members.items():
        best_name, best_overlap = None, 0.5
        for old_cid, omembers in old_members.items():
            name = old_names.get(str(old_cid))
            if not name:
                continue
            overlap = len(nmembers & omembers) / len(nmembers)
            if overlap > best_overlap:
                best_name, best_overlap = name, overlap
        if best_name is not None:
            carried[str(new_cid)] = best_name
    return carried


class FaceClustering:

    def _index_year(self, year, app):
        df = MetadataFile.get_instance(year).df
        if df is None or df.empty:
            return 0
        index, scanned = _load_index(year)
        candidates = [fp for fp in df['filepath']
                      if isinstance(fp, str) and fp not in scanned
                      and _is_picture(fp) and os.path.exists(fp)]
        for i, fp in enumerate(candidates):
            if i % 100 == 0:
                print(f'  [{year}] detecting faces ({i}/{len(candidates)})...')
            try:
                faces = _faces_for_file(fp, app)
            except Exception as e:
                print(f'  [skip] {fp}: {e}')
                faces = []
            scanned.add(fp)
            for j, (bbox, emb, score) in enumerate(faces):
                index[f'{fp}{_KEY_SEP}{j}'] = {
                    'embedding': emb, 'bbox': bbox, 'score': score}
        _save_index(year, index, scanned)
        return len(candidates)

    def _cluster_all(self, eps, min_samples):
        keys, embs = [], []
        for year in helper.get_years():
            index, _ = _load_index(year)
            for key in sorted(index):
                keys.append(key)
                embs.append(index[key]['embedding'])
        if not keys:
            return {'n_faces': 0, 'n_clusters': 0, 'n_named': 0, 'n_unassigned': 0}

        X = np.stack([np.asarray(e, dtype=np.float32) for e in embs])
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X = X / norms

        old_assignments = _load_clusters()
        old_names = _load_names()
        labels = _greedy_cluster(X, eps=eps, min_samples=min_samples)
        assignments = {key: int(label) for key, label in zip(keys, labels)}
        _save_clusters(assignments)
        if old_names:
            _save_names(_carry_names(old_assignments, old_names, assignments))

        names = _load_names()
        live = {c for c in assignments.values() if c != UNASSIGNED}
        return {
            'n_faces': len(keys),
            'n_clusters': len(live),
            'n_named': sum(1 for c in live if str(c) in names),
            'n_unassigned': sum(1 for c in assignments.values() if c == UNASSIGNED),
        }

    def scan(self, years=None, eps=0.5, min_samples=2, build_review=True):
        """Detects faces (incrementally) and re-clusters the full face universe."""
        years = years if years else helper.get_years()
        app = _get_app()
        for year in years:
            n = self._index_year(year, app)
            print(f'[{year}] scanned {n} new file(s).')
        summary = self._cluster_all(eps=eps, min_samples=min_samples)
        print(f"Faces: {summary['n_faces']}, clusters: {summary['n_clusters']} "
              f"({summary['n_named']} named), unassigned: {summary['n_unassigned']}.")
        if build_review:
            page = self.build_review_page()
            print(f'Review page: {page}')
        return summary

    def status(self):
        for year in helper.get_years():
            index, scanned = _load_index(year)
            print(f'{year}: {len(scanned)} file(s) scanned, {len(index)} face(s).')
        assignments = _load_clusters()
        names = _load_names()
        live = sorted({c for c in assignments.values() if c != UNASSIGNED})
        print(f'{len(live)} cluster(s), '
              f'{sum(1 for c in live if str(c) in names)} named, '
              f'{sum(1 for c in assignments.values() if c == UNASSIGNED)} unassigned face(s).')
        for cid in live:
            size = sum(1 for c in assignments.values() if c == cid)
            label = names.get(str(cid), '(unnamed)')
            print(f'  cluster {cid}: {size} face(s) — {label}')

    def name_cluster(self, cluster_id, name):
        names = _load_names()
        names[str(int(cluster_id))] = name.strip()
        _save_names(names)
        print(f'Cluster {cluster_id} named "{name.strip()}".')

    def apply_names(self, dry_run=True):
        """Appends named clusters' person names to the `people` metadata column."""
        names = _load_names()
        assignments = _load_clusters()
        if not names:
            print('No named clusters yet. Name one with: '
                  'python -m src.cli faces name --cluster N --name "..."')
            return

        cluster_files = {}
        for key, cid in assignments.items():
            name = names.get(str(cid))
            if name:
                cluster_files.setdefault(cid, set()).add(key.split(_KEY_SEP)[0])

        files_by_year = {}
        for cid in sorted(cluster_files):
            for fp in sorted(cluster_files[cid]):
                files_by_year.setdefault(
                    helper.get_year_from_filepath(fp), []).append((fp, names[str(cid)]))

        if dry_run:
            print('[dry run] Would append names to the people column:')
        for year in sorted(files_by_year):
            metadata_file = MetadataFile.get_instance(year)
            changed = []
            for fp, name in files_by_year[year]:
                if not metadata_file.has_media_metadata(fp):
                    print(f'  [skip] no metadata record for {fp}')
                    continue
                record = metadata_file.get_media_metadata(fp)
                existing = [] if pd.isna(record.get('people')) else [
                    p.strip() for p in str(record['people']).split(';') if p.strip()]
                if name.lower() in {p.lower() for p in existing}:
                    continue
                record['people'] = ';'.join(existing + [name])
                changed.append((fp, name, record))
            if not changed:
                continue
            if dry_run:
                print(f'  {year}/metadata.csv: {len(changed)} record(s)')
                for fp, name, _ in changed[:10]:
                    print(f'    {os.path.basename(fp)}: +{name}')
                if len(changed) > 10:
                    print(f'    ... and {len(changed) - 10} more')
            else:
                for _, _, record in changed:
                    metadata_file.add_media_metadata(record, update=True, write=False)
                metadata_file.write()
                print(f'Updated {len(changed)} record(s) in {year}/metadata.csv.')

    def build_review_page(self, max_per_cluster=12):
        """One section per cluster with sample photos; unassigned faces last."""
        assignments = _load_clusters()
        names = _load_names()
        clusters = {}
        for key, cid in assignments.items():
            clusters.setdefault(cid, []).append(key)

        def sort_key(cid):
            if cid == UNASSIGNED:
                return (2, 0)
            return (0 if str(cid) in names else 1, -len(clusters[cid]))

        sections = []
        for cid in sorted(clusters, key=sort_key):
            keys = clusters[cid]
            seen, filepaths = set(), []
            for key in keys:
                fp = key.split(_KEY_SEP)[0]
                if fp not in seen:
                    seen.add(fp)
                    filepaths.append(fp)
            heading = names.get(str(cid), f'Cluster {cid}' if cid != UNASSIGNED else 'Unassigned')
            note = f'{len(keys)} face(s)'
            if cid != UNASSIGNED:
                note += (f' — name it: python -m src.cli faces name '
                         f'--cluster {cid} --name "..."')
            else:
                note += ' — not grouped with anyone'
            sections.append({
                'heading': heading,
                'note': note,
                'items': [{'filepath': fp} for fp in filepaths[:max_per_cluster]],
            })

        page_path = GallerySite(constants.REVIEW_DIR).add_page(
            'face-clusters', 'clusters', 'Face clusters', sections)
        return page_path
