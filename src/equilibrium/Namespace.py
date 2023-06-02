"""
The namespace resource is builtin by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from equilibrium.Resource import Resource
from equilibrium.types import FrozenDict, HashableMapping

__all__ = ["Namespace"]


@dataclass
class Namespace(Resource.Spec, apiVersion="v1", kind="Namespace", namespaced=False):
    @staticmethod
    def create_resource(
        name: str, labels: HashableMapping[str, str] | None = None, annotations: HashableMapping[str, str] | None = None
    ) -> Resource[Namespace]:
        return Namespace().as_resource(
            Resource.Metadata(None, name, labels=labels or FrozenDict(), annotations=annotations or FrozenDict())
        )
