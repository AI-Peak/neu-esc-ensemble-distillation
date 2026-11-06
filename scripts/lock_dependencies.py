"""Record the exact installed dependency closure for this Windows/Python environment."""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def lock(source: Path, output: Path):
    pending = [Requirement(line.strip()) for line in source.read_text().splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    seen, versions = set(), {}
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        contexts = requirement.extras or {""}
        if requirement.marker and not any(requirement.marker.evaluate({"extra": extra}) for extra in contexts):
            continue
        distribution = metadata.distribution(requirement.name)
        if requirement.specifier and not requirement.specifier.contains(distribution.version):
            raise ValueError(f"Installed {name} {distribution.version} does not satisfy {requirement}")
        versions[name] = distribution.version
        for extra in contexts:
            if (name, extra) in seen:
                continue
            seen.add((name, extra))
            for dependency in distribution.requires or []:
                child = Requirement(dependency)
                if not child.marker or child.marker.evaluate({"extra": extra}):
                    # Parent extra has already been evaluated; child extras are handled recursively.
                    child.marker = None
                    pending.append(child)
    output.write_text("# Exact installed dependency closure; Windows, CPython 3.10.\n"
                      "# Regenerate with scripts/lock_dependencies.py after validating a new environment.\n"
                      + "".join(f"{name}=={version}\n" for name, version in sorted(versions.items())), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    lock(arguments.source, arguments.output)
