import logging
from dataclasses import dataclass
from equilibrium.core.Resource import Resource
from equilibrium.core.Namespace import Namespace
from equilibrium.core.CrudResourceController import CrudResourceController
from equilibrium.core.ControllerContext import ControllerContext

from rich.logging import RichHandler

logging.basicConfig(
    level="NOTSET",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

@dataclass
class LocalFile(Resource.Spec, apiVersion="example.com/v1", kind="LocalFile"):
    path: str
    content: str

    @dataclass
    class State(Resource.State):
        path: str
        md5sumdigest: str

class LocalFileController(CrudResourceController, spec_type=LocalFile, state_type=LocalFile.State):

    def read(self, resource: Resource[Resource.T_Spec], state: Resource.T_State) -> Resource.T_State:
        return super().read(resource, state)

    def create(self, resource: Resource[LocalFile]) -> None:
        print("Foo")
        pass

    def update(self, resource: Resource[LocalFile]) -> None:
        pass

    def delete(self, resource: Resource[LocalFile]) -> None:
        pass

    def admit(self, resource: Resource[Resource.T_Spec]) -> Resource[Resource.T_Spec]:
        return resource


ctx = ControllerContext.with_json_backend("data")
ctx.register_resource_type(LocalFile)
ctx.register_controller(LocalFileController())
# ctx.put_resource(Namespace().as_resource(Resource.Metadata(None, "default")))
# ctx.put_resource(LocalFile(path="/tmp/foo", content="Hello, world!").as_resource(Resource.Metadata("default", "foo")))
ctx.reconcile_once()
