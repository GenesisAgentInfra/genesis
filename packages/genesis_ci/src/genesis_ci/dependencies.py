"""Read captured dependency declarations; never invoke package managers."""

import re
import tomllib

from genesis_contracts.intelligence import DependencyAnalysis, DependencyDeclaration
from genesis_contracts.models import EvidenceSide

from .flows import whole_file_ref

PACKAGE = re.compile(r"^(openai|anthropic)(?=$|[\s\[<>=!~@;])", re.I)


def read_dependencies(snapshot, registry):
    declarations = []
    limitations = []
    for side in EvidenceSide:
        for path in snapshot.source.list_files(side):
            name = path.rsplit("/", 1)[-1]
            if name not in {"pyproject.toml", "uv.lock", "poetry.lock"} and not (
                name.startswith("requirements") and name.endswith(".txt")
            ):
                continue
            raw = snapshot.source.read_bytes(side, path)
            if len(raw) > 262144:
                limitations.append(f"{side.value}:{path}: dependency metadata exceeds byte budget")
                continue
            found = []
            try:
                if name.endswith(".txt"):
                    strings = [line.strip() for line in raw.decode().splitlines()]
                else:
                    data = tomllib.loads(raw.decode())
                    if name in {"uv.lock", "poetry.lock"}:
                        for package in data.get("package", ()):
                            if (
                                isinstance(package, dict)
                                and package.get("name") in {"openai", "anthropic"}
                                and isinstance(package.get("version"), str)
                            ):
                                found.append((package["name"], package["version"], "lock_version"))
                        strings = []
                    else:
                        project = data.get("project", {})
                        strings = list(project.get("dependencies", ()))
                        for group in project.get("optional-dependencies", {}).values():
                            strings.extend(group)
                        for group in data.get("dependency-groups", {}).values():
                            strings.extend(item for item in group if isinstance(item, str))
                        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                        for package, constraint in poetry.items():
                            if package in {"openai", "anthropic"}:
                                found.append((package, str(constraint), "constraint"))
                for declaration in strings:
                    match = PACKAGE.match(declaration) if isinstance(declaration, str) else None
                    if match:
                        found.append((match[1].lower(), declaration, "constraint"))
                if found:
                    refs = whole_file_ref(snapshot.source, registry, side, path)
                    declarations.extend(
                        DependencyDeclaration(
                            side=side,
                            path=path,
                            package=package,
                            declaration=text,
                            kind=kind,
                            evidence_ids=refs,
                        )
                        for package, text, kind in found
                    )
            except (ValueError, TypeError, AttributeError, RecursionError):
                limitations.append(f"{side.value}:{path}: unsupported dependency metadata")
    limitations.append(
        "Declarations/lock versions do not prove installed SDK versions; extras, markers and lock alternatives are not resolved."
    )
    return DependencyAnalysis(declarations=tuple(declarations), limitations=tuple(limitations))
