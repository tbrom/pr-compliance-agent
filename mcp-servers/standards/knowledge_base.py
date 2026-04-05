import os
import chromadb
from chromadb.utils import embedding_functions
import re

class KnowledgeBase:
    def __init__(self, db_path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.collection = self.client.get_or_create_collection(
            name="compliance_rules",
            embedding_function=self.embedding_function
        )

    def load_rules_from_md(self, file_path):
        if not os.path.exists(file_path):
            return
        
        with open(file_path, "r") as f:
            content = f.read()
        
        # Simple parser for the markdown sections (## Rules)
        sections = re.split(r'\n##\s+', content)[1:]
        
        documents = []
        metadatas = []
        ids = []
        
        for i, section in enumerate(sections):
            lines = section.strip().split('\n')
            title = lines[0]
            body = "\n".join(lines[1:])
            
            documents.append(f"{title}\n{body}")
            metadatas.append({"title": title})
            ids.append(f"rule_{i}")
            
        if documents:
            self.collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

    def search_rules(self, query, n_results=2):
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results["documents"][0]

    def get_standard(self, title):
        results = self.collection.get(
            where={"title": {"$contains": title}}
        )
        if results["documents"]:
            return results["documents"][0]
        return f"Standard with title matching '{title}' not found."

if __name__ == "__main__":
    # Test initialization
    kb = KnowledgeBase()
    kb.load_rules_from_md("standards.md")
    print("✅ Rules loaded into ChromaDB")
    
    # Test search
    test_query = "A Pull Request with an AWS access key and hardcoded credentials."
    results = kb.search_rules(test_query)
    print(f"🔍 Top results for '{test_query}':")
    for res in results:
        print(f"--- \n{res}")
