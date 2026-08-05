import { apiGet, apiSend } from "./client";

export type FavoriteItem = {
  ts_code: string;
  name: string;
  created_at: string;
};

export function fetchFavorites() {
  return apiGet<FavoriteItem[]>("/api/v1/favorites");
}

export function addFavorite(tsCode: string) {
  return apiSend<{ ok: boolean }>("/api/v1/favorites", "POST", { ts_code: tsCode });
}

export function removeFavorite(tsCode: string) {
  return apiSend<{ ok: boolean }>(
    `/api/v1/favorites/${encodeURIComponent(tsCode)}`,
    "DELETE",
  );
}
