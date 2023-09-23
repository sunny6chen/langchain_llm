# langchian_llm

基于langchain适配国内提供的大模型API，自定义相应的子类集成到langchian中。方便后续在langchain中使用

目前实现的类都是继承LLM 和 BaseChatModel

目前在langchain中已经很好的使用了，细节问题不做阐述，目前已经测试通过（打个小样而已，有问题随时指出。）。

llm目录内为：已支持的LLM的模型

## 继承架构图
<img width="487" alt="image" src="https://github.com/sunny6chen/langchain_llm/assets/29888472/fb9b6f46-7701-41cc-bb64-e50a05635675">


## SparkLLM
> 科大讯飞Spark模型 - 已支持
> <img width="462" alt="image" src="https://github.com/sunny6chen/langchain_llm/assets/29888472/0298cf94-c4ee-467b-a49b-fb9090d1afec">
Spark模型的请求限制以及细节优化，可基于需求实现

## BaiChuan2
> 开发中

## BaiduYunFan
> 开发中





