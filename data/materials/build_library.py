"""
data/materials/build_library.py
-------------------------------
Turn FreeCAD .FCMat cards into the JSON this repo ships.

Run it against a local checkout (or a directory of downloaded cards); it does
not fetch anything itself, so a rebuild is reproducible from files you can
diff. All of the conversion and every refusal rule lives in
core/material_library.py -- this script only walks files, applies the licence
filter and writes the results, so that what ships is provably the output of the
code the tests exercise.

    python data/materials/build_library.py --cards <dir> --commit <sha>

The licence filter is a command-line argument rather than a constant because it
is a policy decision, not a fact about the data: this repo is AGPL-3.0 plus a
commercial licence, and content it cannot sublicense cannot go in. See
data/materials/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.material_library import (  # noqa: E402, I001
    CARD_DIR,
    MaterialLibraryError,
    card_from_fcmat,
)

# Attribution-only licences: redistribution needs a credit line and nothing
# else, which data/materials/README.md carries. Everything else upstream uses
# (LGPL-2.0/2.1-or-later, CC-BY-SA-4.0) is copyleft on the data, and this repo
# sells a commercial licence that removes copyleft obligations -- an obligation
# it has no right to remove on somebody else's cards.
DEFAULT_LICENSES = ("CC-BY-3.0", "CC-BY-4.0")

UPSTREAM_REPO = "https://github.com/FreeCAD/FreeCAD"
UPSTREAM_PREFIX = "src/Mod/Material/Resources/Materials/Standard"


def _load_yaml(path: Path) -> dict:
    # utf-8-sig: 17 of the 140 upstream cards start with a BOM, and yaml.safe_load
    # reports that as a parse error on the very first line.
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _upstream_path(path: Path, cards_dir: Path) -> str:
    """Repo-relative upstream path, from either a checkout or a flat dump."""
    name = path.name
    if "__" in name:
        return name[:-len(path.suffix)].replace("__", "/") + path.suffix
    try:
        return "%s/%s" % (UPSTREAM_PREFIX,
                          path.relative_to(cards_dir).as_posix())
    except ValueError:
        return path.name


def build(cards_dir: Path, out_dir: Path, commit: str,
          licences: tuple[str, ...], retrieved: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    examined: list[dict] = []
    written = 0

    for path in sorted(cards_dir.rglob("*.FCMat")):
        upstream = _upstream_path(path, cards_dir)
        stem = upstream.rsplit("/", 1)[-1][: -len(".FCMat")]
        category = upstream.split("/")[-2] if "/" in upstream else ""
        if category in ("Standard", "Materials"):
            category = ""

        record = {"card": stem, "path": upstream}
        try:
            document = _load_yaml(path)
        except Exception as exc:
            record.update(verdict="refused", reason="YAML 解析失败：%s" % exc)
            examined.append(record)
            continue

        licence = str((document.get("General") or {}).get("License") or "").strip()
        record["license"] = licence
        if licence not in licences:
            record.update(
                verdict="refused",
                reason="许可 %r 不在允许分发的清单 %s 里。"
                       % (licence or "(缺失)", "、".join(licences)))
            examined.append(record)
            continue

        source = {
            "project": "FreeCAD",
            "name": stem,
            "category": category,
            "path": upstream,
            "commit": commit,
            "url": "%s/blob/%s/%s" % (UPSTREAM_REPO, commit, upstream),
            "raw_url": "https://raw.githubusercontent.com/FreeCAD/FreeCAD/%s/%s"
                       % (commit, upstream),
            "retrieved": retrieved,
        }
        try:
            card = card_from_fcmat(document, source)
        except MaterialLibraryError as exc:
            record.update(verdict="refused", reason=exc.message)
            examined.append(record)
            continue

        (out_dir / ("%s.json" % stem)).write_text(
            json.dumps(card, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8")
        written += 1
        record.update(verdict="accepted", name=card["name"])
        examined.append(record)

    return {
        "schema": "abaqus_agent.material_provenance/1",
        "upstream": {
            "project": "FreeCAD",
            "repo": UPSTREAM_REPO,
            "path": UPSTREAM_PREFIX,
            "commit": commit,
            "retrieved": retrieved,
        },
        "licenses_accepted": list(licences),
        "counts": {
            "examined": len(examined),
            "accepted": written,
            "refused": len(examined) - written,
        },
        "cards": examined,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", required=True, type=Path,
                        help="directory holding .FCMat files (searched recursively)")
    parser.add_argument("--out", type=Path, default=CARD_DIR)
    parser.add_argument("--commit", required=True,
                        help="FreeCAD commit the cards were taken from")
    parser.add_argument("--retrieved", default=date.today().isoformat())
    parser.add_argument("--licenses", default=",".join(DEFAULT_LICENSES),
                        help="comma-separated licence identifiers to accept")
    args = parser.parse_args(argv)

    licences = tuple(x.strip() for x in args.licenses.split(",") if x.strip())
    report = build(args.cards, args.out, args.commit, licences, args.retrieved)

    provenance = args.out.parent / "provenance.json"
    provenance.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts = report["counts"]
    print("examined %(examined)d, accepted %(accepted)d, refused %(refused)d"
          % counts)
    for record in report["cards"]:
        if record["verdict"] == "refused" and record.get("license") in licences:
            print("  refused %-24s %s" % (record["card"], record["reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
