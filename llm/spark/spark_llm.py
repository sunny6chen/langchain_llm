
import _thread as thread
import base64
import datetime
import hashlib
import hmac
import json
import logging
from urllib.parse import urlparse
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time
from typing import Optional, List, Mapping, Any, AsyncIterable

from langchain.llms.base import LLM
from langchain.cache import InMemoryCache
import time

from openai.error import TryAgain
from openai.openai_response import OpenAIResponse

from openai import  error, util

from llm.spark import websocket_api

logging.basicConfig(level=logging.INFO)

# 启动llm的缓存, 会缓存历史的聊天信息
# langchain.llm_cache = InMemoryCache()

logger = logging.getLogger(__name__)

result_list = []


def _construct_query(chats, temperature, app_id, max_tokens):
    data = {
        "header": {
            "app_id": app_id,
            "uid": "1234"
        },
        "parameter": {
            "chat": {
                "domain": "generalv2",
                "random_threshold": temperature,
                "max_tokens": max_tokens,
                "auditing": "default"
            }
        },
        "payload": {
            "message": {
                "text": chats
            }
        }
    }
    return data

def _run(ws, *args):
    """
    构建给Web socket发送的事件
    :param ws:
    :param args:
    :return:
    """
    data = json.dumps(
        _construct_query(chats=ws.body, temperature=ws.temperature, max_tokens=ws.max_tokens, app_id=ws.app_id)
    )
    ws.send(data)


def on_error(ws, error_msg):
    """
    websocket的error 回调事件
    :param ws:
    :param error_msg:
    :return:
    """
    logger.error(f"Web socket occur error：{error_msg} \n")

def on_close(ws, close_status_code, close_msg):
    """
    websocket的close 回调事件
    :param ws:
    :param close_status_code:
    :param close_msg:
    :return:
    """
    logger.error(f"Web socket close msg：{close_msg}, close_status_code: {close_status_code} \n", )


def on_open(ws):
    """
    websocket的open 回调事件
    :param ws:
    :return:
    """
    logger.error(f"Web socket opening, please wait ! \n", )
    thread.start_new_thread(_run, (ws,))

def parse_message(message, stream, model, app_id):
    """
    解析从web socket服务器接收到的数据，
    构建成Open ai数据格式一样， 方便langchain统一管理
    :param message:
    :param stream:
    :param model:
    :param app_id:
    :return:
    """
    data = json.loads(message)
    code = data["header"]["code"]
    sid = data["header"]['sid']
    status = data["header"]['status']
    choices = {'text':[]}
    usage = {'text':''}
    if code != 0:
        error_msg = data["header"]['message']
        choices['text'].append(
            {"content": error_msg, "role": "assistant", "index": 0}
        )
        print(f"请求错误: {code}, {data}")
    else:
        choices = data["payload"]["choices"]
        # 文本响应状态，取值为[0,1,2]; 0:首个文本结果；1:中间文本结果；2:最后一个文本结果
        if status == 2:
            usage = data["payload"]['usage']

    # Open ai 的是否支持流，返回的格式有稍微，差别此处构建
    if stream:
            build_resp = {
                'choices': [],
                'status': status,
                'app_id': app_id,
                'object': 'chat.completion.chunk',
                'model': model,
                'id': sid,
                'usage': usage
            }
            for txt in choices['text']:
                build_resp['choices'].append(
                    {'delta': txt,
                     'status': status,
                     'finish_reason': None,
                     'index': txt['index']
                     }
                )
            return build_resp
    else:
        resp_data = {
            'choices': [],
            'status': status,
            'app_id': app_id,
            'object': 'chat.completion',
            'model': model,
            'id': sid,
            'usage': usage
        }
        text = ''
        for txt in choices['text']:
            text += txt['content']
        cur = choices['text'][0]
        cur['content'] = text
        resp_data['choices'].append(
            {'message': cur,
             'status': status,
             'finish_reason': None,
             'index': cur['index']
             }
        )
        return  resp_data

def on_message(ws, message):
    """
    websocket的接收message 回调事件， 这些事件为同步的调用
    :param ws:
    :param message:
    :return:
    """
    data = json.loads(message)
    code = data["header"]["code"]
    sid = data["header"]['sid']
    status = data["header"]['status']
    setattr(ws, 'sid', sid)
    setattr(ws, 'status', status)
    if code != 0:
        setattr(ws, 'error', data["header"]['message'])
        logger.error(f"Encountered an exception while receiving data from a WebSocket. code: {code}, data: {data} \n")
        ws.close()
    else:
        choices = data["payload"]["choices"]
        status = choices["status"]
        result_list.append(choices)
        # 文本响应状态，取值为[0,1,2]; 0:首个文本结果；1:中间文本结果；2:最后一个文本结果
        if status == 2:
            usage = data["payload"]['usage']
            ws.close()
            setattr(ws, 'usage', usage)
            setattr(ws, "choices", result_list.copy())
            result_list.clear()


