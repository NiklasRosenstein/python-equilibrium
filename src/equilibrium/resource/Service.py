from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, NewType, TypeVar

from equilibrium.resource.Resource import Resource
from equilibrium.resource.ResourceStore import ResourceStore


def validate_service_id(s: str) -> None:
    try:
        Resource.Type.of(s)
    except ValueError:
        raise ValueError(f"Invalid serviceId: {s!r}")


class Service(ABC):
    """
    Base class for services that can be registered to a context and retrieved by controllers. Services are pluggable
    components that support various actions no resources.
    """

    Id = NewType("Id", str)
    T = TypeVar("T", bound="Service")

    #: A globally unique identifier of the service type. The identifier is used to retrieve the service from the
    #: context. This must begin with an apiVersion and end with a kind, separated by a slash. The apiVersion and kind
    #: must be valid DNS subdomains.
    SERVICE_ID: ClassVar[Id]

    #: Assigned to the service upon registration to the context.
    resources: ResourceStore
    services: Service.Provider

    class Provider(ABC):
        @abstractmethod
        def get(self, resource_type: Resource.Type, service_type: type[Service.T]) -> Service.T | None:
            ...

    def __init_subclass__(cls, serviceId: str | None = None, **kwargs: Any) -> None:
        # Check if any of the base classes is a subclass of the service. In this case, the `serviceId` is inherited
        # and must not be redefined.
        if any(issubclass(x, Service) and x is not Service for x in cls.__bases__):
            if serviceId is not None:
                raise RuntimeError("Service implementation must not redefine serviceId")
            assert hasattr(cls, "SERVICE_ID"), "Service parent class should have a serviceId defined."

        else:
            if serviceId is None:
                raise RuntimeError("Service subclass must define serviceId")
            validate_service_id(serviceId)
            cls.SERVICE_ID = cls.Id(serviceId)

        return super().__init_subclass__(**kwargs)
