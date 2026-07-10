import json


def remove_vector_store(path, doc_id):
    with open(path, 'r') as file:
        data = json.load(file)

    embedding_dict = data['embedding_dict']
    text_id_to_ref_doc_id = data['text_id_to_ref_doc_id']

    # 删除embedding_dict中的内容
    if doc_id in embedding_dict:
        del embedding_dict[doc_id]

    # 删除text_id_to_ref_doc_id字典中的对应项
    if doc_id in text_id_to_ref_doc_id:
        del text_id_to_ref_doc_id[doc_id]

    with open(path, 'w') as file:
        json.dump(data, file, indent=4)


def remove_index_store(path, doc_id):
    with open(path, 'r') as file:
        data = json.load(file)

    if "index_store/data" in data:
        index_data = data["index_store/data"]
        for key, value in index_data.items():
            if "__data__" in value:
                data_str = value["__data__"]
                data_dict = json.loads(data_str)
                if "nodes_dict" in data_dict and doc_id in data_dict["nodes_dict"]:
                    del data_dict["nodes_dict"][doc_id]
                    value["__data__"] = json.dumps(data_dict)
                    break

    with open(path, 'w') as file:
        json.dump(data, file, indent=4)


def remove_docstore(path, doc_id):
    # 读取JSON文件
    with open(path, 'r') as file:
        data = json.load(file)

    # 检查是否存在指定的doc_id
    if doc_id in data['docstore/data']:
        # 删除指定的doc_id信息
        del data['docstore/data'][doc_id]

        # 删除相关的ref_doc_info和metadata
        if doc_id in data['docstore/ref_doc_info']:
            del data['docstore/ref_doc_info'][doc_id]

        if doc_id in data['docstore/metadata']:
            del data['docstore/metadata'][doc_id]

    # 写回JSON文件
    with open(path, 'w') as file:
        json.dump(data, file, indent=4)
