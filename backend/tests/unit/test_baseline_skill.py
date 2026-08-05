import pytest

from awf.registry.skill import (
    SkillValidationError,
    directory_digest,
    load_skill,
    parse_skill,
)


def test_parse_minimal_skill():
    skill = parse_skill(
        {"name": "pdf-processing", "description": "Extract PDF text. Use when handling PDFs."},
        body="Step 1. Do the thing.",
        version="1.0.0",
    )
    assert skill.name == "pdf-processing"
    assert skill.description == "Extract PDF text. Use when handling PDFs."
    assert skill.body == "Step 1. Do the thing."
    assert skill.ref == "pdf-processing@1.0.0"


def test_parse_rejects_uppercase_name():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "PDF-Processing", "description": "x"})


def test_parse_rejects_leading_hyphen():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "-pdf", "description": "x"})


def test_parse_rejects_doubled_hyphen():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "pdf--processing", "description": "x"})


def test_parse_rejects_missing_description():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "pdf-processing"})


def test_parse_rejects_description_over_1024_chars():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "x", "description": "a" * 1025})


def test_parse_rejects_compatibility_over_500_chars():
    with pytest.raises(SkillValidationError):
        parse_skill({"name": "x", "description": "d", "compatibility": "a" * 501})


def test_parse_optional_fields():
    skill = parse_skill(
        {
            "name": "pdf-processing",
            "description": "x",
            "license": "Apache-2.0",
            "compatibility": "Requires git",
            "metadata": {"author": "example-org"},
            "allowed-tools": "Bash(git:*) Read",
        }
    )
    assert skill.license == "Apache-2.0"
    assert skill.compatibility == "Requires git"
    assert skill.metadata == {"author": "example-org"}
    assert skill.allowed_tools == "Bash(git:*) Read"


def test_load_real_skill_file(tmp_path):
    skill_dir = tmp_path / "skills" / "demo-skill" / "1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: A minimal real skill.\n---\n\nDo the thing.\n"
    )
    skill = load_skill(skill_dir / "SKILL.md")
    assert skill.ref == "demo-skill@1.0.0"
    assert skill.body == "Do the thing."


def test_load_rejects_name_directory_mismatch(tmp_path):
    skill_dir = tmp_path / "skills" / "demo-skill" / "1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: wrong-name\ndescription: x\n---\n\nbody\n")
    with pytest.raises(SkillValidationError):
        load_skill(skill_dir / "SKILL.md")


@pytest.mark.live
def test_load_the_real_shipped_demo_skill(repo_file_present, repo_root):
    relative_path = "data/registry/skills/demo-skill/1.0.0/SKILL.md"
    if not repo_file_present(relative_path):
        pytest.skip("demo-skill fixture not present on this host")
    skill = load_skill(repo_root / relative_path)
    assert skill.ref == "demo-skill@1.0.0"


def test_directory_digest_is_deterministic_and_content_sensitive(tmp_path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: x\ndescription: d\n---\n\nbody\n")
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "run.sh").write_text("echo hi\n")

    digest_a = directory_digest(skill_dir)
    digest_b = directory_digest(skill_dir)
    assert digest_a == digest_b

    (skill_dir / "scripts" / "run.sh").write_text("echo bye\n")
    digest_c = directory_digest(skill_dir)
    assert digest_c != digest_a
