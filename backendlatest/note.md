**流式响应**

```python
query_engine = index.as_query_engine(
    streaming=True,
    similarity_top_k=1
)
```

**删除文档**

```python
index.delete_ref_doc(doc_id, delete_from_docstore=True)
```



**Q&A文档切分 CharacterTextSplitter**
首先，我们把“\n\n”这样两个连续的换行符作为一段段文本的分隔符，因为我们的 FAQ 数据里，每一个问答对都有一个空行隔开，正好是连续两个换行。
然后，我们把 chunk_size 设置得比较小，只有 100。这是因为我们所使用的开源模型是个小模型，这样我们才能在单机加载起来。
它能够支持的输入长度有限，只有 128 个 Token，超出的部分会进行截断处理。如果我们不设置 chunk_size，llama-index 会自动合并多个 chunk 变成一个段落。
其次，我们还增加了一个小小的参数，叫做 chunk_overlap。这个参数代表我们自动合并小的文本片段的时候，可以接受多大程度的重叠。它的默认值是 200，
超过了单段文档的 chunk_size，所以我们这里要把它设小一点，不然程序会报错。

```python

pip install spacy
python -m spacy download zh_core_web_sm
```
```python
text_splitter = CharacterTextSplitter(separator="\n\n", chunk_size=100, chunk_overlap=20)
parser = SimpleNodeParser(text_splitter=text_splitter)
documents = SimpleDirectoryReader('./data/faq/').load_data()
nodes = parser.get_nodes_from_documents(documents)
```

文档样例
```txt
Q: 如何注册新帐户？
A: 点击网站右上角的“注册”按钮，然后按照提示填写相关信息并设置密码。完成后，您将收到一封验证电子邮件。点击邮件中的链接以激活您的帐户。

Q: 忘记密码怎么办？
A: 点击登录页面的“忘记密码”链接，输入您的电子邮件地址。我们将向您发送一封包含重置密码链接的邮件。请点击链接并按照提示操作。
```

**文档名作为id**
```python
documents = SimpleDirectoryReader('./data',filename_as_id=True).load_data()
```

**怎么使用自定义prompt**

在LlamaIndex中，您可以通过创建格式字符串来定义自定义提示。以下是一个示例：
```python
from llama_index import Prompt

template = (
    "We have provided context information below. \n"
    "---------------------\n"
    "{context_str}"
    "\n---------------------\n"
    "Given this information, please answer the question: {query_str}\n"
)
qa_template = Prompt(template)
```

在这个例子中，{context_str}和{query_str}是模板字符串中需要替换的参数。这个模板可以直接用于构造自定义提示。

然后，您可以在构建索引或查询引擎时将自定义提示传入。例如，如果您正在使用TreeIndex并希望在构建索引时使用自定义提示，可以这样做：
```python
index = TreeIndex(nodes, summary_template=<custom_prompt>)
```

或者，如果您正在从文档构建索引，可以这样做：
```python
index = TreeIndex.from_documents(docs, summary_template=<custom_prompt>)
```
在查询时，您也可以将自定义提示传入查询引擎：

```python
query_engine = index.as_query_engine(text_qa_template=QA_TEMPLATE)
```

```python
query_engine = index.as_query_engine(
    text_qa_template=custom_prompt,
    refine_template=custom_prompt
)
custom_prompt = Prompt(template)
```

这里的QA_TEMPLATE就是您之前定义的自定义提示。


**设置和获取index summary**
```python
# 设置
index.summary = "summary"
# 获取
index.summary
```

**设置和获取index index_id**
```python
# 设置
index.set_index_id(index_name)
# 获取
index.index_id
```

**将索引聚合成图 -- 旧版**
```python
def compose_indices_to_graph():
    """
    将index合成为graph
    :return:
    """
    for index_dir_name in get_subfolders_list(index_save_directory):
        # 获取索引目录的完整路径和summary文件的完整路径
        index_dir_path = os.path.join(index_save_directory, index_dir_name)
        summary_file_path = os.path.join(index_dir_path, "summary.txt")

        # 如果summary文件存在，则读取其中的摘要
        if os.path.isfile(summary_file_path):
            with open(summary_file_path, "r", encoding="utf-8") as f:
                index_summary = f.read()
        # 否则，使用summary_index()函数生成摘要，并将其写入到summary文件中
        else:
            storage_context = StorageContext.from_defaults(persist_dir=index_dir_path)
            index_ = load_index_from_storage(storage_context)
            index_summary = summary_index(index_)
            with open(summary_file_path, "w", encoding="utf-8") as f:
                f.write(index_summary)

        indexes.append(index_)
        summaries.append(index_summary)

    graph = ComposableGraph.from_indices(
        ListIndex,
        indexes_,
        index_summaries=summaries
        # 不知道具体作用，以及使用的哪一个
        storage_contexts=storage_contexts
    )
    return graph
```

