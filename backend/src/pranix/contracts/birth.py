# SPDX-License-Identifier: AGPL-3.0-only
"""Guest birth input (OpenAPI BirthInput). additionalProperties: false — name, pronouns and other
profile fields are rejected here (FR-INP-07); for guests they never leave the browser."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlaceById(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: Annotated[str, Field(pattern=r"^geonames:[0-9]{1,12}$")]


class PlaceByCoords(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class BirthInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: PlaceById | PlaceByCoords
    local_datetime: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")]
    birth_time_known: bool
    time_accuracy: Literal["exact", "approx_5m", "approx_30m", "approx_1h"] | None = None
    disambiguation: Literal["earlier", "later"] | None = None
    ruleset: Annotated[str, Field(pattern=r"^vedic-core@1$")] = "vedic-core@1"
