"""
The namespace resource is builtin by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from equilibrium.core.Resource import Resource

DEFAULT_NAMESPACE = "default"


@dataclass
class Namespace(Resource.Spec, apiVersion="v1", kind="Namespace", namespaced=False):
    @staticmethod
    def create_resource(name: str) -> Resource[Namespace]:
        return Namespace().as_resource(Resource.Metadata(None, name))
