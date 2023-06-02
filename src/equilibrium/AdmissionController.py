from abc import abstractmethod
from typing import Any

from equilibrium.BaseController import BaseController
from equilibrium.Resource import Resource

__all__ = ["AdmissionController"]


class AdmissionController(BaseController):
    @abstractmethod
    def admit_resource(self, ctx: BaseController.Context, resource: Resource[Any]) -> Resource[Any]:
        """An arbitrary exception may be raised to deny the resource."""
        return resource
