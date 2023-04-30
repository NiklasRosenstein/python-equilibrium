from abc import ABC, abstractmethod

from equilibrium.core.ResourceStore import ResourceStore


class ResourceController(ABC):
    # These are set automatically when the controller is registered to a context.
    resources: ResourceStore

    @abstractmethod
    def reconcile_once(self) -> None:
        ...
