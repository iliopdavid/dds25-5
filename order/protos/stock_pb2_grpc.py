# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

from google.protobuf import struct_pb2 as google_dot_protobuf_dot_struct__pb2
from protos import stock_pb2 as protos_dot_stock__pb2

GRPC_GENERATED_VERSION = '1.71.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in protos/stock_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class StockServiceStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.get_json = channel.unary_unary(
                '/StockService/get_json',
                request_serializer=protos_dot_stock__pb2.EmptySRequest.SerializeToString,
                response_deserializer=google_dot_protobuf_dot_struct__pb2.Struct.FromString,
                _registered_method=True)
        self.batch_init_users = channel.unary_unary(
                '/StockService/batch_init_users',
                request_serializer=protos_dot_stock__pb2.BatchInitStockRequest.SerializeToString,
                response_deserializer=protos_dot_stock__pb2.BatchInitStockResponse.FromString,
                _registered_method=True)
        self.create_item = channel.unary_unary(
                '/StockService/create_item',
                request_serializer=protos_dot_stock__pb2.CreateItemRequest.SerializeToString,
                response_deserializer=protos_dot_stock__pb2.CreateItemResponse.FromString,
                _registered_method=True)
        self.find_item = channel.unary_unary(
                '/StockService/find_item',
                request_serializer=protos_dot_stock__pb2.FindItemRequest.SerializeToString,
                response_deserializer=protos_dot_stock__pb2.FindItemResponse.FromString,
                _registered_method=True)
        self.add_stock = channel.unary_unary(
                '/StockService/add_stock',
                request_serializer=protos_dot_stock__pb2.StockRequest.SerializeToString,
                response_deserializer=protos_dot_stock__pb2.StockResponse.FromString,
                _registered_method=True)
        self.remove_stock = channel.unary_unary(
                '/StockService/remove_stock',
                request_serializer=protos_dot_stock__pb2.StockRequest.SerializeToString,
                response_deserializer=protos_dot_stock__pb2.StockResponse.FromString,
                _registered_method=True)


class StockServiceServicer(object):
    """Missing associated documentation comment in .proto file."""

    def get_json(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def batch_init_users(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def create_item(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def find_item(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def add_stock(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def remove_stock(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_StockServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'get_json': grpc.unary_unary_rpc_method_handler(
                    servicer.get_json,
                    request_deserializer=protos_dot_stock__pb2.EmptySRequest.FromString,
                    response_serializer=google_dot_protobuf_dot_struct__pb2.Struct.SerializeToString,
            ),
            'batch_init_users': grpc.unary_unary_rpc_method_handler(
                    servicer.batch_init_users,
                    request_deserializer=protos_dot_stock__pb2.BatchInitStockRequest.FromString,
                    response_serializer=protos_dot_stock__pb2.BatchInitStockResponse.SerializeToString,
            ),
            'create_item': grpc.unary_unary_rpc_method_handler(
                    servicer.create_item,
                    request_deserializer=protos_dot_stock__pb2.CreateItemRequest.FromString,
                    response_serializer=protos_dot_stock__pb2.CreateItemResponse.SerializeToString,
            ),
            'find_item': grpc.unary_unary_rpc_method_handler(
                    servicer.find_item,
                    request_deserializer=protos_dot_stock__pb2.FindItemRequest.FromString,
                    response_serializer=protos_dot_stock__pb2.FindItemResponse.SerializeToString,
            ),
            'add_stock': grpc.unary_unary_rpc_method_handler(
                    servicer.add_stock,
                    request_deserializer=protos_dot_stock__pb2.StockRequest.FromString,
                    response_serializer=protos_dot_stock__pb2.StockResponse.SerializeToString,
            ),
            'remove_stock': grpc.unary_unary_rpc_method_handler(
                    servicer.remove_stock,
                    request_deserializer=protos_dot_stock__pb2.StockRequest.FromString,
                    response_serializer=protos_dot_stock__pb2.StockResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'StockService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('StockService', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class StockService(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def get_json(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/get_json',
            protos_dot_stock__pb2.EmptySRequest.SerializeToString,
            google_dot_protobuf_dot_struct__pb2.Struct.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def batch_init_users(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/batch_init_users',
            protos_dot_stock__pb2.BatchInitStockRequest.SerializeToString,
            protos_dot_stock__pb2.BatchInitStockResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def create_item(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/create_item',
            protos_dot_stock__pb2.CreateItemRequest.SerializeToString,
            protos_dot_stock__pb2.CreateItemResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def find_item(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/find_item',
            protos_dot_stock__pb2.FindItemRequest.SerializeToString,
            protos_dot_stock__pb2.FindItemResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def add_stock(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/add_stock',
            protos_dot_stock__pb2.StockRequest.SerializeToString,
            protos_dot_stock__pb2.StockResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def remove_stock(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/StockService/remove_stock',
            protos_dot_stock__pb2.StockRequest.SerializeToString,
            protos_dot_stock__pb2.StockResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
