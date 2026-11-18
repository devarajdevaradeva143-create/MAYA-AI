"""Tests for Maya AI knowledge tools."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.knowledge import search_files, read_pdf, read_text_file, index_documents, knowledge_search


def test_search_files():
    """Search for files should return a list."""
    # Search in the custom folder itself
    matches = search_files("test", r"C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS\custom")
    assert isinstance(matches, list), f"Expected list, got {type(matches)}"


def test_read_text_file():
    """Read a text file should return content."""
    # Read the AGENTS.md from project root
    agents_md = r"C:\Users\devar\Desktop\MAYA AI PROJECT\AGENTS.md"
    content = read_text_file(agents_md)
    assert isinstance(content, str), f"Expected string, got {type(content)}"
    assert len(content) > 0, "Expected non-empty content"


def test_read_pdf_fallback():
    """PDF reading should return a string (fallback if no pypdf)."""
    # This tests the fallback path; no actual PDF needed for type check
    result = read_pdf("nonexistent.pdf")
    assert isinstance(result, str), f"Expected string, got {type(result)}"


def test_index_documents():
    """Index documents should return a dict."""
    # Index the tests folder
    index = index_documents(r"C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS\custom\tests")
    assert isinstance(index, dict), f"Expected dict, got {type(index)}"


def test_knowledge_search():
    """Knowledge search should return results list."""
    # Create a simple index
    index = index_documents(r"C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS\custom\tests")
    # Search for "test"
    results = knowledge_search("test", index)
    assert isinstance(results, list), f"Expected list, got {type(results)}"


if __name__ == "__main__":
    test_search_files()
    print("✓ test_search_files passed")
    test_read_text_file()
    print("✓ test_read_text_file passed")
    test_read_pdf_fallback()
    print("✓ test_read_pdf_fallback passed")
    test_index_documents()
    print("✓ test_index_documents passed")
    test_knowledge_search()
    print("✓ test_knowledge_search passed")
    print("\nAll knowledge tests passed!")