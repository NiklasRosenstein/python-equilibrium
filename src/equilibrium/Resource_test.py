from dataclasses import dataclass
from typing import Any

import pytest

from equilibrium.Resource import Resource


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


def test__Resource__get_state() -> None:
    """
    Tests the #Resource.state_as() deserializes the state correctly, or, if the #GenericState is passed, returns the
    original state without copying.
    """

    class MySpec(Resource.Spec, apiVersion="v1", kind="MyResource", namespaced=False):
        pass

    @dataclass
    class MyState(Resource.State):
        a: int

    resource = Resource.create(
        Resource.Metadata(
            name="my-resource",
            namespace=None,
        ),
        MySpec(),
        {"a": 1},
    )

    assert resource.get_state(Resource.GenericState) is resource.state
    assert resource.get_state(dict) is resource.state
    assert resource.get_state(dict[str, Any]) is resource.state
    assert resource.get_state(dict[str, int]) is not resource.state
    assert resource.get_state(dict[str, int]) == resource.state
    assert resource.get_state(MyState) == MyState(a=1)


def test__Resource__URI__parse() -> None:
    # Standard full URI format with namespace.
    assert Resource.URI.of("example.com/v1/MyResource/default/my-resource") == Resource.URI(
        apiVersion="example.com/v1",
        kind="MyResource",
        namespace="default",
        name="my-resource",
    )

    # Full URI format with explicit empty namespace.
    assert Resource.URI.of("example.com/v1/MyResource//my-resource") == Resource.URI(
        apiVersion="example.com/v1",
        kind="MyResource",
        namespace=None,
        name="my-resource",
    )

    # Namespace-less URI with a two-component API version.
    assert Resource.URI.of("example.com/v1/MyResource/my-resource") == Resource.URI(
        apiVersion="example.com/v1",
        kind="MyResource",
        namespace=None,
        name="my-resource",
    )

    # Namespace-less URI with a one-component API version.
    assert Resource.URI.of("v1/MyResource/my-resource") == Resource.URI(
        apiVersion="v1",
        kind="MyResource",
        namespace=None,
        name="my-resource",
    )

    # Namespace-less URI with a one-component API version that does not match one-component heuristics.
    with pytest.raises(ValueError) as excinfo:
        Resource.URI.of("foobar/MyResource/my-resource")
    assert (
        str(excinfo.value) == "invalid Resource.URI: has invalid apiVersion component: 'foobar/MyResource/my-resource'"
    )

    # Bad API versions.
    bad_versions = [
        "example.com/vzero/MyResource/my-resource",
        "example.com/1/MyResource/my-resource",
    ]
    for bad_version in bad_versions:
        with pytest.raises(ValueError) as excinfo:
            Resource.URI.of(bad_version)
        assert str(excinfo.value) == "invalid Resource.URI: has invalid apiVersion component: '%s'" % bad_version

    # Good API versions.
    good_versions = [
        "example.com/v13alpha4/MyResource/my-resource",
    ]
    for good_version in good_versions:
        Resource.URI.of(good_version)
