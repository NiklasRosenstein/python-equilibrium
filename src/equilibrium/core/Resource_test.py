import pytest

from equilibrium.core.Resource import Resource


def test__Resource_URI__validates_apiVersion() -> None:
    Resource.URI("v1", "MyResource", "my-resource", "default")
    Resource.URI("example.com/v1", "MyResource", "my-resource", "default")
    with pytest.raises(ValueError):
        Resource.URI("example_com/v1", "MyResource", "my-resource", "default")
    with pytest.raises(ValueError):
        Resource.URI("v1", "MyResource/v1", "my-resource", "default")
