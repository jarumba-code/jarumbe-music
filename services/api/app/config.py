from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Jarumba Music API"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str = ""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    jamendo_client_id: str = ""
    jamendo_client_secret: str = ""

    # --- API security ----------------------------------------------------
    # Comma-separated list of allowed CORS origins (empty = no cross-origin
    # browser access; the mobile app is native and needs no CORS at all).
    cors_allowed_origins: str = ""
    # Comma-separated list of allowed Host headers (TrustedHost protection).
    # "*" is only acceptable in local development.
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    # Maximum accepted request body size, in bytes (default 64 KiB — a
    # conservative limit for a music-metadata JSON API).
    max_request_body_bytes: int = 64 * 1024

    # --- Rate limiting ----------------------------------------------------
    # Redis connection for the shared, multi-replica rate-limit counters.
    # Empty = in-process fallback counters (single-replica local dev ONLY;
    # not the production source of truth).
    redis_url: str = ""
    # Explicit opt-in to the process-local counter fallback.  A deployed
    # environment (anything other than development/local/test) MUST configure
    # ``redis_url``; it never silently degrades to per-process counters unless
    # this flag is set on purpose.
    rate_limit_allow_memory_fallback: bool = False
    # Redis connection/command timeouts (seconds).  Bounded so an unresponsive
    # Redis can never hold a request open indefinitely.
    redis_connect_timeout_seconds: float = 1.0
    redis_command_timeout_seconds: float = 1.0
    # Global buckets (requests per 60-second window).
    rate_limit_global_anon_per_minute: int = 30
    rate_limit_global_auth_per_minute: int = 120
    # Endpoint-specific buckets (requests per 60-second window).
    rate_limit_auth_per_minute: int = 10
    rate_limit_health_per_minute: int = 60
    rate_limit_music_per_minute: int = 30
    rate_limit_favorites_per_minute: int = 60
    rate_limit_playlists_per_minute: int = 30
    rate_limit_playlist_tracks_per_minute: int = 60
    rate_limit_recently_played_per_minute: int = 60
    rate_limit_profile_per_minute: int = 60
    rate_limit_window_seconds: int = 60

    # --- Trusted proxy policy (client IP resolution) ----------------------
    # Client-supplied forwarding headers are ignored unless this is enabled.
    #
    # ``trust_proxy_headers`` is the master switch: while it is false (the
    # default) ``X-Forwarded-For`` is never consulted, so a client cannot mint
    # a fresh rate-limit bucket by sending a spoofed header.
    trust_proxy_headers: bool = False
    # Which *immediate peers* are trusted reverse proxies.  Accepts IPs
    # (``10.0.0.7``), CIDR ranges (``10.0.0.0/8``) or literal host names as
    # reported by ASGI (e.g. ``testclient`` in tests).  Empty = no peer is
    # trusted even when ``trust_proxy_headers`` is enabled.
    trusted_proxy_ips: str = ""
    # Number of trusted proxy hops at the right-hand end of
    # ``X-Forwarded-For`` that must be skipped when resolving the client IP.
    trusted_proxy_count: int = 1

    # --- Music search cache ----------------------------------------------
    # Short-lived cache for provider search results (metadata only).  The TTL
    # is deliberately small: stream/download URLs are treated as ephemeral and
    # must never be cached long enough to outlive their validity.
    search_cache_ttl_seconds: int = 60
    # Upper bound for the ``q`` search parameter (a longer query is a 422, it
    # is never silently truncated).
    music_search_max_query_length: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def trusted_proxies(self) -> list[str]:
        """Configured trusted-proxy peers (IPs, CIDR ranges or host names)."""
        return [p.strip() for p in self.trusted_proxy_ips.split(",") if p.strip()]

    @property
    def is_local_environment(self) -> bool:
        """True for development/test/local environments.

        Only local environments may use the process-local rate-limit fallback;
        every deployed environment must configure Redis (or set
        ``RATE_LIMIT_ALLOW_MEMORY_FALLBACK=true`` explicitly).
        """
        return self.environment.strip().lower() in {
            "development",
            "dev",
            "local",
            "test",
            "testing",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()