from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

import yaml

from equilibrium.ControllerRegistry import ControllerRegistry
from equilibrium.JsonResourceStore import JsonResourceStore
from equilibrium.Namespace import Namespace
from equilibrium.Resource import GenericResource, Resource
from equilibrium.ResourceController import ResourceController
from equilibrium.ResourceRegistry import ResourceRegistry
from equilibrium.ResourceStore import ResourceStore
from equilibrium.ResourceTypeRegistry import ResourceTypeRegistry
from equilibrium.ServiceRegistry import ServiceRegistry

__all__ = ["ResourceContext"]
T = TypeVar("T")
logger = logging.getLogger(__name__)
DEFAULT_NAMESPACE = "default"


class ResourceContext:
    """
    The controller context is the main entry point for managing

    * Resource controllers
    * Resource types
    * Resources
    * Resource state
    * Resource events [ Todo ]
    """

    store: ResourceStore
    services: ServiceRegistry
    controllers: ControllerRegistry
    resource_types: ResourceTypeRegistry
    resources: ResourceRegistry

    @dataclass
    class InMemoryBackend:
        """Constructor for creating a context with an in-memory backend."""

        max_lock_duration: float | None = 5.0

    @dataclass
    class JsonBackend:
        """Constructor for creating a context with a JSON backend."""

        directory: PathLike[str] | str
        max_lock_duration: float | None = 5.0

    @classmethod
    def create(cls, backend: InMemoryBackend | JsonBackend) -> ResourceContext:
        match backend:
            case cls.InMemoryBackend(max_lock_duration):
                # TODO(@NiklasRosenstein): Actually implement an in-memory backend.
                tempdir = TemporaryDirectory()
                logger.debug("using temporary directory for in-memory backend: %r", tempdir.name)
                atexit.register(tempdir.cleanup)
                return cls(JsonResourceStore(Path(tempdir.name), max_lock_duration))
            case cls.JsonBackend(directory, max_lock_duration):
                logger.debug("using JSON backend: %r", directory)
                return cls(JsonResourceStore(Path(directory), max_lock_duration))
            case _:
                raise TypeError(f"invalid backend type {backend!r}")

    def __init__(self, store: ResourceStore, default_namespace: str = DEFAULT_NAMESPACE) -> None:
        self.store = store
        self.services = ServiceRegistry(store)
        self.controllers = ControllerRegistry()
        self.resource_types = ResourceTypeRegistry()
        self.resource_types.register(Namespace)
        self.resources = ResourceRegistry(
            store, self.resource_types, self.controllers, self.services, default_namespace
        )

    def load_manifest(self, path: PathLike[str] | str) -> list[GenericResource]:
        """
        Loads a YAML file containing resource manifests into the store.
        """

        resources = []
        with Path(path).open() as fp:
            for payload in yaml.safe_load_all(fp):
                resource = Resource.of(payload)
                resources.append(self.resources.put(resource))
        return resources

    def reconcile(self) -> None:
        self.controllers.reconcile(ResourceController.Context(self.resources, self.services))
