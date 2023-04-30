from abc import ABC, abstractmethod
from typing import Any, TypeVar, cast

import databind.json

from equilibrium.core.Resource import Resource

T = TypeVar("T")


class StateStore(ABC):
    @abstractmethod
    def save(self, uri: Resource.URI, state: Resource.GenericState) -> None:
        """Save the state of a resource."""

    @abstractmethod
    def load(self, uri: Resource.URI) -> Resource.GenericState | None:
        """Load the state of a resource. A resource may not have a current state, so this may return None."""

    @abstractmethod
    def delete(self, uri: Resource.URI) -> None:
        """Delete the state of a resource."""

    @abstractmethod
    def put_event(self, uri: Resource.URI, type_: Resource.Event.Type, origin: str, reason: str, message: str) -> None:
        """Log and persist an event for a resource."""

    @abstractmethod
    def get_events(self, uri: Resource.URI) -> list[Resource.Event]:
        """List all retained events for the given resource."""

    # Convenience methods

    def set(self, uri: Resource.URI, state: Resource.GenericState | Any) -> None:
        """
        Set the state of a resource. The difference to #load() is that this method handles the serialization of
        data calsses if passed for *state*.
        """

        if not isinstance(state, dict):
            state = cast(Resource.GenericState, databind.json.dump(state, type(state)))
        self.save(uri, state)

    def get(self, uri: Resource.URI, state_type: type[T] | None) -> T | None:
        """
        Get the state of a resource and deserialize it into the given *state_type*.
        """

        state = self.load(uri)
        if state is None:
            return None
        return databind.json.load(state, state_type)
