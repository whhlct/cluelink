import json
from dataclasses import asdict
from pathlib import Path

from ingest.tmdb import TMDBClient


def main():
    page = TMDBClient().discover_movie({"sort_by": "popularity.desc"})
    output_path = Path(__file__).resolve().parents[1] / "data" / "tmdb_discover_movies.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(page), default=str, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Saved {len(page.results)} movies to {output_path}")


if __name__ == "__main__":
    main()
