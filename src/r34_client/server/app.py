import logging
import threading
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from r34_client.api.client import Rule34Client
from r34_client.core.db import LocalFavoritesStore
from r34_client.core.settings import SettingsStore, AppSettings
from r34_client.core.models import Post, TagSuggestion
from r34_client.core.download_manager import DownloadManager
from r34_client.api.flaresolverr import FlareSolverrFavoritesClient
from r34_client.sync.favorites_sync import sync_remote_favorites
from r34_client.api.scraping import fetch_friend_favorites

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("r34_api_server")

app = FastAPI(title="R34 Client API Bridge")

# Enable CORS for Tauri frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate stores
settings_store = SettingsStore()
db_store = LocalFavoritesStore()
download_manager = DownloadManager(db_store)

# In-memory sync status tracking
class SyncStatus:
    def __init__(self):
        self.is_running = False
        self.last_run_debug = ""
        self.last_run_error = ""
        self.success = False

sync_status = SyncStatus()


@app.on_event("startup")
def startup_event():
    try:
        from r34_client.api.flaresolverr.launcher import start_flaresolverr_container
        settings = settings_store.load()
        thread = threading.Thread(
            target=start_flaresolverr_container,
            args=(settings.flaresolverr_url,),
            daemon=True
        )
        thread.start()
        logger.info("Triggered FlareSolverr container startup in background thread.")
    except Exception as e:
        logger.warning("Failed to trigger FlareSolverr startup on server startup: %s", e)


def get_client() -> Rule34Client:
    settings = settings_store.load()
    if not settings.user_id or not settings.api_key:
        raise HTTPException(status_code=400, detail="API credentials are not configured.")
    return Rule34Client(
        user_id=settings.user_id,
        api_key=settings.api_key,
    )


def serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "tags": post.tags,
        "rating": post.rating,
        "score": post.score,
        "width": post.width,
        "height": post.height,
        "file_size": post.file_size,
        "source": post.source,
        "md5": post.md5,
        "preview_url": post.preview_url,
        "sample_url": post.sample_url,
        "file_url": post.file_url,
        "created_at": post.created_at,
        "page_url": post.page_url,
        "best_preview_url": post.best_preview_url,
        "download_url": post.download_url,
        "dimensions": post.dimensions,
        "file_name": post.file_name,
        "tags_text": post.tags_text,
    }


def serialize_tag(tag: TagSuggestion) -> dict:
    return {
        "value": tag.value,
        "label": tag.label,
        "count": tag.count,
        "display_text": tag.display_text,
    }


# Models for Pydantic requests
class SettingsUpdate(BaseModel):
    user_id: str
    api_key: str
    website_username: Optional[str] = ""
    website_password: Optional[str] = ""
    download_directory: Optional[str] = ""
    page_size: Optional[int] = 50
    flaresolverr_enabled: Optional[bool] = False
    flaresolverr_url: Optional[str] = "http://127.0.0.1:8191"
    sync_conflict_strategy: Optional[str] = "merge"
    background_sync_interval_minutes: Optional[int] = 0
    download_naming_template: Optional[str] = "{id}"
    download_path_template: Optional[str] = ""
    download_use_sample: Optional[bool] = False
    download_sidecar_enabled: Optional[bool] = False
    download_sidecar_format: Optional[str] = "json"
    download_max_retries: Optional[int] = 3


class PostPayload(BaseModel):
    id: int
    tags: List[str]
    rating: str
    score: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    source: str
    md5: str
    preview_url: str
    sample_url: str
    file_url: str
    created_at: str


class CollectionCreate(BaseModel):
    name: str


class CollectionAssign(BaseModel):
    post_ids: List[int]


class FriendPayload(BaseModel):
    user_id: str
    display_name: str
    notes: Optional[str] = ""


# Settings Endpoint
@app.get("/api/settings")
def get_settings():
    s = settings_store.load()
    return {
        "user_id": s.user_id,
        "api_key": s.api_key,
        "website_username": s.website_username,
        "website_password": s.website_password,
        "download_directory": s.download_directory or settings_store.default_download_directory(),
        "page_size": s.page_size,
        "flaresolverr_enabled": s.flaresolverr_enabled,
        "flaresolverr_url": s.flaresolverr_url,
        "sync_conflict_strategy": s.sync_conflict_strategy,
        "background_sync_interval_minutes": s.background_sync_interval_minutes,
        "download_naming_template": s.download_naming_template,
        "download_path_template": s.download_path_template,
        "download_use_sample": s.download_use_sample,
        "download_sidecar_enabled": s.download_sidecar_enabled,
        "download_sidecar_format": s.download_sidecar_format,
        "download_max_retries": s.download_max_retries,
        "has_credentials": s.has_credentials,
    }


