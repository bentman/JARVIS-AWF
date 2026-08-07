import pytest

from awf.registry.kinds import KINDS, UnknownRegistryKindError, by_key, object_path, version_names


def test_by_key_raises_on_unknown_kind():
    with pytest.raises(UnknownRegistryKindError):
        by_key("not-a-real-kind")


def test_by_key_returns_the_matching_kind():
    assert by_key("skills").key == "skills"
    assert by_key("agents").layout == "markdown"


def test_object_path_directory_layout(tmp_path):
    assert object_path(tmp_path, by_key("skills"), "1.0.0") == tmp_path / "1.0.0" / "SKILL.md"


def test_object_path_markdown_layout(tmp_path):
    assert object_path(tmp_path, by_key("agents"), "1.0.0") == tmp_path / "1.0.0.md"


def test_object_path_yaml_layout(tmp_path):
    assert object_path(tmp_path, by_key("capabilities"), "1.0.0") == tmp_path / "1.0.0.yaml"


@pytest.mark.parametrize("kind", KINDS)
def test_version_names_round_trips_against_object_path(tmp_path, kind):
    name_dir = tmp_path / "some-name"
    for version in ("1.0.0", "2.0.0"):
        target = object_path(name_dir, kind, version)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")

    assert version_names(name_dir, kind) == ("1.0.0", "2.0.0")
