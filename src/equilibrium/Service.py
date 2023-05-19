from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, NewType, TypeVar

from equilibrium.Resource import Resource
from equilibrium.ResourceStore import ResourceStore


def validate_service_id(s: str) -> None:
    try:
        Resource.Type.of(s)
    except ValueError:
        raise ValueError(f"Invalid serviceId: {s!r}")


class Service(ABC):
    """
    Base class for services that can be registered to a context and retrieved by controllers. Services are pluggable
    components that support various actions no resources. The same service implementation can be registered multiple
    types to support different resource types, but if that's not the case, the *resourceType* may be specified as part
    of the class definition.
    """

    Id = NewType("Id", str)
    T = TypeVar("T", bound="Service")

    #: A globally unique identifier of the service type. The identifier is used to retrieve the service from the
    #: context. This must begin with an apiVersion and end with a kind, separated by a slash. The apiVersion and kind
    #: must be valid DNS subdomains.
    SERVICE_ID: ClassVar[Id]

    #: The resource type that the service supports. This is used when the service is registered without explicitly
    #: specifying the resource type to register it for. If this is None, the resource type to register the service for
    #: must always be explicitly specified.
    RESOURCE_TYPE: ClassVar[Resource.Type | None] = None

    #: Assigned to the service upon registration to the context.
    resources: ResourceStore
    services: Service.Provider

    class Provider(ABC):
        @abstractmethod
        def get(self, resource_type: Resource.Type, service_type: type[Service.T]) -> Service.T | None:
            ...

    def __init_subclass__(
        cls,
        serviceId: str | None = None,
        resourceType: type[Resource.Spec] | Resource.Type | None = None,
        **kwargs: Any,
    ) -> None:
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

        if resourceType is not None:
            if cls.RESOURCE_TYPE is not None:
                raise RuntimeError("Service subclass must not redefine resourceType")
            if isinstance(resourceType, type):
                resourceType = resourceType.TYPE
            cls.RESOURCE_TYPE = resourceType

        return super().__init_subclass__(**kwargs)
