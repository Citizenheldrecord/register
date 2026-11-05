#!/usr/bin/env python3
"""Run all prevention self-tests and a warn-mode sweep (Barry go t2909u)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKS = [
    "check_quote_on_page.py",
    "check_date_provenance.py",
    "check_source_type.py",
    "check_status_derived.py",
    "check_owner_numbers.py",
    "check_allowlist_rundown.py",
    "check_archive_sources.py",
    "monthly_register_audit.py",
]


def main():
    rc = 0
    print("== prevention self-tests ==")
    for name in CHECKS:
        p = subprocess.run([sys.executable, str(HERE / name), "--selftest"], cwd=str(HERE.parents[1]))
        if p.returncode != 0:
            rc = 1
            print("SELFTEST FAIL", name)
    print("== prevention warn sweep ==")
    sweeps = [
        ("check_date_provenance.py", ["--mode", "warn"]),
        ("check_source_type.py", ["--mode", "warn"]),
        ("check_status_derived.py", ["--mode", "warn"]),
        ("check_owner_numbers.py", ["--mode", "warn"]),
        ("check_allowlist_rundown.py", ["--write-draft"]),
        ("check_archive_sources.py", ["--mode", "warn"]),
        ("monthly_register_audit.py", ["--write"]),
    ]
    for name, extra in sweeps:
        p = subprocess.run([sys.executable, str(HERE / name), *extra], cwd=str(HERE.parents[1]))
        print("RAN", name, "rc", p.returncode)
        if name == "check_allowlist_rundown.py" and p.returncode not in (0,):
            # renewals would be 1; argparse should be 0 now
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
