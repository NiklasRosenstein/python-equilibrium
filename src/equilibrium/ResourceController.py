from abc import abstractmethod

from equilibrium.BaseController import BaseController

__all__ = ["ResourceController"]


class ResourceController(BaseController):
    @abstractmethod
    def reconcile(self, ctx: BaseController.Context) -> None:
        ...