**更新doc --未完成**

通过找到node所在的doc
新建doc下的所有node，将要修改的node content修改
然后 删除所有node,插入新的所有node
- 能保持node_id不变，但doc_id不能设置会为None
```python
def updateById(id, text):
    global index
    node = index.docstore.get_node(node_id=id)
    doc_id = node.ref_doc_id
    docs = get_doc_by_id(doc_id)
    无法设置doc_id
    nodes = [Node(id_=node['node_id'], text=text if node['node_id'] == id else node['text'],doc_id=doc_id) for node in docs]
    deleteDocById(doc_id)
    index.insert_nodes(nodes)
```

**spacy分词库**
```python
pip install spacy
python -m spacy download zh_core_web_sm
```

**旧uploadFile**
```python
@app.post("/index/{index_name}/uploadFile")
async def upload_file(index_name, file: UploadFile = File(...)):
    index = get_index_by_name(index_name)
    filepath = None
    try:
        filename = f"{uuid4()}_{file.filename}"  # Generate a safe filename
        filepath = os.path.join(LOAD_PATH, filename)
        savepath = os.path.join(SAVE_PATH, filename)
        file_bytes = await file.read()
        with open(filepath, 'wb') as f:
            f.write(file_bytes)
        with open(savepath, 'wb') as f:
            f.write(file_bytes)
        insert_into_index(index,filepath)
    except Exception as e:
        logging.error(f"Error while handling file: {str(e)}")  # Log the error
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
        return "Error: {}".format(str(e)), 500
    finally:
        # Always cleanup the temp file
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
    return "File inserted!", 200
```

将query转化为chat
```python
from llama_index.prompts  import Prompt

custom_prompt = Prompt("""\
Given a conversation (between Human and Assistant) and a follow up message from Human, \
rewrite the message to be a standalone question that captures all relevant context \
from the conversation.

<Chat History> 
{chat_history}

<Follow Up Message>
{question}

<Standalone question>
""")

# list of (human_message, ai_message) tuples
custom_chat_history = [
    (
        'Hello assistant, we are having a insightful discussion about Paul Graham today.', 
        'Okay, sounds good.'
    )
]

query_engine = index.as_query_engine()
chat_engine = CondenseQuestionChatEngine.from_defaults(
    query_engine=query_engine, 
    condense_question_prompt=custom_prompt,
    chat_history=custom_chat_history,
    verbose=True
)
```

# 留存
```python
def createIndexZh(index_name):
    global index
    llm_predictor = LLMPredictor(
        llm=ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo-16k", max_tokens=1024, openai_api_key=openai.api_key))
    text_splitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=512)
    parser = SimpleNodeParser(text_splitter=text_splitter)
    documents = SimpleDirectoryReader('./data', filename_as_id=True).load_data()
    nodes = parser.get_nodes_from_documents(documents)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index = VectorStoreIndex(nodes, service_context=service_context)
    index.storage_context.persist(index_save_directory + index_name)
```

## 更新索引
```python
def updateById(index_, id_, text):
    """
    通过node_id，更新node中的内容 会删除doc中所有node再重新添加，node_id会变化
    :param index_: 索引
    :param id_: node_id
    :param text: 更改后的内容
    :return:
    """
    node = index_.docstore.get_node(node_id=id_)
    doc_id = node.ref_doc_id
    docs = get_doc_by_id(index_, doc_id)
    documents = [Document(id_=doc_id, text=text if node['node_id'] == id_ else node['text']) for node in docs]
    deleteDocById(index_, doc_id)
    for doc in documents:
        index_.insert(doc)

def get_doc_by_id(index, doc_id):
    """
    通过node_id获取所在的Doc
    :param doc_id: 文档id
    :param index: 索引
    :return: 文档列表
    """
    return [doc for doc in get_all_docs(index) if doc['doc_id'] == doc_id]
```
```python
def updateNodeById(index: BaseIndex, id, text):
    node = index.docstore.get_node(node_id=id)
    node.set_content(text)
    doc = Document(id=node.ref_doc_id, text=node.get_content())
    index.update_ref_doc(doc, update_kwargs={"delete_kwargs": {'delete_from_docstore': True}})
    index.delete_ref_doc(id, delete_from_docstore=True)
```