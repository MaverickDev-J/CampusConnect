"""Debug: Inspect metadata of specific files in ChromaDB."""
import sys, os
from dotenv import load_dotenv

# Load env vars first
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.chroma import get_chroma_collection

def check_metadata():
    collection = get_chroma_collection()
    if not collection:
        print("Error: Could not connect to ChromaDB collection!")
        return
    
    # Files we want to check
    files = ["unit 4 os.pptx.pdf", "Module 02.pdf"]
    
    print(f"Checking metadata for: {files}")
    
    # Query mainly by source to get metadata
    # We can't query by filename directly easily without getting all, 
    # so let's just peek at some chunks.
    
    results = collection.get(
        where={"source": {"$in": files}},
        include=["metadatas"]
    )
    
    seen_files = {}
    
    for meta in results["metadatas"]:
        fname = meta.get("source")
        if fname in seen_files:
            continue
            
        seen_files[fname] = meta
        print(f"\nExample Metadata for {fname}:")
        print(f"  Subject: {meta.get('subject')}")
        print(f"  Year:    {meta.get('year')}")
        print(f"  Branch:  {meta.get('branch')}")
        
    if not seen_files:
        print("\nNo chunks found for these files!")

if __name__ == "__main__":
    check_metadata()
