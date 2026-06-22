"""Discover profiles with cron jobs and cache job lists for the global scheduler."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

from core.cron.models import CronJob
from core.cron.store import CronStore, jobs_path

logger = logging.getLogger(__name__)

DISCOVERY_INTERVAL_S = 300.0
_SKIP_PROFILE_DIRS = frozenset({"global"})


class CronProfileIndex:
    """Lazy index of per-profile cron jobs, keyed by jobs.json mtime."""

    def __init__(self, *, discovery_interval_s: float = DISCOVERY_INTERVAL_S) -> None:
        self._discovery_interval_s = discovery_interval_s
        self._last_full_scan = 0.0
        self._cache: dict[str, tuple[float, list[CronJob]]] = {}

    def invalidate(self, profile: str) -> None:
        self._cache.pop(profile, None)

    def warm_profile(self, profile: str) -> None:
        if _profile_has_jobs(profile):
            self._load_profile(profile, force=True)
        else:
            self.invalidate(profile)

    def scan_profiles_with_jobs(self) -> list[str]:
        from cli.core import profiles_dir

        root = profiles_dir()
        if not root.exists():
            return []

        from core.profile.names import ProfileNameError, validate_profile_name

        found: list[str] = []
        for item in root.iterdir():
            if not item.is_dir() or item.name in _SKIP_PROFILE_DIRS:
                continue
            try:
                validate_profile_name(item.name)
            except ProfileNameError:
                continue
            if _profile_has_jobs(item.name):
                found.append(item.name)
        return sorted(found)

    def refresh_known_profiles(self) -> None:
        now = time.monotonic()
        if (
            self._last_full_scan > 0
            and now - self._last_full_scan < self._discovery_interval_s
        ):
            return
        for profile in self.scan_profiles_with_jobs():
            self._load_profile(profile, force=True)
        stale = [p for p in self._cache if not jobs_path(p).exists()]
        for profile in stale:
            self._cache.pop(profile, None)
        self._last_full_scan = now

    def iter_enabled_jobs(self) -> Iterator[tuple[str, list[CronJob]]]:
        self.refresh_known_profiles()
        for profile in sorted(self._cache):
            jobs = self._get_jobs(profile)
            if jobs:
                yield profile, jobs

    def refresh_all_next_runs(self) -> None:
        for profile in self.scan_profiles_with_jobs():
            try:
                CronStore(profile).refresh_all_next_runs()
                self._load_profile(profile, force=True)
            except Exception:
                logger.exception("Failed to refresh cron next_run for profile=%s", profile)

    def _get_jobs(self, profile: str) -> list[CronJob]:
        path = jobs_path(profile)
        if not path.exists():
            self._cache.pop(profile, None)
            return []
        mtime = path.stat().st_mtime
        cached = self._cache.get(profile)
        if cached and cached[0] == mtime:
            return cached[1]
        return self._load_profile(profile)

    def _load_profile(self, profile: str, *, force: bool = False) -> list[CronJob]:
        path = jobs_path(profile)
        if not path.exists():
            self._cache.pop(profile, None)
            return []
        try:
            mtime = path.stat().st_mtime
        except OSError:
            self._cache.pop(profile, None)
            return []

        if not force:
            cached = self._cache.get(profile)
            if cached and cached[0] == mtime:
                return cached[1]

        if not _profile_has_jobs(profile):
            self._cache.pop(profile, None)
            return []

        jobs = CronStore(profile).list_jobs(enabled_only=True)
        self._cache[profile] = (mtime, jobs)
        return jobs


_index: CronProfileIndex | None = None


def get_profile_index() -> CronProfileIndex:
    global _index
    if _index is None:
        interval = float(
            __import__("os").environ.get("HOLIX_CRON_DISCOVERY_INTERVAL", DISCOVERY_INTERVAL_S)
        )
        _index = CronProfileIndex(discovery_interval_s=interval)
    return _index


def invalidate_profile(profile: str) -> None:
    get_profile_index().warm_profile(profile)


def _profile_has_jobs(profile: str) -> bool:
    path = jobs_path(profile)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    jobs = data.get("jobs")
    return isinstance(jobs, list) and bool(jobs)