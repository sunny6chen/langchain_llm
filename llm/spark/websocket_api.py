import json
import _thread as thread
import logging
import ssl
from typing import Callable, Any, AsyncIterable

import websocket
import websockets
from websocket import WebSocketApp
from websockets.exceptions import ConnectionClosed, ConnectionClosedError



logger = logging.getLogger(__name__)
def on_error(ws, error):
    logger.error(f"error: {error}", )


def on_close(ws, close_status_code, close_msg):
    logger.info(f"closed[close_status_code:{close_status_code}, close_msg:{close_msg}]...")

def _run(ws, *args):
    ws.send(ws.body)


def on_open(ws):
    thread.start_new_thread(_run, (ws,))


def on_message(ws, message):
    setattr(ws, 'data', message)


class WebsocketApi:
    """
    0–999		保留段，未使用。
    1000	CLOSE_NORMAL	正常关闭; 无论为何目的而创建，该链接都已成功完成任务。
    1001	CLOSE_GOING_AWAY	终端离开，可能因为服务端错误，也可能因为浏览器正从打开连接的页面跳转离开。
    1002	CLOSE_PROTOCOL_ERROR	由于协议错误而中断连接。
    1003	CLOSE_UNSUPPORTED	由于接收到不允许的数据类型而断开连接 (如仅接收文本数据的终端接收到了二进制数据).
    1004		保留。 其意义可能会在未来定义。
    1005	CLOSE_NO_STATUS	保留。 表示没有收到预期的状态码。
    1006	CLOSE_ABNORMAL	保留。 用于期望收到状态码时连接非正常关闭 (也就是说，没有发送关闭帧).
    1007	Unsupported Data	由于收到了格式不符的数据而断开连接 (如文本消息中包含了非 UTF-8 数据).
    1008	Policy Violation	由于收到不符合约定的数据而断开连接。这是一个通用状态码，用于不适合使用 1003 和 1009 状态码的场景。
    1009	CLOSE_TOO_LARGE	由于收到过大的数据帧而断开连接。
    1010	Missing Extension	客户端期望服务器商定一个或多个拓展，但服务器没有处理，因此客户端断开连接。
    1011	Internal Error	客户端由于遇到没有预料的情况阻止其完成请求，因此服务端断开连接。
    1012	Service Restart	服务器由于重启而断开连接。[Ref]
    1013	Try Again Later	服务器由于临时原因断开连接，如服务器过载因此断开一部分客户端连接。[Ref]
    1014		由 WebSocket 标准保留以便未来使用。
    1015	TLS Handshake	保留。 表示连接由于无法完成 TLS 握手而关闭 (例如无法验证服务器证书).
    1016–1999		由 WebSocket 标准保留以便未来使用。
    2000–2999		由 WebSocket 拓展保留使用。
    3000–3999		?可以由库或框架使用.? 不应由应用使用。可以在 IANA 注册，先到先得。
    4000–4999		可以由应用使用。
    """
    enableTrace:bool = False
    ws:WebSocketApp = None
    ws_url = None
    def __init__(self,
                 ws_url: str,
                 api_key:str = None,
                 api_secret:str = None,
                 message_event:Callable = None,
                 error_event:Callable = None,
                 close_event:Callable = None,
                 open_event:Callable = None
                 ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.on_message = message_event or on_message
        self.on_error = error_event or on_error
        self.on_close = close_event or on_close
        self.on_open = open_event   or on_open
        self.ws_url = ws_url
        self.ws = websocket.WebSocketApp(self.ws_url, on_message=self.on_message, on_error=self.on_error,
                                    on_close=self.on_close, on_open=self.on_open)

    def get_websocket(self):
        return self.ws

    async def get_awebsocket(self):
        return websockets.connect(self.ws_url)
    def request(self, body:Any = None, enable_trace:bool=False, ssl_opt = None):
        if ssl_opt is None:
            ssl_opt = {"cert_reqs": ssl.CERT_NONE}
        self.enableTrace  = enable_trace

        websocket.enableTrace(self.enableTrace)

        self.ws.body = body
        self.ws.run_forever(sslopt=ssl_opt)
        return self.ws

    async def arequest(self, body: Any = None) -> AsyncIterable[str]:
        aws = await self.get_awebsocket()
        async with aws as wsocket:
            try:
                await self.__send(wsocket, body)

                async for message in wsocket:
                    if wsocket.closed:
                        return
                    logger.info(f"Received message: {message}")
                    yield message
            except ConnectionClosed as e:
                logger.error(f"连接关闭: {e}")

    async def __send(self, wsocket, message):
        try:
            # Ensure the connection is open before sending a message
            await wsocket.ensure_open()
            await wsocket.send(message)
            logger.info(f"Sent message: {message}")
        except ConnectionClosedError as e:
            logger.error(f"发送消息失败: {e.code} - {e.reason}")


