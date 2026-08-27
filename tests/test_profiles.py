import pytest

from abhayleads import profiles


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path, monkeypatch):
    """Every test gets its own fake app-data dir so profiles.json and
    profile folders never touch the real ~/AbhayLeads."""
    monkeypatch.setattr("abhayleads.profiles.default_paths", lambda: (tmp_path / "config", tmp_path))
    return tmp_path


def test_no_profiles_initially():
    assert profiles.list_profiles() == []
    assert profiles.get_active_profile() is None


def test_create_profile_makes_it_active_and_writes_a_config(tmp_path):
    config_path, db_path = profiles.create_profile("Abhay")

    assert profiles.list_profiles() == ["Abhay"]
    assert profiles.get_active_profile() == "Abhay"
    assert config_path.exists()
    assert "product:" in config_path.read_text()
    assert db_path.parent == config_path.parent


def test_second_profile_does_not_become_active(tmp_path):
    profiles.create_profile("Abhay")
    profiles.create_profile("OtherCo")

    assert sorted(profiles.list_profiles()) == ["Abhay", "OtherCo"]
    assert profiles.get_active_profile() == "Abhay"


def test_create_duplicate_profile_raises(tmp_path):
    profiles.create_profile("Abhay")
    with pytest.raises(ValueError):
        profiles.create_profile("Abhay")


def test_create_profile_rejects_bad_names(tmp_path):
    with pytest.raises(ValueError):
        profiles.create_profile("   ")
    with pytest.raises(ValueError):
        profiles.create_profile("bad/name")


def test_set_active_profile(tmp_path):
    profiles.create_profile("Abhay")
    profiles.create_profile("OtherCo")

    profiles.set_active_profile("OtherCo")
    assert profiles.get_active_profile() == "OtherCo"


def test_set_active_profile_unknown_raises(tmp_path):
    with pytest.raises(ValueError):
        profiles.set_active_profile("NoSuchProfile")


def test_delete_profile_keeps_files_by_default(tmp_path):
    config_path, _ = profiles.create_profile("Abhay")
    profiles.delete_profile("Abhay")

    assert profiles.list_profiles() == []
    assert config_path.exists()  # files kept unless delete_files=True


def test_delete_profile_with_delete_files_removes_them(tmp_path):
    config_path, _ = profiles.create_profile("Abhay")
    profiles.delete_profile("Abhay", delete_files=True)

    assert not config_path.exists()


def test_delete_active_profile_falls_back_to_another(tmp_path):
    profiles.create_profile("Abhay")
    profiles.create_profile("OtherCo")
    profiles.set_active_profile("Abhay")

    profiles.delete_profile("Abhay")
    assert profiles.get_active_profile() == "OtherCo"


def test_delete_last_profile_leaves_no_active(tmp_path):
    profiles.create_profile("Abhay")
    profiles.delete_profile("Abhay")
    assert profiles.get_active_profile() is None


def test_migrates_legacy_single_install_into_default_profile(tmp_path):
    # Simulate a pre-profiles install: config.yaml and leads.db directly
    # under the app data dir, no profiles.json yet.
    legacy_config_dir = tmp_path / "config"
    legacy_config_dir.mkdir(parents=True)
    (legacy_config_dir / "config.yaml").write_text("product:\n  name: Abhay\n  keywords: [foo]\n")
    (tmp_path / "leads.db").write_bytes(b"fake-sqlite-bytes")

    assert profiles.list_profiles() == ["default"]
    assert profiles.get_active_profile() == "default"

    config_path, db_path = profiles.profile_paths("default")
    assert "foo" in config_path.read_text()
    assert db_path.read_bytes() == b"fake-sqlite-bytes"
    # Original files must be untouched, not moved.
    assert (legacy_config_dir / "config.yaml").exists()
    assert (tmp_path / "leads.db").exists()