@app.post("/api/settings")
def update_settings(payload: SettingsUpdate):
    s = AppSettings(
        user_id=payload.user_id,
        api_key=payload.api_key,
        website_username=payload.website_username,
        website_password=payload.website_password,
        download_directory=payload.download_directory,
        page_size=payload.page_size,
        flaresolverr_enabled=payload.flaresolverr_enabled,
        flaresolverr_url=payload.flaresolverr_url,
        sync_conflict_strategy=payload.sync_conflict_strategy,
        background_sync_interval_minutes=payload.background_sync_interval_minutes,
        download_naming_template=payload.download_naming_template,
        download_path_template=payload.download_path_template,
        download_use_sample=payload.download_use_sample,
        download_sidecar_enabled=payload.download_sidecar_enabled,
        download_sidecar_format=payload.download_sidecar_format,
        download_max_retries=payload.download_max_retries,
    )
    settings_store.save(s)
    return {"status": "ok"}


# Search & Autocomplete Endpoints
@app.get("/api/search")
def search_posts(tags: str = "all", page: int = 0, limit: int = 50):
    client = get_client()
    try:
        posts = client.search_posts(tags, page, limit)
        return [serialize_post(p) for p in posts]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/autocomplete")
def autocomplete_tags(prefix: str = "") -> List[dict]:
    client = get_client()
    try:
        suggestions = client.autocomplete_tags(prefix)
        return [serialize_tag(s) for s in suggestions]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Favorites Endpoints
@app.get("/api/favorites")
def list_favorites(limit: Optional[int] = None, collection: Optional[str] = None):
    try:
        favorites = db_store.list_favorites(limit=limit, collection_name=collection)
        return [serialize_post(p) for p in favorites]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites")
def add_favorite(payload: PostPayload):
    try:
        post = Post.from_payload(payload.model_dump())
        db_store.add_favorite(post)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/favorites/{post_id}")
def remove_favorite(post_id: int):
    try:
        db_store.remove_favorite(post_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Collections Endpoints
@app.get("/api/collections")
def list_collections():
    try:
        return db_store.list_collections()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/collections")
def create_collection(payload: CollectionCreate):
    try:
        normalized = db_store.create_collection(payload.name)
        return {"status": "ok", "name": normalized}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/collections/{name}")
def delete_collection(name: str):
    try:
        db_store.delete_collection(name)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/collections/{name}/posts")
def assign_posts_to_collection(name: str, payload: CollectionAssign):
    try:
        count = db_store.assign_posts_to_collection(payload.post_ids, name)
        return {"status": "ok", "assigned": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/collections/{name}/posts")
def remove_posts_from_collection(name: str, payload: CollectionAssign):
    try:
        count = db_store.remove_posts_from_collection(payload.post_ids, name)
        return {"status": "ok", "removed": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Friends Endpoints
@app.get("/api/friends")
def list_friends():
    try:
        return db_store.list_friends()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/friends")
def add_friend(payload: FriendPayload):
    try:
        db_store.add_friend(payload.user_id, payload.display_name, payload.notes)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/friends/{user_id}")
def remove_friend(user_id: str):
    try:
        db_store.remove_friend(user_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Download Endpoint
@app.post("/api/download")
def download_post(payload: PostPayload):
    try:
        post = Post.from_payload(payload.model_dump())
        settings = settings_store.load()
        dest = download_manager.download_post(post, settings)
        if dest:
            return {"status": "downloaded", "path": str(dest)}
        else:
            return {"status": "already_downloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Sync Endpoints
def run_sync_in_background():
    sync_status.is_running = True
    sync_status.last_run_debug = "Sync started."
    sync_status.last_run_error = ""
    sync_status.success = False

    settings = settings_store.load()

    def log_debug(title, content):
        sync_status.last_run_debug += f"\n[{title}]: {content}"

    def log_error(err):
        sync_status.last_run_error += f"\n{err}"

    def make_client(s):
        if not s.flaresolverr_enabled:
            return None
        return FlareSolverrFavoritesClient(
            user_id=s.user_id,
            api_key=s.api_key,
            solver_url=s.flaresolverr_url,
            website_username=s.website_username,
            website_password=s.website_password,
            timeout=20,
            max_timeout_ms=20000,
        )

    try:
        posts, fallback_used = sync_remote_favorites(
            settings=settings,
            local_favorites=db_store,
            make_sync_client=make_client,
            log_sync_debug=log_debug,
            on_sync_error=log_error,
        )
        sync_status.success = not fallback_used
        sync_status.last_run_debug += "\nSync completed successfully."
    except Exception as e:
        sync_status.last_run_error += f"\nUnexpected sync exception: {e}"
        sync_status.success = False
    finally:
        sync_status.is_running = False


@app.post("/api/sync/run")
def start_sync(background_tasks: BackgroundTasks):
    if sync_status.is_running:
        return {"status": "already_running"}
    background_tasks.add_task(run_sync_in_background)
    return {"status": "started"}


@app.get("/api/sync/status")
def get_sync_status():
    return {
        "is_running": sync_status.is_running,
        "debug": sync_status.last_run_debug,
        "error": sync_status.last_run_error,
        "success": sync_status.success,
    }


# Friend Favorites Scraping Endpoint
@app.get("/api/friends/{user_id}/favorites")
def get_friend_favorites(user_id: str, page: int = 0):
    client = get_client()
    settings = settings_store.load()
    try:
        posts = fetch_friend_favorites(
            client=client,
            user_id=user_id,
            flare_solver_url=settings.flaresolverr_url if settings.flaresolverr_enabled else "",
            page=page,
        )
        return [serialize_post(p) for p in posts]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
