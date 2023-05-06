from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeVar

import yaml

from equilibrium.core.AdmissionController import AdmissionController
from equilibrium.core.JsonResourceStore import JsonResourceStore
from equilibrium.core.Namespace import Namespace
from equilibrium.core.Resource import GenericResource, Resource
from equilibrium.core.ResourceController import ResourceController
from equilibrium.core.ResourceStore import ResourceStore
from equilibrium.core.Service import Service

__all__ = ["Context"]
T = TypeVar("T")
logger = logging.getLogger(__name__)
DEFAULT_NAMESPACE = "default"


class Context:
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
    def create(cls, backend: InMemoryBackend | JsonBackend) -> Context:
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
        self.controllers = ControllerRegistry(self.store, self.services)
        self.resource_types = ResourceTypeRegistry()
        self.resource_types.register(Namespace)
        self.resources = ResourceRegistry(store, self.resource_types, self.controllers, default_namespace)

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


class ControllerRegistry:
    def __init__(self, resources: ResourceStore, services: ServiceRegistry) -> None:
        self._resources = resources
        self._services = services
        self._resource_controllers: list[ResourceController] = []
        self._admission_controllers: list[AdmissionController] = []

    def register(self, controller: ResourceController | AdmissionController) -> None:
        assert isinstance(controller, (ResourceController, AdmissionController))
        controller.resources = self._resources
        controller.services = self._services
        if isinstance(controller, AdmissionController):
            self._admission_controllers.append(controller)
        if isinstance(controller, ResourceController):
            self._resource_controllers.append(controller)

    def admit(self, resource: Resource[Any]) -> Resource[Any]:
        uri = resource.uri
        # Pass resource through admission controllers.
        for controller in self._admission_controllers:
            try:
                new_resource = controller.admit_resource(resource)
            except Exception as e:
                raise Resource.AdmissionFailed(resource.uri, e) from e
            if new_resource.uri != uri:
                raise RuntimeError(f"Admission controller mutated resource URI (controller: {controller!r})")
            if type(new_resource.spec) != type(resource.spec):  # noqa: E721
                raise RuntimeError(f"Admission controller mutated resource spec type (controller: {controller!r})")
            resource = new_resource
        return resource

    def reconcile(self) -> None:
        for controller in self._resource_controllers:
            logger.debug(f"Reconciling {controller!r}")
            controller.reconcile()


class ResourceTypeRegistry:
    def __init__(self) -> None:
        self._resource_types: dict[str, dict[str, type[Resource.Spec]]] = {}

    def __contains__(self, resource_type: Resource.Type) -> bool:
        if resource_type.apiVersion not in self._resource_types:
            return False
        return resource_type.kind in self._resource_types[resource_type.apiVersion]

    def register(self, spec_type: type[Resource.Spec]) -> None:
        self._resource_types.setdefault(spec_type.API_VERSION, {})[spec_type.KIND] = spec_type

    def get(self, resource_type: Resource.Type) -> type[Resource.Spec] | None:
        return self._resource_types.get(resource_type.apiVersion, {}).get(resource_type.kind)


class ServiceRegistry(Service.Provider):
    def __init__(self, resources: ResourceStore) -> None:
        self._resources = resources
        self._services: dict[Resource.Type, dict[Service.Id, Service]] = {}

    def register(self, resource_type: Resource.Type, service: Service) -> None:
        """
        Register a service to the controller for the given resource type.
        """

        service.resources = self._resources
        service.services = self
        services = self._services.setdefault(resource_type, {})
        if service.SERVICE_ID in services:
            raise ValueError(
                f"Service '{service.SERVICE_ID}' is already registered for resource type {resource_type!r}"
            )
        services[service.SERVICE_ID] = service

    def get(self, resource_type: Resource.Type, service_type: type[Service.T]) -> Service.T | None:
        """
        Obtain a service for the given resource type. If the service is not registered, None is returned.
        """

        services = self._services.get(resource_type)
        service = services.get(service_type.SERVICE_ID) if services else None
        if service is not None and not isinstance(service, service_type):
            raise RuntimeError(f"Service '{service_type.SERVICE_ID}' is not of type {service_type!r}")
        return service


