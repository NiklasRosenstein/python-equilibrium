from abc import ABC, abstractmethod

from equilibrium.core.Resource import GenericResource
from equilibrium.core.ResourceStore import ResourceStore

__all__ = ["AdmissionController"]


class AdmissionController(ABC):
    """Controller to allow or deny admission of resources to the system."""

    # These are set automatically when the controller is registered to a context.
    resources: ResourceStore

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    @abstractmethod
    def admit_resource(self, resource: GenericResource) -> GenericResource:
        """An arbitrary exception may be raised to deny the resource."""
        ...
