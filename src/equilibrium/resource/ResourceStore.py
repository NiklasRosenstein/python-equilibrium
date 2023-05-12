from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, NewType

from equilibrium.resource.Namespace import Namespace
from equilibrium.resource.Resource import GenericResource, Resource

__all__ = ["ResourceStore"]


class ResourceStore(ABC):
    """Provides an API for storing and loading resources."""

    LockID = NewType("LockID", str)

    @dataclass
    class LockRequest:
        apiVersion: str | None = None
        kind: str | None = None
        namespace: str | None = ""
        name: str | None = None
        block: bool = True
        timeout: float | None = None

        @classmethod
        def from_uri(
            cls, uri: Resource.URI, block: bool = True, timeout: float | None = None
        ) -> ResourceStore.LockRequest:
            return cls(
                apiVersion=uri.apiVersion,
                kind=uri.kind,
                namespace=uri.namespace,
                name=uri.name,
                block=block,
                timeout=timeout,
            )

    class LockExpired(RuntimeError):
        """
        This exception is raised when a lock is expired.
        """

    @dataclass
    class SearchRequest:
        apiVersion: str | None = None
        kind: str | None = None
        namespace: str | None = ""
        name: str | None = None
        labels: dict[str, str] | None = None

    class NamespaceNotEmpty(RuntimeError):
        """
        This exception is raised when attempting to delete a namespace that is not empty.
        """

    @contextmanager
    def enter(self, request: LockRequest) -> Iterator[LockID]:
        """
        Enter a context in which a lock is acquired and a transaction ID is available. If a lock cannot be acquired
        until the timeout expires then a #TimeoutError exception is raised.
        """

        lock = self.acquire_lock(request)
        if lock is None:
            raise TimeoutError(f"Could not acquire lock (request: {request})")
        try:
            yield lock
        finally:
            self.release_lock(lock)

    @abstractmethod
    def acquire_lock(self, request: LockRequest) -> LockID | None:
        """
        Acquire a lock on the store for any resource that matches the specified filters.

        The *namespace* parameter accepts an empty string to delinate between a lock for unnamespaced resources (None),
        namespaced resources in a specific namespace (str), or namespaced resources in all namespaces ("").

        If *block* is True then this method will block until the lock is acquired. If *timeout* is specified then this
        method will block for at most *timeout* seconds before returning. If *block* is False then this method will
        return immediatey, and return a lock handle if the lock was acquired, or `False` otherwise.

        The resource store may decide to invalidate a lock if it is open for too long. If this happens then any
        subsequent calls to `get`, `put`, or `delete` with the returned lock ID will raise a #LockExpired exception.
        State that has been modified while the lock was valid is guaranteed to be persisted.
        """

    @abstractmethod
    def release_lock(self, lock: LockID) -> None:
        """Release a lock on the store. Is a no-op if the lock is expired."""

    @abstractmethod
    def check_lock(self, lock: LockID, *, valid_for: float | None = None) -> bool:
        """
        Check if a lock is still valid. If *valid_for* is specified, the lock must be valid for at least the
        specified number of seconds for this method to return True.
        """

    @abstractmethod
    def namespaces(self) -> list[Resource[Namespace]]:
        """Iterate over all namespaces."""

    @abstractmethod
    def search(self, lock: LockID, request: SearchRequest) -> list[Resource.URI]:
        """
        Search for resources matching the given filter criteria.

        Because resources may not be namespaced, the *namespace* parameter accepts an empty string to delinate between
        a search for unnamespaced resources (None), a search for resources in a specific namespace (str), or a search
        for resources in all namespaces ("").
        """

    @abstractmethod
    def get(self, lock: LockID, uri: Resource.URI) -> GenericResource | None:
        """Retrieve a resource by URI. Return None if the resource does not exist."""

    @abstractmethod
    def put(self, lock: LockID, resource: GenericResource) -> None:
        """Commit a resource to the store. Note for namespaced resources the namespace must already exist."""

    @abstractmethod
    def delete(self, lock: LockID, uri: Resource.URI) -> bool:
        """Delete a resource from the store. Returns `False` if the resource didn't exist."""
