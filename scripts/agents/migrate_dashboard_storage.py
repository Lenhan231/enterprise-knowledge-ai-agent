"""Copy existing SQLite dashboards to shared Supabase storage; keep the source as a backup."""
import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Path to an existing dashboards.sqlite3 file')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    from core.dashboards.postgres_store import PostgresDashboardStore
    print(json.dumps(PostgresDashboardStore().import_sqlite(args.source)))


if __name__ == '__main__':
    main()
