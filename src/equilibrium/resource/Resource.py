from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import total_ordering
from typing import Any, ClassVar, Generic, Literal, Mapping, Protocol, Type as _Type, TypeVar, cast, overload

import databind.json
from databind.json.settings import JsonConverter
from typing_extensions import Self  # 3.11+

__all__ = ["Resource", "match_labels", "validate_api_version", "validate_identifier"]

T = TypeVar("T")

VALID_IDENTIFIER_REGEX = r"^[a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?$"
VALID_APIVERSION_REGEX = r"^[\.a-z0-9]([-\.a-z0-9]*[\.a-z0-9])?(/[\.a-z0-9]([-\.a-z0-9]*[\.a-z0-9])?)*$"


class Dataclass(Protocol):
    __dataclass_fields__: Mapping[str, Any]


def validate_identifier(s: str, name: str) -> None:
    assert isinstance(s, str), type(s)
    if not re.match(VALID_IDENTIFIER_REGEX, s):
        raise ValueError(f"invalid {name}: {s!r}")


def validate_api_version(s: str, name: str) -> None:
    assert isinstance(s, str), type(s)
    if not re.match(VALID_APIVERSION_REGEX, s):
        raise ValueError(f"invalid {name}: {s!r}")


@dataclass
class Resource(Generic[T]):
    class Error(Exception):
        pass

    @dataclass(frozen=True)
    class NotFound(Error):
        uri: Resource.URI

    @dataclass(frozen=True)
    class ValidationFailed(Error):
        uri: Resource.URI
        exc: Exception

    @dataclass
    class AdmissionFailed(Error):
        uri: Resource.URI
        exc: Exception

    class Spec(Dataclass):
        __dataclass_fields__: Mapping[str, Any]
        API_VERSION: ClassVar[str]
        KIND: ClassVar[str]
        NAMESPACED: ClassVar[bool]
        TYPE: ClassVar[Resource.Type]

        def __init_subclass__(cls, apiVersion: str, kind: str, namespaced: bool = True) -> None:
            cls.API_VERSION = apiVersion
            cls.KIND = kind
            cls.NAMESPACED = namespaced
            cls.TYPE = Resource.Type(apiVersion, kind)
            return super().__init_subclass__()

        @overload
        @classmethod
        def uri(cls, name: str, /) -> Resource.URI:
            ...

        @overload
        @classmethod
        def uri(cls, namespace: str, name: str, /) -> Resource.URI:
            ...

        @classmethod
        def uri(cls, namespace: str, name: str | None = None, /) -> Resource.URI:
            if name is None:
                name, namespace = namespace, ""
                if cls.NAMESPACED:
                    raise TypeError(f"missing argument 'name' for namespaced resource {cls.API_VERSION}/{cls.KIND}")
                return Resource.URI(cls.API_VERSION, cls.KIND, None, name)
            else:
                if not cls.NAMESPACED:
                    raise TypeError(
                        f"unexpected argument 'namespace' for non-namespaced resource {cls.API_VERSION}/{cls.KIND}"
                    )
                return Resource.URI(cls.API_VERSION, cls.KIND, namespace, name)

        @classmethod
        def check_uri(cls, uri: Resource.URI, *, do_raise: bool = False) -> bool:
            """
            Check if the given URI matches this resource type.
            """

            if cls.NAMESPACED and uri.namespace is None:
                if do_raise:
                    raise ValueError(f"missing namespace for Resource of type '{cls.TYPE}' (uri: {uri!r}).")
                return False
            if not cls.NAMESPACED and uri.namespace is not None:
                if do_raise:
                    raise ValueError(f"Resource of type '{cls.TYPE}' is not namespaced (uri: {uri!r}).")
                return False
            return uri.apiVersion == cls.API_VERSION and uri.kind == cls.KIND

        def as_resource(self, metadata: Resource.Metadata) -> Resource[Self]:
            return Resource.create(metadata, self)

        def validate(self) -> None:
            """
            Validate the resource spec. This method is practically an admission controller and can raise any
            exception to prevent the resource from being committed to the database. The default implementation
            does nothing.
            """

    class State(Dataclass):
        __dataclass_fields__: Mapping[str, Any]

    T_Spec = TypeVar("T_Spec", bound="Resource.Spec")
    T_State = TypeVar("T_State", bound="Resource.State")
    GenericSpec = dict[str, Any]
    GenericState = dict[str, Any]

    @JsonConverter.using_classmethods(serialize="__str__", deserialize="of")
    @total_ordering
    @dataclass(frozen=True)
    class URI:
        apiVersion: str
        kind: str
        namespace: str | None
        name: str

        def __post_init__(self) -> None:
            validate_api_version(self.apiVersion, "apiVersion")
            validate_identifier(self.kind, "kind")
            if self.namespace is not None:
                validate_identifier(self.namespace, "namespace")
            validate_identifier(self.name, "name")

        def __str__(self) -> str:
            if self.namespace is not None:
                return f"{self.apiVersion}/{self.kind}/{self.namespace}/{self.name}"
            else:
                return f"{self.apiVersion}/{self.kind}//{self.name}"

        def __lt__(self, other: Any) -> bool:
            if type(other) == Resource.URI:
                return str(self) < str(other)
            else:
                return NotImplemented

        @staticmethod
        def of(s: str) -> Resource.URI:
            parts = s.split("/")
            try:
                apiVersion = "/".join(parts[:-3])
                kind = parts[-3]
                namespace = parts[-2] or None
                name = parts[-1]
            except IndexError:
                raise ValueError(f"invalid Resource.URI: {s!r}")
            return Resource.URI(apiVersion, kind, namespace, name)

        @property
        def type(self) -> Resource.Type:
            return Resource.Type(self.apiVersion, self.kind)

        @property
        def locator(self) -> Resource.Locator:
            return Resource.Locator(self.namespace, self.name)

    @JsonConverter.using_classmethods(serialize="__str__", deserialize="of")
    @dataclass(frozen=True)
    class Type:
        apiVersion: str
        kind: str

        def __post_init__(self) -> None:
            validate_api_version(self.apiVersion, "apiVersion")
            validate_identifier(self.kind, "kind")

        def __str__(self) -> str:
            return f"{self.apiVersion}/{self.kind}"

        @classmethod
        def of(cls, s: str) -> Resource.Type:
            apiVersion, kind = s.rpartition("/")[::2]
            return cls(apiVersion, kind)

    @JsonConverter.using_classmethods(serialize="__str__", deserialize="of")
    @dataclass(frozen=True)
    class Locator:
        namespace: str | None
        name: str

        def __post_init__(self) -> None:
            if self.namespace is not None:
                validate_identifier(self.namespace, "namespace")
            validate_identifier(self.name, "name")

        def __str__(self) -> str:
            if self.namespace is None:
                return self.name
            return f"{self.namespace}/{self.name}"

        @classmethod
        def of(cls, s: str) -> Resource.Locator:
            namespace, name = s.rpartition("/")[::2]
            return cls(namespace or None, name)

    @dataclass(frozen=True)
    class Metadata:
        namespace: str | None
        name: str
        labels: dict[str, str] = field(default_factory=dict)
        annotations: dict[str, str] = field(default_factory=dict)

        def __post_init__(self) -> None:
            validate_identifier(self.name, "name")
            if self.namespace is not None:
                validate_identifier(self.namespace, "namespace")

        def __repr__(self) -> str:
            return f"Resource.Metadata(namespace={self.namespace!r}, name={self.name!r})"

        def with_namespace(self, namespace: str | None) -> Resource.Metadata:
            return replace(self, namespace=namespace)

    @dataclass(frozen=True)
    class DeletionMarker:
        timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @dataclass(frozen=True)
    class Event:
        Type = Literal["Normal", "Warning", "Error"]
        timestamp: datetime
        type: Type
        origin: str
        reason: str
        message: str

    apiVersion: str
    kind: str
    metadata: Metadata

    # Namespaces in particular should not require an explicit spec to be specified when it is
    # actually empty. However, we must be careful because when we create a non-generic Resource,
    # this default value is actually invalid.
    #
    # A feature to only specify a default value for deserialization would improve this, but is still
    # not perfectly safe because a non-generic Resource could also be deserialized directly.
    #
    # Related databind FR: https://github.com/NiklasRosenstein/python-databind/issues/43
    spec: T = field(default_factory=lambda: cast(T, {}))

    deletion_marker: DeletionMarker | None = None
    state: GenericState | None = None

    def __post_init__(self) -> None:
        validate_api_version(self.apiVersion, "apiVersion")
        validate_identifier(self.kind, "kind")

    def __repr__(self) -> str:
        return f"Resource('{self.uri}')"

    @property
    def type(self) -> Type:
        return Resource.Type(self.apiVersion, self.kind)

    @property
    def locator(self) -> Locator:
        return Resource.Locator(self.metadata.namespace, self.metadata.name)

    @property
    def uri(self) -> URI:
        return Resource.URI(self.apiVersion, self.kind, self.metadata.namespace, self.metadata.name)

    def into_generic(self) -> GenericResource:
        if isinstance(self.spec, dict):
            return cast(GenericResource, self)
        return Resource(
            self.apiVersion,
            self.kind,
            self.metadata,
            cast(dict[str, Any], databind.json.dump(self.spec, type(self.spec))),
            self.deletion_marker,
            self.state,
        )

    def into(self, spec_type: _Type[U_Spec]) -> Resource[U_Spec]:
        if spec_type.API_VERSION != self.apiVersion:
            raise ValueError(
                f"{self.apiVersion=!r} does not match {spec_type.__name__}.apiVersion={spec_type.API_VERSION!r}"
            )
        if spec_type.KIND != self.kind:
            raise ValueError(f"{self.kind=!r} does not match {spec_type.__name__}.kind={spec_type.KIND!r}")
        if isinstance(self.spec, spec_type):
            return cast(Resource[U_Spec], self)
        if not isinstance(self.spec, dict):
            raise RuntimeError("Resource.into() can only be used for generic resources")
        spec = databind.json.load(self.spec, spec_type)
        return Resource(self.apiVersion, self.kind, self.metadata, spec, self.deletion_marker, self.state)

    @overload
    @staticmethod
    def of(payload: dict[str, Any]) -> GenericResource:
        ...

    @overload
    @staticmethod
    def of(payload: dict[str, Any], spec_type: _Type[U_Spec]) -> Resource[U_Spec]:
        ...

    @staticmethod
    def of(payload: dict[str, Any], spec_type: _Type[U_Spec] | None = None) -> Resource[Any]:
        return databind.json.load(payload, GenericResource if spec_type is None else Resource[spec_type])  # type: ignore[valid-type]  # noqa: E501

    @staticmethod
    def create(metadata: Resource.Metadata, spec: U_Spec, state: GenericState | None = None) -> Resource[U_Spec]:
        resource = Resource(spec.API_VERSION, spec.KIND, metadata, spec, None, state)
        spec.check_uri(resource.uri, do_raise=True)
        return resource

    @overload
    def get_state(self, state_type: _Type[T_State]) -> T_State:
        ...

    @overload
    def get_state(self, state_type: _Type[GenericState]) -> GenericState:
        ...

    def get_state(self, state_type: _Type[U_State] | _Type[GenericState]) -> U_State | GenericState:
        if self.state is None:
            raise ValueError("resource has no state")
        if state_type == Resource.GenericState or state_type is dict:
            return self.state
        else:
            return cast(U_State, databind.json.load(self.state, state_type))

    def set_state(self, state_type: _Type[T_State], state: T_State) -> None:
        self.state = cast(Resource.GenericState, databind.json.dump(state, state_type))


# NOTE(@NiklasRosenstein): We repeat the definition of the type variables here for use inside the Resource class.
#       Attempting to reference a type variable inside the class definition in which the variable is defined
#       leads to issues, especially if that type variable needs to be referenced in a cast() inside a method.
U_Spec = TypeVar("U_Spec", bound="Resource.Spec")
U_State = TypeVar("U_State", bound="Resource.State")
GenericResource = Resource[Resource.GenericSpec]


def match_labels(resource_labels: Mapping[str, str], selector: Mapping[str, str]) -> bool:
    """
    Returns True if the resource labels match the selector.
    """

    for key, value in selector.items():
        if resource_labels.get(key) != value:
            return False
    return True
