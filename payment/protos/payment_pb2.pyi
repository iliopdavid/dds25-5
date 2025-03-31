from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class BatchInitPayRequest(_message.Message):
    __slots__ = ("n", "starting_money")
    N_FIELD_NUMBER: _ClassVar[int]
    STARTING_MONEY_FIELD_NUMBER: _ClassVar[int]
    n: int
    starting_money: int
    def __init__(self, n: _Optional[int] = ..., starting_money: _Optional[int] = ...) -> None: ...

class BatchInitPayResponse(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class CreateUserRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CreateUserResponse(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class FindUserRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class FindUserResponse(_message.Message):
    __slots__ = ("user_id", "credit")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CREDIT_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    credit: int
    def __init__(self, user_id: _Optional[str] = ..., credit: _Optional[int] = ...) -> None: ...

class FundsRequest(_message.Message):
    __slots__ = ("user_id", "amount")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    amount: int
    def __init__(self, user_id: _Optional[str] = ..., amount: _Optional[int] = ...) -> None: ...

class FundsResponse(_message.Message):
    __slots__ = ("message", "statuscode")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STATUSCODE_FIELD_NUMBER: _ClassVar[int]
    message: str
    statuscode: int
    def __init__(self, message: _Optional[str] = ..., statuscode: _Optional[int] = ...) -> None: ...
