"""Root GraphQL schema for h-mem."""

import strawberry

from hmem.api.graphql.queries import Query
from hmem.api.graphql.mutations import Mutation

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
