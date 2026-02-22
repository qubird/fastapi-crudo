"""
🍖 Dynamic Pydantic schema generation from SQLAlchemy models.

Inspects SQLAlchemy model columns and creates Read / Create / Update
Pydantic schemas automatically.
"""

from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, create_model, model_serializer
from sqlalchemy import inspect as sa_inspect


def _serialize_value(v: Any) -> Any:
    """Convert non-JSON-serializable values (e.g. PostGIS WKBElement)."""
    cls_name = type(v).__name__
    if cls_name == "WKBElement":
        try:
            from geoalchemy2.shape import to_shape

            geom = to_shape(v)
            return f"POINT({geom.x} {geom.y})" if geom.geom_type == "Point" else geom.wkt
        except Exception:
            return str(v)
    return v


# ---------------------------------------------------------------------------
# Base schema – all generated schemas inherit from this
# ---------------------------------------------------------------------------


class CrudoBaseSchema(BaseModel):
    """Base Pydantic schema with ORM-mode (from_attributes) enabled."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        """Convert geometry values after model construction."""
        for field_name in self.model_fields:
            val = getattr(self, field_name, None)
            if val is not None and type(val).__name__ == "WKBElement":
                object.__setattr__(self, field_name, _serialize_value(val))


# ---------------------------------------------------------------------------
# SQLAlchemy type → (json_type_string, python_type) mapping
# ---------------------------------------------------------------------------

_SA_TYPE_MAP: Dict[str, Tuple[str, type]] = {
    # Integers
    "INTEGER": ("integer", int),
    "SMALLINT": ("integer", int),
    "SMALLINTEGER": ("integer", int),
    "BIGINT": ("integer", int),
    "BIGINTEGER": ("integer", int),
    "SERIAL": ("integer", int),
    "BIGSERIAL": ("integer", int),
    # Strings
    "VARCHAR": ("string", str),
    "NVARCHAR": ("string", str),
    "CHAR": ("string", str),
    "NCHAR": ("string", str),
    "STRING": ("string", str),
    "TEXT": ("string", str),
    "UNICODE": ("string", str),
    "UNICODETEXT": ("string", str),
    "CLOB": ("string", str),
    # Boolean
    "BOOLEAN": ("boolean", bool),
    # Numeric
    "FLOAT": ("number", float),
    "REAL": ("number", float),
    "DOUBLE": ("number", float),
    "DOUBLE_PRECISION": ("number", float),
    "NUMERIC": ("number", float),
    "DECIMAL": ("number", float),
    # Date / Time
    "DATETIME": ("datetime", datetime),
    "DATE": ("date", date),
    "TIME": ("time", time),
    "TIMESTAMP": ("datetime", datetime),
    # Enum
    "ENUM": ("enum", str),
    # JSON
    "JSON": ("json", Any),
    "JSONB": ("json", Any),
    # Array
    "ARRAY": ("array", list),
    # UUID
    "UUID": ("string", str),
    # Binary (mapped to str for JSON transport)
    "BLOB": ("string", str),
    "BYTEA": ("string", str),
    "LARGEBINARY": ("string", str),
    # Misc
    "INTERVAL": ("string", str),
    "INET": ("string", str),
    "CIDR": ("string", str),
    "MACADDR": ("string", str),
    # Geometry / PostGIS (use Any — WKBElement needs custom serialization)
    "GEOMETRY": ("geometry", Any),
    "GEOGRAPHY": ("geometry", Any),
    "RASTER": ("geometry", Any),
}


def _get_sa_type_info(column) -> Tuple[str, type]:
    """Return (json_type_string, python_type) for a SQLAlchemy column."""
    type_name = type(column.type).__name__.upper()
    if type_name in _SA_TYPE_MAP:
        return _SA_TYPE_MAP[type_name]

    # Fallback: try to match by the string representation
    type_str = str(column.type).upper()
    if "INT" in type_str:
        return ("integer", int)
    if any(t in type_str for t in ("CHAR", "TEXT", "CLOB")):
        return ("string", str)
    if "BOOL" in type_str:
        return ("boolean", bool)
    if any(t in type_str for t in ("FLOAT", "DOUBLE", "NUMERIC", "DECIMAL")):
        return ("number", float)
    if "TIMESTAMP" in type_str or "DATETIME" in type_str:
        return ("datetime", datetime)
    if "DATE" in type_str:
        return ("date", date)
    if "TIME" in type_str:
        return ("time", time)
    if "JSON" in type_str:
        return ("json", Any)
    if "UUID" in type_str:
        return ("string", str)

    return ("string", str)


# ---------------------------------------------------------------------------
# Column metadata (used by the React UI)
# ---------------------------------------------------------------------------


def get_column_metadata(model) -> List[Dict[str, Any]]:
    """Extract rich column metadata from a SQLAlchemy model for the UI."""
    columns: List[Dict[str, Any]] = []
    mapper = sa_inspect(model)

    for col in mapper.columns:
        json_type, _ = _get_sa_type_info(col)

        # Enum values
        enum_values = None
        if hasattr(col.type, "enums"):
            enum_values = list(col.type.enums)
        elif hasattr(col.type, "enum_class") and col.type.enum_class:
            enum_values = [
                e.value if hasattr(e, "value") else str(e)
                for e in col.type.enum_class
            ]

        max_length = getattr(col.type, "length", None)
        is_fk = bool(col.foreign_keys)

        columns.append(
            {
                "name": col.name,
                "type": json_type,
                "sa_type": type(col.type).__name__,
                "primary_key": col.primary_key,
                "nullable": bool(col.nullable),
                "has_default": (
                    col.default is not None or col.server_default is not None
                ),
                "is_auto_pk": _is_auto_pk(col),
                "is_foreign_key": is_fk,
                "foreign_key_target": (
                    str(list(col.foreign_keys)[0].target_fullname)
                    if is_fk
                    else None
                ),
                "enum_values": enum_values,
                "max_length": max_length,
                "comment": col.comment,
            }
        )

    return columns


# ---------------------------------------------------------------------------
# Primary-key helpers
# ---------------------------------------------------------------------------


def _is_auto_pk(column) -> bool:
    """Check whether a column is an auto-generated primary key."""
    if not column.primary_key:
        return False
    if column.server_default is not None:
        return True
    if column.default is not None:
        return True
    autoincrement = getattr(column, "autoincrement", None)
    if autoincrement is True:
        return True
    if autoincrement == "auto":
        type_name = type(column.type).__name__.upper()
        if "INT" in type_name:
            return True
    return False


def get_pk_columns(model) -> List[str]:
    """Return primary key column names for a model."""
    mapper = sa_inspect(model)
    return [col.name for col in mapper.columns if col.primary_key]


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------


def create_schemas_for_model(model) -> Dict[str, Any]:
    """
    Create **Read**, **Create**, and **Update** Pydantic schemas for a
    SQLAlchemy model.

    Returns a dict::

        {
            "read":       <ReadSchema>,
            "create":     <CreateSchema>,
            "update":     <UpdateSchema>,
            "pk_columns": ["id"],
        }
    """
    mapper = sa_inspect(model)
    pk_columns = get_pk_columns(model)

    read_fields: Dict[str, Any] = {}
    create_fields: Dict[str, Any] = {}
    update_fields: Dict[str, Any] = {}

    for col in mapper.columns:
        _, python_type = _get_sa_type_info(col)

        # Read schema — always Optional for resilience
        read_fields[col.name] = (Optional[python_type], None)

        # Create schema — skip auto-generated PKs
        if _is_auto_pk(col):
            pass  # omit from create payload
        elif (
            col.server_default is not None
            or col.default is not None
            or col.nullable
        ):
            create_fields[col.name] = (Optional[python_type], None)
        else:
            create_fields[col.name] = (python_type, ...)

        # Update schema — everything optional
        update_fields[col.name] = (Optional[python_type], None)

    read_schema = create_model(
        f"{model.__name__}Read",
        __base__=CrudoBaseSchema,
        **read_fields,
    )
    create_schema = create_model(
        f"{model.__name__}Create",
        __base__=CrudoBaseSchema,
        **create_fields,
    )
    update_schema = create_model(
        f"{model.__name__}Update",
        __base__=CrudoBaseSchema,
        **update_fields,
    )

    return {
        "read": read_schema,
        "create": create_schema,
        "update": update_schema,
        "pk_columns": pk_columns,
    }
