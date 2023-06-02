from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from equilibrium.ResourceRegistry import ResourceRegistry
    from equilibrium.Service import Service


class BaseController(ABC):
    @dataclass(frozen=True)
    class Context:
        #: The resource registry allows controllers to access resources that they do not own in a simpler way. It does
        #: not require the controller to manually acquire locks on the resources it would like to read, however it is
        #: not suitable for controllers that may work in a highly contested environment. In such cases, a controller
        #: should use the resource store directly.
        resources: "ResourceRegistry"

        #: Provides access to the service registry.
        services: "Service.Provider"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
