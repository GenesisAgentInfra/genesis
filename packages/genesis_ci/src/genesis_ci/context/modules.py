"""Conservative module candidates from frozen analyzed paths, never sys.path."""


def local_module_candidates(name, side, owner, modules):
    if not name:
        return set()
    if name.startswith("."):
        dots = len(name) - len(name.lstrip("."))
        parts = owner.split("/")[:-1]
        if dots > len(parts):
            return set()
        prefix = parts[: len(parts) - dots + 1]
        suffix = "/".join([*prefix, *name[dots:].split(".")]).rstrip("/")
        endings = {suffix + ext for ext in (".py", ".pyi", "/__init__.py", "/__init__.pyi")}
        return {
            path for candidate_side, path in modules if candidate_side == side and path in endings
        }
    suffix = name.replace(".", "/")
    endings = tuple(suffix + ext for ext in (".py", ".pyi", "/__init__.py", "/__init__.pyi"))
    return {
        path
        for candidate_side, path in modules
        if candidate_side == side
        and any(path == ending or path.endswith("/" + ending) for ending in endings)
    }


def local_module_path(name, side, owner, modules):
    candidates = local_module_candidates(name, side, owner, modules)
    return next(iter(candidates)) if len(candidates) == 1 else None
