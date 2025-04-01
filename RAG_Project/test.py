# from rag_system import DocumentProcessor, VectorDBManager, ChatSystem
# import os
#
# # 环境变量配置（推荐方式）
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"
#
#
# def init_system():
#     """系统初始化"""
#     try:
#         # 首次运行需要创建数据库
#         # docs = DocumentProcessor.load_pdf("llm.pdf")
#         docs = DocumentProcessor.load_text("./eat.txt")
#         VectorDBManager.get_db(docs)
#
#     except ValueError as e:
#         print(f"⚠️ 初始化警告: {str(e)}")
#     except Exception as e:
#         print(f"❌ 初始化失败: {str(e)}")
#         return False
#
#     return True
#
#
# if __name__ == "__main__":
#     if init_system():
#         chat = ChatSystem()
#
#         # 交互式查询
#         while True:
#             query = input("\n请输入问题（输入q退出）: ")
#             if query.lower() == 'q':
#                 break
#
#             # 流式输出
#             print("\n🤖 回答：")
#             chat.query(query, stream=True)
#
#             # 或获取完整回答
#             # response = chat.query(query)
#             # print(f"\n回答：{response}")
