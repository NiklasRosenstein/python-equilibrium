import logging
from typing import Any

from equilibrium import BaseController
from equilibrium.AdmissionController import AdmissionController
from equilibrium.Resource import Resource
from equilibrium.ResourceController import ResourceController

logger = logging.getLogger(__name__)


class ControllerRegistry:
    def __init__(self) -> None:
        self._resource_controllers: list[ResourceController] = []
        self._admission_controllers: list[AdmissionController] = []

    def register(self, controller: ResourceController | AdmissionController) -> None:
        assert isinstance(controller, (ResourceController, AdmissionController))
        if isinstance(controller, AdmissionController):
            self._admission_controllers.append(controller)
        if isinstance(controller, ResourceController):
            self._resource_controllers.append(controller)

    def admit(self, ctx: BaseController.Context, resource: Resource[Any]) -> Resource[Any]:
        uri = resource.uri
        # Pass resource through admission controllers.
        for controller in self._admission_controllers:
            try:
                new_resource = controller.admit_resource(ctx, resource)
            except Exception as e:
                raise Resource.AdmissionFailed(resource.uri, e) from e
            if new_resource.uri != uri:
                raise RuntimeError(f"Admission controller mutated resource URI (controller: {controller!r})")
            if type(new_resource.spec) != type(resource.spec):  # noqa: E721
                raise RuntimeError(f"Admission controller mutated resource spec type (controller: {controller!r})")
            resource = new_resource
        return resource

    def reconcile(self, ctx: BaseController.Context) -> None:
        for controller in self._resource_controllers:
            logger.debug(f"Reconciling {controller!r}")
            controller.reconcile(ctx)
