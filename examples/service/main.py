"""
An example to illustrate resource serviecs.
"""

from dataclasses import dataclass

from equilibrium.core.Context import Context
from equilibrium.core.Resource import Resource
from equilibrium.core.ResourceController import ResourceController
from equilibrium.core.Service import Service


@dataclass
class Add(Resource.Spec, apiVersion="example.com/v1", kind="Add"):
    a: int
    b: int


class Adder(Service, serviceId="example.com/v1/Adder"):
    def add(self, add: Add) -> int:
        return add.a + add.b


class AdderTest(ResourceController):
    def reconcile_once(self) -> None:
        adder = self.services.get(Add.TYPE, Adder)
        assert adder is not None
        print("result is:", adder.add(Add(a=1, b=2)))


ctx = Context.with_json_backend("data")
ctx.register_resource_type(Add)
ctx.register_service(Add.TYPE, Adder())
ctx.put_resource(Resource.create(Resource.Metadata("default", "onePlusTwo"), Add(a=1, b=2)))
ctx.register_controller(AdderTest())
ctx.reconcile_once()
