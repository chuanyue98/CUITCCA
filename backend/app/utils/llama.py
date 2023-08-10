from langchain.text_splitter import SpacyTextSplitter
from llama_index import SimpleDirectoryReader
from llama_index.node_parser import SimpleNodeParser


def get_nodes_from_file(file_path):
    """
    从文件中获取节点
    :param file_path: 文件路径
    :return:
    """
    # 加载文本分词器
    text_splitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=512)
    parser = SimpleNodeParser(text_splitter=text_splitter)
    documents = SimpleDirectoryReader(file_path, filename_as_id=True).load_data()
    return parser.get_nodes_from_documents(documents)

if __name__ == '__main__':
    nodes = get_nodes_from_file('../utils')
    for  node in nodes:
        print(node)