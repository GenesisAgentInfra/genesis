from pydantic import BaseModel


def _refs(value: object) -> list[str]:
    if isinstance(value, BaseModel):
        refs: list[str] = []
        for name in type(value).model_fields:
            field_value = getattr(value, name)
            if name.endswith("evidence_ids") and isinstance(field_value, tuple):
                refs.extend(field_value)
            else:
                refs.extend(_refs(field_value))
        return refs
    if isinstance(value, (tuple, list)):
        return [ref for item in value for ref in _refs(item)]
    return []
