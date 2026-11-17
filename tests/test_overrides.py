"""A method called on an instance also leads to the overrides of the instance's subclasses."""

from test_python_entries import entries

MODELS = """class Model:
    def embed(self, text):
        return self.tokenize(text)

    def tokenize(self, text):
        raise NotImplementedError


class Splade(Model):
    def tokenize(self, text):
        return text.split()

    def first(self, text):
        return self.tokenize(text)[0]


class Fast(Splade):
    def tokenize(self, text):
        return [text]


class Other:
    def tokenize(self, text):
        return text
"""


def call(facts, symbol, text):
    [found] = [
        fact
        for fact in facts.facts
        if fact.kind == "call" and fact.symbol_id == symbol and fact.text == text
    ]
    return found


def test_a_call_on_self_leads_to_the_overrides_of_subclasses(source_repo):
    found, facts = entries(source_repo, {"lib/__init__.py": "", "lib/models.py": MODELS})
    base = call(facts, "lib/models.py#Model.embed", "self.tokenize(text)")
    assert base.target.status == "candidate"
    assert base.target.targets == (
        "lib/models.py#Fast.tokenize",
        "lib/models.py#Model.tokenize",
        "lib/models.py#Splade.tokenize",
    )
    # From a subclass, only its own method and those of its subclasses can run.
    middle = call(facts, "lib/models.py#Splade.first", "self.tokenize(text)")
    assert middle.target.targets == ("lib/models.py#Fast.tokenize", "lib/models.py#Splade.tokenize")
    # An override that a base class calls is not an uncalled function.
    assert "lib/models.py#Splade.tokenize" not in found
    assert "lib/models.py#Other.tokenize" in found
