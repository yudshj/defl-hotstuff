"""
@generated by mypy-protobuf.  Do not edit manually!
isort:skip_file
"""
import builtins
import google.protobuf.descriptor
import google.protobuf.internal.containers
import google.protobuf.internal.enum_type_wrapper
import google.protobuf.message
import typing
import typing_extensions

DESCRIPTOR: google.protobuf.descriptor.FileDescriptor

class RegisterInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor
    HOST_FIELD_NUMBER: builtins.int
    PORT_FIELD_NUMBER: builtins.int
    PASV_HOST_FIELD_NUMBER: builtins.int
    PASV_PORT_FIELD_NUMBER: builtins.int
    host: typing.Text
    port: builtins.int
    pasv_host: typing.Text
    pasv_port: builtins.int
    def __init__(self,
        *,
        host: typing.Text = ...,
        port: builtins.int = ...,
        pasv_host: typing.Text = ...,
        pasv_port: builtins.int = ...,
        ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["host",b"host","pasv_host",b"pasv_host","pasv_port",b"pasv_port","port",b"port"]) -> None: ...
global___RegisterInfo = RegisterInfo

class ClientRequest(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor
    class _Method:
        ValueType = typing.NewType('ValueType', builtins.int)
        V: typing_extensions.TypeAlias = ValueType
    class _MethodEnumTypeWrapper(google.protobuf.internal.enum_type_wrapper._EnumTypeWrapper[ClientRequest._Method.ValueType], builtins.type):
        DESCRIPTOR: google.protobuf.descriptor.EnumDescriptor
        FETCH_W_LAST: ClientRequest._Method.ValueType  # 0
        NEW_WEIGHTS: ClientRequest._Method.ValueType  # 1
        NEW_EPOCH_REQUEST: ClientRequest._Method.ValueType  # 2
        CLIENT_REGISTER: ClientRequest._Method.ValueType  # 7
        """Registration"""

    class Method(_Method, metaclass=_MethodEnumTypeWrapper):
        pass

    FETCH_W_LAST: ClientRequest.Method.ValueType  # 0
    NEW_WEIGHTS: ClientRequest.Method.ValueType  # 1
    NEW_EPOCH_REQUEST: ClientRequest.Method.ValueType  # 2
    CLIENT_REGISTER: ClientRequest.Method.ValueType  # 7
    """Registration"""


    METHOD_FIELD_NUMBER: builtins.int
    REQUEST_UUID_FIELD_NUMBER: builtins.int
    CLIENT_NAME_FIELD_NUMBER: builtins.int
    TARGET_EPOCH_ID_FIELD_NUMBER: builtins.int
    WEIGHTS_FIELD_NUMBER: builtins.int
    REGISTER_INFO_FIELD_NUMBER: builtins.int
    method: global___ClientRequest.Method.ValueType
    request_uuid: typing.Text
    client_name: typing.Text
    target_epoch_id: builtins.int
    weights: builtins.bytes
    @property
    def register_info(self) -> global___RegisterInfo: ...
    def __init__(self,
        *,
        method: global___ClientRequest.Method.ValueType = ...,
        request_uuid: typing.Text = ...,
        client_name: typing.Text = ...,
        target_epoch_id: typing.Optional[builtins.int] = ...,
        weights: typing.Optional[builtins.bytes] = ...,
        register_info: typing.Optional[global___RegisterInfo] = ...,
        ) -> None: ...
    def HasField(self, field_name: typing_extensions.Literal["_register_info",b"_register_info","_target_epoch_id",b"_target_epoch_id","_weights",b"_weights","register_info",b"register_info","target_epoch_id",b"target_epoch_id","weights",b"weights"]) -> builtins.bool: ...
    def ClearField(self, field_name: typing_extensions.Literal["_register_info",b"_register_info","_target_epoch_id",b"_target_epoch_id","_weights",b"_weights","client_name",b"client_name","method",b"method","register_info",b"register_info","request_uuid",b"request_uuid","target_epoch_id",b"target_epoch_id","weights",b"weights"]) -> None: ...
    @typing.overload
    def WhichOneof(self, oneof_group: typing_extensions.Literal["_register_info",b"_register_info"]) -> typing.Optional[typing_extensions.Literal["register_info"]]: ...
    @typing.overload
    def WhichOneof(self, oneof_group: typing_extensions.Literal["_target_epoch_id",b"_target_epoch_id"]) -> typing.Optional[typing_extensions.Literal["target_epoch_id"]]: ...
    @typing.overload
    def WhichOneof(self, oneof_group: typing_extensions.Literal["_weights",b"_weights"]) -> typing.Optional[typing_extensions.Literal["weights"]]: ...
global___ClientRequest = ClientRequest

class Response(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor
    class _Status:
        ValueType = typing.NewType('ValueType', builtins.int)
        V: typing_extensions.TypeAlias = ValueType
    class _StatusEnumTypeWrapper(google.protobuf.internal.enum_type_wrapper._EnumTypeWrapper[Response._Status.ValueType], builtins.type):
        DESCRIPTOR: google.protobuf.descriptor.EnumDescriptor
        OK: Response._Status.ValueType  # 0
        NOT_MEET_QUORUM_WAIT: Response._Status.ValueType  # 1
        UNEXPECTED_TARGET_EPOCH_ID_ERROR: Response._Status.ValueType  # 2
        NO_WEIGHTS_IN_REQUEST_ERROR: Response._Status.ValueType  # 3
        CLIENT_ALREADY_VOTED_ERROR: Response._Status.ValueType  # 4
        SERVER_INTERNAL_ERROR: Response._Status.ValueType  # 404
    class Status(_Status, metaclass=_StatusEnumTypeWrapper):
        pass

    OK: Response.Status.ValueType  # 0
    NOT_MEET_QUORUM_WAIT: Response.Status.ValueType  # 1
    UNEXPECTED_TARGET_EPOCH_ID_ERROR: Response.Status.ValueType  # 2
    NO_WEIGHTS_IN_REQUEST_ERROR: Response.Status.ValueType  # 3
    CLIENT_ALREADY_VOTED_ERROR: Response.Status.ValueType  # 4
    SERVER_INTERNAL_ERROR: Response.Status.ValueType  # 404

    class WLastEntry(google.protobuf.message.Message):
        DESCRIPTOR: google.protobuf.descriptor.Descriptor
        KEY_FIELD_NUMBER: builtins.int
        VALUE_FIELD_NUMBER: builtins.int
        key: typing.Text
        value: builtins.bytes
        def __init__(self,
            *,
            key: typing.Text = ...,
            value: builtins.bytes = ...,
            ) -> None: ...
        def ClearField(self, field_name: typing_extensions.Literal["key",b"key","value",b"value"]) -> None: ...

    STAT_FIELD_NUMBER: builtins.int
    REQUEST_UUID_FIELD_NUMBER: builtins.int
    R_LAST_EPOCH_ID_FIELD_NUMBER: builtins.int
    W_LAST_FIELD_NUMBER: builtins.int
    stat: global___Response.Status.ValueType
    request_uuid: typing.Text
    r_last_epoch_id: builtins.int
    @property
    def w_last(self) -> google.protobuf.internal.containers.ScalarMap[typing.Text, builtins.bytes]: ...
    def __init__(self,
        *,
        stat: global___Response.Status.ValueType = ...,
        request_uuid: typing.Text = ...,
        r_last_epoch_id: typing.Optional[builtins.int] = ...,
        w_last: typing.Optional[typing.Mapping[typing.Text, builtins.bytes]] = ...,
        ) -> None: ...
    def HasField(self, field_name: typing_extensions.Literal["_r_last_epoch_id",b"_r_last_epoch_id","r_last_epoch_id",b"r_last_epoch_id"]) -> builtins.bool: ...
    def ClearField(self, field_name: typing_extensions.Literal["_r_last_epoch_id",b"_r_last_epoch_id","r_last_epoch_id",b"r_last_epoch_id","request_uuid",b"request_uuid","stat",b"stat","w_last",b"w_last"]) -> None: ...
    def WhichOneof(self, oneof_group: typing_extensions.Literal["_r_last_epoch_id",b"_r_last_epoch_id"]) -> typing.Optional[typing_extensions.Literal["r_last_epoch_id"]]: ...
global___Response = Response
