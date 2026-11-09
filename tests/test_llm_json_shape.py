import pytest

from autopilot.providers.llm import ScriptPlanner


def test_json_accepts_single_object_wrapped_in_array():
    assert ScriptPlanner._json('[{"title": "A plan"}]') == {"title": "A plan"}


@pytest.mark.parametrize("payload", ['[]', '[{"a": 1}, {"b": 2}]', '"text"'])
def test_json_rejects_non_object_shapes(payload: str):
    with pytest.raises(ValueError, match="must be an object"):
        ScriptPlanner._json(payload)
