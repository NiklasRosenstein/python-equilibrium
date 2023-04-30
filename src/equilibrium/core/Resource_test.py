import pytest

from equilibrium.core.Resource import Resource


def test__Resource_URI__validates_apiVersion() -> None:
    Resource.URI("v1", "MyResource", "default", "my-resource")
    Resource.URI("example.com/v1", "MyResource", "default", "my-resource")
    with pytest.raises(ValueError):
        Resource.URI("example_com/v1", "MyResource", "default", "my-resource")
    with pytest.raises(ValueError):
        Resource.URI("v1", "MyResource/v1", "default", "my-resource")


def test__Resource_Spec__check_uri__validates_namespaced_uri() -> None:
    class MySpec(Resource.Spec, apiVersion="v1", kind="MyResource", namespaced=True):
        pass

    assert MySpec.check_uri(Resource.URI("v1", "MyResource", "default", "my-resource")) is True
    assert MySpec.check_uri(Resource.URI("v1", "MyResource", None, "my-resource")) is False


def test__Resource_Spec__check_uri__validates_namespaceless_uri() -> None:
    class MySpec(Resource.Spec, apiVersion="v1", kind="MyResource", namespaced=False):
        pass

    assert MySpec.check_uri(Resource.URI("v1", "MyResource", "default", "my-resource")) is False
    assert MySpec.check_uri(Resource.URI("v1", "MyResource", None, "my-resource")) is True
