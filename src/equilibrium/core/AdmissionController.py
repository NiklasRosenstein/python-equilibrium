from abc import ABC, abstractmethod
from typing import Any

from equilibrium.core.Resource import Resource
from equilibrium.core.ResourceStore import ResourceStore
from equilibrium.core.Service import Service

__all__ = ["AdmissionController"]


class AdmissionController(ABC):
    """Controller to allow or deny admission of resources to the system."""

    # These are set automatically when the controller is registered to a context.
    resources: ResourceStore
    services: Service.Provider

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    @abstractmethod
    def admit_resource(self, resource: Resource[Any]) -> Resource[Any]:
        """An arbitrary exception may be raised to deny the resource."""
        ...
