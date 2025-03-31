from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class EmptyRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BatchInitOrderRequest(_message.Message):
    __slots__ = ("n", "n_items", "n_users", "item_price")
    N_FIELD_NUMBER: _ClassVar[int]
    N_ITEMS_FIELD_NUMBER: _ClassVar[int]
    N_USERS_FIELD_NUMBER: _ClassVar[int]
    ITEM_PRICE_FIELD_NUMBER: _ClassVar[int]
    n: int
    n_items: int
    n_users: int
    item_price: int
    def __init__(self, n: _Optional[int] = ..., n_items: _Optional[int] = ..., n_users: _Optional[int] = ..., item_price: _Optional[int] = ...) -> None: ...

class BatchInitOrderResponse(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class CreateOrderRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class CreateOrderResponse(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class OrderIdRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class FindOrderResponse(_message.Message):
    __slots__ = ("order_id", "paid", "items", "user_id", "total_cost")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    PAID_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COST_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    paid: bool
    items: _containers.RepeatedScalarFieldContainer[str]
    user_id: str
    total_cost: int
    def __init__(self, order_id: _Optional[str] = ..., paid: bool = ..., items: _Optional[_Iterable[str]] = ..., user_id: _Optional[str] = ..., total_cost: _Optional[int] = ...) -> None: ...

class AddItemRequest(_message.Message):
    __slots__ = ("order_id", "item_id", "quantity")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    item_id: str
    quantity: int
    def __init__(self, order_id: _Optional[str] = ..., item_id: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class StatuscodeResponse(_message.Message):
    __slots__ = ("message", "statuscode")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STATUSCODE_FIELD_NUMBER: _ClassVar[int]
    message: str
    statuscode: int
    def __init__(self, message: _Optional[str] = ..., statuscode: _Optional[int] = ...) -> None: ...
