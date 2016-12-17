from __future__ import absolute_import

import six
from sqlalchemy.orm import Query

import graphjoiner
from graphjoiner import declarative
from . import ObjectType


class SqlAlchemyObjectType(ObjectType):
    __abstract__ = True
    
    @staticmethod
    def __field__(column):
        # TODO: SQLAlchemy type to GraphQL type
        return graphjoiner.field(column=column, type=None)
    
    @classmethod
    def __select_all__(cls):
        return Query([]).select_from(cls.__model__)
    
    @classmethod
    def __relationship__(cls, target, join=None):
        # TODO: use join when join condition is explicity set for SQLAlchemy
        if join is None:
            if issubclass(target, SqlAlchemyObjectType):
                return _relationship_to_sqlalchemy(cls, target)
            else:
                raise Exception("join must be explicitly set when joining to non-SQLAlchemy types")
        else:
            def select(parent_select, context):
                return parent_select.with_entities(*(
                        local_field.column.label(remote_field.attr_name)
                        for local_field, remote_field in six.iteritems(join)
                    )) \
                    .with_session(context.session) \
                    .all()
            
            return select, dict(
                (local_field.field_name, remote_field.field_name)
                for local_field, remote_field in six.iteritems(join)
            )
        
    @classmethod
    def __fetch_immediates__(cls, selections, query, context):
        query = query.with_entities(*(
            selection.field.column
            for selection in selections
        ))
        for primary_key_column in cls.__model__.__mapper__.primary_key:
            query = query.add_columns(primary_key_column)
        
        return query.distinct().with_session(context.session).all()
        
        
def _relationship_to_sqlalchemy(local, target):
    local_field, remote_field = _find_foreign_key(local, target)
    
    def select(parent_select, context):
        parents = parent_select \
            .with_entities(local_field._kwargs["column"]) \
            .subquery()
            
        return Query([]) \
            .select_from(target.__model__) \
            .join(parents, parents.c.values()[0] == remote_field._kwargs["column"])

    
    join = {local_field.field_name: remote_field.field_name}
    
    return select, join
    

def _find_foreign_key(local, target):
    foreign_keys = list(_find_join_candidates(local, target))
    if len(foreign_keys) == 1:
        foreign_key, = foreign_keys
        return foreign_key
    else:
        raise Exception("TODO")
    
def _find_join_candidates(local, target):
    for local_field, target_field in _find_join_candidates_directional(local, target):
        yield local_field, target_field
    for target_field, local_field in _find_join_candidates_directional(target, local):
        yield local_field, target_field

def _find_join_candidates_directional(local, remote):
    for field_definition in _get_simple_field_definitions(local):
        column, = field_definition._kwargs["column"].property.columns
        for foreign_key in column.foreign_keys:
            if remote.__model__.__table__ == foreign_key.column.table:
                remote_primary_key_column, = foreign_key.column.table.primary_key
                remote_field = _find_field_for_column(remote, remote_primary_key_column)
                yield field_definition, remote_field
    

def _find_field_for_column(cls, column):
    for field_definition in _get_simple_field_definitions(cls):
        if field_definition._kwargs["column"] == column:
            return field_definition
    raise Exception("Could not find find field in {} for {}".format(cls.__name__, column))

def _get_simple_field_definitions(cls):
    for field_definition in six.itervalues(cls.__dict__):
        if isinstance(field_definition, declarative.SimpleFieldDefinition):
            yield field_definition
