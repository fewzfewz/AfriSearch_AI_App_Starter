"""Recover an orphaned workspace from the System Recovery Organization to a real organization.

Usage:
    python -m backend.recover_workspace --workspace <workspace_id> --target-org <org_id>
"""
import argparse
import sys

from backend import db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Workspace ID to recover")
    parser.add_argument("--target-org", required=True, help="Target Organization ID")
    args = parser.parse_args()

    try:
        db.recover_workspace(args.workspace, args.target_org)
        print(f"Successfully recovered workspace {args.workspace} to organization {args.target_org}")
    except Exception as exc:
        sys.exit(f"Recovery failed: {exc}")


if __name__ == "__main__":
    main()
