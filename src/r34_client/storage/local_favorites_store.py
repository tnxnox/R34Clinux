from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from ..core.models import Post


def _default_database_path() -> Path:
    try:
        from PySide6.QtCore import QStandardPaths  # type: ignore

        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if app_data:
            root = Path(app_data)
        else:
            root = Path.home() / ".local" / "share" / "R34LinuxClient"
    except Exception:
        root = Path.home() / ".local" / "share" / "R34LinuxClient"

    root.mkdir(parents=True, exist_ok=True)
    return root / "favorites.db"


class LocalFavoritesStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or _default_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY,
                    tags TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    score INTEGER,
                    width INTEGER,
                    height INTEGER,
                    file_size INTEGER,
                    source TEXT NOT NULL,
                    md5 TEXT NOT NULL,
                    preview_url TEXT NOT NULL,
                    sample_url TEXT NOT NULL,
                    file_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    favorited_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_favorites_favorited_at ON favorites (favorited_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_collections (
                    name TEXT PRIMARY KEY
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_collection_items (
                    collection_name TEXT NOT NULL,
                    post_id INTEGER NOT NULL,
                    PRIMARY KEY (collection_name, post_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_favorite_collection_items_post_id "
                "ON favorite_collection_items (post_id)"
            )
            connection.commit()

    def list_favorites(self, limit: int | None = None, collection_name: str | None = None) -> list[Post]:
        if collection_name:
            query = (
                "SELECT f.id, f.tags, f.rating, f.score, f.width, f.height, f.file_size, f.source, f.md5, "
                "f.preview_url, f.sample_url, f.file_url, f.created_at "
                "FROM favorites f "
                "INNER JOIN favorite_collection_items ci ON ci.post_id = f.id "
                "WHERE ci.collection_name = ? "
                "ORDER BY f.favorited_at DESC"
            )
            params: tuple[object, ...] = (collection_name,)
        else:
            query = (
                "SELECT id, tags, rating, score, width, height, file_size, source, md5, "
                "preview_url, sample_url, file_url, created_at "
                "FROM favorites ORDER BY favorited_at DESC"
            )
            params = ()

        if limit is not None:
            query = f"{query} LIMIT ?"
            params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        posts: list[Post] = []
        for row in rows:
            payload = {
                "id": row["id"],
                "tags": row["tags"],
                "rating": row["rating"],
                "score": row["score"],
                "width": row["width"],
                "height": row["height"],
                "file_size": row["file_size"],
                "source": row["source"],
                "md5": row["md5"],
                "preview_url": row["preview_url"],
                "sample_url": row["sample_url"],
                "file_url": row["file_url"],
                "created_at": row["created_at"],
            }
            posts.append(Post.from_payload(payload))
        return posts

    def add_favorite(self, post: Post) -> None:
        with self._connect() as connection:
            self._upsert(connection, post)
            connection.commit()

    def replace_all(self, posts: list[Post]) -> None:
        with self._connect() as connection:
            keep_ids = {int(post.id) for post in posts}
            if keep_ids:
                placeholders = ", ".join("?" for _ in keep_ids)
                connection.execute(
                    f"DELETE FROM favorites WHERE id NOT IN ({placeholders})",
                    tuple(sorted(keep_ids)),
                )
                connection.execute(
                    f"DELETE FROM favorite_collection_items WHERE post_id NOT IN ({placeholders})",
                    tuple(sorted(keep_ids)),
                )
            else:
                connection.execute("DELETE FROM favorites")
                connection.execute("DELETE FROM favorite_collection_items")

            for post in posts:
                self._upsert(connection, post)
            connection.commit()

    def remove_favorite(self, post_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM favorite_collection_items WHERE post_id = ?", (post_id,))
            connection.execute("DELETE FROM favorites WHERE id = ?", (post_id,))
            connection.commit()

    def list_collections(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM favorite_collections ORDER BY lower(name)").fetchall()
        return [str(row["name"]) for row in rows if row["name"]]

    def create_collection(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Collection name cannot be empty.")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO favorite_collections (name) VALUES (?)",
                (normalized,),
            )
            connection.commit()
        return normalized

    def delete_collection(self, name: str) -> None:
        normalized = name.strip()
        if not normalized:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM favorite_collection_items WHERE collection_name = ?", (normalized,))
            connection.execute("DELETE FROM favorite_collections WHERE name = ?", (normalized,))
            connection.commit()

    def assign_posts_to_collection(self, post_ids: list[int], collection_name: str) -> int:
        normalized = collection_name.strip()
        if not normalized:
            raise ValueError("Collection name cannot be empty.")
        unique_ids = sorted({int(post_id) for post_id in post_ids})
        if not unique_ids:
            return 0

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO favorite_collections (name) VALUES (?)",
                (normalized,),
            )

            existing_rows = connection.execute(
                f"SELECT id FROM favorites WHERE id IN ({', '.join('?' for _ in unique_ids)})",
                tuple(unique_ids),
            ).fetchall()
            existing_ids = {int(row["id"]) for row in existing_rows}

            for post_id in sorted(existing_ids):
                connection.execute(
                    "INSERT OR IGNORE INTO favorite_collection_items (collection_name, post_id) VALUES (?, ?)",
                    (normalized, post_id),
                )
            connection.commit()
        return len(existing_ids)

    def remove_posts_from_collection(self, post_ids: list[int], collection_name: str) -> int:
        normalized = collection_name.strip()
        unique_ids = sorted({int(post_id) for post_id in post_ids})
        if not normalized or not unique_ids:
            return 0

        with self._connect() as connection:
            before = connection.total_changes
            connection.execute(
                f"DELETE FROM favorite_collection_items WHERE collection_name = ? "
                f"AND post_id IN ({', '.join('?' for _ in unique_ids)})",
                (normalized, *unique_ids),
            )
            connection.commit()
            return connection.total_changes - before

    def _upsert(self, connection: sqlite3.Connection, post: Post) -> None:
        connection.execute(
            """
            INSERT INTO favorites (
                id, tags, rating, score, width, height, file_size, source, md5,
                preview_url, sample_url, file_url, created_at, favorited_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tags=excluded.tags,
                rating=excluded.rating,
                score=excluded.score,
                width=excluded.width,
                height=excluded.height,
                file_size=excluded.file_size,
                source=excluded.source,
                md5=excluded.md5,
                preview_url=excluded.preview_url,
                sample_url=excluded.sample_url,
                file_url=excluded.file_url,
                created_at=excluded.created_at,
                favorited_at=excluded.favorited_at
            """,
            (
                post.id,
                post.tags_text,
                post.rating,
                post.score,
                post.width,
                post.height,
                post.file_size,
                post.source,
                post.md5,
                post.preview_url,
                post.sample_url,
                post.file_url,
                post.created_at,
                int(time.time()),
            ),
        )
