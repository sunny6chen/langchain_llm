import langchain

from llm.spark.spark_ai import SparkChat


class OpenAiChatLLM(object):
    oaModel: dict = {}
    defaultModel: str = 'gpt-3.5-turbo'

    def __init__(self):
        self.oaModel['spark-v2.1'] = self.getSparkAiModel
        langchain.debug = True
        langchain.verbose = True


    def getSparkAiModel(self, callbacks=None):
        model_name = 'spark-v2.1'
        if callbacks is None:
            callbacks = []

        initArgs = {
        "spark_app_id": "xxx",
        "spark_api_key": "xxx",
        "spark_api_secret": "xxx",
        "spark_api_base": "wss://spark-api.xf-yun.com/v2.1/chat",
        "temperature": 0.5
    }
        sparkModel = SparkChat(
            model = model_name,
            streaming = True,
            verbose = True,
            timeout = 25,
            callbacks = callbacks,
            **initArgs
        )

        return sparkModel

    def open_ai_model(self, model=None, callbacks: list = None):
        if model is None:
            model = 'spark-v2.1'
        if callbacks is None:
            callbacks = []

        print(f"Current use model: {model} \n")
        
        return self.oaModel.get(model, self.defaultModel)(callbacks)