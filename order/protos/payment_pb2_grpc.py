# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

from google.protobuf import struct_pb2 as google_dot_protobuf_dot_struct__pb2
from protos import payment_pb2 as protos_dot_payment__pb2

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
        + f' but the generated code in protos/payment_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class PaymentServiceStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.get_json = channel.unary_unary(
                '/PaymentService/get_json',
                request_serializer=protos_dot_payment__pb2.CreateUserRequest.SerializeToString,
                response_deserializer=google_dot_protobuf_dot_struct__pb2.Struct.FromString,
                _registered_method=True)
        self.batch_init_users = channel.unary_unary(
                '/PaymentService/batch_init_users',
                request_serializer=protos_dot_payment__pb2.BatchInitPayRequest.SerializeToString,
                response_deserializer=protos_dot_payment__pb2.BatchInitPayResponse.FromString,
                _registered_method=True)
        self.create_user = channel.unary_unary(
                '/PaymentService/create_user',
                request_serializer=protos_dot_payment__pb2.CreateUserRequest.SerializeToString,
                response_deserializer=protos_dot_payment__pb2.CreateUserResponse.FromString,
                _registered_method=True)
        self.find_user = channel.unary_unary(
                '/PaymentService/find_user',
                request_serializer=protos_dot_payment__pb2.FindUserRequest.SerializeToString,
                response_deserializer=protos_dot_payment__pb2.FindUserResponse.FromString,
                _registered_method=True)
        self.add_credit = channel.unary_unary(
                '/PaymentService/add_credit',
                request_serializer=protos_dot_payment__pb2.FundsRequest.SerializeToString,
                response_deserializer=protos_dot_payment__pb2.FundsResponse.FromString,
                _registered_method=True)
        self.remove_credit = channel.unary_unary(
                '/PaymentService/remove_credit',
                request_serializer=protos_dot_payment__pb2.FundsRequest.SerializeToString,
                response_deserializer=protos_dot_payment__pb2.FundsResponse.FromString,
                _registered_method=True)


class PaymentServiceServicer(object):
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

    def create_user(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def find_user(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def add_credit(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def remove_credit(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_PaymentServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'get_json': grpc.unary_unary_rpc_method_handler(
                    servicer.get_json,
                    request_deserializer=protos_dot_payment__pb2.CreateUserRequest.FromString,
                    response_serializer=google_dot_protobuf_dot_struct__pb2.Struct.SerializeToString,
            ),
            'batch_init_users': grpc.unary_unary_rpc_method_handler(
                    servicer.batch_init_users,
                    request_deserializer=protos_dot_payment__pb2.BatchInitPayRequest.FromString,
                    response_serializer=protos_dot_payment__pb2.BatchInitPayResponse.SerializeToString,
            ),
            'create_user': grpc.unary_unary_rpc_method_handler(
                    servicer.create_user,
                    request_deserializer=protos_dot_payment__pb2.CreateUserRequest.FromString,
                    response_serializer=protos_dot_payment__pb2.CreateUserResponse.SerializeToString,
            ),
            'find_user': grpc.unary_unary_rpc_method_handler(
                    servicer.find_user,
                    request_deserializer=protos_dot_payment__pb2.FindUserRequest.FromString,
                    response_serializer=protos_dot_payment__pb2.FindUserResponse.SerializeToString,
            ),
            'add_credit': grpc.unary_unary_rpc_method_handler(
                    servicer.add_credit,
                    request_deserializer=protos_dot_payment__pb2.FundsRequest.FromString,
                    response_serializer=protos_dot_payment__pb2.FundsResponse.SerializeToString,
            ),
            'remove_credit': grpc.unary_unary_rpc_method_handler(
                    servicer.remove_credit,
                    request_deserializer=protos_dot_payment__pb2.FundsRequest.FromString,
                    response_serializer=protos_dot_payment__pb2.FundsResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'PaymentService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('PaymentService', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class PaymentService(object):
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
            '/PaymentService/get_json',
            protos_dot_payment__pb2.CreateUserRequest.SerializeToString,
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
            '/PaymentService/batch_init_users',
            protos_dot_payment__pb2.BatchInitPayRequest.SerializeToString,
            protos_dot_payment__pb2.BatchInitPayResponse.FromString,
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
    def create_user(request,
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
            '/PaymentService/create_user',
            protos_dot_payment__pb2.CreateUserRequest.SerializeToString,
            protos_dot_payment__pb2.CreateUserResponse.FromString,
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
    def find_user(request,
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
            '/PaymentService/find_user',
            protos_dot_payment__pb2.FindUserRequest.SerializeToString,
            protos_dot_payment__pb2.FindUserResponse.FromString,
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
    def add_credit(request,
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
            '/PaymentService/add_credit',
            protos_dot_payment__pb2.FundsRequest.SerializeToString,
            protos_dot_payment__pb2.FundsResponse.FromString,
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
    def remove_credit(request,
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
            '/PaymentService/remove_credit',
            protos_dot_payment__pb2.FundsRequest.SerializeToString,
            protos_dot_payment__pb2.FundsResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
