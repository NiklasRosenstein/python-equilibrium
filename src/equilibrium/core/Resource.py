from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, Literal, Mapping, TypeVar, cast, overload

import databind.json
from databind.json.settings import JsonConverter
from typing_extensions import Self  # 3.11+

from equilibrium.utils.protocols import Dataclass

T = TypeVar("T")

VALID_IDENTIFIER_REGEX = r"^[a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?$"
VALID_APIVERSION_REGEX = r"^[\.a-z0-9]([-\.a-z0-9]*[\.a-z0-9])?(/[\.a-z0-9]([-\.a-z0-9]*[\.a-z0-9])?)*$"


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
    @dataclass(frozen=True)
    class NotFound(Exception):
        uri: Resource.URI

    class Spec(Dataclass):
        __dataclass_fields__: Mapping[str, Any]
        API_VERSION: ClassVar[str] = ""
        KIND: ClassVar[str] = ""
        NAMESPACED: ClassVar[bool] = False

        def __init_subclass__(cls, apiVersion: str, kind: str, namespaced: bool = True) -> None:
            cls.API_VERSION = apiVersion
            cls.KIND = kind
            cls.NAMESPACED = namespaced
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

            if do_raise and (uri.namespace is None if cls.NAMESPACED else uri.namespace is not None):
                raise ValueError(f"invalid namespace for {cls.API_VERSION}/{cls.KIND}: {uri.namespace!r}")

            return uri.apiVersion == cls.API_VERSION and uri.kind == cls.KIND

        def as_resource(self, metadata: Resource.Metadata) -> Resource[Self]:
            return Resource.create(metadata, self)

    class State(Dataclass):
        __dataclass_fields__: Mapping[str, Any]

    T_Spec = TypeVar("T_Spec", bound="Resource.Spec")
    T_State = TypeVar("T_State", bound="Resource.State")
    GenericSpec = dict[str, Any]
    GenericState = dict[str, Any]

    @JsonConverter.using_classmethods(serialize="__str__", deserialize="of")
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
            return f"{self.apiVersion}/{self.kind}/{self.namespace}/{self.name}"

        @staticmethod
        def of(s: str) -> Resource.URI:
            parts = s.split("/")
            try:
                apiVersion = "/".join(parts[:-3])
                kind = parts[-3]
                namespace = parts[-2]
                name = parts[-1]
            except IndexError:
                raise ValueError(f"invalid Resource.URI: {s!r}")
            return Resource.URI(apiVersion, kind, namespace, name)

    @JsonConverter.using_classmethods(serialize="__str__", deserialize="of")
    @dataclass(frozen=True)
    class Locator:
        name: str
        namespace: str | None

        def __str__(self) -> str:
            if self.namespace is None:
                return self.name
            return f"{self.namespace}/{self.name}"

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
    spec: T
    deletion_marker: DeletionMarker | None = None
    state: GenericState | None = None

    def __post_init__(self) -> None:
        validate_api_version(self.apiVersion, "apiVersion")
        validate_identifier(self.kind, "kind")

    def __repr__(self) -> str:
        return f"Resource(apiVersion={self.apiVersion!r}, kind={self.kind!r}, metadata={self.metadata!r})"

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
        )

    def into(self, spec_type: type[U_Spec]) -> Resource[U_Spec]:
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
    def of(payload: dict[str, Any], spec_type: type[U_Spec]) -> Resource[U_Spec]:
        ...

    @staticmethod
    def of(payload: dict[str, Any], spec_type: type[U_Spec] | None = None) -> Resource[Any]:
        return databind.json.load(payload, GenericResource if spec_type is None else Resource[spec_type])  # type: ignore[valid-type]  # noqa: E501

    @staticmethod
    def create(metadata: Resource.Metadata, spec: U_Spec, state: GenericState | None = None) -> Resource[U_Spec]:
        resource = Resource(spec.API_VERSION, spec.KIND, metadata, spec, None, state)
        spec.check_uri(resource.uri, do_raise=True)
        return resource

    def state_as(self, state_type: type[T_State]) -> T_State:
        if self.state is None:
            raise ValueError("resource has no state")
        return databind.json.load(self.state, state_type)

    def state_from(self, state_type: type[T_State], state: T_State) -> None:
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