class ResourceRegistry:
    """
    A high-level interface to the resource store, which can controls resource admission.
    """

    def __init__(
        self,
        store: ResourceStore,
        resource_types: ResourceTypeRegistry,
        controllers: ControllerRegistry,
        default_namespace: str,
    ) -> None:
        self._store = store
        self._resource_types = resource_types
        self._controllers = controllers
        self._default_namespace = default_namespace

    def get(self, uri: Resource.URI) -> GenericResource | None:
        """
        Get a resource by full URI.
        """

        with self._store.enter(self._store.LockRequest.from_uri(uri)) as lock:
            return self._store.get(lock, uri)

    def put(self, resource: Resource[Any]) -> Resource[Any]:
        """
        Put a resource into the resource store. This will trigger the admission controllers. Any admission controller
        may complain about the resource, mutate it and raise an exception if necessary. This exception will propagate
        to the caller of #put().

        Note that this method does not permit a resource which has state. This method can only be used to update a
        resource's metadata and spec. The state will be inherited from the existing resource, if it exists.
        """

        if resource.state is not None:
            raise ValueError("Cannot put a resource with state into the resource store")

        resource_spec = self._resource_types.get(resource.type)
        if resource_spec is None:
            raise ValueError(f"Unknown resource type: {resource.apiVersion}/{resource.kind}")

        # Ensure that we have the resource in its deserialized (i.e. non-generic) form.
        uri = resource.uri
        resource = resource.into(resource_spec)

        # Validate the resource spec.
        try:
            resource.spec.validate()
        except Exception as e:
            raise Resource.ValidationFailed(resource.uri, e) from e

        # Give the resource the default namespace.
        if uri.namespace is None and resource_spec.NAMESPACED:
            resource.metadata = resource.metadata.with_namespace(self._default_namespace)
            uri = resource.uri
        resource_spec.check_uri(resource.uri, do_raise=True)

        # Check for admission errors.
        resource = self._controllers.admit(resource)

        with self._store.enter(self._store.LockRequest.from_uri(uri)) as lock:
            # Inherit the state of an existing resource, if it exists.
            existing_resource = self._store.get(lock, uri)
            resource.state = existing_resource.state if existing_resource else None

            logger.debug("Putting resource '%s'.", uri)
            self._store.put(lock, resource.into_generic())

        return resource

    def delete(self, uri: Resource.URI, *, do_raise: bool = True, force: bool = False) -> bool:
        """
        Mark a resource as deleted. A controller must take care of actually removing it from the system.
        If *force* is True, the resource will be removed from the store immediately. If the resource is not found,
        a #Resource.NotFound error will be raised.

        If *do_raise* is False, this method will return False if the resource was not found.
        """

        with self._store.enter(self._store.LockRequest.from_uri(uri)) as lock:
            resource = self._store.get(lock, uri)
            if resource is None:
                logger.info("Could not delete Resource '%s', not found.", uri)
                if do_raise:
                    raise Resource.NotFound(uri)
                return False
            if force:
                logger.info("Force deleting resource '%s'.", uri)
                self._store.delete(lock, uri)
            elif resource.deletion_marker is None:
                logger.info("Marking resource '%s' as deleted.", uri)
                resource.deletion_marker = Resource.DeletionMarker()
                self._store.put(lock, resource)
            else:
                logger.info("Resource '%s' is already marked as deleted.", uri)
            return True

    def search(
        self,
        *,
        apiVersion: str | None = None,
        kind: str | None = None,
        namespace: str | None = "",
        name: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[Resource.URI]:
        """
        Search for resources of the given type. If *namespace* is `""`, all namespaces and unnamespaced resources will
        be searched. If *namespace* is `None`, only unnamespaced resources will be searched. If *name* is given, only
        resources with that name will be returned.
        """

        with self._store.enter(self._store.LockRequest(apiVersion, kind, namespace, name)) as lock:
            return list(
                self._store.search(
                    lock,
                    self._store.SearchRequest(
                        apiVersion,
                        kind,
                        namespace,
                        name,
                        labels,
                    ),
                )
            )
