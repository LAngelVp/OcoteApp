"""Verify or reproduce the pinned, licensed offline NCSC password blocklist."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

COMMIT = "1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56"
BASE = f"https://raw.githubusercontent.com/danielmiessler/SecLists/{COMMIT}/"
ASSETS = (
    (
        "Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt",
        "ncsc-100k.txt",
        "c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0",
    ),
    (
        "LICENSE",
        "SecLists-LICENSE.txt",
        "3dbdc93d5f8829de0941744841730a09c106d0732e5ae0e98ca1d77be7ded66c",
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    arguments = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / "app" / "core" / "data"
    for source, name, digest in ASSETS:
        destination = directory / name
        if arguments.download:
            with urlopen(BASE + source, timeout=30) as response:
                content = response.read(2_000_001)
        else:
            content = destination.read_bytes()
        if len(content) > 2_000_000 or hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError("Invalid pinned asset: " + name)
        if arguments.download:
            directory.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        print(f"Verified {name}: {len(content)} bytes, SHA256 {digest}")


if __name__ == "__main__":
    main()
