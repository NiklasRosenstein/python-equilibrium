from typing import TypeVar, overload

from equilibrium.NotSet import NotSet
from equilibrium.Resource import Resource
from equilibrium.ResourceStore import ResourceStore
from equilibrium.Service import Service

T = TypeVar("T")


class ServiceRegistry(Service.Provider):
    def __init__(self, resources: ResourceStore) -> None:
        self._resources = resources
        self._services: dict[Resource.Type, dict[Service.Id, Service]] = {}

    def register(self, service: Service, resource_type: Resource.Type | type[Resource.Spec] | None = None) -> None:
        """
        Register a service to the controller for the given resource type. If no resource type is specified, the
        service must have a resource type specified in its class definition. If no resource type is specified, a
        `ValueError` is raised.
        """

        if resource_type is None:
            if service.RESOURCE_TYPE is None:
                raise ValueError(f"Service {service!r} does not specify a resource type")
            resource_type = service.RESOURCE_TYPE
        elif isinstance(resource_type, type):
            resource_type = resource_type.TYPE

        service.resources = self._resources
        service.services = self
        services = self._services.setdefault(resource_type, {})
        if service.SERVICE_ID in services:
            raise ValueError(
                f"Service '{service.SERVICE_ID}' is already registered for resource type {resource_type!r}"
            )
        services[service.SERVICE_ID] = service

    @overload
    def get(
        self,
        resource_type: Resource.Type | type[Resource.Spec],
        service_type: type[Service.T],
    ) -> Service.T:
        ...

    @overload
    def get(
        self,
        resource_type: Resource.Type | type[Resource.Spec],
        service_type: type[Service.T],
        default: T,
    ) -> Service.T | T:
        ...

    def get(
        self,
        resource_type: Resource.Type | type[Resource.Spec],
        service_type: type[Service.T],
        default: T | NotSet = NotSet.Value,
    ) -> Service.T | T:
        """
        Obtain a service for the given resource type. If the service is not registered, None is returned.
        """

        if isinstance(resource_type, type):
            resource_type = resource_type.TYPE

        services = self._services.get(resource_type)
        service = services.get(service_type.SERVICE_ID) if services else None
        if service is not None and not isinstance(service, service_type):
            raise RuntimeError(f"Service '{service_type.SERVICE_ID}' is not of type {service_type!r}")
        if service is None:
            if default is NotSet.Value:
                raise KeyError(
                    f"Service '{service_type.SERVICE_ID}' is not registered for resource type {resource_type!r}"
                )
            return default
        return service
