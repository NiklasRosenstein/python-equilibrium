from __future__ import annotations

import logging
from os import PathLike
from pathlib import Path
from typing import Any, TypeVar

import yaml
from nr.proxy import proxy

from equilibrium.core.AdmissionController import AdmissionController
from equilibrium.core.JsonResourceStore import JsonResourceStore
from equilibrium.core.Namespace import Namespace
from equilibrium.core.Resource import Resource
from equilibrium.core.ResourceController import ResourceController
from equilibrium.core.ResourceStore import ResourceStore

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ControllerContext:
    """
    The controller context is the main entry point for managing

    * Resource controllers
    * Resource types
    * Resources
    * Resource state
    * Resource events [ Todo ]
    """

    resources: ResourceStore

    @classmethod
    def with_json_backend(cls, directory: PathLike[str] | str) -> ControllerContext:
        return cls(JsonResourceStore(Path(directory)))

    def __init__(self, store: ResourceStore, default_namespace_name: str = "default") -> None:
        self._resource_controllers: list[ResourceController] = []
        self._admission_controllers: list[AdmissionController] = []
        self._resource_types: dict[str, dict[str, type[Resource.Spec]]] = {}
        self._default_namespace_name = default_namespace_name
        self.resources = store
        self.register_resource_type(Namespace)

    def register_resource_type(self, resource_type: type[Resource.Spec]) -> None:
        self._resource_types.setdefault(resource_type.API_VERSION, {})[resource_type.KIND] = resource_type

    def register_controller(self, controller: ResourceController | AdmissionController) -> None:
        controller.resources = proxy(lambda: self.resources)  # type: ignore[assignment]
        if isinstance(controller, AdmissionController):
            self._admission_controllers.append(controller)
        if isinstance(controller, ResourceController):
            self._resource_controllers.append(controller)

    def put_resource(self, resource: Resource[Any]) -> None:
        """
        Put a resource into the resource store. This will trigger the admission controllers. Any admission controller
        may complain about the resource, mutate it and raise an exception if necessary. This exception will propagate
        to the caller of #put_resource().

        Note that this method does not permit a resource which has state. This method can only be used to update a
        resource's metadata and spec. The state will be inherited from the existing resource, if it exists.
        """

        # Validate that the resource type is registered.
        if resource.apiVersion not in self._resource_types:
            raise ValueError(f"Unknown resource type: {resource.apiVersion}/{resource.kind}")
        if resource.kind not in self._resource_types[resource.apiVersion]:
            raise ValueError(f"Unknown resource type: {resource.apiVersion}/{resource.kind}")

        if resource.state is not None:
            raise ValueError("Cannot put a resource with state into the resource store")

        uri = resource.uri
        resource_spec = self._resource_types[resource.apiVersion][resource.kind]
        with self.resources.enter(self.resources.LockRequest.from_uri(uri)) as lock:
            # Give the resource the default namespace.
            if uri.namespace is None and resource_spec.NAMESPACED:
                resource.metadata = resource.metadata.with_namespace(self._default_namespace_name)
                uri = resource.uri
            resource_spec.check_uri(resource.uri, do_raise=True)

            # Pass resource through admission controllers.
            generic_resource = resource.into_generic()
            for controller in self._admission_controllers:
                new_resource = controller.admit_resource(generic_resource)
                if new_resource.uri != uri:
                    raise RuntimeError(f"Admission controller mutated resource URI (controller: {controller!r})")
                generic_resource = new_resource

            # Inherit the state of an existing resource, if it exists.
            existing_resource = self.resources.get(lock, uri)
            generic_resource.state = existing_resource.state if existing_resource else None

            logger.debug("Putting resource '%s'.", uri)
            self.resources.put(lock, generic_resource)

    def delete_resource(self, uri: Resource.URI, *, do_raise: bool = True, force: bool = False) -> bool:
        """
        Mark a resource as deleted. A controller must take care of actually removing it from the system.
        If *force* is True, the resource will be removed from the store immediately. If the resource is not found,
        a #Resource.NotFound error will be raised.

        If *do_raise* is False, this method will return False if the resource was not found.
        """

        with self.resources.enter(self.resources.LockRequest.from_uri(uri)) as lock:
            resource = self.resources.get(lock, uri)
            if resource is None:
                logger.info("Could not delete Resource '%s', not found.", uri)
                if do_raise:
                    raise Resource.NotFound(uri)
                return False
            if force:
                logger.info("Force deleting resource '%s'.", uri)
                self.resources.delete(lock, uri)
            elif resource.deletion_marker is None:
                logger.info("Marking resource '%s' as deleted.", uri)
                resource.deletion_marker = Resource.DeletionMarker()
            else:
                logger.info("Resource '%s' is already marked as deleted.", uri)
            return True

    def load_manifest(self, path: PathLike[str] | str) -> None:
        with Path(path).open() as fp:
            for payload in yaml.safe_load_all(fp):
                resource = Resource.of(payload)
                self.put_resource(resource)

    def reconcile_once(self) -> None:
        for controller in self._resource_controllers:
            logger.debug(f"Reconciling {controller!r}")
            controller.reconcile_once()