MAX_TIMEOUT = 20
class SparkLLM(LLM):
    """
    科大讯飞的Spark模型在langchain的自定义子类，继承自LLM。
    因为使用websocket，拿了一些官网例子图方便没有额外修改太多，
    细节问题后面修改。
    目前该类的websocket 使用了两个类分别来自：
        - websocket-client
        - websockets
    主要用于同步和异步的处理
    """
    spark_app_id: str = None
    spark_api_key: str = None
    spark_api_secret: str = None
    spark_api_base: str = None
    temperature: float = 0.8
    kwargs: Any = None
    max_tokens: int = 8192
    status:int = -1
    timeout:int = MAX_TIMEOUT
    model:str= None

    @property
    def _llm_type(self) -> str:
        # 模型简介
        return "Spark"

    def _get_url(self):
        # 获取请求路径
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + urlparse(self.spark_api_base).netloc + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + urlparse(self.spark_api_base).path  + " HTTP/1.1"

        signature_sha = hmac.new(self.spark_api_secret.encode("utf-8"), signature_origin.encode("utf-8"),
                                 digestmod=hashlib.sha256).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding="utf-8")

        authorization_origin = f"""api_key="{self.spark_api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}" """

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(encoding="utf-8")

        v = {
            "authorization": authorization,
            "date": date,
            "host": urlparse(self.spark_api_base).netloc
        }
        url = self.spark_api_base + "?" + urlencode(v)
        return url

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        pass

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """
        Get the identifying parameters.
        """
        _param_dict = {
            "url": self.spark_api_base
        }
        return _param_dict

    @classmethod
    def create(cls, **kwargs):
        """
        Creates a new chat completion for the provided messages and parameters.

        See https://platform.openai.com/docs/api-reference/chat/create
        for a list of valid parameters.
        """
        start = time.time()
        timeout = kwargs.get("timeout", None)

        while True:
            try:
                return SparkLLM.__create(**kwargs)
            except TryAgain as e:
                if timeout is not None and time.time() > start + timeout:
                    raise

                util.log_info("Waiting for model to warm up", error=e)

    @classmethod
    def __prepare_create_request(
            cls,
            spark_app_id=None,
            spark_api_key=None,
            spark_api_secret=None,
            spark_api_base=None,
            spark_api_type=None,
            spark_api_version=None,
            **params,
    ):
        model = params.get("model", None)
        timeout = params.pop("timeout", None)
        stream = params.get("stream", False)
        request_timeout = params.pop("request_timeout", None)
        typed_api_type = params.pop("spark_api_type", None)

        if model is None:
            raise error.InvalidRequestError(
                "Must provide an 'model' parameter to create a %s"
                % cls,
                "model",
            )

        if timeout is None:
            # No special timeout handling
            pass
        elif timeout > 0:
            # API only supports timeouts up to MAX_TIMEOUT
            params["timeout"] = min(timeout, MAX_TIMEOUT)
            timeout = (timeout - params["timeout"]) or None
        elif timeout == 0:
            params["timeout"] = MAX_TIMEOUT

        params['spark_app_id'] = spark_app_id
        params['spark_api_key'] = spark_api_key
        params['spark_api_secret'] = spark_api_secret
        params['spark_api_base'] = spark_api_base
        sf = cls(**params)
        url = sf._get_url()
        params['client'] = sf

        requestor = websocket_api.WebsocketApi(
                                url,
                                spark_api_key,
                                spark_api_secret,
                                message_event=on_message,
                                error_event=on_error,
                                close_event=on_close,
                                open_event=on_open
                    )
        return (
            spark_app_id,
            model,
            timeout,
            stream,
            request_timeout,
            typed_api_type,
            requestor,
            url,
            params
        )

    @classmethod
    async def __acreate(
            cls,
            spark_app_id=None,
            spark_api_key=None,
            spark_api_secret=None,
            spark_api_base=None,
            spark_api_type=None,
            spark_api_version=None,
            **params,
    ):
        (
            app_id,
            model,
            timeout,
            stream,
            request_timeout,
            typed_api_type,
            requestor,
            url,
            params,
        ) = cls.__prepare_create_request(
            spark_app_id,
            spark_api_key,
            spark_api_secret,
            spark_api_base,
            spark_api_type,
            spark_api_version,
            **params
        )
        client = params['client']
        # Will send messages by async websocket
        body = json.dumps(
                _construct_query(params['messages'],
                         app_id = client.spark_app_id,
                         temperature = client.temperature,
                         max_tokens = client.max_tokens
                ),
                ensure_ascii=False
           )
        responses = requestor.arequest(body)
        async def generator(reps:AsyncIterable[str]) -> AsyncIterable[OpenAIResponse]:
            async for msg in reps:
                resp = parse_message(msg, stream, model, app_id)
                params['client'].status = resp.get('status', -1)
                yield OpenAIResponse(resp, {})

        response =  generator(responses)

        # 创建异步对象
        if stream:
            assert not isinstance(response, OpenAIResponse)
            return (
                util.convert_to_openai_object(
                    line,
                    spark_api_key,
                    spark_api_version,
                    engine=model,
                )
                async for line in response
            )
        else:
            obj = util.convert_to_openai_object(
                response,
                spark_api_key,
                spark_api_version,
                engine=model
            )
            if timeout is not None:
                await params['client'].await_(msg=params['messages'],timeout=timeout or None)
            return obj

    @classmethod
    def __create(
            cls,
            spark_app_id=None,
            spark_api_key=None,
            spark_api_secret=None,
            spark_api_base=None,
            spark_api_type=None,
            spark_api_version=None,
            **params,
    ):
        (
            app_id,
            model,
            timeout,
            stream,
            request_timeout,
            typed_api_type,
            requestor,
            url,
            params,
        ) = cls.__prepare_create_request(
            spark_app_id,
            spark_api_key,
            spark_api_secret,
            spark_api_base,
            spark_api_type,
            spark_api_version,
            **params
        )
        ws = requestor.get_websocket()
        spark = params['client']
        setattr(ws, "temperature", spark.temperature)
        setattr(ws, "max_tokens", spark.max_tokens)
        setattr(ws, "app_id", spark.spark_app_id)

        requestor.request(params['messages'])

        params['client'].status = ws.status if hasattr(ws, "status") else -1

        msg = ws.error if hasattr(ws, "error") else None

        choices = ws.choices if hasattr(ws, "choices") else [
            {
                "status": params['client'].status,
                "seq": 0,
                "text": [
                    {
                        "content": msg,
                        "role": "assistant",
                        "index": 0
                    }
                ]
            }]
        sid = ws.sid if hasattr(ws, "sid") else ''
        usage = ws.usage if hasattr(ws, "usage") else {}

        if stream:
            response = []
            for con in choices:
                build_resp = {
                    'choices': [],
                    'app_id': app_id,
                    'object': 'chat.completion.chunk',
                    'model': model,
                    'id': sid,
                    'usage': usage
                }
                for txt in con['text']:
                    build_resp['choices'].append(
                        {'delta': txt,
                         'finish_reason': None,
                         'index': txt['index']
                         }
                    )
                response.append(OpenAIResponse(build_resp, {}))
            assert not isinstance(response, OpenAIResponse)

            return (
                    util.convert_to_openai_object(
                        line,
                        spark_api_key,
                        spark_api_version,
                        engine=model)
                    for line in response
            )
        else:
            resp_data = {
                'choices': [],
                'app_id': app_id,
                'object': 'chat.completion',
                'model': model,
                'id': sid,
                'usage': usage
            }
            text = ''
            for con in choices:
                for txt in con['text']:
                    text += txt['content']
            cur = choices[0]['text'][0]
            cur['content'] = text
            resp_data['choices'].append(
                {'message': cur,
                 'finish_reason': None,
                 'index': cur['index']
                 }
            )

            response = OpenAIResponse(resp_data, {})

            obj = util.convert_to_openai_object(
                response,
                spark_api_key,
                spark_api_version,
                engine=model
            )
            if timeout is not None:
                params['client'].wait(msg=params['messages'], timeout=timeout or None)

            return obj
    def wait(self, msg, timeout=None):
        start = time.time()
        while self.status != "2":
            self.timeout = (
                min(timeout + start - time.time(), MAX_TIMEOUT)
                if timeout is not None
                else MAX_TIMEOUT
            )
            if self.timeout < 0:
                del self.timeout
                break
        return self

    async def await_(self, msg, timeout=None):
        """Async version of `EngineApiResource.wait`"""
        start = time.time()
        while self.status != 2:
            self.timeout = (
                min(timeout + start - time.time(), MAX_TIMEOUT)
                if timeout is not None
                else MAX_TIMEOUT
            )
            if self.timeout < 0:
                del self.timeout
                break
        return self

    @classmethod
    async def acreate(cls, **kwargs):
        """
        Creates a new chat completion for the provided messages and parameters.

        See https://platform.openai.com/docs/api-reference/chat/create
        for a list of valid parameters.
        """
        start = time.time()
        timeout = kwargs.get("timeout", None)

        while True:
            try:
                return await SparkLLM.__acreate(**kwargs)
            except TryAgain as e:
                if timeout is not None and time.time() > start + timeout:
                    raise

                util.log_info("Waiting for model to warm up", error=e)

