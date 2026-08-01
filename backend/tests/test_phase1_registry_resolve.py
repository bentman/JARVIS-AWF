import pytest

from awf.registry.resolve import RegistryObjectNotFoundError, resolve_registry_object


def _make_object(root, source_root, kind, name, version, is_skill=False):
    base = root / source_root / kind / name
    if is_skill:
        target = base / version / "SKILL.md"
    else:
        target = base / f"{version}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("placeholder: true\n")
    return target


def test_resolves_from_data_when_only_data_has_it(tmp_path):
    expected = _make_object(tmp_path, "data/registry", "capabilities", "demo", "1.0.0")

    path, source = resolve_registry_object(tmp_path, "capabilities", "demo", "1.0.0")

    assert path == expected
    assert source == "data"


def test_resolves_from_config_when_only_config_has_it(tmp_path):
    expected = _make_object(tmp_path, "config/app_registry", "capabilities", "demo", "1.0.0")

    path, source = resolve_registry_object(tmp_path, "capabilities", "demo", "1.0.0")

    assert path == expected
    assert source == "config"


def test_data_shadows_config_for_same_name(tmp_path):
    _make_object(tmp_path, "config/app_registry", "capabilities", "demo", "1.0.0")
    data_path = _make_object(tmp_path, "data/registry", "capabilities", "demo", "2.0.0")

    # config only has 1.0.0; data has a presence (2.0.0) for this name, so
    # resolution uses the data tree exclusively - it must not fall back to
    # config's 1.0.0 even though the requested version isn't in data/.
    with pytest.raises(RegistryObjectNotFoundError):
        resolve_registry_object(tmp_path, "capabilities", "demo", "1.0.0")

    path, source = resolve_registry_object(tmp_path, "capabilities", "demo", "2.0.0")
    assert path == data_path
    assert source == "data"


def test_raises_when_absent_from_both(tmp_path):
    with pytest.raises(RegistryObjectNotFoundError):
        resolve_registry_object(tmp_path, "capabilities", "missing", "1.0.0")


def test_model_profiles_never_falls_back_to_config(tmp_path):
    (tmp_path / "config/app_registry/model-profiles/demo").mkdir(parents=True)
    (tmp_path / "config/app_registry/model-profiles/demo/1.0.0.yaml").write_text("x: 1\n")

    with pytest.raises(RegistryObjectNotFoundError):
        resolve_registry_object(tmp_path, "model-profiles", "demo", "1.0.0")


def test_skills_resolve_to_skill_md(tmp_path):
    expected = _make_object(
        tmp_path, "data/registry", "skills", "demo", "1.0.0", is_skill=True
    )

    path, source = resolve_registry_object(tmp_path, "skills", "demo", "1.0.0")

    assert path == expected
    assert source == "data"
