"""
An example to illustrate resource serviecs.
"""

from dataclasses import dataclass

from equilibrium.Namespace import Namespace
from equilibrium.Resource import Resource
from equilibrium.ResourceContext import ResourceContext
from equilibrium.ResourceController import ResourceController
from equilibrium.Service import Service


@dataclass
class Add(Resource.Spec, apiVersion="example.com/v1", kind="Add"):
    a: int
    b: int


class Adder(Service, serviceId="example.com/v1/Adder", resourceType=Add):
    def add(self, add: Add) -> int:
        return add.a + add.b


class AdderTest(ResourceController):
    def reconcile(self) -> None:
        adder = self.services.get(Add.TYPE, Adder)
        assert adder is not None
        print("result is:", adder.add(Add(a=1, b=2)))


ctx = ResourceContext.create(ResourceContext.InMemoryBackend())
ctx.resource_types.register(Add)
ctx.services.register(Adder())
ctx.resources.put(Namespace.create_resource("default"))
ctx.resources.put(Resource.create(Resource.Metadata("default", "onePlusTwo"), Add(a=1, b=2)))
ctx.controllers.register(AdderTest())
ctx.controllers.reconcile()
