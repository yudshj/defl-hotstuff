import base64

from client import MetaInfo, ClientRequest, client_request_to_bytes

if __name__ == '__main__':
    b64_str: str = 'AAAAd3sibWV0aG9kIjowLCJsaXN0ZW5faG9zdCI6IjEyNy4wLjAuMSIsImxpc3Rlbl9wb3J0Ijo4MDgwLCJ1dWlkIjoidXVpZ \
                    CIsImNsaWVudF9uYW1lIjoiY2xpZW50X25hbWUiLCJ0YXJnZXRfZXBvY2hfaWQiOjF9AQIDBA=='
    meta: MetaInfo = {"method": 0, "listen_host": "127.0.0.1", "listen_port": 8080, "uuid": "uuid",
                      "client_name": "client_name", "target_epoch_id": 1}
    client_request = ClientRequest(meta=meta, weights=b'\001\002\003\004')
    b64_bytes = base64.b64decode(b64_str)
    b64_client_request = client_request_to_bytes(client_request)
    print(base64.b64encode(b64_client_request))
    assert b64_bytes == b64_client_request
