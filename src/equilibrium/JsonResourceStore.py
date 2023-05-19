from __future__ import annotations

import json
from contextlib import contextmanager
from logging import getLogger
from pathlib import Path
from threading import Condition, get_ident as get_thread_id
from time import perf_counter
from typing import Any, Callable, Iterable, Iterator, TypeAlias
from uuid import uuid4

import databind.json

from equilibrium.Namespace import Namespace
from equilibrium.Resource import GenericResource, Resource, match_labels
from equilibrium.ResourceStore import ResourceStore

logger = getLogger(__name__)

__all__ = ["JsonResourceStore"]


class JsonResourceStore(ResourceStore):
    """
    This class manages resources and their state in a hierarchy of JSON files: `namespace/apiVersion/kind/name.json`.
    Only a single process should access the directory at a time.

    For simplification, the store does not currently support granular locking. It is only possible to lock the entire
    store for reading or writing. This is sufficient for small use cases, but will not scale to large deployments.
    """

    LockID: TypeAlias = ResourceStore.LockID

    # This is the name of the directory where namespaceless resources are stored. It is not a valid namespace name.
    NAMESPACELESS = "@namespaceless"

    def __init__(
        self,
        directory: Path,
        max_lock_duration: float | None = 5.0,
        gettime: Callable[[], float] = perf_counter,
        make_lock_id: Callable[[], LockID] = lambda: ResourceStore.LockID(str(uuid4())),
    ) -> None:
        """
        :param directory: The directory where resources are stored.
        :param max_lock_duration: The maximum duration that a lock can be held for. If None, locks will never expire.
        :param gettime: A function that returns the current time in seconds.
        """

        self._directory = directory
        self._max_lock_duration = max_lock_duration
        self._gettime = gettime
        self._make_lock_id = make_lock_id

        self._cache: dict[Resource.URI, GenericResource] = {}
        self._condition = Condition()
        self._lock_thread_id: int | None = None
        self._lock_reentry_counter: int = 0
        self._lock_id: ResourceStore.LockID | None = None
        self._expires_at: float | None = None

    def _get_resource_path(self, uri: Resource.URI) -> Path:
        """
        Get the path to the JSON file where the resource entry is stored.
        """

        if uri.namespace is None:
            namespace = self.NAMESPACELESS
        else:
            namespace = uri.namespace

        return self._directory / namespace / uri.apiVersion.replace("/", "_") / uri.kind / f"{uri.name}.json"

    def _get_namespaces(self) -> dict[str, Resource[Namespace]]:
        """
        Loads all namespace resources and returns a set of all namespace names.
        """

        logger.debug("Loading namespaces from disk.")
        namespaces: dict[str, Resource[Namespace]] = {}

        search_request = self.SearchRequest(
            apiVersion=Namespace.API_VERSION,
            kind=Namespace.KIND,
            namespace=None,
        )
        for uri in self._search_unsafe(search_request):
            resource = self._get_unsafe(uri)
            if resource is None:
                logger.warning("Namespace resource %s is missing.", uri.name)
            else:
                namespaces[resource.metadata.name] = resource.into(Namespace)

        return namespaces

    def _get_unsafe(self, uri: Resource.URI) -> GenericResource | None:
        if uri in self._cache:
            logger.debug("Returning resource '%s' from cache.", uri)
            return self._cache[uri]

        path = self._get_resource_path(uri)
        try:
            with path.open() as fp:
                raw_data = json.load(fp)
                resource = databind.json.load(raw_data, GenericResource)
        except FileNotFoundError:
            return None
        else:
            logger.debug("Loaded resource '%s' from disk.", uri)
            self._cache[uri] = resource
            return resource

    @property
    def _namespaces(self) -> dict[str, Resource[Namespace]]:
        """
        Pull-through cache for the namespaces set.
        """

        self._namespaces_cache: dict[str, Resource[Namespace]]
        if not hasattr(self, "_namespaces_cache"):
            self._namespaces_cache = self._get_namespaces()
        return self._namespaces_cache

    def _search_unsafe(self, request: ResourceStore.SearchRequest) -> Iterable[Resource.URI]:
        """
        Performs a search for resources without locking.
        """

        logger.debug("Searching for resources: %s", request)

        apiVersion = request.apiVersion
        if apiVersion is not None:
            apiVersion = apiVersion.replace("/", "_")

        for namespace_path in self._directory.iterdir():
            # logger.debug("  Checking namespace '%s'.", namespace_path)
            if not namespace_path.is_dir():
                continue

            namespace_name: str | None = namespace_path.name
            if namespace_name == self.NAMESPACELESS:
                namespace_name = None

            if request.namespace != "" and namespace_name != request.namespace:
                continue

            for apiVersion_path in namespace_path.iterdir():
                # logger.debug("  Checking apiVersion '%s'.", apiVersion_path)
                if not apiVersion_path.is_dir():
                    continue
                if apiVersion is not None and apiVersion_path.name != apiVersion:
                    continue

                for kind_path in apiVersion_path.iterdir():
                    # logger.debug("  Checking kind '%s'.", kind_path)
                    if not kind_path.is_dir():
                        continue
                    if request.kind is not None and kind_path.name != request.kind:
                        continue

                    for name_path in kind_path.iterdir():
                        # logger.debug("  Checking name '%s'.", name_path)
                        if not name_path.is_file() or name_path.suffix != ".json":
                            continue
                        if request.name is not None and name_path.stem != request.name:
                            continue

                        uri = Resource.URI(
                            apiVersion_path.name.replace("_", "/"),
                            kind_path.name,
                            namespace_name,
                            name_path.stem,
                        )

                        if request.labels is not None:
                            resource = self._get_unsafe(uri)
                            assert resource is not None, uri
                            if not match_labels(resource.metadata.labels, request.labels):
                                continue

                        yield uri

    @contextmanager
    def _checked(self, lock: LockID) -> Iterator[None]:
        """
        Validates the lock and keeps the internal state of the resource store locked.
        """

        with self._condition:
            if self._lock_id != lock:
                raise self.LockExpired(f"Lock {lock!r} has expired")
            yield

    def acquire_lock(self, request: ResourceStore.LockRequest) -> LockID | None:
        current_thread_id = get_thread_id()

        def _wait_for_release() -> bool:
            if self._expires_at is not None and self._gettime() >= self._expires_at:
                self._lock_thread_id = None
                self._lock_reentry_counter = 0
                self._lock_id = None
                self._expires_at = None
                return True
            if self._lock_id is None:
                return True
            if self._lock_thread_id == current_thread_id:
                return True
            return False

        with self._condition:
            if not request.block and not _wait_for_release():
                return None
            elif request.block and not self._condition.wait_for(_wait_for_release, timeout=request.timeout):
                return None

            if self._lock_thread_id == current_thread_id:
                self._lock_reentry_counter += 1
                # NOTE: We don't want to refresh the lock expiration time here. Otherwise, you can easily run into
                #       one thread constantly refreshing the lock.
            else:
                self._lock_thread_id = current_thread_id
                self._lock_reentry_counter = 0
                self._lock_id = self._make_lock_id()
                if self._max_lock_duration is not None:
                    self._expires_at = self._gettime() + self._max_lock_duration

            return self._lock_id

    def release_lock(self, lock: LockID) -> None:
        # TODO(@NiklasRosenstein): Keep track of expired locks to distinguish between expired and invalid locks.
        current_thread_id = get_thread_id()

        with self._condition:
            if self._lock_id != lock:
                raise self.LockExpired(f"Lock {lock!r} has expired")

            if self._lock_thread_id != current_thread_id:
                logger.error(
                    "Thread %s is not holding lock %s, releasing it regardless.",
                    current_thread_id,
                    lock,
                    stack_info=True,
                )

            if self._lock_reentry_counter > 0:
                self._lock_reentry_counter -= 1
            else:
                self._lock_thread_id = None
                self._lock_reentry_counter = 0
                self._lock_id = None
                self._expires_at = None

    def check_lock(self, lock: LockID, *, valid_for: float | None = None) -> bool:
        with self._condition:
            if self._lock_id != lock:
                return False
            if self._expires_at is None or valid_for is None:
                return True
            return self._gettime() + valid_for < self._expires_at

    def namespaces(self) -> list[Resource[Namespace]]:
        return list(self._namespaces.values())

    def search(self, lock: LockID, request: ResourceStore.SearchRequest) -> list[Resource.URI]:
        with self._checked(lock):
            return list(self._search_unsafe(request))

    def put(self, lock: LockID, resource: Resource[Any]) -> None:
        """
        Put a resource entry into the store.
        """

        is_namespace = Namespace.check_uri(resource.uri)

        with self._checked(lock):
            logger.debug("Persisting resource '%s'", resource.uri)
            # If the resource is namespaced, the associated namespace must exist.
            namespace = resource.metadata.namespace
            if namespace and namespace not in self._namespaces:
                raise ValueError(f"Namespace '{namespace}' does not exist")

            path = self._get_resource_path(resource.uri)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w") as fp:
                data = databind.json.dump(resource.into_generic(), GenericResource)
                json.dump(data, fp)
                self._cache[resource.uri] = resource
                if is_namespace:
                    self._namespaces[resource.metadata.name] = resource

    def get(self, lock: LockID, uri: Resource.URI) -> GenericResource | None:
        """
        Get a resource entry from the store.
        """

        with self._checked(lock):
            return self._get_unsafe(uri)

    def delete(self, lock: LockID, uri: Resource.URI) -> bool:
        """
        Delete a resource entry from the store. If the resource points to a namespace resource, the namespace
        must be empty before it can be deleted.
        """

        with self._checked(lock):
            # Validate that the namespace is empty before it can be deleted.
            is_namespace = Namespace.check_uri(uri)
            if is_namespace and any(self._search_unsafe(self.SearchRequest(namespace=uri.name))):
                raise self.NamespaceNotEmpty(uri.name)

            logger.debug("Deleting resource %s from disk.", uri)
            self._cache.pop(uri, None)
            if is_namespace:
                self._namespaces.pop(uri.name, None)

            path = self._get_resource_path(uri)
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                removed = False

            if removed:
                # Remove empty parent directories.
                relative_parts = path.relative_to(self._directory).parts[:-1]
                for i in range(len(relative_parts), 0, -1):
                    path = self._directory / Path(*relative_parts[:i])
                    if not any(path.iterdir()):
                        path.rmdir()

            return removed
