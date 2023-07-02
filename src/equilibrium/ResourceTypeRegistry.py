from typing import TypeVar, overload

from equilibrium.NotSet import NotSet
from equilibrium.Resource import Resource

T = TypeVar("T")


class ResourceTypeRegistry:
    def __init__(self) -> None:
        self._resource_types: dict[str, dict[str, type[Resource.Spec]]] = {}

    def __contains__(self, resource_type: Resource.Type) -> bool:
        if resource_type.apiVersion not in self._resource_types:
            return False
        return resource_type.kind in self._resource_types[resource_type.apiVersion]

    def register(self, spec_type: type[Resource.Spec]) -> None:
        self._resource_types.setdefault(spec_type.API_VERSION, {})[spec_type.KIND] = spec_type

    @overload
    def get(self, resource_type: Resource.Type) -> type[Resource.Spec]:
        ...

    @overload
    def get(self, resource_type: Resource.Type, default: T) -> type[Resource.Spec] | T:
        ...

    def get(self, resource_type: Resource.Type, default: T | NotSet = NotSet.Value) -> type[Resource.Spec] | T:
        try:
            return self._resource_types.get(resource_type.apiVersion, {})[resource_type.kind]
        except KeyError:
            if default is NotSet.Value:
                raise KeyError(resource_type)
            return default
