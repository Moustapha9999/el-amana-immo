from pydantic import BaseModel, Field


class PlateformeModuleRead(BaseModel):
    id: str
    titre: str
    description: str
    route: str | None = None
    entry_path: str | None = None
    statut: str
    accessible: bool
    espace_id: str | None = None
    espace_titre: str | None = None
    espace_route: str | None = None


class PlateformeEspaceRead(BaseModel):
    id: str
    titre: str
    description: str
    route: str | None = None
    statut: str
    accessible: bool
    modules: list[PlateformeModuleRead] = Field(default_factory=list)
