from concurrent.futures import ThreadPoolExecutor

import pytest

from src.personal_store import PersonalStore


@pytest.fixture
def store(tmp_path):
    return PersonalStore(tmp_path / "personal.sqlite3")


def test_memories_persist_and_are_isolated(tmp_path):
    path = tmp_path / "nested" / "personal.sqlite3"
    store = PersonalStore(path)
    memory = store.remember("alice", "나는 커피를 좋아해")
    assert memory == {"id": memory["id"], "text": "나는 커피를 좋아해"}
    assert PersonalStore(path).recall("alice", "커피") == [memory]
    assert store.recall("bob") == []
    assert not store.forget("bob", memory["id"])
    assert store.recall("alice") == [memory]
    assert store.forget("alice", memory["id"])
    assert not store.forget("alice", memory["id"])
    assert PersonalStore(path).recall("alice") == []


def test_tasks_persist_and_completion_is_owner_scoped(tmp_path):
    path = tmp_path / "personal.sqlite3"
    store = PersonalStore(path)
    task = store.add_task("alice", "화분 물 주기")
    assert task == {"id": task["id"], "title": "화분 물 주기", "done": False}
    assert PersonalStore(path).list_tasks("alice") == [task]
    assert store.list_tasks("bob", include_done=True) == []
    assert not store.complete_task("bob", task["id"])
    assert store.list_tasks("alice") == [task]
    assert store.complete_task("alice", task["id"])
    assert not store.complete_task("alice", task["id"])
    assert PersonalStore(path).list_tasks("alice") == []
    assert store.list_tasks("alice", include_done=True) == [dict(task, done=True)]


def test_search_treats_sql_metacharacters_as_literal_data(store):
    special = store.remember("alice", "100%_done ' OR 1=1 --")
    store.remember("alice", "ordinary")
    store.remember("bob", "100%_done ' OR 1=1 --")
    assert store.recall("alice", "%_") == [special]
    assert store.recall("alice", "' OR 1=1 --") == [special]
    assert store.recall("alice' OR 1=1 --") == []


def test_owner_identity_is_preserved(store):
    memory = store.remember("alice", "private")
    assert store.recall(" alice") == []
    assert store.recall("ALICE") == []
    assert store.recall("alice") == [memory]


@pytest.mark.parametrize("owner", ["", "  \t", "x" * 129, None, 7])
@pytest.mark.parametrize("operation", [
    lambda s, o: s.remember(o, "text"),
    lambda s, o: s.recall(o),
    lambda s, o: s.forget(o, 1),
    lambda s, o: s.add_task(o, "title"),
    lambda s, o: s.list_tasks(o),
    lambda s, o: s.complete_task(o, 1),
])
def test_invalid_owners_are_rejected(store, owner, operation):
    with pytest.raises(ValueError):
        operation(store, owner)


@pytest.mark.parametrize("method, value", [
    ("remember", ""), ("remember", " \n"), ("remember", "x" * 2001),
    ("remember", None), ("add_task", ""), ("add_task", "\t"),
    ("add_task", "x" * 301), ("add_task", 1),
    ("recall", "x" * 201), ("recall", None),
])
def test_invalid_content_is_rejected(store, method, value):
    with pytest.raises(ValueError):
        getattr(store, method)("alice", value)


def test_valid_length_boundaries_and_blank_search(store):
    owner = "o" * 128
    memory = store.remember(owner, "x" * 2000)
    task = store.add_task(owner, "t" * 300)
    assert store.recall(owner, "x" * 200) == [memory]
    assert store.recall(owner, " \t") == [memory]
    assert store.list_tasks(owner) == [task]


@pytest.mark.parametrize("item_id", [True, 0, -1, "1", 1.0, None, 2**63])
@pytest.mark.parametrize("method", ["forget", "complete_task"])
def test_invalid_ids_are_rejected(store, method, item_id):
    with pytest.raises(ValueError):
        getattr(store, method)("alice", item_id)


def test_concurrent_operations_use_independent_connections(store):
    def write(index):
        owner = f"owner-{index % 2}"
        memory = store.remember(owner, f"memory-{index}")
        task = store.add_task(owner, f"task-{index}")
        assert store.complete_task(owner, task["id"])
        return memory["id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(write, range(40)))
    assert len(set(ids)) == 40
    for owner in ("owner-0", "owner-1"):
        assert len(store.recall(owner)) == 20
        assert len(store.list_tasks(owner, include_done=True)) == 20
        assert store.list_tasks(owner) == []
