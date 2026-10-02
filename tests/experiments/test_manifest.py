"""Tests for `ibqn.experiments.manifests` (Fase H3.2)."""
import pytest

from ibqn.experiments.campaigns import CampaignSpec
from ibqn.experiments.manifests import (
    build_initial_manifest,
    manifest_path,
    read_manifest,
    update_manifest_progress,
    write_manifest,
)


def _spec(**overrides):
    kwargs = dict(
        name="C01", description="test campaign", scenario_file="s.yaml", intents=["i.yaml"],
        seeds=[42, 1042], strategies={"routing": ["shortest_hop_count", "least_loss"]},
    )
    kwargs.update(overrides)
    return CampaignSpec(**kwargs)


@pytest.mark.unit
def test_read_manifest_missing_is_none(tmp_path):
    assert read_manifest(manifest_path(tmp_path, "C01")) is None


@pytest.mark.unit
def test_build_initial_manifest_has_required_fields():
    manifest = build_initial_manifest(_spec(), campaign_file="configs/campaigns/C01.yaml", expected_trials=4)
    for key in [
        "campaign", "description", "created_at", "updated_at", "project_git_commit", "sequence_git_commit",
        "python_version", "platform", "dependencies", "campaign_file", "scenario_files", "intent_files",
        "parameter_grid", "strategies", "seeds", "expected_trials", "completed_trials", "skipped_trials",
        "failed_trials", "output_files",
    ]:
        assert key in manifest, f"manifest missing required field '{key}'"
    assert manifest["expected_trials"] == 4
    assert manifest["completed_trials"] == 0
    assert manifest["seeds"] == [42, 1042]


@pytest.mark.unit
def test_write_then_read_manifest_round_trips(tmp_path):
    path = manifest_path(tmp_path, "C01")
    manifest = build_initial_manifest(_spec(), campaign_file="c.yaml", expected_trials=4)
    write_manifest(path, manifest)
    loaded = read_manifest(path)
    assert loaded["campaign"] == "C01"
    assert loaded["expected_trials"] == 4


@pytest.mark.unit
def test_update_manifest_progress_updates_counts_and_timestamp(tmp_path):
    path = manifest_path(tmp_path, "C01")
    manifest = build_initial_manifest(_spec(), campaign_file="c.yaml", expected_trials=4)
    write_manifest(path, manifest)

    updated = update_manifest_progress(
        path, completed_trials=2, skipped_trials=1, failed_trials=0, output_files=["results/raw/C01/trials.csv"],
    )
    assert updated["completed_trials"] == 2
    assert updated["skipped_trials"] == 1
    assert updated["output_files"] == ["results/raw/C01/trials.csv"]
    assert updated["updated_at"] >= updated["created_at"]

    reloaded = read_manifest(path)
    assert reloaded["completed_trials"] == 2


@pytest.mark.unit
def test_update_manifest_progress_without_existing_manifest_raises(tmp_path):
    path = manifest_path(tmp_path, "does-not-exist")
    with pytest.raises(FileNotFoundError):
        update_manifest_progress(path, completed_trials=1, skipped_trials=0, failed_trials=0, output_files=[])


@pytest.mark.unit
def test_write_manifest_retries_while_another_process_holds_the_file(tmp_path, monkeypatch):
    """On Windows, replacing a file that an antivirus scan or an editor has
    open raises PermissionError for a few milliseconds - that must not
    abort a campaign that rewrites its manifest after every trial."""
    from ibqn.experiments import manifests

    real_replace, calls = manifests.os.replace, []

    def flaky_replace(source, destination):
        calls.append(source)
        if len(calls) <= 3:
            raise PermissionError(5, "Access is denied")
        real_replace(source, destination)

    monkeypatch.setattr(manifests.os, "replace", flaky_replace)
    monkeypatch.setattr(manifests, "REPLACE_RETRY_DELAY_S", 0.0)
    target = tmp_path / "manifests" / "campaign.json"

    manifests.write_manifest(target, {"campaign": "X", "completed_trials": 7})

    assert len(calls) == 4
    assert manifests.read_manifest(target) == {"campaign": "X", "completed_trials": 7}


@pytest.mark.unit
def test_write_manifest_gives_up_when_the_file_stays_locked(tmp_path, monkeypatch):
    from ibqn.experiments import manifests

    def locked(source, destination):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(manifests.os, "replace", locked)
    monkeypatch.setattr(manifests, "REPLACE_RETRY_DELAY_S", 0.0)
    with pytest.raises(PermissionError):
        manifests.write_manifest(tmp_path / "campaign.json", {"campaign": "X"})
