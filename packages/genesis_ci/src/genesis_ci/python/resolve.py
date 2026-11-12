"""Conservative static resolution over frozen modules, never Python import machinery."""

from __future__ import annotations

import ast
import builtins

from genesis_contracts.models import Resolution
from genesis_contracts.python import NameOrigin, ValueExpr

# A declared type says what a value is meant to be, never what it is at run time.
ANNOTATED = "Type taken from an annotation; a subclass or another object may be passed at run time"
RETURNED = "Type taken from a return annotation; a subclass or another object may be returned"
PROVIDED = "Type taken from a dependency provider; an override may supply another object"
ENTERED = "Context manager __enter__ result is unknown"
_TYPING = ("typing", "typing_extensions", "collections.abc", "contextlib")
# Wrappers around the type that is actually meant.
_UNWRAPPED = {"Optional", "Union", "Final", "ClassVar", "Required", "NotRequired", "ReadOnly"}
# What a generator or context-manager provider hands to the code that uses it.
_PRODUCED = {
    "Iterator",
    "Generator",
    "Iterable",
    "AsyncIterator",
    "AsyncGenerator",
    "AsyncIterable",
    "Awaitable",
    "ContextManager",
    "AsyncContextManager",
    "AbstractContextManager",
    "AbstractAsyncContextManager",
}
_CONTAINERS = {
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Tuple": "tuple",
}
_PROPERTIES = {"property", "cached_property"}
# Library functions whose result is an object of a known class.
_RESULTS = {"external:logging.getLogger": "external:logging.Logger"}
INHERITED = "Member found in a base class; another base or a subclass may define it instead"
PASSED = "Taken from what callers in this code base pass; another caller may pass something else"
# How many call sites of one function are read to learn what a parameter receives.
MAX_CALL_SITES = 24
# How deep one parameter's value may lead through the parameters of its callers.
MAX_PASSING_DEPTH = 8
_NEVER = 1 << 30


