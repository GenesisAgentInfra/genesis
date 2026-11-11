"""Conservative static resolution over frozen modules, never Python import machinery."""

from __future__ import annotations

from genesis_contracts.models import Resolution
from genesis_contracts.python import NameOrigin, ValueExpr


def unknown(reason):
    return Resolution(status="unknown", reason=reason)


def qualified(name):
    return name.replace(".<locals>.", ".")


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
            for binding in file.bindings:
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
            return self.resolve(bindings[0].value, side, path, seen)
        if bindings:
            targets = tuple(
                sorted(
                    {
                        target
                        for b in bindings
                        for target in self.resolve(b.value, side, path, seen).targets
                    }
                )
            )
            return (
                Resolution(
                    status="candidate", targets=targets, reason="Reassigned or conditional binding"
                )
                if targets
                else unknown("Reassigned or conditional binding")
            )
        # Attribute of an imported module or a locally assigned constructor.
        parts = name.split(".")
        for count in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:count])
            if (side, path, prefix) in self.bindings:
                result = self._local(prefix, side, path, seen)
                return self._attribute(result, ".".join(parts[count:]), side, seen)
        # self attributes: only a unique unconditional initializer assignment is a candidate.
        if ".self." in name:
            cls, attr = name.split(".self.", 1)
            cls = cls.rsplit(".", 1)[0]
            found = [
                b
                for fkey, file in self.files.items()
                if fkey == (side, path)
                for b in file.bindings
                if b.symbol_id.startswith(path + "#" + cls + ".")
                and b.target.text == "self." + attr
            ]
            if (
                len(found) == 1
                and found[0].symbol_id == path + "#" + cls + ".__init__"
                and not found[0].conditional
            ):
                result = self.resolve(found[0].value, side, path, seen)
                if result.targets:
                    return Resolution(
                        status="candidate",
                        targets=result.targets,
                        reason="Instance attribute inferred from __init__; runtime mutation is possible",
                    )
            # A method of the same class, when no instance attribute shadows its name.
            methods = [
                s
                for s in self.symbols.get((side, path, cls + "." + attr), [])
                if s.kind == "function"
            ]
            if not found and methods:
                return Resolution(
                    status="candidate",
                    targets=tuple(sorted({s.symbol_id for s in methods})),
                    reason="Method looked up on self; a subclass or the instance may override it",
                )
        return unknown("Parameter, dynamic attribute, or unsupported assignment")

    def _attribute(self, base, attribute, side, seen):
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
            elif target.startswith(("external:", "instance:")):
                member = target.removeprefix("instance:") + "." + attribute
                # A member of a local class must be defined in that class itself;
                # inherited and dynamically added members stay unresolved.
                if member.startswith("external:") or (side, member) in self.kinds:
                    targets.append(member)
                else:
                    uncertain = True
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
            if constructor.targets and all(
                self.kinds.get((side, target)) == {"class"} for target in constructor.targets
            ):
                return Resolution(
                    status="candidate",
                    targets=tuple("instance:" + target for target in constructor.targets),
                    reason="Instance of a local class; subclasses and dynamic dispatch are not modelled",
                )
            return unknown("Function return type is not statically known")
        return unknown("Dynamic callable or unsupported expression")

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
