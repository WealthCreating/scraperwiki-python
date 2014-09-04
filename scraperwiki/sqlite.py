from collections import Iterable, Mapping, OrderedDict
from sqlalchemy.dialects.sqlite import TEXT, INTEGER, BOOLEAN, REAL, DATE, DATETIME, BLOB

import atexit
import datetime
import os
import re
import time
import sys
import warnings
import sqlalchemy

DATABASE_NAME = os.environ.get("SCRAPERWIKI_DATABASE_NAME", "scraperwiki.sqlite")
DATABASE_TIMEOUT = float(os.environ.get("SCRAPERWIKI_DATABASE_TIMEOUT", 300))

class Blob(str):
    """
    Represents a blob as a string.
    """
    def __init__(self, *args, **kwargs):
        super(Blob, self).__init__(*args, **kwargs)

PYTHON_SQLITE_TYPE_MAP = {
    unicode: TEXT,
    str: TEXT,

    int: INTEGER,
    long: REAL,
    bool: BOOLEAN,
    float: REAL,

    datetime.date: DATE,
    datetime.datetime: DATETIME,

    Blob: BLOB
}


class _State(object):
    """
    This class maintains global state relating to the database such as
    table_name, connection. It does not form part of the public interface.
    """
    db_path = 'sqlite:///{}'.format(DATABASE_NAME)
    engine = None
    _connection = None
    _transaction = None
    metadata = None
    table = None
    table_name = 'swdata'
    table_pending = True
    vars_table_name = 'swvariables'
    
    @classmethod
    def connection(cls):
        if cls._connection is None:
            cls.engine = sqlalchemy.create_engine(cls.db_path, echo=True,
                    connect_args={'timeout': DATABASE_TIMEOUT})
            cls._connection = cls.engine.connect()
            cls.new_transaction()
        cls.reflect_metadata()
        cls.table = sqlalchemy.Table(cls.table_name, _State.metadata,
                                     extend_existing=True)
        return cls._connection

    @classmethod
    def new_transaction(cls):
        if cls._transaction is not None:
            cls._transaction.commit()
        cls._transaction = cls._connection.begin()

    @classmethod
    def reflect_metadata(cls):
        if cls.metadata is None:
            cls.metadata = sqlalchemy.MetaData(bind=cls.engine)
        cls.metadata.reflect()

def execute(query, data=None):
    connection = _State.connection()
    _State.new_transaction()

    if data is None:
        data = []

    result = connection.execute(query, data)

    if not result.returns_rows:
        return {u'data': [], u'keys': []}

    return {u'data': result.fetchall(), u'keys': result.keys()}

def select(query, data=None):
    connection = _State.connection()
    _State.new_transaction()
    if data is None:
        data = []

    result = connection.execute('select ' + query, data)

    rows = []
    for row in result:
        rows.append(OrderedDict(row.items()))

    return rows

def save(unique_keys, data, table_name=None):
    if table_name is not None:
        warnings.warn("scraperwiki.sql.save table_name is deprecated, \
                call scraperwiki.sql.set_table instead")
        table = sqlalchemy.Table(table_name, _State.metadata, extend_existing=True)
    else:
        table_name = _State.table_name

    connection = _State.connection()

    if isinstance(data, Mapping):
        # Is a single datum
        data = [data]
    elif not isinstance(data, Iterable):
        raise TypeError("Data must be a single mapping or an iterable \
                         of mappings")

    insert = _State.table.insert(prefixes=['OR REPLACE'])
    for row in data:
        fit_row(connection, row)
        insert.values(row).execute()

def set_table(table_name):
    _State.table = sqlalchemy.Table(table_name, _State.metadata, extend_existing=True)
    _State.table_pending = True
    _State.table_name = table_name

def show_tables():
    _State.connection()

    raise NotImplementedError()
    return {row['name']: row['sql'] for row in response}

def save_var(name, value):
    _State.connection()

    table_name = _State.table_name

    raise NotImplementedError()
    return data

def get_var(name, default=None):
    _State.connection()
    _State.new_transaction()

    table_name = _State.table_name

    raise NotImplementedError()
    return value

def create_index(column_names, table_name, unique=False):
    """
    Create a new index of the columns in column_names, where column_names is
    a list of strings, on table table_name. If unique is True, it will be a
    unique index. If if_not_exists is True, the index be checked to make sure
    it does not already exists, otherwise creating duplicate
    indices will result in an error.
    """
    connection = _State.connection()
    _State.reflect_metadata()

    table = sqlalchemy.Table(table_name, _State.metadata)

    index_name = re.sub(r'[^a-zA-Z0-9]', '', table_name) + '_'
    index_name += '_'.join(map(lambda x: re.sub(r'[^a-zA-Z0-9]', '', x), column_names))
    if unique:
        index_name += '_unique'

    columns = []
    for column_name in column_names:
        columns.append(table.columns[column_name])

    current_indices = [x.name for x in table.indexes]
    index = sqlalchemy.schema.Index(index_name, *columns, unique=unique)
    if index.name not in current_indices:
        index.create(bind=_State.engine)

def fit_row(connection, row):
    """
    Takes a row and checks to make sure it fits in the columns of the
    current table. If it does not fit, adds the required columns.
    """
    _State.reflect_metadata()

    original_columns = list(_State.table.columns)

    new_columns = []
    for column_name, column_value in row.items():
        new_column = sqlalchemy.Column(column_name, get_column_type(column_value))
        if not str(new_column) in _State.table.columns:
            new_columns.append(new_column)
            _State.table.append_column(new_column)

    if _State.table_pending:
        _State.metadata.create_all(_State.engine)
        _State.table_pending = False

    if original_columns != list(_State.table.columns) and original_columns != []:
        for new_column in new_columns:
            query = 'ALTER TABLE {} ADD {} {}'
            query = query.format(_State.table_name, new_column.name, new_column.type)
            s = sqlalchemy.sql.text(query)
            connection.execute(s)
            _State.reflect_metadata()

def get_column_type(column_value):
    """
    Return the appropriate SQL column type for the given value.
    """
    return PYTHON_SQLITE_TYPE_MAP[type(column_value)]

def commit():
    warnings.warn("scraperwiki.sql.commit is now a no-op")