def _is_test_path(path):
    """Tests hand in doubles; what they pass says nothing about the product's own objects."""
    name = path.rsplit("/", 1)[-1]
    return (
        bool({"tests", "test"} & set(path.split("/")[:-1]))
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def unknown(reason):
    return Resolution(status="unknown", reason=reason)


def qualified(name):
    return name.replace(".<locals>.", ".")


def _typing_name(target):
    """The bare name of the builtin or `typing` construct a target denotes, if it is one."""
    if target.startswith("builtin:"):
        return target.removeprefix("builtin:")
    name = target.removeprefix("external:")
    if name == target:
        return None
    return next(
        (name[len(module) + 1 :] for module in _TYPING if name.startswith(module + ".")), None
    )


def _is_builtin_type(name):
    return name != "object" and isinstance(getattr(builtins, name, None), type)


def _is_dependency(target):
    """FastAPI's marker for a parameter the framework fills in by calling a provider."""
    return target.startswith("external:fastapi") and target.rsplit(".", 1)[-1] in {
        "Depends",
        "Security",
    }


def _is_property(symbol):
    return any(item.text.rsplit(".", 1)[-1] in _PROPERTIES for item in symbol.decorators)


class Resolver:
    def __init__(self, files, roots, unavailable=()):
        self.files = files
        self.roots = roots
        self.unavailable = set(unavailable)
        self.modules = {}
        self.module_for_path = {}
        self.bindings = {}
        self.symbols = {}
        self.kinds = {}
        self.by_id = {}
        # Assignments to `self.<attribute>`, by every class or function they are nested in.
        self.attributes = {}
        # Where each function or class is called, once the calls have been resolved a
        # first time. Empty until then, so the first pass reads declarations only.
        self.call_sites = {}
        self._passed_cache = {}
        self._passing = []
        self._taint = _NEVER
        for side, path in sorted(set(files) | self.unavailable):
            file = files.get((side, path))
            candidates = []
            for root in roots:
                if root == ".":
                    suffix = path
                elif path.startswith(root + "/"):
                    suffix = path[len(root) + 1 :]
                else:
                    continue
                if suffix.endswith((".py", ".pyi")):
                    stem = suffix.rsplit(".", 1)[0]
                    parts = stem.split("/")
                    if parts[-1] == "__init__":
                        parts.pop()
                    if parts and all(p.isidentifier() for p in parts):
                        candidates.append((len(root) if root != "." else 0, ".".join(parts)))
            if candidates:
                module = max(candidates)[1]
                self.module_for_path[(side, path)] = module
                self.modules.setdefault((side, module), []).append(path)
            if file is None:
                continue
            for symbol in file.symbols:
                self.symbols.setdefault((side, path, symbol.qualified_name), []).append(symbol)
                self.kinds.setdefault((side, symbol.symbol_id), set()).add(symbol.kind)
                self.by_id.setdefault((side, symbol.symbol_id), []).append(symbol)
            for binding in file.bindings:
                if binding.target.text.startswith("self."):
                    attribute = binding.target.text.removeprefix("self.")
                    owners = binding.symbol_id.partition("#")[2].split(".")
                    for count in range(1, len(owners)):
                        key = (side, path, ".".join(owners[:count]), attribute)
                        self.attributes.setdefault(key, []).append(binding)
                for origin in binding.target.origins:
                    if origin.source == "local":
                        self.bindings.setdefault((side, path, qualified(origin.name)), []).append(
                            binding
                        )

    def absolute(self, name, side, path):
        if not name.startswith("."):
            return name
        dots = len(name) - len(name.lstrip("."))
        module = self.module_for_path.get((side, path))
        if module is None:
            return None
        parts = module.split(".")
        if not path.endswith(("/__init__.py", "/__init__.pyi")):
            parts.pop()
        if dots > len(parts):
            return None
        prefix = parts[: len(parts) - dots + 1]
        return ".".join([*prefix, *name[dots:].split(".")]).rstrip(".")

    def _import(self, name, side, path, seen):
        absolute = self.absolute(name, side, path)
        if not absolute:
            return unknown("Relative import escapes configured package roots")
        key = (side, "import", absolute)
        if key in seen:
            return unknown("Cyclic re-export or import alias")
        seen = seen | {key}
        parts = absolute.split(".")
        for count in range(len(parts), 0, -1):
            module = ".".join(parts[:count])
            paths = self.modules.get((side, module), [])
            if not paths:
                continue
            if len(paths) != 1:
                return unknown("Ambiguous module across source roots or .py/.pyi files")
            target_path = paths[0]
            if (side, target_path) in self.unavailable:
                return unknown("Captured or omitted local module was not analyzed")
            file = self.files[(side, target_path)]
            if file.dynamic_namespace:
                return unknown("Imported module has dynamic namespace mutation")
            tail = ".".join(parts[count:])
            if not tail:
                return Resolution(status="resolved", targets=("module:" + target_path,))
            symbols = self.symbols.get((side, target_path, tail), [])
            bindings = self.bindings.get((side, target_path, tail), [])
            if symbols and not bindings:
                decorated = any(s.decorators or s.declaration_conditions for s in symbols)
                return Resolution(
                    status="candidate" if len(symbols) > 1 or decorated else "resolved",
                    targets=tuple(sorted({s.symbol_id for s in symbols})),
                    reason="Decorators or duplicate definitions may alter target"
                    if decorated or len(symbols) > 1
                    else None,
                )
            first, *rest = tail.split(".")
            origins = file.exports.get(first, ())
            if origins and not bindings:
                expanded = [
                    NameOrigin(
                        name=o.name + ("." + ".".join(rest) if rest else ""), source=o.source
                    )
                    for o in origins
                ]
                return self._origins(expanded, side, target_path, seen)
            if bindings:
                return self._local(tail, side, target_path, seen)
            # Parent packages can re-export modules: export child + attribute.
            if origins:
                return self._origins(origins, side, target_path, seen)
            return unknown("Target is absent from captured module or requires dynamic attributes")
        # Do not mislabel a missing child of a captured package as external.
        if any((side, ".".join(parts[:i])) in self.modules for i in range(1, len(parts))):
            return unknown("Local module member is not captured")
        if any(s == side and module.split(".")[0] == parts[0] for s, module in self.modules):
            return unknown("Captured namespace package may shadow this external import")
        return Resolution(status="resolved", targets=("external:" + absolute,))

    def _origins(self, origins, side, path, seen):
        results = []
        for origin in origins:
            if origin.source == "import":
                file = self.files.get((side, path))
                result = self._import(origin.name, side, path, seen)
                if file and any(
                    origin.name == name or origin.name.startswith(name + ".")
                    for name in file.uncertain_imports
                ):
                    result = (
                        Resolution(
                            status="candidate",
                            targets=result.targets,
                            reason="Import is conditional or its attribute is reassigned",
                        )
                        if result.targets
                        else result
                    )
                results.append(result)
            elif origin.source == "builtin":
                if origin.name.removeprefix("builtins.").split(".")[0] in {
                    "None",
                    "True",
                    "False",
                    "Ellipsis",
                    "NotImplemented",
                    "__debug__",
                }:
                    results.append(unknown("Builtin constant metadata is not a callable target"))
                    continue
                results.append(
                    Resolution(
                        status="resolved",
                        targets=("builtin:" + origin.name.removeprefix("builtins."),),
                    )
                )
            else:
                results.append(self._local(qualified(origin.name), side, path, seen))
        targets = tuple(sorted({t for result in results for t in result.targets}))
        if not targets:
            return unknown(
                "; ".join(sorted({r.reason or "Unresolved target" for r in results}))
                or "No static name binding"
            )
        if len(results) == 1 and results[0].status == "resolved":
            return results[0]
        return Resolution(
            status="candidate",
            targets=targets,
            reason="Multiple, conditional, decorated, or partially resolved name bindings",
        )

    def _local(self, name, side, path, seen):
        key = (side, path, name)
        if key in seen or len(seen) > 64:
            return unknown("Binding cycle or resolution budget exceeded")
        seen = seen | {key}
        symbols = self.symbols.get(key, [])
        bindings = self.bindings.get(key, [])
        if symbols and not bindings:
            return Resolution(
                status="candidate"
                if len(symbols) > 1
                or any(s.decorators or s.declaration_conditions for s in symbols)
                else "resolved",
                targets=tuple(sorted({s.symbol_id for s in symbols})),
                reason="Duplicate/decorated definition may change runtime target"
                if len(symbols) > 1
                or any(s.decorators or s.declaration_conditions for s in symbols)
                else None,
            )
        if len(bindings) == 1 and not bindings[0].conditional:
            return self._or_declared(
                self._bound(bindings[0], side, path, seen), name, side, path, seen
            )
        if bindings:
            targets = tuple(
                sorted(
                    {
                        target
                        for b in bindings
                        for target in self._bound(b, side, path, seen).targets
                    }
                )
            )
            result = (
                Resolution(
                    status="candidate", targets=targets, reason="Reassigned or conditional binding"
                )
                if targets
                else unknown("Reassigned or conditional binding")
            )
            return self._or_declared(result, name, side, path, seen)
        # Attribute of an imported module, a locally assigned constructor or a typed name.
        file = self.files.get((side, path))
        parts = name.split(".")
        for count in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:count])
            if (side, path, prefix) in self.bindings or (
                file is not None and (prefix in file.annotations or prefix in file.defaults)
            ):
                result = self._local(prefix, side, path, seen)
                return self._attribute(result, ".".join(parts[count:]), side, seen)
        if ".self." in name:
            owner, attr = name.split(".self.", 1)
            member = self._instance_member(owner.rsplit(".", 1)[0], attr, side, path, seen)
            if member is not None:
                return member
        owner, inside, attr = name.partition(".cls.")
        if not inside and name.endswith(".cls"):
            owner, inside = name.removesuffix(".cls"), ".cls"
        if inside and self._takes_class(owner, side, path):
            cls = owner.rsplit(".", 1)[0]
            reason = "Looked up on cls; a subclass may be the class at run time"
            if not attr:
                return Resolution(status="candidate", targets=(path + "#" + cls,), reason=reason)
            targets = self._class_member(cls, attr, side, path, seen)
            if targets:
                return Resolution(status="candidate", targets=targets, reason=reason)
        declared = self._declared(name, side, path, seen)
        if declared is not None and declared.targets:
            return declared
        return unknown("Parameter, dynamic attribute, or unsupported assignment")

    def _takes_class(self, function, side, path):
        """Whether `function` is written in a class and names its first parameter `cls`."""
        cls, dot, _ = function.rpartition(".")
        return (
            bool(dot)
            and any(item.kind == "class" for item in self.symbols.get((side, path, cls), ()))
            and any(
                item.kind == "function" and item.parameters[:1] == ("cls",)
                for item in self.symbols.get((side, path, function), ())
            )
        )

    def _bound(self, binding, side, path, seen):
        """What a binding assigns: each side of `a or b` and `a if c else b` counts."""
        file = self.files.get((side, path))
        options = file.alternatives.get(binding.binding_id) if file is not None else None
        if not options:
            value = binding.value
            if value.kind == "unknown" and value.reason == ENTERED and value.children:
                return self._entered(value.children[0], side, path, seen)
            return self.resolve(value, side, path, seen)
        targets = tuple(
            sorted(
                {
                    target
                    for option in options
                    for target in self.resolve(option, side, path, seen).targets
                }
            )
        )
        if not targets:
            return unknown("None of the alternative values is statically known")
        return Resolution(
            status="candidate", targets=targets, reason="One of several alternative values"
        )

    def _or_declared(self, result, name, side, path, seen):
        """Fall back on the declared type; a reassigned parameter may hold either value."""
        declared = self._declared(name, side, path, seen)
        if declared is None or not declared.targets:
            return result
        if not result.targets:
            return declared
        function, _, parameter = name.rpartition(".")
        if not any(
            parameter in item.parameters for item in self.symbols.get((side, path, function), ())
        ):
            return result
        return Resolution(
            status="candidate",
            targets=tuple(sorted({*result.targets, *declared.targets})),
            reason=declared.reason,
        )

    def _declared(self, name, side, path, seen):
        """The values the declaration of a parameter, variable or attribute admits."""
        file = self.files.get((side, path))
        if file is None:
            return None
        result = None
        annotation = file.annotations.get(name)
        if annotation is not None:
            result = self._typed(annotation, side, path, seen)
        if (result is None or not result.targets) and name in file.defaults:
            result = self._injected(file.defaults[name], side, path, seen)
        if (result is None or not result.targets) and annotation is None and self.call_sites:
            targets = self._passed(name, side, path)
            if targets:
                result = Resolution(status="candidate", targets=targets, reason=PASSED)
        return result

    def learn_call_sites(self):
        """Index where every local function and class is called, from the resolved calls.

        A parameter without an annotation is then typed by what its callers pass. Calls
        written in tests are left out for product code: they pass doubles.
        """
        sites = {}
        for (side, path), file in self.files.items():
            for call in file.calls:
                for target in call.target.targets:
                    if (side, target) in self.kinds and not (
                        _is_test_path(path) and not _is_test_path(target.partition("#")[0])
                    ):
                        sites.setdefault((side, target), []).append((path, call))
        self.call_sites = sites
        self._passed_cache = {}

    def _passed(self, name, side, path):
        """What the callers in this code base pass for an unannotated parameter."""
        key = (side, path, name)
        if key in self._passed_cache:
            return self._passed_cache[key]
        if key in self._passing:
            # A value that leads back to a parameter still being worked out.
            self._taint = min(self._taint, self._passing.index(key))
            return ()
        depth = len(self._passing)
        if depth >= MAX_PASSING_DEPTH:
            self._taint = 0
            return ()
        self._passing.append(key)
        try:
            targets = self._arguments_for(name, side, path)
        finally:
            self._passing.pop()
        # Keep the answer only when it did not lean on one that is still unfinished.
        if self._taint >= depth:
            self._passed_cache[key] = targets
            self._taint = _NEVER
        return targets

    def _arguments_for(self, name, side, path):
        function, _, parameter = name.rpartition(".")
        symbols = [
            item for item in self.symbols.get((side, path, function), ()) if item.kind == "function"
        ]
        if len(symbols) != 1 or parameter not in symbols[0].parameters:
            return ()
        symbol = symbols[0]
        if parameter in symbol.variadic_parameters:
            return ()
        index = symbol.parameters.index(parameter)
        cls, _, method = function.rpartition(".")
        in_class = bool(cls) and any(
            item.kind == "class" for item in self.symbols.get((side, path, cls), ())
        )
        bound = in_class and symbol.parameters[:1] in (("self",), ("cls",))
        if bound and index == 0:
            return ()
        # Creating an object calls the class, and its arguments go to `__init__`.
        callee = path + "#" + (cls if in_class and method == "__init__" else function)
        found = set()
        for site_path, call in self.call_sites.get((side, callee), ())[:MAX_CALL_SITES]:
            if any(item.spread for item in call.arguments):
                continue
            value = next((item.value for item in call.arguments if item.name == parameter), None)
            if value is None:
                positional = [item.value for item in call.arguments if item.name is None]
                at = index - int(bound)
                value = positional[at] if 0 <= at < len(positional) else None
            if value is None:
                continue
            for target in self.resolve(value, side, site_path).targets:
                # An object, a class or a function: something whose members can be followed.
                if target.startswith("instance:") or (side, target) in self.kinds:
                    found.add(target)
        return tuple(sorted(found))

    def _injected(self, default, side, path, seen):
        """A parameter whose default is `Depends(provider)` receives what the provider makes."""
        if default.kind != "call" or not default.children:
            return None
        marker = self.resolve(default.children[0], side, path, seen)
        if not marker.targets or not all(_is_dependency(item) for item in marker.targets):
            return None
        provider = next(
            (
                item.value
                for item in default.arguments
                if item.name in {None, "dependency"} and not item.spread
            ),
            None,
        )
        if provider is None:
            return None
        values = []
        for target in self.resolve(provider, side, path, seen).targets:
            kinds = self.kinds.get((side, target))
            if kinds == {"class"}:
                values.append("instance:" + target)
            elif kinds == {"function"}:
                values.extend(self._returned(target, side, seen, produced=True).targets)
        if not values:
            return None
        return Resolution(status="candidate", targets=tuple(sorted(set(values))), reason=PROVIDED)

    def _returned(self, function, side, seen, *, awaited=None, produced=False):
        """What calling a local function yields, going by its return annotation alone."""
        path, _, name = function.partition("#")
        file = self.files.get((side, path))
        annotation = file.returns.get(name) if file is not None else None
        key = (side, "returns", function)
        if annotation is None or key in seen or len(seen) > 64:
            return unknown("Function return type is not statically known")
        seen = seen | {key}
        symbols = self.by_id.get((side, function), ())
        if awaited is not None and any(item.is_async for item in symbols) != awaited:
            return unknown("A coroutine function yields its result only when awaited")
        cls = name.rpartition(".")[0]
        owner = (
            path + "#" + cls
            if cls and any(item.kind == "class" for item in self.symbols.get((side, path, cls), ()))
            else None
        )
        result = self._typed(annotation, side, path, seen, owner=owner, produced=produced)
        if not result.targets:
            return result
        return Resolution(status="candidate", targets=result.targets, reason=RETURNED)

    def _entered(self, manager, side, path, seen):
        """What `with manager as name` binds: the yielded value, or the manager itself."""
        if manager.kind == "await" and manager.children:
            manager = manager.children[0]
        if manager.kind != "call" or not manager.children:
            return unknown(ENTERED)
        values = []
        for target in self.resolve(manager.children[0], side, path, seen).targets:
            kinds = self.kinds.get((side, target))
            if kinds == {"class"}:
                values.append("instance:" + target)
            elif kinds == {"function"}:
                values.extend(self._returned(target, side, seen, produced=True).targets)
        entered = []
        for value in values:
            cls = value.removeprefix("instance:")
            enter = next(
                (
                    cls + "." + name
                    for name in ("__enter__", "__aenter__")
                    if value != cls and (side, cls + "." + name) in self.kinds
                ),
                None,
            )
            own = self._returned(enter, side, seen).targets if enter else ()
            # Without a declared result, `__enter__` is taken to return the manager.
            entered.extend(own or (value,))
        if not entered:
            return unknown(ENTERED)
        return Resolution(status="candidate", targets=tuple(sorted(set(entered))), reason=RETURNED)

    def _typed(self, annotation, side, path, seen, *, owner=None, produced=False):
        """The values an annotation admits: instances, or the class itself for `type[X]`."""
        targets = self._admits(annotation, side, path, seen, owner, produced, 0)
        if not targets:
            return unknown("Annotation does not name a class whose members can be looked up")
        return Resolution(status="candidate", targets=tuple(sorted(set(targets))), reason=ANNOTATED)

    def _admits(self, expr, side, path, seen, owner, produced, depth):
        if depth > 8:
            return []

        def admits(item, produced=False):
            return self._admits(item, side, path, seen, owner, produced, depth + 1)

        if expr.kind == "literal":
            # A quoted annotation is a forward reference to a name of this module.
            reference = (
                self._reference(expr.value, side, path) if isinstance(expr.value, str) else None
            )
            return admits(reference, produced) if reference is not None else []
        if expr.kind == "unknown":
            # `X | None`
            return [target for child in expr.children for target in admits(child)]
        if expr.kind == "subscript" and expr.children:
            base, *items = expr.children
            names = {_typing_name(item) for item in self.resolve(base, side, path, seen).targets}
            if names & {"Annotated"}:
                return admits(items[0], produced) if items else []
            if names & _UNWRAPPED:
                return [target for item in items for target in admits(item)]
            if names & {"Type", "type"}:
                return [
                    target
                    for item in items
                    for target in self.resolve(item, side, path, seen).targets
                    if self.kinds.get((side, target)) == {"class"}
                ]
            if names & _PRODUCED:
                return admits(items[0]) if produced and items else []
            container = next((_CONTAINERS[name] for name in names if name in _CONTAINERS), None)
            if container is not None:
                return ["instance:builtin:" + container]
            # A generic class: `Repository[Order]` is still a `Repository`.
            return admits(base)
        if expr.kind not in {"name", "attribute"}:
            return []
        values = []
        for target in self.resolve(expr, side, path, seen).targets:
            name = _typing_name(target)
            if self.kinds.get((side, target)) == {"class"}:
                values.append("instance:" + target)
            elif target.startswith("builtin:"):
                if _is_builtin_type(name):
                    values.append("instance:" + target)
            elif name == "Self" and owner is not None:
                values.append("instance:" + owner)
            elif target.startswith("external:") and name is None:
                values.append("instance:" + target)
        return values

    def _reference(self, text, side, path):
        """Read a quoted annotation as an expression; only its syntax is looked at."""
        try:
            node = ast.parse(text.strip(), mode="eval").body
        except (SyntaxError, ValueError):
            return None
        return self._referenced(node, side, path, 0)

    def _referenced(self, node, side, path, depth):
        if depth > 8:
            return None
        if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, str)):
            return ValueExpr(kind="literal", text=repr(node.value), value=node.value)
        if isinstance(node, ast.Name):
            file = self.files.get((side, path))
            origins = file.imported.get(node.id) if file is not None else None
            if origins is None:
                local = (side, path, node.id) in self.symbols or (
                    side,
                    path,
                    node.id,
                ) in self.bindings
                origins = (
                    (NameOrigin(name="builtins." + node.id, source="builtin"),)
                    if not local and hasattr(builtins, node.id)
                    else (NameOrigin(name=node.id, source="local"),)
                )
            return ValueExpr(kind="name", text=node.id, origins=origins)
        if isinstance(node, ast.Attribute):
            base = self._referenced(node.value, side, path, depth + 1)
            if base is None or base.kind not in {"name", "attribute"}:
                return None
            return ValueExpr(
                kind="attribute",
                text=base.text + "." + node.attr,
                attribute=node.attr,
                children=(base,),
                origins=tuple(
                    NameOrigin(name=item.name + "." + node.attr, source=item.source)
                    for item in base.origins
                ),
            )
        opaque = ValueExpr(kind="unknown", text="", reason="Not a type that can be followed")
        if isinstance(node, ast.Subscript):
            base = self._referenced(node.value, side, path, depth + 1)
            if base is None:
                return None
            items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            children = [self._referenced(item, side, path, depth + 1) or opaque for item in items]
            return ValueExpr(kind="subscript", text=ast.unparse(node), children=(base, *children))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            sides = [
                self._referenced(item, side, path, depth + 1) or opaque
                for item in (node.left, node.right)
            ]
            return ValueExpr(
                kind="unknown",
                text=ast.unparse(node),
                children=tuple(sides),
                reason="Union of types",
            )
        return None

    def _bases(self, cls, side, path, seen):
        """The base classes of `cls` that are written in the captured code, in order."""
        file = self.files.get((side, path))
        found = []
        for base in file.bases.get(cls, ()) if file is not None else ():
            for target in self.resolve(base, side, path, seen).targets:
                if self.kinds.get((side, target)) == {"class"}:
                    found.append((target.partition("#")[0], target.partition("#")[2]))
        return found

    def _class_member(self, cls, attribute, side, path, seen):
        """`attribute` looked up on the class itself: its own, else the first base that has it."""
        key = (side, path, "class member", cls, attribute)
        if key in seen or len(seen) > 64:
            return ()
        seen = seen | {key}
        own = self._local(cls + "." + attribute, side, path, seen).targets
        if own:
            return own
        for base_path, base in self._bases(cls, side, path, seen):
            inherited = self._class_member(base, attribute, side, base_path, seen)
            if inherited:
                return inherited
        return ()

    def _instance_member(self, cls, attribute, side, path, seen):
        """`attribute` looked up on an instance of the class `cls` written in `path`.

        What the class itself says comes first: a unique unconditional assignment in its
        initializer, a declared type, then a method. A name the class does not mention is
        looked up in its base classes, in the order they are listed.
        """
        key = (side, path, "member", cls, attribute)
        if key in seen or len(seen) > 64:
            return None
        seen = seen | {key}
        own = self._own_member(cls, attribute, side, path, seen)
        if own is not None or self.attributes.get((side, path, cls, attribute)):
            return own
        for base_path, base in self._bases(cls, side, path, seen):
            inherited = self._instance_member(base, attribute, side, base_path, seen)
            if inherited is not None:
                return Resolution(status="candidate", targets=inherited.targets, reason=INHERITED)
        return None

    def _own_member(self, cls, attribute, side, path, seen):
        found = self.attributes.get((side, path, cls, attribute), [])
        if (
            len(found) == 1
            and found[0].symbol_id == path + "#" + cls + ".__init__"
            and not found[0].conditional
        ):
            result = self._bound(found[0], side, path, seen)
            if result.targets:
                return Resolution(
                    status="candidate",
                    targets=result.targets,
                    reason="Instance attribute inferred from __init__; runtime mutation is possible",
                )
        declared = self._declared(cls + "." + attribute, side, path, seen)
        if declared is not None and declared.targets:
            return declared
        # A method of the same class, when no instance attribute shadows its name.
        methods = [
            item
            for item in self.symbols.get((side, path, cls + "." + attribute), [])
            if item.kind == "function"
        ]
        if found or not methods:
            return None
        if any(_is_property(item) for item in methods):
            value = self._returned(methods[0].symbol_id, side, seen)
            if value.targets:
                return value
        return Resolution(
            status="candidate",
            targets=tuple(sorted({item.symbol_id for item in methods})),
            reason="Method looked up on self; a subclass or the instance may override it",
        )

    def _attribute(self, base, attribute, side, seen):
        if "." in attribute and any(
            item.startswith("instance:") and not item.startswith("instance:external:")
            for item in base.targets
        ):
            first, rest = attribute.split(".", 1)
            return self._attribute(self._attribute(base, first, side, seen), rest, side, seen)
        targets = []
        uncertain = base.status != "resolved"
        for target in base.targets:
            if target.startswith("module:"):
                path = target.removeprefix("module:")
                module = self.module_for_path.get((side, path))
                result = (
                    self._import(module + "." + attribute, side, path, seen)
                    if module
                    else unknown("Module name unavailable")
                )
                targets.extend(result.targets)
                uncertain |= result.status != "resolved"
            elif target.startswith("instance:builtin:"):
                name = target.removeprefix("instance:builtin:")
                if _is_builtin_type(name) and hasattr(getattr(builtins, name), attribute):
                    targets.append("builtin:" + name + "." + attribute)
                else:
                    uncertain = True
            elif target.startswith(("external:", "instance:external:")):
                targets.append(target.removeprefix("instance:") + "." + attribute)
            elif target.startswith("instance:"):
                # A member of a local class must come from that class itself;
                # inherited and dynamically added members stay unresolved.
                cls = target.removeprefix("instance:")
                member = self._instance_member(
                    cls.partition("#")[2], attribute, side, cls.partition("#")[0], seen
                )
                uncertain = True
                if member is not None:
                    targets.extend(member.targets)
                elif (side, cls + "." + attribute) in self.kinds:
                    targets.append(cls + "." + attribute)
            elif self.kinds.get((side, target)) == {"class"}:
                # Looked up on the class itself, as `cls.method` or through `type[X]`.
                uncertain = True
                targets.extend(
                    self._class_member(
                        target.partition("#")[2], attribute, side, target.partition("#")[0], seen
                    )
                )
            else:
                uncertain = True
        if not targets:
            return unknown("Attribute target requires runtime type or descriptor resolution")
        return Resolution(
            status="candidate" if uncertain or len(targets) > 1 else "resolved",
            targets=tuple(sorted(set(targets))),
            reason="Attribute receiver is only a static candidate"
            if uncertain or len(targets) > 1
            else None,
        )

    def forward_binding(self, expr, side, path):
        if expr.position is None:
            return False
        for origin in expr.origins:
            if origin.source != "local":
                continue
            name = qualified(origin.name)
            for count in range(1, len(name.split(".")) + 1):
                prefix = ".".join(name.split(".")[:count])
                symbols = self.symbols.get((side, path, prefix), ())
                for symbol in symbols:
                    parent = (
                        symbol.qualified_name.rsplit(".", 1)[0]
                        if "." in symbol.qualified_name
                        else "<module>"
                    )
                    if (
                        expr.scope == path + "#" + parent
                        and (symbol.range.start_line, symbol.range.start_column or 0)
                        >= expr.position
                    ):
                        return True
                bindings = self.bindings.get((side, path, prefix), ())
                if any(
                    b.symbol_id == expr.scope
                    and b.target.position
                    and b.target.position >= expr.position
                    for b in bindings
                ):
                    return True
        return False

    def resolve(self, expr, side, path, seen=frozenset()):
        if self.forward_binding(expr, side, path):
            return unknown(
                "Binding assigned at or after this use; value is not available at this statement"
            )

        if (side, path) in self.files and self.files[(side, path)].dynamic_namespace:
            return unknown(
                "Dynamic namespace mutation, deletion, or unsupported unpacking prevents reliable binding resolution"
            )
        if len(seen) > 64:
            return unknown("Resolution budget exceeded")
        if expr.kind == "name":
            return self._origins(expr.origins, side, path, seen)
        if expr.kind == "attribute":
            # Full qualified origins preserve imports, scopes and shadowing.
            # QualifiedNameProvider can attach builtin None to attributes of
            # unsupported expressions. Only a syntactic name/attribute chain
            # supports direct qualified lookup; other receivers stay uncertain.
            receiver = expr.children[0]
            while receiver.kind == "attribute" and receiver.children:
                receiver = receiver.children[0]
            if expr.origins and receiver.kind == "name":
                direct = self._origins(expr.origins, side, path, seen)
                if direct.targets:
                    return direct
            return self._attribute(
                self.resolve(expr.children[0], side, path, seen), expr.attribute, side, seen
            )
        if expr.kind == "call":
            return self._called(expr, side, path, seen, awaited=False)
        if expr.kind == "await" and expr.children and expr.children[0].kind == "call":
            return self._called(expr.children[0], side, path, seen, awaited=True)
        return unknown("Dynamic callable or unsupported expression")

    def _called(self, expr, side, path, seen, *, awaited):
        """The value of a call: an instance of the class, or what the function declares."""
        constructor = self.resolve(expr.children[0], side, path, seen)
        # Only official SDK client constructors have a known returned client family.
        allowed = {
            "external:openai.OpenAI",
            "external:openai.AsyncOpenAI",
            "external:anthropic.Anthropic",
            "external:anthropic.AsyncAnthropic",
        }
        if constructor.targets and set(constructor.targets) <= allowed:
            return Resolution(
                status=constructor.status,
                targets=tuple("instance:" + t for t in constructor.targets),
                reason=constructor.reason,
            )
        values = []
        declared = False
        if constructor.targets == ("builtin:super",) and not expr.arguments and expr.scope:
            # `super()` in a method: the instance, seen from the bases of its class.
            scope_path, _, function = expr.scope.partition("#")
            values = [
                "instance:" + base_path + "#" + base
                for base_path, base in self._bases(
                    function.rpartition(".")[0], side, scope_path, seen
                )
            ]
        for target in constructor.targets:
            kinds = self.kinds.get((side, target))
            if target in _RESULTS:
                values.append("instance:" + _RESULTS[target])
            elif target == "builtin:super":
                continue
            elif kinds == {"class"}:
                values.append("instance:" + target)
            elif kinds == {"function"}:
                declared = True
                values.extend(self._returned(target, side, seen, awaited=awaited).targets)
            else:
                return unknown("Function return type is not statically known")
        if not values:
            return unknown("Function return type is not statically known")
        return Resolution(
            status="candidate",
            targets=tuple(sorted(set(values))),
            reason=RETURNED
            if declared
            else "Instance of a local class; subclasses and dynamic dispatch are not modelled",
        )

    def callable_target(self, target, side):
        """Resolve calling an instance of a local class to its own `__call__`, if it has one."""
        local = [
            item
            for item in target.targets
            if item.startswith("instance:") and not item.startswith("instance:external:")
        ]
        if not local:
            return target
        callables = [
            item.removeprefix("instance:") + ".__call__"
            for item in local
            if (side, item.removeprefix("instance:") + ".__call__") in self.kinds
        ]
        kept = [item for item in target.targets if item not in local]
        if not callables and not kept:
            return unknown("Called object is an instance without a statically known __call__")
        return Resolution(
            status="candidate",
            targets=tuple(sorted({*kept, *callables})),
            reason="Call through an instance of a local class; dynamic dispatch is not modelled",
        )

    def value(self, expr, side, path, seen=frozenset(), budget=None):
        """Substitute only unique unconditional local values; never evaluate customer expressions."""
        if self.forward_binding(expr, side, path):
            return ValueExpr(
                kind="unknown", text=expr.text, reason="Binding assigned at or after this use"
            )
        budget = [2048] if budget is None else budget
        budget[0] -= 1
        file = self.files.get((side, path))
        if budget[0] < 0 or (file and file.dynamic_namespace):
            return ValueExpr(
                kind="unknown",
                text=expr.text,
                reason="Value resolution budget or namespace uncertainty",
            )
        if expr.kind in {"literal", "list", "tuple", "dict", "call", "unknown"}:
            return expr.model_copy(
                update={
                    "children": tuple(
                        self.value(child, side, path, seen, budget) for child in expr.children
                    ),
                    "entries": tuple(
                        entry.model_copy(
                            update={"value": self.value(entry.value, side, path, seen, budget)}
                        )
                        for entry in expr.entries
                    ),
                    "arguments": tuple(
                        arg.model_copy(
                            update={"value": self.value(arg.value, side, path, seen, budget)}
                        )
                        for arg in expr.arguments
                    ),
                }
            )
        if expr.kind == "name" and len(expr.origins) == 1 and expr.origins[0].source == "local":
            key = (side, path, qualified(expr.origins[0].name))
            if key in seen or len(seen) > 32:
                return ValueExpr(kind="unknown", text=expr.text, reason="Value binding cycle")
            bindings = self.bindings.get(key, [])
            if (
                file
                and file.mutable_values
                and bindings
                and bindings[0].value.kind in {"list", "dict"}
            ):
                return ValueExpr(kind="unknown", text=expr.text, reason="Container may be mutated")
            if len(bindings) == 1 and not bindings[0].conditional:
                value = self.value(bindings[0].value, side, path, seen | {key}, budget)
                return value.model_copy(
                    update={
                        "evidence_ids": tuple(
                            sorted(
                                set(
                                    (
                                        *expr.evidence_ids,
                                        *bindings[0].evidence_ids,
                                        *value.evidence_ids,
                                    )
                                )
                            )
                        )
                    }
                )
        return expr
