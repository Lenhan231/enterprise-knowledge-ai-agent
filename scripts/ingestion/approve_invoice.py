"""Publish one reviewed extraction; DATABASE_URL must be an administrative writer."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.database.invoice_repository import InvoiceRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('invoice_id', help='Extraction ID whose fields you have reviewed')
    args = parser.parse_args()
    repository = InvoiceRepository()
    try:
        count = repository.approve(args.invoice_id)
        print(f'Published invoice {args.invoice_id} with {count} items.')
    finally:
        repository.close()


if __name__ == '__main__':
    main()
