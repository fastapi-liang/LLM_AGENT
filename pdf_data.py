from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import traceback
 #pip install pypdf
loader = PyPDFLoader("./llm.pdf")
documents = loader.load()
# print(documents)
# print(len(documents))
#
# for document in documents:
#     print(document.page_content)


def load_and_process_pdf(pdf_path: str):
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


if __name__ == "__main__":
    # 使用示例
    pdf_documents = load_and_process_pdf("./llm.pdf")

    # 后续可以添加：
    # - 向量存储操作
    # - 问答系统集成
    # - 摘要生成等处理