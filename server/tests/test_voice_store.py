from src.voice_id import SpeakerStore


def test_speaker_store_upsert_and_delete(tmp_path):
    store = SpeakerStore(tmp_path)
    store.upsert_profile("alice", sample_count=5, threshold=0.73)
    assert store.list_users() == ["alice"]

    (tmp_path / "alice.npy").write_bytes(b"dummy")
    assert store.delete_profile("alice") is True
    assert store.list_users() == []
    assert not (tmp_path / "alice.npy").exists()
