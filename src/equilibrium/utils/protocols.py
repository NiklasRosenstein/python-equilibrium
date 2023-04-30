from typing import Any, Mapping, Protocol


class Dataclass(Protocol):
    __dataclass_fields__: Mapping[str, Any]
