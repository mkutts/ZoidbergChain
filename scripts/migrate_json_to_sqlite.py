from pathlib import Path
import sys


def main():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from storage_migration import main as migration_main

    return migration_main()


if __name__ == "__main__":
    raise SystemExit(main())
