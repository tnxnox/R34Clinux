from __future__ import annotations

import urllib.parse

RULE34_WEB_BASE_URL = "https://rule34.xxx"
RULE34_API_BASE_URL = "https://api.rule34.xxx/index.php"
RULE34_AUTOCOMPLETE_URL = "https://api.rule34.xxx/autocomplete.php"
RULE34_WIMG_HOST = "wimg.rule34.xxx"
RULE34_IMG_HOST = "img.rule34.xxx"


def favorites_view_url(user_id: str, page: int = 0) -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=view&id={urllib.parse.quote(user_id.strip(), safe='')}&pid={page}"


def favorites_list_url() -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=list"


def account_home_url() -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=account&s=home"


def account_login_url() -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=account&s=login&code=00"


def add_favorite_public_url(post_id: int) -> str:
    return f"{RULE34_WEB_BASE_URL}/public/addfav.php?id={int(post_id)}"


def add_favorite_web_url(post_id: int) -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=add&id={int(post_id)}"


def delete_favorite_web_url(post_id: int) -> str:
    return f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=delete&id={int(post_id)}&return_pid=0"
