import logging
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path

from rich.logging import RichHandler

from equilibrium.core.ControllerContext import ControllerContext
from equilibrium.core.CrudResourceController import CrudResourceController
from equilibrium.core.Resource import Resource

logging.basicConfig(level="NOTSET", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])


@dataclass
class LocalFile(Resource.Spec, apiVersion="example.com/v1", kind="LocalFile"):
    path: str
    content: str

    @dataclass
    class State(Resource.State):
        path: str
        md5sumdigest: str


class LocalFileController(
    CrudResourceController[LocalFile, LocalFile.State],
    spec_type=LocalFile,
    state_type=LocalFile.State,
):
    def read(
        self,
        resource: Resource[LocalFile],
        state: LocalFile.State,
    ) -> LocalFile.State | CrudResourceController.Status:
        try:
            with Path(state.path).open("rb") as f:
                return LocalFile.State(state.path, md5(f.read()).hexdigest())
        except FileNotFoundError:
            return self.Deleted

    def create(self, resource: Resource[LocalFile]) -> LocalFile.State:
        logging.info("Creating local file '%s'", resource.spec.path)
        Path(resource.spec.path).write_text(resource.spec.content)
        return LocalFile.State(resource.spec.path, md5(resource.spec.content.encode("utf-8")).hexdigest())

    def update(self, resource: Resource[LocalFile], state: LocalFile.State) -> LocalFile.State:
        recreate = False
        if state.path != resource.spec.path:
            logging.info("Moving local file '%s' to '%s'", state.path, resource.spec.path)
            try:
                Path(state.path).rename(resource.spec.path)
            except OSError:
                logging.info("Cannot move file '%s' to '%s', recreating it instead.", state.path, resource.spec.path)
                Path(state.path).unlink()
                recreate = True

        md5sum = md5(resource.spec.content.encode("utf-8")).hexdigest()
        if state.md5sumdigest != md5sum or recreate:
            logging.info("Updating local file '%s'", resource.spec.path)
            Path(resource.spec.path).write_text(resource.spec.content)

        return LocalFile.State(resource.spec.path, md5sum)

    def delete(self, state: LocalFile.State) -> CrudResourceController.Status:
        if Path(state.path).exists():
            logging.info("Deleting local file '%s'", state.path)
            Path(state.path).unlink()
        return self.Deleted

    def admit(self, resource: Resource[Resource.T_Spec]) -> Resource[Resource.T_Spec]:
        return resource


ctx = ControllerContext.with_json_backend("data")
ctx.register_resource_type(LocalFile)
ctx.register_controller(LocalFileController())
ctx.load_manifest(Path(__file__).parent / "manifest.yaml")
# ctx.delete_resource(LocalFile.uri("default", "local-file"), do_raise=False)
ctx.reconcile_once()
