"""
An example to illustrate resource serviecs.
"""

from dataclasses import dataclass

from equilibrium.resource.Context import Context
from equilibrium.resource.Namespace import Namespace
from equilibrium.resource.Resource import Resource
from equilibrium.resource.ResourceController import ResourceController
from equilibrium.resource.Service import Service


@dataclass
class Add(Resource.Spec, apiVersion="example.com/v1", kind="Add"):
    a: int
    b: int


class Adder(Service, serviceId="example.com/v1/Adder"):
    def add(self, add: Add) -> int:
        return add.a + add.b


class AdderTest(ResourceController):
    def reconcile(self) -> None:
        adder = self.services.get(Add.TYPE, Adder)
        assert adder is not None
        print("result is:", adder.add(Add(a=1, b=2)))


ctx = Context.create(Context.InMemoryBackend())
ctx.resource_types.register(Add)
ctx.services.register(Add.TYPE, Adder())
ctx.resources.put(Namespace.create_resource("default"))
ctx.resources.put(Resource.create(Resource.Metadata("default", "onePlusTwo"), Add(a=1, b=2)))
ctx.controllers.register(AdderTest())
ctx.controllers.reconcile()
