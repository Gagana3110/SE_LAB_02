from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Code = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=32,
                      pattern=r"^[A-Za-z0-9_-]+$"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class ItemCreate(BaseModel):
    code: Code
    name: Name
    unit: Unit
    category: Category | None = None


class ItemUpdate(BaseModel):
    """Only the fields sent are changed. Send active=false to deactivate."""

    code: Code | None = None
    name: Name | None = None
    unit: Unit | None = None
    category: Category | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_cleared(self):
        for field in ("code", "name", "unit", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    unit: str
    category: str | None
    active: bool


class BomLineIn(BaseModel):
    material_id: int
    qty_per_unit: Decimal = Field(gt=0, max_digits=12, decimal_places=4)


class BomUpdate(BaseModel):
    lines: list[BomLineIn]

    @model_validator(mode="after")
    def materials_are_unique(self):
        ids = [line.material_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("A material can appear only once in a BOM")
        return self


class BomLineOut(BaseModel):
    material: ItemOut
    qty_per_unit: float
