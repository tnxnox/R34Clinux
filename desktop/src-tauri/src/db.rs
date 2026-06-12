use crate::models::{Friend, Post};
use rusqlite::{params, Connection, Result};
use std::env;
use std::path::PathBuf;
use std::time::SystemTime;

fn default_database_path() -> PathBuf {
    let root = if let Ok(xdg_data) = env::var("XDG_DATA_HOME") {
        PathBuf::from(xdg_data).join("R34LinuxClient")
    } else {
        let home = env::var("HOME").unwrap_or_else(|_| "/".to_string());
        PathBuf::from(home)
            .join(".local")
            .join("share")
            .join("R34LinuxClient")
    };
    std::fs::create_dir_all(&root).ok();
    root.join("favorites.db")
}

pub struct LocalFavoritesStore {
    database_path: PathBuf,
}

impl LocalFavoritesStore {
    pub fn new(database_path: Option<PathBuf>) -> Self {
        let path = database_path.unwrap_or_else(default_database_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let store = Self {
            database_path: path,
        };
        store
            .init_schema()
            .expect("Failed to initialize database schema");
        store
    }

    fn connect(&self) -> Result<Connection> {
        let conn = Connection::open(&self.database_path)?;
        conn.execute_batch(
            "
            PRAGMA journal_mode = WAL;
            PRAGMA busy_timeout = 30000;
        ",
        )?;
        Ok(conn)
    }

    fn init_schema(&self) -> Result<()> {
        let conn = self.connect()?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS favorites (
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
            )",
            [],
        )?;

        // Migration: Add is_favorite column if it doesn't exist
        let mut check_col = conn.prepare("PRAGMA table_info(favorites)")?;
        let mut rows = check_col.query([])?;
        let mut has_is_favorite = false;
        while let Some(row) = rows.next()? {
            let col_name: String = row.get(1)?;
            if col_name == "is_favorite" {
                has_is_favorite = true;
                break;
            }
        }
        if !has_is_favorite {
            conn.execute(
                "ALTER TABLE favorites ADD COLUMN is_favorite INTEGER DEFAULT 1",
                [],
            )?;
        }

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorites_favorited_at ON favorites (favorited_at DESC)",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS favorite_collections (
                name TEXT PRIMARY KEY
            )",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS favorite_collection_items (
                collection_name TEXT NOT NULL,
                post_id INTEGER NOT NULL,
                PRIMARY KEY (collection_name, post_id)
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorite_collection_items_post_id ON favorite_collection_items (post_id)",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS downloads (
                post_id INTEGER PRIMARY KEY,
                md5 TEXT NOT NULL,
                file_path TEXT NOT NULL,
                downloaded_at INTEGER NOT NULL
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_downloads_md5 ON downloads (md5)",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS friends (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                notes TEXT DEFAULT '',
                added_at INTEGER NOT NULL
            )",
            [],
        )?;

        Ok(())
    }

    pub fn is_downloaded(&self, post_id: i64, md5: &str) -> Result<bool> {
        let conn = self.connect()?;
        let mut stmt =
            conn.prepare("SELECT 1 FROM downloads WHERE post_id = ?1 OR md5 = ?2 LIMIT 1")?;
        let exists = stmt.exists(params![post_id, md5])?;
        Ok(exists)
    }

    pub fn record_download(&self, post_id: i64, md5: &str, file_path: &str) -> Result<()> {
        let conn = self.connect()?;
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        conn.execute(
            "INSERT OR REPLACE INTO downloads (post_id, md5, file_path, downloaded_at) VALUES (?1, ?2, ?3, ?4)",
            params![post_id, md5, file_path, now],
        )?;
        Ok(())
    }

    pub fn list_favorites(
        &self,
        limit: Option<u32>,
        collection_name: Option<&str>,
    ) -> Result<Vec<Post>> {
        let conn = self.connect()?;
        let mut posts = Vec::new();

        match collection_name {
            Some(name) => {
                let query = if let Some(l) = limit {
                    format!(
                        "SELECT f.id, f.tags, f.rating, f.score, f.width, f.height, f.file_size, f.source, f.md5, \
                         f.preview_url, f.sample_url, f.file_url, f.created_at \
                         FROM favorites f \
                         INNER JOIN favorite_collection_items ci ON ci.post_id = f.id \
                         WHERE ci.collection_name = ?1 \
                         ORDER BY f.favorited_at DESC LIMIT {}",
                        l
                    )
                } else {
                    "SELECT f.id, f.tags, f.rating, f.score, f.width, f.height, f.file_size, f.source, f.md5, \
                     f.preview_url, f.sample_url, f.file_url, f.created_at \
                     FROM favorites f \
                     INNER JOIN favorite_collection_items ci ON ci.post_id = f.id \
                     WHERE ci.collection_name = ?1 \
                     ORDER BY f.favorited_at DESC".to_string()
                };
                let mut stmt = conn.prepare(&query)?;
                let mapped = stmt.query_map([name], |row| self.row_to_post(row))?;
                for p in mapped {
                    posts.push(p?);
                }
            }
            None => {
                let query = if let Some(l) = limit {
                    format!(
                        "SELECT id, tags, rating, score, width, height, file_size, source, md5, \
                         preview_url, sample_url, file_url, created_at \
                         FROM favorites WHERE is_favorite = 1 ORDER BY favorited_at DESC LIMIT {}",
                        l
                    )
                } else {
                    "SELECT id, tags, rating, score, width, height, file_size, source, md5, \
                     preview_url, sample_url, file_url, created_at \
                     FROM favorites WHERE is_favorite = 1 ORDER BY favorited_at DESC"
                        .to_string()
                };
                let mut stmt = conn.prepare(&query)?;
                let mapped = stmt.query_map([], |row| self.row_to_post(row))?;
                for p in mapped {
                    posts.push(p?);
                }
            }
        };

        Ok(posts)
    }

    fn row_to_post(&self, row: &rusqlite::Row) -> Result<Post> {
        let tags_str: String = row.get(1)?;
        let tags = tags_str.split_whitespace().map(|s| s.to_string()).collect();
        Ok(Post {
            id: row.get(0)?,
            tags,
            rating: row.get(2)?,
            score: row.get(3)?,
            width: row.get(4)?,
            height: row.get(5)?,
            file_size: row.get(6)?,
            source: row.get(7)?,
            md5: row.get(8)?,
            preview_url: row.get(9)?,
            sample_url: row.get(10)?,
            file_url: row.get(11)?,
            created_at: row.get(12)?,
        })
    }

    pub fn add_favorite(&self, post: &Post) -> Result<()> {
        self.upsert_many(std::slice::from_ref(post))
    }

    pub fn upsert_many(&self, posts: &[Post]) -> Result<()> {
        if posts.is_empty() {
            return Ok(());
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;

        {
            let mut stmt = tx.prepare(
                "INSERT INTO favorites (
                    id, tags, rating, score, width, height, file_size, source, md5,
                    preview_url, sample_url, file_url, created_at, favorited_at, is_favorite
                ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, 1)
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
                    is_favorite=1",
            )?;

            for post in posts {
                let tags_str = post.tags.join(" ");
                stmt.execute(params![
                    post.id,
                    tags_str,
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
                    now,
                ])?;
            }
        }

        tx.commit()?;
        Ok(())
    }

    pub fn replace_all(&self, posts: &[Post]) -> Result<()> {
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;

        if !posts.is_empty() {
            let keep_ids: Vec<i64> = posts.iter().map(|p| p.id).collect();
            let placeholders = keep_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");

            // Update favorites not in keep_ids to have is_favorite = 0
            let update_favs_query = format!(
                "UPDATE favorites SET is_favorite = 0 WHERE id NOT IN ({})",
                placeholders
            );
            let mut stmt = tx.prepare(&update_favs_query)?;
            stmt.execute(rusqlite::params_from_iter(keep_ids.iter()))?;

            // Delete favorites that are is_favorite = 0 and not in any collection
            tx.execute(
                "DELETE FROM favorites WHERE is_favorite = 0 AND id NOT IN (SELECT post_id FROM favorite_collection_items)",
                [],
            )?;
        } else {
            tx.execute("UPDATE favorites SET is_favorite = 0", [])?;
            tx.execute(
                "DELETE FROM favorites WHERE is_favorite = 0 AND id NOT IN (SELECT post_id FROM favorite_collection_items)",
                [],
            )?;
        }

        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;

        {
            let mut stmt = tx.prepare(
                "INSERT INTO favorites (
                    id, tags, rating, score, width, height, file_size, source, md5,
                    preview_url, sample_url, file_url, created_at, favorited_at, is_favorite
                ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, 1)
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
                    is_favorite=1",
            )?;

            for post in posts {
                let tags_str = post.tags.join(" ");
                stmt.execute(params![
                    post.id,
                    tags_str,
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
                    now,
                ])?;
            }
        }

        tx.commit()?;
        Ok(())
    }

    pub fn remove_favorite(&self, post_id: i64) -> Result<()> {
        self.remove_favorites(&[post_id])?;
        Ok(())
    }

    pub fn remove_favorites(&self, post_ids: &[i64]) -> Result<u32> {
        if post_ids.is_empty() {
            return Ok(0);
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        let mut removed = 0;

        for chunk in post_ids.chunks(500) {
            let placeholders = chunk.iter().map(|_| "?").collect::<Vec<_>>().join(",");

            // Set is_favorite = 0 for post_ids
            let update_favs = format!(
                "UPDATE favorites SET is_favorite = 0 WHERE id IN ({})",
                placeholders
            );
            let mut stmt = tx.prepare(&update_favs)?;
            stmt.execute(rusqlite::params_from_iter(chunk.iter()))?;

            // Delete favorites if they are is_favorite = 0 and not in any collection
            let delete_favs = format!(
                "DELETE FROM favorites WHERE id IN ({}) AND is_favorite = 0 AND id NOT IN (SELECT post_id FROM favorite_collection_items)",
                placeholders
            );
            let mut stmt = tx.prepare(&delete_favs)?;
            let deleted_chunk = stmt.execute(rusqlite::params_from_iter(chunk.iter()))?;
            removed += deleted_chunk as u32;
        }

        tx.commit()?;
        Ok(removed)
    }

    pub fn list_collections(&self) -> Result<Vec<String>> {
        let conn = self.connect()?;
        let mut stmt =
            conn.prepare("SELECT name FROM favorite_collections ORDER BY lower(name)")?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        let mut collections = Vec::new();
        for r in rows {
            let name = r?;
            if !name.is_empty() {
                collections.push(name);
            }
        }
        Ok(collections)
    }

    pub fn create_collection(&self, name: &str) -> Result<String> {
        let normalized = name.trim().to_string();
        if normalized.is_empty() {
            return Err(rusqlite::Error::InvalidQuery);
        }
        let conn = self.connect()?;
        conn.execute(
            "INSERT OR IGNORE INTO favorite_collections (name) VALUES (?1)",
            params![normalized],
        )?;
        Ok(normalized)
    }

    pub fn delete_collection(&self, name: &str) -> Result<()> {
        let normalized = name.trim();
        if normalized.is_empty() {
            return Ok(());
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;

        // Find which posts are in this collection before deleting
        let mut post_ids = Vec::new();
        {
            let mut stmt = tx.prepare(
                "SELECT post_id FROM favorite_collection_items WHERE collection_name = ?1",
            )?;
            let rows = stmt.query_map([normalized], |row| row.get::<_, i64>(0))?;
            for r in rows {
                post_ids.push(r?);
            }
        }

        tx.execute(
            "DELETE FROM favorite_collection_items WHERE collection_name = ?1",
            params![normalized],
        )?;
        tx.execute(
            "DELETE FROM favorite_collections WHERE name = ?1",
            params![normalized],
        )?;

        // Cleanup orphaned non-favorites
        if !post_ids.is_empty() {
            for chunk in post_ids.chunks(500) {
                let placeholders = chunk.iter().map(|_| "?").collect::<Vec<_>>().join(",");
                let cleanup_query = format!(
                    "DELETE FROM favorites WHERE id IN ({}) AND is_favorite = 0 AND id NOT IN (SELECT post_id FROM favorite_collection_items)",
                    placeholders
                );
                let mut stmt = tx.prepare(&cleanup_query)?;
                stmt.execute(rusqlite::params_from_iter(chunk.iter()))?;
            }
        }

        tx.commit()?;
        Ok(())
    }

    pub fn assign_posts_to_collection(&self, posts: &[Post], collection_name: &str) -> Result<u32> {
        let normalized = collection_name.trim();
        if normalized.is_empty() || posts.is_empty() {
            return Ok(0);
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;

        tx.execute(
            "INSERT OR IGNORE INTO favorite_collections (name) VALUES (?1)",
            params![normalized],
        )?;

        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;

        let mut assigned = 0;
        {
            let mut insert_post_stmt = tx.prepare(
                "INSERT INTO favorites (
                    id, tags, rating, score, width, height, file_size, source, md5,
                    preview_url, sample_url, file_url, created_at, favorited_at, is_favorite
                ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, 0)
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
                    created_at=excluded.created_at",
            )?;

            let mut insert_item_stmt = tx.prepare(
                "INSERT OR IGNORE INTO favorite_collection_items (collection_name, post_id) VALUES (?1, ?2)"
            )?;

            for post in posts {
                let tags_str = post.tags.join(" ");
                insert_post_stmt.execute(params![
                    post.id,
                    tags_str,
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
                    now,
                ])?;

                let rows_affected = insert_item_stmt.execute(params![normalized, post.id])?;
                assigned += rows_affected as u32;
            }
        }

        tx.commit()?;
        Ok(assigned)
    }

    pub fn remove_posts_from_collection(
        &self,
        post_ids: &[i64],
        collection_name: &str,
    ) -> Result<u32> {
        let normalized = collection_name.trim();
        if normalized.is_empty() || post_ids.is_empty() {
            return Ok(0);
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        let mut removed = 0;

        for chunk in post_ids.chunks(500) {
            let placeholders = chunk.iter().map(|_| "?").collect::<Vec<_>>().join(",");
            let query = format!(
                "DELETE FROM favorite_collection_items WHERE collection_name = ?1 AND post_id IN ({})",
                placeholders
            );
            let mut stmt = tx.prepare(&query)?;
            let mut params = vec![normalized.to_string()];
            for &id in chunk {
                params.push(id.to_string());
            }
            let params_ref: Vec<&dyn rusqlite::ToSql> =
                params.iter().map(|s| s as &dyn rusqlite::ToSql).collect();
            let deleted = stmt.execute(params_ref.as_slice())?;
            removed += deleted as u32;

            let cleanup_query = format!(
                "DELETE FROM favorites WHERE id IN ({}) AND is_favorite = 0 AND id NOT IN (SELECT post_id FROM favorite_collection_items)",
                placeholders
            );
            let mut stmt = tx.prepare(&cleanup_query)?;
            stmt.execute(rusqlite::params_from_iter(chunk.iter()))?;
        }

        tx.commit()?;
        Ok(removed)
    }

    pub fn add_friend(&self, user_id: &str, display_name: &str, notes: &str) -> Result<()> {
        let conn = self.connect()?;
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        conn.execute(
            "INSERT OR REPLACE INTO friends (user_id, display_name, notes, added_at) VALUES (?1, ?2, ?3, ?4)",
            params![user_id.trim(), display_name.trim(), notes.trim(), now],
        )?;
        Ok(())
    }

    pub fn remove_friend(&self, user_id: &str) -> Result<()> {
        let conn = self.connect()?;
        conn.execute(
            "DELETE FROM friends WHERE user_id = ?1",
            params![user_id.trim()],
        )?;
        Ok(())
    }

    pub fn list_friends(&self) -> Result<Vec<Friend>> {
        let conn = self.connect()?;
        let mut stmt = conn.prepare("SELECT user_id, display_name, notes, added_at FROM friends ORDER BY lower(display_name)")?;
        let rows = stmt.query_map([], |row| {
            Ok(Friend {
                user_id: row.get(0)?,
                display_name: row.get(1)?,
                notes: row.get(2)?,
                added_at: row.get(3)?,
            })
        })?;
        let mut friends = Vec::new();
        for f in rows {
            friends.push(f?);
        }
        Ok(friends)
    }

    #[allow(dead_code)]
    pub fn get_friend(&self, user_id: &str) -> Result<Option<Friend>> {
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT user_id, display_name, notes, added_at FROM friends WHERE user_id = ?1",
        )?;
        let mut rows = stmt.query_map([user_id.trim()], |row| {
            Ok(Friend {
                user_id: row.get(0)?,
                display_name: row.get(1)?,
                notes: row.get(2)?,
                added_at: row.get(3)?,
            })
        })?;
        if let Some(res) = rows.next() {
            Ok(Some(res?))
        } else {
            Ok(None)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::Post;

    fn temp_db() -> LocalFavoritesStore {
        let mut path = std::env::temp_dir();
        let name = format!(
            "r34_test_{}.db",
            std::time::SystemTime::now()
                .duration_since(std::time::SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        path.push(name);
        LocalFavoritesStore::new(Some(path))
    }

    #[test]
    fn test_db_init_and_favorites() {
        let store = temp_db();

        let post = Post {
            id: 12345,
            tags: vec!["tag1".to_string(), "tag2".to_string()],
            rating: "q".to_string(),
            score: Some(10),
            width: Some(800),
            height: Some(600),
            file_size: Some(123456),
            source: "https://example.com".to_string(),
            md5: "abcde12345".to_string(),
            preview_url: "https://example.com/preview.jpg".to_string(),
            sample_url: "https://example.com/sample.jpg".to_string(),
            file_url: "https://example.com/file.jpg".to_string(),
            created_at: "2026-06-12 12:00:00".to_string(),
        };

        // Add favorite
        store.add_favorite(&post).unwrap();

        // Check is_downloaded
        assert!(!store.is_downloaded(12345, "abcde12345").unwrap());
        store
            .record_download(12345, "abcde12345", "/path/to/file.jpg")
            .unwrap();
        assert!(store.is_downloaded(12345, "abcde12345").unwrap());

        // List favorites
        let favorites = store.list_favorites(None, None).unwrap();
        assert_eq!(favorites.len(), 1);
        assert_eq!(favorites[0].id, 12345);
        assert_eq!(
            favorites[0].tags,
            vec!["tag1".to_string(), "tag2".to_string()]
        );

        // Remove favorite
        store.remove_favorite(12345).unwrap();
        let favorites = store.list_favorites(None, None).unwrap();
        assert_eq!(favorites.len(), 0);

        // Clean up test file
        let _ = std::fs::remove_file(&store.database_path);
    }

    #[test]
    fn test_collections() {
        let store = temp_db();

        // Create collection
        let col_name = store.create_collection("My Collection").unwrap();
        assert_eq!(col_name, "My Collection");

        // List collections
        let collections = store.list_collections().unwrap();
        assert_eq!(collections, vec!["My Collection".to_string()]);

        // Post 999 (favorited)
        let post = Post {
            id: 999,
            tags: vec![],
            rating: "s".to_string(),
            score: None,
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "md5".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        };
        store.add_favorite(&post).unwrap();

        // Post 888 (non-favorited)
        let post_non_fav = Post {
            id: 888,
            tags: vec![],
            rating: "s".to_string(),
            score: None,
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "md5_888".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        };

        // Assign both posts to collection
        let assigned = store
            .assign_posts_to_collection(&[post.clone(), post_non_fav.clone()], "My Collection")
            .unwrap();
        assert_eq!(assigned, 2);

        // List favorites (should only show 999, not 888)
        let favorites = store.list_favorites(None, None).unwrap();
        assert_eq!(favorites.len(), 1);
        assert_eq!(favorites[0].id, 999);

        // List collection (should show both 999 and 888)
        let col_items = store.list_favorites(None, Some("My Collection")).unwrap();
        assert_eq!(col_items.len(), 2);
        assert!(col_items.iter().any(|p| p.id == 999));
        assert!(col_items.iter().any(|p| p.id == 888));

        // Remove favorited post 999 from favorites
        store.remove_favorite(999).unwrap();

        // Favorites should be empty now
        let favorites = store.list_favorites(None, None).unwrap();
        assert_eq!(favorites.len(), 0);

        // Collection should still have both since 999 remains in collection even if unfavorited
        let col_items = store.list_favorites(None, Some("My Collection")).unwrap();
        assert_eq!(col_items.len(), 2);

        // Remove post 888 from collection
        let removed = store
            .remove_posts_from_collection(&[888], "My Collection")
            .unwrap();
        assert_eq!(removed, 1);

        // Collection should have only 999 left
        let col_items = store.list_favorites(None, Some("My Collection")).unwrap();
        assert_eq!(col_items.len(), 1);
        assert_eq!(col_items[0].id, 999);

        // Delete collection
        store.delete_collection("My Collection").unwrap();
        let collections = store.list_collections().unwrap();
        assert_eq!(collections.len(), 0);

        let _ = std::fs::remove_file(&store.database_path);
    }

    #[test]
    fn test_friends() {
        let store = temp_db();

        // Add friend
        store
            .add_friend("friend123", "Nice Friend", "A cool friend")
            .unwrap();

        // Get friend
        let friend = store.get_friend("friend123").unwrap();
        assert!(friend.is_some());
        let f = friend.unwrap();
        assert_eq!(f.user_id, "friend123");
        assert_eq!(f.display_name, "Nice Friend");
        assert_eq!(f.notes, "A cool friend");

        // List friends
        let friends = store.list_friends().unwrap();
        assert_eq!(friends.len(), 1);
        assert_eq!(friends[0].user_id, "friend123");

        // Remove friend
        store.remove_friend("friend123").unwrap();
        let friends = store.list_friends().unwrap();
        assert_eq!(friends.len(), 0);

        let _ = std::fs::remove_file(&store.database_path);
    }
}
