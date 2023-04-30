from __future__ import annotations

import logging
from os import PathLike
from pathlib import Path
from typing import Any, TypeVar

import yaml
from nr.proxy import proxy

from equilibrium.core.AdmissionController import AdmissionController
from equilibrium.core.JsonResourceStore import JsonResourceStore
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

    def __init__(self, store: ResourceStore) -> None:
        self._resource_controllers: list[ResourceController] = []
        self._admission_controllers: list[AdmissionController] = []
        self._resource_types: dict[str, dict[str, type[Resource.Spec]]] = {}
        self.resources = store

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
        """

        uri = resource.uri
        with self.resources.enter(self.resources.LockRequest.from_uri(uri)) as lock:
            generic_resource = resource.into_generic()
            for controller in self._admission_controllers:
                new_resource = controller.admit_resource(generic_resource)
                if new_resource.uri != uri:
                    raise RuntimeError(f"Admission controller mutated resource URI (controller: {controller!r})")
                generic_resource = new_resource
            self.resources.put(lock, generic_resource)

    def load_manifest(self, path: Path) -> None:
        with path.open() as fp:
            for payload in yaml.safe_load_all(fp):
                resource = Resource.of(payload)
                self.put_resource(resource)

    def reconcile_once(self) -> None:
        for controller in self._resource_controllers:
            logger.debug(f"Reconciling {controller!r}")
            controller.reconcile_once()
