def test_package_importable():
    import doc_chunk

    assert doc_chunk.__version__ == "0.1.0"
