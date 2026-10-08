"""Owner-scoped, durable personal memories and tasks.

Owner identifiers are opaque, case-sensitive values supplied by the caller.
They are never inferred from stored content or normalized into another owner.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator, TypedDict


class Memory(TypedDict):
    id: int
    text: str


class Task(TypedDict):
    id: int
    title: str
    done: bool


def _validate_text(value: str, field: str, limit: int, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{field} must be a string of at most {limit} characters")
    if not allow_blank and not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value


def _validate_id(item_id: int) -> int:
    if type(item_id) is not int or not 0 < item_id < 2**63:
        raise ValueError("item_id must be a positive SQLite integer")
    return item_id


class PersonalStore:
    """SQLite store with one short-lived connection per operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS personal_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL,
                    text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS personal_memories_owner
                    ON personal_memories(owner, id);
                CREATE TABLE IF NOT EXISTS personal_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL,
                    title TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
                );
                CREATE INDEX IF NOT EXISTS personal_tasks_owner
                    ON personal_tasks(owner, done, id);
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def remember(self, owner: str, text: str) -> Memory:
        owner = _validate_text(owner, "owner", 128)
        text = _validate_text(text, "text", 2000)
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO personal_memories(owner, text) VALUES (?, ?)", (owner, text)
            )
            return {"id": int(cursor.lastrowid), "text": text}

    def recall(self, owner: str, query: str = "") -> list[Memory]:
        owner = _validate_text(owner, "owner", 128)
        query = _validate_text(query, "query", 200, allow_blank=True).strip()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, text FROM personal_memories "
                "WHERE owner = ? AND instr(text, ?) > 0 ORDER BY id", (owner, query)
            ).fetchall()
        return [{"id": row["id"], "text": row["text"]} for row in rows]

    def forget(self, owner: str, item_id: int) -> bool:
        owner = _validate_text(owner, "owner", 128)
        item_id = _validate_id(item_id)
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM personal_memories WHERE owner = ? AND id = ?", (owner, item_id)
            )
            return cursor.rowcount == 1

    def add_task(self, owner: str, title: str) -> Task:
        owner = _validate_text(owner, "owner", 128)
        title = _validate_text(title, "title", 300)
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO personal_tasks(owner, title) VALUES (?, ?)", (owner, title)
            )
            return {"id": int(cursor.lastrowid), "title": title, "done": False}

    def list_tasks(self, owner: str, include_done: bool = False) -> list[Task]:
        owner = _validate_text(owner, "owner", 128)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, title, done FROM personal_tasks "
                "WHERE owner = ? AND (? OR done = 0) ORDER BY id", (owner, include_done)
            ).fetchall()
        return [{"id": row["id"], "title": row["title"], "done": bool(row["done"])} for row in rows]

    def complete_task(self, owner: str, item_id: int) -> bool:
        owner = _validate_text(owner, "owner", 128)
        item_id = _validate_id(item_id)
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE personal_tasks SET done = 1 WHERE owner = ? AND id = ? AND done = 0",
                (owner, item_id),
            )
            return cursor.rowcount == 1
