"""Set this checkout's virtual environment to use the shared bytecode folder."""

from pathlib import Path
import sys
import sysconfig


def main():
    root = Path(__file__).resolve().parents[1]
    if Path(sys.prefix).resolve() != (root / '.venv').resolve():
        raise SystemExit('Run this with the repository virtual environment: uv run python scripts/configure_python_cache.py')

    cache = root / 'agent_cache'
    config = Path(sysconfig.get_path('purelib')) / '00_repository_bytecode_cache.pth'
    config.write_text(
        f'import sys; sys.pycache_prefix = sys.pycache_prefix or {ascii(str(cache))}\n',
        encoding='ascii',
    )
    print(f'New Python processes in .venv will write bytecode under {cache}')


if __name__ == '__main__':
    main()
