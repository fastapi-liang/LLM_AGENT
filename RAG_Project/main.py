import os
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.runnables import (
    RunnablePassthrough,
    RunnableParallel,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
import traceback
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
import warnings

warnings.filterwarnings("ignore")
llm = ChatOpenAI(
    temperature=0.95,
    model="glm-4-plus",
    openai_api_key="xxxxxxxxxxxxx",
    openai_api_base="https://open.bigmodel.cn/api/paas/v4/",
)


def load_and_process_pdf(pdf_path: str):
    """
    加载并处理PDF文件
    :param pdf_path:
    :return:
    """
    try:
        # 1. 加载PDF文档
        print(f"正在加载PDF文件: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()

        # 2. 初始化文本分割器
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " "],  # 分割符优先级 [[6]][[8]]
            is_separator_regex=False,
        )

        # 3. 分割文档
        print("正在分割文本...")
        chunks = text_splitter.split_documents(documents)

        # 4. 显示处理结果
        print(f"\n共加载 {len(documents)} 页")
        print(f"分割为 {len(chunks)} 个文本块\n")

        # 显示前3个块的示例
        for i, chunk in enumerate(chunks[:3]):
            print(f"块 {i + 1}:")
            print("-" * 50)
            print(chunk.page_content[:300] + "...")  # 显示前300个字符
            print(f"\n元数据: {chunk.metadata}")
            print("=" * 50 + "\n")

        return chunks

    except FileNotFoundError:
        print(f"错误：文件 {pdf_path} 不存在")
    except Exception as e:
        print(f"处理PDF时发生错误: {str(e)}")
        print(traceback.format_exc())


def load_and_split_pdf(pdf_path):
    # 加载PDF文件
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()

    # 初始化中文文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,  # 每个分块500字符
        chunk_overlap=50,  # 分块间重叠50字符
        separators=["\n\n", "\n", "。", "，", " ", "", "\u200c"],  # 中文分割符
    )

    return text_splitter.split_documents(pages)


def init_embedding():
    """
    初始化嵌入模型
    :return:
    """
    from langchain_community.embeddings import ModelScopeEmbeddings
    from modelscope.utils.hub import snapshot_download

    # 下载中文基础嵌入模型 根据电脑的大小来进行 base或者large
    model_id = "iic/nlp_corom_sentence-embedding_chinese-base"
    # model_id = "iic/nlp_gte_sentence-embedding_chinese-large"
    model_dir = snapshot_download(
        model_id,
        cache_dir="./hugface-model_base",  # 模型下载路径
    )  # 模型下载路径

    # 初始化嵌入模型（自动使用CPU/GPU）
    embedding = ModelScopeEmbeddings(
        model_id=model_dir,
    )
    return embedding


def create_vector_store(docs, embeddings):
    """
    创建向量存储
    :param docs:
    :param embeddings:
    :return:
    """
    return Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory="./doc_db_base",  # 持久化存储路径
    )


# 加载text文本进行处理
def load_and_split_text():
    loader = TextLoader("./eat.txt", encoding="utf-8")  # 替换为实际文件路径
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=50, separators=["\n\n", "\n", "。", "，", " ", ""]
    )
    split_docs = text_splitter.split_documents(documents)

    return split_docs


def load_vector_store(embeddings):
    # 检查数据库是否存在
    if os.path.exists("./doc_db_base"):
        print("检测到已有向量数据库，正在加载...")
        return Chroma(persist_directory="./doc_db_base", embedding_function=embeddings)
    else:
        print("没有向量数据库，请及时加载数据库...")
        return None


# 5. 创建提示模板
def create_prompt():
    template = """请使用使用以下上下文来回答问题：
    {context}

    问题：{question}"""
    prompt = ChatPromptTemplate.from_template(template)
    return prompt


def create_retriever(vectorstore):
    retriever = vectorstore.as_retriever()
    return retriever


def create_rag_chain(retriever, prompt, model):
    rag_chain = (
        RunnableParallel(
            {"context": retriever, "question": RunnablePassthrough()})
        | prompt
        | model
        | StrOutputParser()
    )
    return rag_chain


def chatbot(query: str):
    embeddings = init_embedding()
    db = load_vector_store(embeddings)
    retriever = create_retriever(db)
    prompt = create_prompt()
    chain = create_rag_chain(retriever, prompt, llm)
    print(f"正在搜索与「{query}」相关的内容...")
    return chain.invoke(query)


def stream_out(query):
    embeddings = init_embedding()
    db = load_vector_store(embeddings)
    retriever = create_retriever(db)
    prompt = create_prompt()
    print(f"正在搜索与「{query}」相关的内容...")
    chain = create_rag_chain(retriever, prompt, llm)
    for chunk in chain.stream(query):
        print(chunk, end="", flush=True)


def main():
    """
    加载文本 切分文本 存储到数据库
    :return:
    """
    documents = load_and_split_text()
    embeddings = init_embedding()
    vector_db = create_vector_store(documents, embeddings)
    print(vector_db)


if __name__ == "__main__":
    # main() # 第一次执行需要执行main 下面的关掉
    query = "姨妈期间吃苹果的好处"
    resp = chatbot(query)
    print(resp)
