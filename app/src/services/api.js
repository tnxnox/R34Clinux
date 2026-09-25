import { invoke } from "@tauri-apps/api/core";

export const api = {
  // Settings
  getSettings: () => invoke("get_settings"),
  updateSettings: (payload) => invoke("update_settings", { payload }),

  // Search & Tags
  searchPosts: ({ tags, page, limit }) =>
    invoke("search_posts", { tags, page, limit }),
  getPostById: (id) => invoke("get_post_by_id", { id }),
  autocompleteTags: (prefix) => invoke("autocomplete_tags", { prefix }),
  getTagsWithTypes: ({ postId, tags }) =>
    invoke("get_tags_with_types", { postId, tags }),
  cancelTagFetching: () => invoke("cancel_tag_fetching"),

  // Favorites
  listFavorites: ({ limit, collection } = {}) =>
    invoke("list_favorites", { limit, collection }),
  addFavorite: (post) => invoke("add_favorite", { post }),
  removeFavorite: (postId) => invoke("remove_favorite", { postId }),

  // Collections
  listCollections: () => invoke("list_collections"),
  createCollection: (name) => invoke("create_collection", { name }),
  deleteCollection: (name) => invoke("delete_collection", { name }),
  assignPostsToCollection: (name, posts) =>
    invoke("assign_posts_to_collection", { name, posts }),

  // Friends
  listFriends: () => invoke("list_friends"),
  addFriend: ({ userId, displayName, notes }) =>
    invoke("add_friend", { userId, displayName, notes }),
  removeFriend: (userId) => invoke("remove_friend", { userId }),
  getFriendFavorites: ({ userId, page }) =>
    invoke("get_friend_favorites", { userId, page }),

  // Downloads
  downloadPost: (post) => invoke("download_post", { post }),
  getDownloadedPath: ({ postId, md5 = "" }) =>
    invoke("get_downloaded_path", { postId, md5 }),

  // Sync & Mutations
  getSyncStatus: () => invoke("get_sync_status"),
  getMutationProgress: () => invoke("get_mutation_progress"),
  startSync: () => invoke("start_sync"),
};

export default api;
