from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class EmptySRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BatchInitStockRequest(_message.Message):
    __slots__ = ("n", "starting_money", "item_price")
    N_FIELD_NUMBER: _ClassVar[int]
    STARTING_MONEY_FIELD_NUMBER: _ClassVar[int]
    ITEM_PRICE_FIELD_NUMBER: _ClassVar[int]
    n: int
    starting_money: int
    item_price: int
    def __init__(self, n: _Optional[int] = ..., starting_money: _Optional[int] = ..., item_price: _Optional[int] = ...) -> None: ...

class BatchInitStockResponse(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class CreateItemRequest(_message.Message):
    __slots__ = ("price",)
    PRICE_FIELD_NUMBER: _ClassVar[int]
    price: int
    def __init__(self, price: _Optional[int] = ...) -> None: ...

class CreateItemResponse(_message.Message):
    __slots__ = ("item_id",)
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    def __init__(self, item_id: _Optional[str] = ...) -> None: ...

class FindItemRequest(_message.Message):
    __slots__ = ("item_id",)
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    def __init__(self, item_id: _Optional[str] = ...) -> None: ...

class FindItemResponse(_message.Message):
    __slots__ = ("stock", "price")
    STOCK_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    stock: int
    price: int
    def __init__(self, stock: _Optional[int] = ..., price: _Optional[int] = ...) -> None: ...

class StockRequest(_message.Message):
    __slots__ = ("item_id", "amount")
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    amount: int
    def __init__(self, item_id: _Optional[str] = ..., amount: _Optional[int] = ...) -> None: ...

class StockResponse(_message.Message):
    __slots__ = ("message", "statuscode")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STATUSCODE_FIELD_NUMBER: _ClassVar[int]
    message: str
    statuscode: int
    def __init__(self, message: _Optional[str] = ..., statuscode: _Optional[int] = ...) -> None: ...
