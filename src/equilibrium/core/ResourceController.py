from abc import ABC, abstractmethod

from equilibrium.core.ResourceStore import ResourceStore
from equilibrium.core.Service import Service

__all__ = ["ResourceController"]


class ResourceController(ABC):
    # These are set automatically when the controller is registered to a context.
    resources: ResourceStore
    services: Service.Provider

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    @abstractmethod
    def reconcile_once(self) -> None:
        ...
