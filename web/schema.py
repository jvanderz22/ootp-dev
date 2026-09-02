from pathlib import Path

from ariadne import make_executable_schema, upload_scalar
from ariadne.scalars import ScalarType

from web.resolvers.mutation import mutation
from web.resolvers.query import query

_SDL = (Path(__file__).parent / "schema.graphql").read_text()

json_scalar = ScalarType("JSON")


@json_scalar.serializer
def serialize_json(value):
    return value


schema = make_executable_schema(
    _SDL, query, mutation, upload_scalar, json_scalar, convert_names_case=True
)
