# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: order.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'order.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0border.proto\"S\n\x10\x42\x61tchInitRequest\x12\t\n\x01n\x18\x01 \x01(\x05\x12\x0f\n\x07n_items\x18\x02 \x01(\x05\x12\x0f\n\x07n_users\x18\x03 \x01(\x05\x12\x12\n\nitem_price\x18\x04 \x01(\x05\"$\n\x11\x42\x61tchInitResponse\x12\x0f\n\x07message\x18\x01 \x01(\t\"%\n\x12\x43reateOrderRequest\x12\x0f\n\x07user_id\x18\x01 \x01(\t\"\'\n\x13\x43reateOrderResponse\x12\x10\n\x08order_id\x18\x01 \x01(\t\"\"\n\x0eOrderIdRequest\x12\x10\n\x08order_id\x18\x01 \x01(\t\"\xb4\x01\n\x11\x46indOrderResponse\x12\x10\n\x08order_id\x18\x01 \x01(\t\x12\x0c\n\x04paid\x18\x02 \x01(\x08\x12,\n\x05items\x18\x03 \x03(\x0b\x32\x1d.FindOrderResponse.ItemsEntry\x12\x0f\n\x07user_id\x18\x04 \x01(\t\x12\x12\n\ntotal_cost\x18\x05 \x01(\x05\x1a,\n\nItemsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x05:\x02\x38\x01\"E\n\x0e\x41\x64\x64ItemRequest\x12\x10\n\x08order_id\x18\x01 \x01(\t\x12\x0f\n\x07item_id\x18\x02 \x01(\t\x12\x10\n\x08quantity\x18\x03 \x01(\x05\"(\n\x12StatuscodeResponse\x12\x12\n\nstatuscode\x18\x01 \x01(\x05\x32\x9b\x02\n\x0cOrderService\x12\x39\n\x10\x62\x61tch_init_users\x12\x11.BatchInitRequest\x1a\x12.BatchInitResponse\x12\x39\n\x0c\x63reate_order\x12\x13.CreateOrderRequest\x1a\x14.CreateOrderResponse\x12\x31\n\nfind_order\x12\x0f.OrderIdRequest\x1a\x12.FindOrderResponse\x12\x30\n\x08\x61\x64\x64_item\x12\x0f.AddItemRequest\x1a\x13.StatuscodeResponse\x12\x30\n\x08\x63heckout\x12\x0f.OrderIdRequest\x1a\x13.StatuscodeResponseb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'order_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_FINDORDERRESPONSE_ITEMSENTRY']._loaded_options = None
  _globals['_FINDORDERRESPONSE_ITEMSENTRY']._serialized_options = b'8\001'
  _globals['_BATCHINITREQUEST']._serialized_start=15
  _globals['_BATCHINITREQUEST']._serialized_end=98
  _globals['_BATCHINITRESPONSE']._serialized_start=100
  _globals['_BATCHINITRESPONSE']._serialized_end=136
  _globals['_CREATEORDERREQUEST']._serialized_start=138
  _globals['_CREATEORDERREQUEST']._serialized_end=175
  _globals['_CREATEORDERRESPONSE']._serialized_start=177
  _globals['_CREATEORDERRESPONSE']._serialized_end=216
  _globals['_ORDERIDREQUEST']._serialized_start=218
  _globals['_ORDERIDREQUEST']._serialized_end=252
  _globals['_FINDORDERRESPONSE']._serialized_start=255
  _globals['_FINDORDERRESPONSE']._serialized_end=435
  _globals['_FINDORDERRESPONSE_ITEMSENTRY']._serialized_start=391
  _globals['_FINDORDERRESPONSE_ITEMSENTRY']._serialized_end=435
  _globals['_ADDITEMREQUEST']._serialized_start=437
  _globals['_ADDITEMREQUEST']._serialized_end=506
  _globals['_STATUSCODERESPONSE']._serialized_start=508
  _globals['_STATUSCODERESPONSE']._serialized_end=548
  _globals['_ORDERSERVICE']._serialized_start=551
  _globals['_ORDERSERVICE']._serialized_end=834
# @@protoc_insertion_point(module_scope)
