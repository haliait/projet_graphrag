"""Explicit, pinned downloads. Importing this module never accesses the network."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
import zipfile

from hetionet_utils import DATA, charger_graphe
from medquad_utils import preparer_passages

HETIONET_REV = "8a6cc0c5604d0e2908786e4de38af67b8e46ee4a"
MEDQUAD_REV = "577bd37b96c02d1833b2c9eed2de9f96964e96cb"
URLS = {
    "hetionet-v1.0-nodes.tsv": f"https://raw.githubusercontent.com/hetio/hetionet/{HETIONET_REV}/hetnet/tsv/hetionet-v1.0-nodes.tsv",
    "hetionet-v1.0-edges.sif.gz": f"https://media.githubusercontent.com/media/hetio/hetionet/{HETIONET_REV}/hetnet/tsv/hetionet-v1.0-edges.sif.gz",
    "MedQuAD.zip": f"https://codeload.github.com/abachaa/MedQuAD/zip/{MEDQUAD_REV}",
}


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, max_bytes=150_000_000):
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as out:
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise ValueError("Download exceeds size limit")
                out.write(block)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(DATA))
    parser.add_argument("--graph-only", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = Path(__file__).with_name("data_checksums.json")
    expected = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    records = {}
    for name, url in URLS.items():
        if args.graph_only and name.endswith(".zip"):
            continue
        path = args.data_dir / name
        if not path.exists():
            print("Downloading", name, flush=True)
            download(url, path)
        digest = sha256(path)
        if name in expected and expected[name] != digest:
            raise ValueError(f"SHA256 mismatch: {name}; remove file and retry")
        records[name] = {"url": url, "sha256": digest, "bytes": path.stat().st_size}
    graph = charger_graphe(args.data_dir)
    if not args.graph_only:
        # Never extract arbitrary archive paths. Copy XML entries under known collections only.
        from medquad_utils import COLLECTIONS
        with tempfile.TemporaryDirectory(dir=args.data_dir) as directory:
            root = Path(directory)
            with zipfile.ZipFile(args.data_dir / "MedQuAD.zip") as archive:
                total = 0
                for item in archive.infolist():
                    parts = Path(item.filename).parts
                    if len(parts) != 3 or parts[1] not in COLLECTIONS or not parts[2].endswith(".xml"):
                        continue
                    total += item.file_size
                    if total > 300_000_000 or item.file_size > 5_000_000:
                        raise ValueError("Archive exceeds size limit")
                    target = root / parts[1] / parts[2]
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(archive.read(item))
            passages = preparer_passages(str(root), str(args.data_dir / "medquad_passages.jsonl"))
            if not passages:
                raise ValueError("Empty MedQuAD corpus")
            print("Passages:", len(passages))
    manifest = {"hetionet_revision": HETIONET_REV, "medquad_revision": MEDQUAD_REV,
                "files": records, "nodes": len(graph.nom), "edges": graph.n_aretes}
    path = args.data_dir / "medquad_passages.jsonl"
    if path.exists():
        manifest["passages_sha256"] = sha256(path)
    (args.data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Nodes:", len(graph.nom), "edges:", graph.n_aretes)


if __name__ == "__main__":
    main()
